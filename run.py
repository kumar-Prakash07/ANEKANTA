#!/usr/bin/env python
"""ANEKANTA command line.

    python run.py serve       start the dashboard on http://127.0.0.1:8000
    python run.py bench       run the evaluation and print the report
    python run.py report A B  render the evidence report for one persona pair
    python run.py dossiers    render every resolved actor dossier
    python run.py live <addr> crawl a live onion service over Tor and analyse it
                              (recursive: follows onion links it discovers)
    python run.py preflight   check the ONIONLAB container isolation
    python run.py discover    find live onion services by keyword (darkdump)
    python run.py realworld   benchmark against live services on the real network
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import os

from anveshak import pipeline
from anveshak.reporting import dossier_report, evidence_report

# Container-friendly defaults. Inside Docker the proxy is another container, so
# 127.0.0.1 is wrong there; on a workstation it is right. Reading the
# environment lets one image serve both without a second entrypoint.
ENV_TOR = os.environ.get("ANEKANTA_TOR", "127.0.0.1:9050")
ENV_ACTORS = int(os.environ.get("ANEKANTA_ACTORS", "150"))
ENV_SEED = int(os.environ.get("ANEKANTA_SEED", "1337"))


def _banner(r) -> None:
    rep = r.report
    c, op, d = rep["corpus"], rep["operating_point"], rep["discrimination"]
    print()
    print("  ANEKANTA  |  Uncovering the Many Sides of Anonymous Actors")
    print("  " + "-" * 62)
    print("  corpus       %d personas / %d actors / %s posts"
          % (c["personas"], c["actors"], format(c["posts"], ",")))
    print("  base rate    1 true link per %d pairs" % round(1 / c["base_rate"]))
    print("  blocking     %s of pairs skipped, %s of true links retained"
          % ("{:.1%}".format(rep["blocking"]["reduction_ratio"]),
             "{:.1%}".format(rep["blocking"]["pair_completeness"])))
    print("  " + "-" * 62)
    print("  ROC AUC      %.4f      (held-out actors)" % d["roc_auc"])
    print("  precision    %.4f      recall %.4f      F1 %.4f"
          % (op["precision"], op["recall"], op["f1"]))
    print("  Cllr         %.4f      (min %.4f)"
          % (rep["calibration"]["cllr"], rep["calibration"]["cllr_min"]))
    print("  B-Cubed F1   %.4f      %d clusters vs %d actors"
          % (rep["clustering"]["bcubed_f1"], rep["clustering"]["predicted_clusters"],
             rep["clustering"]["true_actors"]))
    print("  " + "-" * 62)
    print("  recall by operator discipline")
    for tier in ("sloppy", "mixed", "disciplined"):
        o = rep["by_opsec"].get(tier) or {}
        if not o.get("true_pairs"):
            continue
        print("    %-12s %5.1f%%   (%d/%d)   median log10 LR %+.2f"
              % (tier, 100 * (o["recall"] or 0), o["recovered"], o["true_pairs"],
                 o.get("median_log10_lr", 0)))
    q = rep["review_queue"]
    if q.get("leads"):
        print("    leads        %d pairs, %d true -- %.1f%% precise vs %.1f%% "
              "in the scored pool (%.0fx)"
              % (q["leads"], q["true_links_in_band"],
                 100 * q["band_precision"],
                 100 * q["candidate_pool_base_rate"],
                 q["enrichment_vs_candidate_pool"]))
    print("  " + "-" * 62)
    print("  channel discrimination (AUC) by operator discipline")
    tiers = [t for t in ("sloppy", "mixed", "disciplined")
             if rep["channel_auc_by_opsec"].get(t)]
    print("    %-12s %s" % ("", "".join("%12s" % t for t in tiers)))
    for ch in ("pgp", "handle", "crypto", "device", "infra", "favicon",
               "tls", "template", "stylometry", "authorship",
               "temporal", "FUSED"):
        cells = ""
        for t in tiers:
            v = rep["channel_auc_by_opsec"][t].get(ch)
            cells += "%12s" % ("%.3f" % v if v is not None else "--")
        mark = ("  <- behavioural"
                if ch in ("stylometry", "temporal", "authorship") else "")
        print("    %-12s%s%s" % (ch, cells, mark))
    print()
    print("  traps: %s" % json.dumps(
        {k: (v.get("survived") if "survived" in v else v.get("recall"))
         for k, v in rep["traps"].items()}))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(prog="anekanta")
    ap.add_argument("command",
                    choices=["serve", "bench", "report", "dossiers", "live",
                             "preflight", "discover", "realworld"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--seed", type=int, default=ENV_SEED)
    ap.add_argument("--actors", type=int, default=ENV_ACTORS)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address; 0.0.0.0 only inside a "
                         "container whose port is published to "
                         "127.0.0.1 on the host")
    ap.add_argument("--json", action="store_true", help="dump the full report")
    ap.add_argument("--tor", default=ENV_TOR,
                    help="Tor SOCKS proxy for live mode")
    ap.add_argument("--truth", default="onionlab/ground_truth.json",
                    help="operator map used only to grade a live run")
    ap.add_argument("--max-onions", type=int, default=4,
                    help="how many services the recursive crawl may visit")
    ap.add_argument("--engines", default="",
                    help="comma-separated search engines for discovery")
    ap.add_argument("--queries", default="",
                    help="comma-separated search terms")
    ap.add_argument("--services", type=int, default=12,
                    help="how many discovered services the benchmark crawls")
    ap.add_argument("--pages-each", type=int, default=6,
                    help="page budget per service in the benchmark")
    ap.add_argument("--out", default="", help="where to write a JSON report")
    ap.add_argument("--verify-osint", action="store_true",
                    help="perform the safe live OSINT lookups (Gravatar). Off "
                         "by default: querying a third party reveals your "
                         "interest in an identifier, which is the "
                         "investigator's call, not the tool's")
    a = ap.parse_args()

    if a.command == "serve":
        import uvicorn
        from anveshak.api import server
        print("  building the case file, this takes a moment ...")
        server.load(seed=a.seed, n_actors=a.actors)
        _banner(server._state["result"])
        server.DEFAULT_TOR = a.tor
        print("  dashboard  ->  http://127.0.0.1:%d\n" % a.port)
        # Binds a.host, which defaults to loopback. Inside the container it is
        # 0.0.0.0, because a container's loopback is reachable only from that
        # container -- Docker's published port would connect and then be closed,
        # while the container's own health check kept passing.
        uvicorn.run(server.app, host=a.host, port=a.port, log_level="warning")
        return 0

    if a.command == "discover":
        return _discover(a)

    if a.command == "realworld":
        return _realworld(a)

    if a.command == "preflight":
        from anveshak.preflight import run_preflight
        return run_preflight()

    if a.command == "live":
        if not a.args:
            print("usage: run.py live <address>.onion")
            return 2
        return _live(a)

    r = pipeline.run(seed=a.seed, n_actors=a.actors)

    if a.command == "bench":
        _banner(r)
        if a.json:
            print(json.dumps(r.report, indent=2, default=str))
        return 0

    if a.command == "dossiers":
        for d in r.dossiers:
            print(dossier_report(d))
            print()
        return 0

    if a.command == "report":
        if len(a.args) != 2:
            print("usage: run.py report <persona_a> <persona_b>")
            return 2
        x, y = a.args
        by = {(l.persona_a, l.persona_b): l for l in r.links}
        link = by.get((x, y)) or by.get((y, x))
        if link is None:
            print("no scored link for that pair; strongest available:")
            for l in r.links[:10]:
                print("   %s  %s   log10 LR %.2f" % (l.persona_a, l.persona_b, l.log10_lr))
            return 1
        personas = {p.persona_id: p for p in r.corpus.personas}
        print(evidence_report(link, personas, r.engines["temporal"],
                              r.report["settings"]["prior_odds"],
                              r.report["settings"]["threshold_log10_lr"]))
        return 0
    return 0




def _live(a) -> int:
    """Crawl a real hidden service and analyse it with a transferred calibration."""
    import json as _json

    from anveshak import live as live_mod
    from anveshak.collect.crawler import TorCrawler

    host, _, port = a.tor.partition(":")
    crawler = TorCrawler(host or "127.0.0.1", int(port or 9050), delay=0.6)
    ok, msg = crawler.check_reachable()
    print("  tor: %s" % msg)
    if not ok:
        return 1

    print("  calibrating on the benchmark (live data carries no labels) ...")
    bench = pipeline.run(seed=a.seed, n_actors=a.actors)
    thr = bench.report["settings"]["threshold_log10_lr"]
    floor = bench.report["settings"]["lead_floor_log10_lr"]

    target = a.args[0]
    print("  crawling %s (following discovered onions, max %d) ..."
          % (target, a.max_onions))
    crawl = crawler.crawl(target, max_onions=a.max_onions)
    if not crawl.personas:
        print("  no personas extracted: %s" % "; ".join(crawl.notes))
        return 1

    result = live_mod.analyse(crawl, bench.model, thr, floor)
    if a.verify_osint:
        from anveshak.osint import pivot as _pivot
        for _entry in result.osint.get('developed', {}).values():
            _pivot._verify(_entry['leads'])

    print()
    print("  LIVE ANALYSIS  %s" % result.onion)
    print("  " + "-" * 62)
    c = result.crawl
    print("  crawled      %d services / %d pages / %s bytes / %d accounts / %d posts"
          % (c["services_crawled"], c["pages_fetched"],
             format(c["bytes_fetched"], ","), c["personas"], c["posts"]))
    for found, via in (c.get("discovered_from") or {}).items():
        print("  discovered   %s...  via  %s..." % (found[:20], via[:20]))
    fp = result.fingerprint
    print("  favicon      mmh3 %s  dhash %s"
          % (fp.get("favicon_mmh3", "-"), fp.get("favicon_dhash", "-")))
    tls = fp.get("tls") or {}
    if tls.get("present"):
        print("  tls          %s / serial %s / spki %s"
              % (tls.get("issuer_o", "?"), (tls.get("serial") or "")[:16],
                 (tls.get("spki_sha256") or "")[:16]))
    print("  stack        server %r / header-order %s / dom %s"
          % (fp.get("server_banner", ""), (fp.get("header_order_hash") or "")[:12],
             (fp.get("dom_skeleton_hash") or "")[:12]))
    print("  " + "-" * 62)
    print("  threshold    log10 LR >= %.2f   (transferred calibration)" % thr)
    print()
    print("  %-26s %-26s %8s  %s" % ("persona A", "persona B", "log10LR", "channels"))
    for l in result.links[:15]:
        tier = "LINK" if l.log10_lr >= thr else "lead"
        print("  %-26s %-26s %8.2f  [%s] %s"
              % (l.persona_a.split(":")[-1][:26], l.persona_b.split(":")[-1][:26],
                 l.log10_lr, tier, ",".join(l.channels[:4])))
    print()
    for cl in result.clusters:
        if cl["size"] > 1:
            print("  cluster %s: %s"
                  % (cl["cluster_id"],
                     ", ".join(x.split(":")[-1] for x in cl["personas"])))

    # ---- Dark2Clear stage -------------------------------------------------
    from anveshak.osint import context as osint_context

    from anveshak.osint.pivot import NON_PIVOT_KINDS

    ranked, seen = [], set()
    for m in sorted(result.mentions, key=lambda x: -x.priority):
        if m.key in seen or m.kind in NON_PIVOT_KINDS:
            continue
        seen.add(m.key)
        ranked.append(m)

    print()
    print("  CLEAR-WEB MENTIONS  (harvested %d, %d distinct clear-web identifiers)"
          % (len(result.mentions), len(ranked)))
    print("  %-5s %-9s %-38s %-16s %s"
          % ("band", "kind", "identifier", "on account", "why"))
    for m in ranked[:12]:
        name, _note = osint_context.band(m.priority)
        why = m.reasons[0][:52] if m.reasons else ""
        print("  %-5s %-9s %-38s %-16s %s"
              % (name, m.kind, m.value[:38], (m.handle or "-")[:16], why))

    if result.exposure:
        print()
        print("  OPERATOR EXPOSURE  (a leak on one account implicates the cluster)")
        for entry in sorted(result.exposure.values(),
                            key=lambda e: -e["top_priority"]):
            leaked = ", ".join(h.split(":")[-1] for h in entry["leaking_personas"])
            also = [p.split(":")[-1] for p in entry["exposed_by_association"]]
            print("    %s  leaked by: %s" % (entry["cluster_id"], leaked))
            print("        identifiers: %s"
                  % ", ".join(sorted({m.value for m in entry["leaks"]})[:3]))
            if also:
                print("        also implicates (leaked nothing themselves): %s"
                      % ", ".join(also))

    developed = result.osint.get("developed", {})
    corr = [(k, e) for k, e in developed.items()
            if any(l.method == "identity correlation" for l in e["leads"])]
    if corr:
        print()
        print("  IDENTITY CORRELATION  (leaked identifier vs dark-web handle)")
        for _key, entry in corr[:6]:
            for lead in entry["leads"]:
                if lead.method != "identity correlation":
                    continue
                print("    %s" % lead.identifier)
                print("        %s" % lead.detail[:150])

    ev = live_mod.score_against_truth(result, a.truth)
    if ev.get("available"):
        print()
        print("  GRADED AGAINST THE LAB OPERATOR MAP (crawler never saw it)")
        print("    %d personas, %d pairs, %d true"
              % (ev["personas_matched"], ev["pairs_scored"], ev["true_pairs"]))
        print("    precision %.2f  recall %.2f  AUC %s  B-Cubed F1 %.3f"
              % (ev["precision"], ev["recall"], ev["roc_auc"], ev["bcubed_f1"]))
        print("    tp %d  fp %d  fn %d" % (ev["tp"], ev["fp"], ev["fn"]))
    else:
        print("\n  no ground-truth map: results are hypotheses, ungraded")

    oev = live_mod.score_osint_against_truth(result, a.truth)
    if oev.get("available"):
        print()
        print("  CLEAR-WEB HARVEST, GRADED")
        print("    planted leaks recovered   %d/%d (%.0f%%), %d attributed to the "
              "right account"
              % (oev["recovered"], oev["planted"], 100 * oev["recall"],
                 oev["attribution_correct"]))
        print("    decoys collected          %d/%d (kept, but ranked down)"
              % (oev["decoys_collected"], oev["decoys_present"]))
        print("    ranking separates them    %s (worst real %.2f > best decoy %.2f)"
              % ("yes" if oev["ranking_separates_leaks_from_decoys"] else "NO",
                 oev["worst_real_leak_priority"] or 0.0,
                 oev["best_decoy_priority"] or 0.0))
        print("    identity correlations     %d"
              % oev["identifiers_with_identity_correlation"])
        print("    accounts implicated by association  %d"
              % oev["accounts_exposed_by_association"])
        if oev["missed"]:
            print("    MISSED: %s" % ", ".join(oev["missed"]))
    print()
    if a.json:
        print(_json.dumps({"crawl": result.crawl, "fingerprint": result.fingerprint,
                           "evaluation": ev,
                           "links": [l.to_json() for l in result.links]},
                          indent=2, default=str))
    return 0


def _tor_session(tor: str):
    """A requests session pinned to Tor. socks5h so the proxy resolves names."""
    import requests
    host, _, port = tor.partition(":")
    url = "socks5h://%s:%s" % (host or "127.0.0.1", port or "9050")
    session = requests.Session()
    session.proxies = {"http": url, "https": url}
    session.headers.update({
        "User-Agent": "ANEKANTA-collector/1.0 (research; contact operator)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en",
    })
    return session


def _discovery(a):
    from anveshak.collect.discovery import OnionDiscovery
    return OnionDiscovery(_tor_session(a.tor), delay=1.5)


def _engines(a):
    from anveshak.collect.discovery import SEARCHABLE_ENGINES
    if not a.engines:
        return SEARCHABLE_ENGINES
    chosen = [e.strip() for e in a.engines.split(",") if e.strip()]
    return chosen or SEARCHABLE_ENGINES


def _discover(a) -> int:
    """Keyword discovery of live hidden services (darkdump integration)."""
    from anveshak.collect.crawler import TorCrawler

    probe = TorCrawler(*(a.tor.split(":")[0], int(a.tor.split(":")[1])))
    ok, message = probe.check_reachable()
    print("  tor: %s" % message)
    if not ok:
        return 1

    queries = ([q.strip() for q in a.queries.split(",") if q.strip()]
               or (a.args or ["hosting"]))
    d = _discovery(a)
    try:
        info = d.prepare()
    except Exception as exc:
        print("  ABORTED: Ahmia blacklist unavailable (%s). Discovery fails "
              "closed by design -- a filter that silently stops filtering is "
              "worse than none." % type(exc).__name__)
        return 1
    print("  blacklist: %d hashed addresses from %s"
          % (info["blacklist_hashes"], info["source"]))

    engines = _engines(a)
    print("  engines: %s" % ", ".join(engines))
    print("  queries: %s" % ", ".join(queries))
    print()

    found = d.multi_search(queries, engines=engines, per_query=10)
    for note in d.notes:
        print("  note: %s" % note)

    print()
    print("  %-58s %-22s %s" % ("onion", "engines", "title"))
    for onion, entry in sorted(found.items(),
                               key=lambda kv: -len(kv[1]["engines"]))[:40]:
        print("  %-58s %-22s %s"
              % (onion, ",".join(entry["engines"])[:22],
                 (entry["hit"].title or "")[:40]))

    print()
    print("  %d unique addresses; %d raw hits, %d removed by the blacklist, "
          "%d by the safety gate"
          % (len(found), d.stats["raw_hits"], d.stats["blacklisted"],
             d.stats["safety_excluded"]))
    print("  %d corroborated by more than one engine"
          % sum(1 for v in found.values() if len(v["engines"]) > 1))
    print()
    return 0


def _realworld(a) -> int:
    """Benchmark against live services on the real Tor network."""
    import json as _json

    from anveshak.collect.crawler import TorCrawler
    from anveshak.evaluation import realworld

    host, _, port = a.tor.partition(":")
    crawler = TorCrawler(host or "127.0.0.1", int(port or 9050), delay=0.8,
                         max_pages=400)
    ok, message = crawler.check_reachable()
    print("  tor: %s" % message)
    if not ok:
        return 1

    queries = [q.strip() for q in a.queries.split(",") if q.strip()] or None
    d = _discovery(a)

    print()
    print("  REAL-WORLD BENCHMARK")
    print("  Live services on the public Tor network. There is no operator map")
    print("  for these, so linkage precision is NOT estimated -- see the")
    print("  labelled benchmark for that. What is measured here is discovery,")
    print("  throughput, extraction, and infrastructure correlation, which are")
    print("  verifiable without labels.")
    print("  " + "-" * 66)

    try:
        report = realworld.run(crawler, d, queries=queries, engines=_engines(a),
                               max_services=a.services,
                               max_pages_each=a.pages_each,
                               progress=lambda m: print("  %s" % m))
    except Exception as exc:
        print("  ABORTED: %s: %s" % (type(exc).__name__, str(exc)[:180]))
        return 1

    disc, crawl = report["discovery"], report["crawl"]
    safety, extraction = report["safety"], report["extraction"]
    clusters = report["infrastructure_clusters"]

    print("  " + "-" * 66)
    print("  DISCOVERY")
    print("    unique addresses          %d  (%d corroborated by >1 engine)"
          % (disc["unique_addresses"], disc["corroborated_by_multiple_engines"]))
    print("    raw hits / blacklisted    %d / %d"
          % (disc["engine_stats"]["raw_hits"], disc["engine_stats"]["blacklisted"]))
    print("    blacklist size            %s hashed addresses"
          % format(disc["blacklist_hashes"], ","))
    for note in disc["notes"]:
        print("    note: %s" % note[:96])

    print("  SAFETY")
    print("    excluded before fetch     %d blacklisted, %d by the content gate"
          % (safety["blacklisted_before_fetch"],
             safety["excluded_by_gate_before_fetch"]))
    print("    excluded after fetch      %d service(s) discarded whole"
          % safety["services_excluded_after_fetch"])

    print("  CRAWL")
    print("    reachable                 %d/%d (%.0f%%)"
          % (crawl["services_reachable"], crawl["services_attempted"],
             100 * crawl["reachability"]))
    print("    throughput                %.1f pages/min, %.1fs per service"
          % (crawl["pages_per_minute"], crawl["seconds_per_service"]))
    print("    volume                    %d pages, %s bytes in %.0fs"
          % (crawl["pages"], format(crawl["bytes"], ","), crawl["seconds"]))

    print("  EXTRACTION")
    print("    clear-web identifiers     %d (%.1f per reachable service)"
          % (extraction["clear_web_mentions"],
             extraction["mentions_per_reachable_service"]))
    print("    account extraction        %d service(s) -- see note"
          % extraction["services_with_accounts_extracted"])

    print("  INFRASTRUCTURE CORRELATION  (verifiable without ground truth)")
    print("    clusters found            %d (%d non-generic)"
          % (clusters["total"], clusters["non_generic"]))
    for c in clusters["clusters"][:8]:
        if c["generic"]:
            continue
        print("    %-16s %d services share %s"
              % (c["label"], c["size"], c["meaning"]))
        for svc in c["services"][:3]:
            print("        %s" % svc)
    print()
    print("  NOT MEASURED: %s" % report["what_is_not_measured"][:150])
    print()

    out = getattr(a, "out", "") or "realworld-report.json"
    pathlib_write(out, _json.dumps(report, indent=2, default=str))
    print("  full report written to %s" % out)
    return 0


def pathlib_write(path: str, text: str) -> None:
    from pathlib import Path
    Path(path).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
