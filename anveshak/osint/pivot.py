"""OSINT pivots from a harvested identifier.

The final stage of the Dark2Clear framework: take a clear-web identifier
harvested from a hidden service and develop it into something an investigator
can act on. Wangchuk & Rathod do this with Maltego and Lampyre -- commercial
tools that query paid data sources and return a graph.

This module does not reimplement those, and should not pretend to. What it
does instead is the part that does not need a subscription, and one thing they
cannot do at all.

What it computes locally
------------------------
  identity correlation   the strongest and cheapest pivot. An e-mail local part
                         is normalised with the *same* function the handle
                         engine uses, then compared against every persona
                         handle in the corpus. `kavach.supply@gmail.example`
                         and the account `kavach_supply` collapse to the same
                         string. This is Ulbricht's "altoid" mistake, found
                         automatically.
  actor attribution      the thing the paper cannot do. Because the linkage
                         engines have already resolved personas into actors, a
                         leak on ONE persona attaches to the WHOLE cluster --
                         including the accounts that leaked nothing. An
                         operator who is careful on four accounts and careless
                         on the fifth is compromised on all five.
  gravatar               MD5 of the lowercased address, which is a public
                         lookup an analyst can check in a browser. Standard
                         OSINT, free, and either it resolves or it does not.
  candidate profiles     constructed URLs for the platforms where a username
                         of this shape would live.
  infrastructure         for a domain: certificate transparency and WHOIS
                         lookup URLs.

Why nothing is fetched by default
---------------------------------
Every pivot is emitted as a URL to check, not as a result. Querying a
third-party service tells that service you are interested in the identifier,
from your own address, at a recorded time -- which is an operational decision
belonging to the investigator, not to a library. `verify=True` enables live
checking for the handful of lookups where it is harmless, and the report says
plainly which findings were checked and which were merely constructed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict

from ..engines.handle import normalise

# Platforms worth constructing a candidate URL for: a username there is public,
# checkable by a human in one click, and commonly reused.
USERNAME_PLATFORMS = [
    ("github", "https://github.com/%s"),
    ("keybase", "https://keybase.io/%s"),
    ("reddit", "https://www.reddit.com/user/%s"),
    ("twitter", "https://twitter.com/%s"),
    ("instagram", "https://www.instagram.com/%s/"),
    ("telegram", "https://t.me/%s"),
    ("gitlab", "https://gitlab.com/%s"),
    ("pastebin", "https://pastebin.com/u/%s"),
]

DOMAIN_LOOKUPS = [
    ("certificate transparency", "https://crt.sh/?q=%s"),
    ("passive DNS / WHOIS", "https://whois.domaintools.com/%s"),
    ("wayback history", "https://web.archive.org/web/*/%s"),
]

SEPARATORS = re.compile(r"[._\-+]")

# Identifiers that are not clear-web pivots. Wallets and key fingerprints are
# evidence, but they are the *linkage engines'* evidence -- following them means
# chain analysis, not OSINT. They are excluded here by kind rather than by
# score, because a wallet block printed next to a "contact me directly"
# paragraph inherits that paragraph's solicitation score and would otherwise
# outrank the e-mail address the paragraph was actually about.
NON_PIVOT_KINDS = frozenset({"btc", "xmr", "eth", "pgp_fingerprint"})

# Forum-sourced identifier kinds that carry a username or handle and are
# therefore eligible for the identity-correlation pivot (same normaliser as the
# handle engine, same logic as the e-mail local-part).  Tox IDs and Session IDs
# are long hex strings -- they do not normalise to a username, so they are not
# candidates for handle correlation.  They are still developed into candidate
# URLs (t.me equivalent does not exist for Tox/Session, but the identifier is
# emitted as a checkable string for the analyst).
_HANDLE_CORRELATION_KINDS = frozenset({
    "email", "jabber", "telegram", "wickr", "paypal",
    "twitter", "instagram", "github", "keybase", "reddit",
})


@dataclass
class Lead:
    """One developed pivot: a checkable claim with a stated basis."""

    identifier: str
    kind: str
    method: str
    detail: str
    url: str = ""
    confidence: str = "unverified"     # unverified | checked | confirmed
    linked_personas: list = field(default_factory=list)
    linked_cluster: str = ""

    def to_json(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Identity correlation
# ---------------------------------------------------------------------------

def username_candidates(identifier: str, kind: str) -> list:
    """Plausible usernames implied by an identifier."""
    if kind in ("email", "jabber"):
        local = identifier.split("@", 1)[0]
    else:
        local = identifier
    cands = {local}
    cands.add(SEPARATORS.sub("", local))
    cands.add(SEPARATORS.sub("_", local))
    # a trailing digit run is decoration far more often than identity
    stripped = re.sub(r"\d{1,4}$", "", local)
    if len(stripped) >= 4:
        cands.add(stripped)
    return sorted({c for c in cands if len(c) >= 3})


def correlate_with_personas(identifier: str, kind: str, personas: list) -> list:
    """Match a leaked identifier against dark-web handles.

    Both sides go through the handle engine's `normalise`, so leetspeak,
    separators and numeric suffixes collapse the same way here as they do in
    the linkage engine. Using a second, subtly different normaliser here would
    be a quiet source of both misses and false matches.

    Forum-sourced identifiers (telegram, jabber, wickr, paypal, social profiles)
    are processed exactly the same way as market-profile identifiers: the local
    part or the handle is extracted, normalised, and compared.  The kind check
    uses _HANDLE_CORRELATION_KINDS so that Tox IDs and Session IDs (which are
    long hex strings, not usernames) are quietly skipped -- they cannot match a
    dark-web handle and attempting to match them produces spurious short-string
    collisions.

    The forum_position of the source mention does NOT affect identity
    correlation: even an identifier found in a quoted reply is worth correlating
    against handles, because the caller (develop/develop_all) has already
    filtered by min_priority, and a low-priority quoted-reply identifier will
    not reach this function unless the analyst explicitly lowered the floor.
    """
    if kind not in _HANDLE_CORRELATION_KINDS:
        return []
    if kind in ("email", "jabber"):
        local = identifier.split("@", 1)[0]
    else:
        local = identifier
    target = normalise(local)
    if len(target) < 4:
        return []

    hits = []
    for p in personas:
        h = normalise(p.handle or "")
        if not h or len(h) < 4:
            continue
        if h == target:
            hits.append((p, 1.0, "normalised handle is identical (%s)" % h))
        elif h in target or target in h:
            shorter = min(len(h), len(target))
            if shorter >= 5:
                hits.append((p, 0.75,
                             "normalised forms contain one another (%s / %s)"
                             % (h, target)))
    return hits


# ---------------------------------------------------------------------------
# Pivot construction
# ---------------------------------------------------------------------------

def gravatar_url(email: str) -> str:
    """Gravatar's published scheme: MD5 of the trimmed, lowercased address."""
    digest = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return "https://www.gravatar.com/avatar/%s?d=404" % digest


def develop(mention, personas: list, cluster_of: dict | None = None,
            verify: bool = False) -> list:
    """Turn one harvested mention into a list of checkable leads."""
    cluster_of = cluster_of or {}
    leads: list = []
    ident, kind = mention.value, mention.kind

    # --- identity correlation, and attribution to a resolved actor ---------
    # Grouped by cluster rather than by persona. Two accounts of one operator
    # frequently normalise to the same string -- kavach_supply and
    # kavach.supply2 both reduce to "kavachsupply" -- and emitting a separate
    # lead for each prints the same finding twice.
    matches = correlate_with_personas(ident, kind, personas)
    by_cluster: dict = {}
    for persona, strength, why in matches:
        cluster = cluster_of.get(persona.persona_id, "")
        key = cluster or ("persona:" + persona.persona_id)
        entry = by_cluster.setdefault(key, {"cluster": cluster, "hits": []})
        entry["hits"].append((persona, strength, why))

    for entry in by_cluster.values():
        cluster = entry["cluster"]
        best = max(entry["hits"], key=lambda h: h[1])
        persona, strength, why = best
        matched = sorted({h[0].handle for h in entry["hits"]})
        siblings = sorted(p for p, c in cluster_of.items() if c and c == cluster)
        detail = ("%s. Matched account(s): %s. The identifier was published on "
                  "%s; %s"
                  % (why, ", ".join(matched),
                     mention.handle or "an unattributed page",
                     ("the linkage engine places that account in cluster %s "
                      "with %d other persona(s), so the leak attaches to all "
                      "of them" % (cluster, len(siblings) - 1))
                     if cluster and len(siblings) > 1 else
                     "no larger cluster was resolved for it"))
        leads.append(Lead(
            identifier=ident, kind=kind,
            method="identity correlation",
            detail=detail,
            confidence="confirmed" if strength >= 1.0 else "unverified",
            linked_personas=siblings or [persona.persona_id],
            linked_cluster=cluster))

    # --- e-mail specific ---------------------------------------------------
    if kind == "email":
        leads.append(Lead(
            identifier=ident, kind=kind, method="gravatar",
            detail="If a Gravatar exists for this address, the account was "
                   "registered on a service using Gravatar and may expose a "
                   "profile image and display name.",
            url=gravatar_url(ident)))
        leads.append(Lead(
            identifier=ident, kind=kind, method="breach corpora",
            detail="A mainstream mailbox frequently appears in public breach "
                   "corpora alongside reused passwords, recovery addresses and "
                   "linked services. Query through an authorised source."
                   if mention.provider_class == "mainstream" else
                   "Address is at an anonymous provider, so breach corpora are "
                   "less likely to hold anything; check anyway, it is cheap.",
            url="https://haveibeenpwned.com/unifiedsearch/%s" % ident))

    # --- Tox / Session: no URL pivot, but emit as a checkable string -------
    # These are opaque identifiers that can only be acted on from within the
    # respective application.  The lead records them with a plain-language
    # description so they appear in the analyst's queue alongside the others,
    # rather than being silently dropped.
    if kind == "tox":
        leads.append(Lead(
            identifier=ident, kind=kind, method="tox contact",
            detail="Tox ID (76 hex chars). Add via the Tox client to initiate "
                   "contact. No automated check is performed -- doing so would "
                   "reveal the investigation to the contact.",
            url=""))
    if kind == "session":
        leads.append(Lead(
            identifier=ident, kind=kind, method="session contact",
            detail="Session ID (66 hex chars, starts with 0). Contact via the "
                   "Session app. No automated check is performed.",
            url=""))

    # --- username reuse across platforms -----------------------------------
    if kind in ("email", "jabber", "telegram", "wickr", "paypal", "twitter",
                "instagram", "github", "keybase", "reddit"):
        for candidate in username_candidates(ident, kind)[:3]:
            for platform, template in USERNAME_PLATFORMS:
                leads.append(Lead(
                    identifier=ident, kind=kind, method="username reuse",
                    detail="Candidate %s account for the username %r derived "
                           "from this identifier." % (platform, candidate),
                    url=template % candidate))

    # --- domain infrastructure ---------------------------------------------
    if kind == "domain":
        for label, template in DOMAIN_LOOKUPS:
            leads.append(Lead(
                identifier=ident, kind=kind, method=label,
                detail="Infrastructure history for %s. Certificate "
                       "transparency in particular often exposes sibling "
                       "hostnames and the registration timeline." % ident,
                url=template % ident))

    if verify:
        _verify(leads)
    return leads


def _verify(leads: list) -> None:
    """Optionally check the lookups that are safe to perform.

    Only Gravatar, and only on request. It is an unauthenticated GET for a
    hash, it reveals nothing about the investigation beyond the hash itself,
    and its answer is unambiguous. Everything else on the list is left for the
    investigator to run deliberately, from wherever they choose to run it.
    """
    import requests
    for lead in leads:
        if lead.method != "gravatar" or not lead.url:
            continue
        try:
            r = requests.get(lead.url, timeout=12)
            lead.confidence = "confirmed" if r.status_code == 200 else "checked"
            lead.detail += (" Checked: Gravatar %s."
                            % ("exists" if r.status_code == 200 else "not found"))
        except Exception as exc:
            lead.detail += " Check failed (%s)." % type(exc).__name__


def develop_all(mentions: list, personas: list, cluster_of: dict | None = None,
                min_priority: float = 0.5, verify: bool = False) -> dict:
    """Develop every mention above the priority floor, grouped by identifier.

    Works identically for mentions from market profile pages and forum thread
    posts: the mention's provenance (thread_id, post_id, author_persona,
    forum_position) is carried through to the Lead records via the Lead.detail
    field and the source Mention stored under the "mention" key.

    Tox IDs and Session IDs are included (they are not in NON_PIVOT_KINDS) but
    skip the identity-correlation step because _HANDLE_CORRELATION_KINDS does
    not include them -- they produce a contact-info lead instead.
    """
    out: dict = {}
    for m in sorted(mentions, key=lambda x: -x.priority):
        if m.priority < min_priority or m.kind in NON_PIVOT_KINDS:
            continue
        if m.key in out:
            continue
        leads = develop(m, personas, cluster_of, verify=verify)
        out[m.key] = {"mention": m, "leads": leads}
    return out


def actor_exposure(mentions: list, personas: list, cluster_of: dict,
                   min_priority: float = 0.5) -> dict:
    """Roll leaks up to resolved actors.

    The composition that neither system achieves alone. Dark2Clear finds that
    an account leaked an address. The linkage engines find that the account
    shares an operator with four others. Put together, the operator is exposed
    across every persona they run -- and the report can say which accounts to
    seize on the strength of a mistake made on only one of them.

    Forum thread mentions are processed identically to market profile mentions.
    The forum_position on each mention is preserved in the leak list so
    downstream consumers (exposure.py, the API, the dashboard) can distinguish
    original-post leaks from quoted-reply artefacts.
    """
    by_persona = {p.persona_id: p for p in personas}
    exposure: dict = {}
    for m in mentions:
        if (m.priority < min_priority or not m.persona_id
                or m.kind in NON_PIVOT_KINDS):
            continue
        cluster = cluster_of.get(m.persona_id)
        if not cluster:
            continue
        entry = exposure.setdefault(cluster, {
            "cluster_id": cluster, "personas": set(), "leaks": [],
            "leaking_personas": set(),
        })
        entry["leaking_personas"].add(m.persona_id)
        entry["leaks"].append(m)

    for cluster, entry in exposure.items():
        members = [pid for pid, c in cluster_of.items() if c == cluster]
        entry["personas"] = sorted(members)
        entry["leaking_personas"] = sorted(entry["leaking_personas"])
        entry["exposed_by_association"] = sorted(
            set(entry["personas"]) - set(entry["leaking_personas"]))
        entry["handles"] = [by_persona[p].handle for p in entry["personas"]
                            if p in by_persona]
        entry["leaks"] = sorted(entry["leaks"], key=lambda m: -m.priority)
        entry["top_priority"] = entry["leaks"][0].priority if entry["leaks"] else 0.0
    return exposure
