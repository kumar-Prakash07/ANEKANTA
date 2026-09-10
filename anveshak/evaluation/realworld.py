"""Real-world benchmark against live hidden services.

The labelled benchmark measures precision and recall because ONIONLAB's
operator map is known. No such map exists for the live Tor network, so the
honest thing is to be explicit about which claims survive the loss of labels
and which do not.

What CAN be measured without ground truth
-----------------------------------------
  discovery yield      addresses returned per query, per engine, and how many
                       were removed by the blacklist and the safety gate
  reachability         what fraction of discovered services actually answer
  throughput           pages and bytes per minute over Tor, which is the real
                       constraint on operating this at scale
  extraction yield     fingerprints and clear-web identifiers recovered per
                       reachable service
  **infrastructure clusters**  services sharing a favicon hash, a TLS public
                       key, a DOM skeleton or a header ordering

That last one is the point of the exercise. It is a *verifiable fact*, not a
prediction: if two independently discovered onion services present the same
SHA-256 of the same favicon, they present the same favicon, and anyone can
check it. No labels are needed to state it, and it is exactly the pivot an
analyst wants -- two addresses, one operator's stack.

What CANNOT be measured, and is not claimed
-------------------------------------------
Precision and recall of *persona linkage*. Deciding whether two accounts share
an operator requires knowing the answer, and on the live network nobody does.
Any figure quoted for it would be invented. The labelled benchmark exists
precisely so that number has somewhere honest to come from.

A second limitation, reported rather than hidden: the persona extractor keys on
profile-page structure, and real services do not share ONIONLAB's. Account-level
extraction from an arbitrary marketplace needs a per-site adapter, and this run
reports how often it found nothing so the gap is visible rather than implied.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

# Neutral infrastructure terms. The queries are deliberately dull: the object of
# this benchmark is to measure crawl and correlation behaviour across many real
# services, and dull terms return many ordinary sites. Steering the query set
# toward illicit subject matter would not improve the measurement and would
# increase the chance of retrieving material the safety gate then has to throw
# away.
DEFAULT_QUERIES = [
    "hosting", "forum", "search engine", "email", "wiki",
    "bitcoin", "library", "chat", "directory", "market",
]

# Fingerprints worth clustering on, and how much a shared value means. A DOM
# skeleton match is a shared template, which is common for off-the-shelf
# software; a shared TLS public key means the same private key file.
CLUSTER_KEYS = [
    ("tls_spki", "TLS public key", "the same private key file is deployed on both"),
    ("favicon_sha256", "favicon (exact)", "byte-identical icon"),
    ("favicon_mmh3", "favicon (mmh3)", "same icon, Shodan hash convention"),
    ("dom_skeleton", "DOM skeleton", "same page template"),
    ("css_vocab", "CSS vocabulary", "same theme"),
    ("header_order", "header order", "same server and proxy chain"),
    ("error_page", "404 shape", "same error template"),
]


def _fingerprint_values(fp) -> dict:
    """Flatten a ServiceFingerprint to the values worth clustering on."""
    out = {
        "favicon_sha256": fp.favicon_sha256,
        "favicon_mmh3": fp.favicon_mmh3,
        "dom_skeleton": fp.dom_skeleton_hash,
        "css_vocab": fp.css_vocab_hash,
        "header_order": fp.header_order_hash,
        "error_page": fp.error_page_hash,
    }
    tls = fp.tls or {}
    if tls.get("present"):
        out["tls_spki"] = tls.get("spki_sha256", "")
    return {k: v for k, v in out.items() if v}


def infrastructure_clusters(fingerprints: dict) -> list:
    """Group services by shared fingerprints. Label-free and verifiable.

    A value held by only one service is not a cluster. A value held by *every*
    service is not one either -- an empty favicon or a default nginx header
    order says nothing -- so anything covering more than half the sample is
    reported as generic rather than as a finding.
    """
    total = len(fingerprints)
    index: dict = defaultdict(lambda: defaultdict(set))
    for onion, fp in fingerprints.items():
        for key, value in _fingerprint_values(fp).items():
            index[key][value].add(onion)

    clusters: list = []
    for key, label, meaning in CLUSTER_KEYS:
        for value, members in index.get(key, {}).items():
            if len(members) < 2:
                continue
            share = len(members) / max(1, total)
            clusters.append({
                "artefact": key,
                "label": label,
                "meaning": meaning,
                "value": value[:24],
                "services": sorted(members),
                "size": len(members),
                "share_of_sample": round(share, 3),
                # A value on most of the sample identifies the software, not
                # the operator, and is reported as such rather than as a link.
                "generic": share > 0.5,
            })
    clusters.sort(key=lambda c: (c["generic"], -c["size"]))
    return clusters


def run(crawler, discovery, queries: list | None = None,
        engines: list | None = None, per_query: int = 8,
        max_services: int = 12, max_pages_each: int = 6,
        progress=None) -> dict:
    """Discover, crawl and measure. Returns a report dict."""
    queries = queries or DEFAULT_QUERIES
    say = progress or (lambda m: None)
    started = time.time()

    say("loading Ahmia blacklist (mandatory; discovery aborts without it)")
    bl = discovery.prepare()
    say("blacklist: %d hashed addresses" % bl["blacklist_hashes"])

    say("searching %d quer%s across %s"
        % (len(queries), "y" if len(queries) == 1 else "ies",
           ", ".join(engines or ["default"])))
    t_disc = time.time()
    found = discovery.multi_search(queries, engines=engines, per_query=per_query)
    disc_seconds = time.time() - t_disc
    say("discovered %d unique addresses in %.0fs" % (len(found), disc_seconds))

    # Prefer addresses corroborated by more than one engine or more than one
    # query: they are likelier to be live, and a benchmark that spends its Tor
    # budget on dead addresses measures nothing.
    ranked = sorted(found.items(),
                    key=lambda kv: (-len(kv[1]["engines"]),
                                    -len(kv[1]["queries"]),
                                    kv[1]["hit"].rank))
    targets = [onion for onion, _ in ranked[:max_services]]

    say("crawling %d service(s), at most %d pages each"
        % (len(targets), max_pages_each))
    # Both budgets. The per-service cap is what stops one link-heavy site
    # starving the rest of the sweep; the lifetime cap bounds the whole run.
    crawler.max_pages_per_service = max_pages_each
    crawler.max_pages = max_pages_each * len(targets) + 16
    crawler.max_bytes = max(crawler.max_bytes, 4_000_000 * len(targets))

    per_service: list = []
    fingerprints: dict = {}
    t_crawl = time.time()
    reachable = 0
    total_pages = total_bytes = 0
    total_mentions = 0
    excluded_services: list = []

    for onion in targets:
        t0 = time.time()
        try:
            one = crawler.crawl_service(onion)
        except Exception as exc:
            per_service.append({"onion": onion, "reachable": False,
                                "error": type(exc).__name__})
            continue

        pages = one.pages_fetched
        nbytes = one.bytes_fetched
        total_pages += pages
        total_bytes += nbytes

        if one.excluded_services:
            excluded_services.extend(one.excluded_services)
            per_service.append({"onion": onion, "reachable": True,
                                "excluded_by_safety_gate": True,
                                "seconds": round(time.time() - t0, 1)})
            say("  %s... excluded by the safety gate" % onion[:20])
            continue

        ok = bool(one.fingerprint.dom_skeleton_hash)
        if ok:
            reachable += 1
            fingerprints[onion] = one.fingerprint

        from ..osint import context as osint_context
        osint_context.score_all(one.mentions)
        clearweb = [m for m in one.mentions
                    if m.kind in ("email", "domain", "telegram", "jabber",
                                  "session", "wickr", "paypal", "twitter",
                                  "github", "keybase", "reddit")]
        total_mentions += len(clearweb)

        per_service.append({
            "onion": onion,
            "reachable": ok,
            "title": found[onion]["hit"].title[:80],
            "engines": found[onion]["engines"],
            "queries": found[onion]["queries"],
            "pages": pages,
            "bytes": nbytes,
            "seconds": round(time.time() - t0, 1),
            "accounts_extracted": len(one.personas),
            "clear_web_mentions": len(clearweb),
            "high_priority_mentions": sum(1 for m in clearweb if m.priority >= 0.7),
            "tls": bool((one.fingerprint.tls or {}).get("present")),
            "favicon": bool(one.fingerprint.favicon_sha256),
        })
        say("  %s... %s, %d pages, %d mentions"
            % (onion[:20], "reachable" if ok else "no content",
               pages, len(clearweb)))

    crawl_seconds = time.time() - t_crawl
    clusters = infrastructure_clusters(fingerprints)
    real_clusters = [c for c in clusters if not c["generic"]]

    with_accounts = sum(1 for s in per_service if s.get("accounts_extracted"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "queries": queries,
        "engines": engines,
        "discovery": {
            "unique_addresses": len(found),
            "seconds": round(disc_seconds, 1),
            "engine_stats": dict(discovery.stats),
            "blacklist_hashes": bl["blacklist_hashes"],
            "notes": discovery.notes,
            "corroborated_by_multiple_engines": sum(
                1 for _o, v in found.items() if len(v["engines"]) > 1),
        },
        "safety": {
            "blacklisted_before_fetch": discovery.stats["blacklisted"],
            "excluded_by_gate_before_fetch": discovery.stats["safety_excluded"],
            "services_excluded_after_fetch": len(excluded_services),
            "gate": discovery.safety.summary(),
        },
        "crawl": {
            "services_attempted": len(targets),
            "services_reachable": reachable,
            "reachability": round(reachable / max(1, len(targets)), 3),
            "pages": total_pages,
            "bytes": total_bytes,
            "seconds": round(crawl_seconds, 1),
            "pages_per_minute": round(total_pages / max(1e-9, crawl_seconds / 60), 1),
            "seconds_per_service": round(crawl_seconds / max(1, len(targets)), 1),
        },
        "extraction": {
            "clear_web_mentions": total_mentions,
            "mentions_per_reachable_service": round(
                total_mentions / max(1, reachable), 1),
            "services_with_accounts_extracted": with_accounts,
            "account_extraction_note": (
                "The persona extractor keys on ONIONLAB's profile-page "
                "structure. Real services do not share it, so account-level "
                "extraction from an arbitrary marketplace needs a per-site "
                "adapter. Service fingerprinting and the clear-web harvest are "
                "structure-agnostic and do generalise."),
        },
        "infrastructure_clusters": {
            "total": len(clusters),
            "non_generic": len(real_clusters),
            "clusters": clusters[:25],
            "note": ("A shared fingerprint is a verifiable fact, not a "
                     "prediction: no ground truth is needed to state that two "
                     "services present the same favicon or the same TLS public "
                     "key. Clusters covering more than half the sample are "
                     "marked generic -- they identify the software, not an "
                     "operator."),
        },
        "services": per_service,
        "total_seconds": round(time.time() - started, 1),
        "what_is_not_measured": (
            "Persona-linkage precision and recall. That requires knowing which "
            "accounts share an operator, which nobody does for the live "
            "network. Those figures come from the labelled benchmark and are "
            "not estimated here."),
    }
