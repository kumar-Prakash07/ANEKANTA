#!/usr/bin/env python
"""Export a self-contained static build of the dashboard.

Why this exists
---------------
The live platform is four containers: a Tor daemon holding circuits open, two
hidden services, and an application that trains a model at startup, keeps state
between requests, and runs crawls lasting minutes. None of that fits a
serverless host -- there is no persistent process to run Tor in, no way to hold
a crawl open past a function timeout, and PyTorch alone is several times the
function size limit.

What does fit is the *evidence*: every number this project produces is
deterministic given a seed, so it can be computed once here and served as JSON.
The result is the real dashboard, with the real results, that anyone can open
from a URL -- and which cannot crawl anything, because there is nothing behind
it to crawl with.

The distinction is made visible in the page rather than left for a visitor to
discover by clicking a button that does nothing: the static build labels itself,
and the two live tabs explain what they would do and where to run it.

    python export_static.py --out public
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _json(obj) -> str:
    return json.dumps(obj, indent=1, default=str)


def export_benchmark(out: Path, seed: int, actors: int) -> dict:
    """Run the labelled pipeline and dump everything the dashboard reads."""
    from anveshak import pipeline
    from anveshak.fusion import graph

    print("  running the benchmark (this is the slow part) ...")
    r = pipeline.run(seed=seed, n_actors=actors)

    personas_by_id = {p.persona_id: p for p in r.corpus.personas}
    cluster_of = {p: c["cluster_id"] for c in r.clusters for p in c["personas"]}
    temporal = r.engines["temporal"]
    thr = r.report["settings"]["threshold_log10_lr"]

    (out / "report.json").write_text(_json(r.report), encoding="utf-8")

    links = []
    for l in r.links:
        d = l.to_json()
        d["tier"] = "linkage" if l.log10_lr >= thr else "lead"
        for side, pid in (("a", l.persona_a), ("b", l.persona_b)):
            p = personas_by_id.get(pid)
            d["handle_" + side] = p.handle if p else pid
            d["site_" + side] = p.site if p else ""
        links.append(d)
    (out / "links.json").write_text(
        _json({"threshold_log10_lr": thr,
               "lead_floor": r.report["settings"]["lead_floor_log10_lr"],
               "count": len(links), "links": links[:400]}), encoding="utf-8")

    nodes = [{
        "id": p.persona_id, "handle": p.handle, "site": p.site,
        "cluster": cluster_of.get(p.persona_id),
        "utc_offset": temporal.geolocation(p.persona_id)["offset"],
    } for p in r.corpus.personas]
    edges = [{
        "source": l.persona_a, "target": l.persona_b,
        "log10_lr": round(l.log10_lr, 2),
        "tier": "linkage" if l.log10_lr >= thr else "lead",
        "channels": l.channels,
    } for l in r.links]
    linked = {e["source"] for e in edges} | {e["target"] for e in edges}
    (out / "graph.json").write_text(
        _json({"nodes": [n for n in nodes if n["id"] in linked], "edges": edges}),
        encoding="utf-8")

    clusters = []
    dossiers = {d["cluster_id"]: d for d in r.dossiers}
    for c in r.clusters:
        if c["size"] < 2:
            continue
        d = dict(c)
        d["handles"] = [personas_by_id[p].handle for p in c["personas"]
                        if p in personas_by_id]
        d["dossier"] = dossiers.get(c["cluster_id"])
        clusters.append(d)
    (out / "clusters.json").write_text(_json(clusters), encoding="utf-8")

    return {"personas": len(r.corpus.personas), "links": len(r.links),
            "clusters": len(clusters)}


def export_live(out: Path, address: str, tor: str, seed: int, actors: int) -> dict:
    """Crawl the lab once and dump what the Live tab renders."""
    from anveshak import live as live_mod
    from anveshak import pipeline
    from anveshak.collect.crawler import TorCrawler
    from anveshak.osint import context as osint_context
    from anveshak.osint.pivot import NON_PIVOT_KINDS

    host, _, port = tor.partition(":")
    crawler = TorCrawler(host or "127.0.0.1", int(port or 9050), delay=0.4,
                         max_pages=90)
    ok, message = crawler.check_reachable()
    print("  tor: %s" % message)
    if not ok:
        return {"skipped": message}

    print("  crawling the lab ...")
    crawl = crawler.crawl(address, max_onions=3)
    if not crawl.personas:
        return {"skipped": "no accounts extracted"}

    bench = pipeline.run(seed=seed, n_actors=actors)
    thr = bench.report["settings"]["threshold_log10_lr"]
    floor = bench.report["settings"]["lead_floor_log10_lr"]
    result = live_mod.analyse(crawl, bench.model, thr, floor)

    truth = ROOT / "onionlab" / "ground_truth.json"
    graded = live_mod.score_against_truth(result, truth)
    osint_graded = live_mod.score_osint_against_truth(result, truth)

    by_id = {p.persona_id: p for p in result.personas}
    cluster_of = {p: c["cluster_id"] for c in result.clusters
                  for p in c["personas"]}
    short = lambda pid: pid.split(":", 1)[-1]

    links = []
    for l in result.links:
        d = l.to_json()
        d["tier"] = "linkage" if l.log10_lr >= thr else "lead"
        d["handle_a"], d["handle_b"] = short(l.persona_a), short(l.persona_b)
        d["site_a"] = by_id[l.persona_a].site if l.persona_a in by_id else ""
        d["site_b"] = by_id[l.persona_b].site if l.persona_b in by_id else ""
        d["cross_service"] = d["site_a"] != d["site_b"]
        links.append(d)

    ranked, seen = [], set()
    for m in sorted(result.mentions, key=lambda x: -x.priority):
        if m.key in seen or m.kind in NON_PIVOT_KINDS:
            continue
        seen.add(m.key)
        row = m.to_json()
        row["band"] = osint_context.band(m.priority)[0]
        ranked.append(row)

    developed = []
    for entry in result.osint.get("developed", {}).values():
        m = entry["mention"]
        if m.kind in NON_PIVOT_KINDS:
            continue
        developed.append({"identifier": m.value, "kind": m.kind,
                          "handle": m.handle, "priority": round(m.priority, 3),
                          "leads": [l.to_json() for l in entry["leads"]]})
    developed.sort(key=lambda d: -d["priority"])

    exposure = [{
        "cluster_id": e["cluster_id"],
        "personas": [short(p) for p in e["personas"]],
        "leaking_personas": [short(p) for p in e["leaking_personas"]],
        "exposed_by_association": [short(p) for p in e["exposed_by_association"]],
        "identifiers": sorted({m.value for m in e["leaks"]
                               if m.kind not in NON_PIVOT_KINDS}),
        "top_priority": round(e["top_priority"], 3),
    } for e in sorted(result.exposure.values(), key=lambda e: -e["top_priority"])]

    payload = {
        "available": True, "onion": result.onion, "crawl": result.crawl,
        "settings": result.settings, "fingerprints": result.fingerprints,
        "accounts": [{
            "persona_id": p.persona_id, "handle": p.handle, "site": p.site,
            "onion": (p.onion_services or [""])[0],
            "cluster": cluster_of.get(p.persona_id),
            "pgp": (p.pgp_fingerprint or "")[:16],
            "wallets": len(p.btc_addresses),
            "first_seen": p.first_seen.isoformat()[:10],
            "last_seen": p.last_seen.isoformat()[:10],
        } for p in result.personas],
        "links": links,
        "clusters": [c for c in result.clusters if c["size"] > 1],
        "mentions": ranked, "developed": developed, "exposure": exposure,
        "graded": graded, "osint_graded": osint_graded,
    }
    (out / "live.json").write_text(_json(payload), encoding="utf-8")
    return {"accounts": len(result.personas), "mentions": len(ranked),
            "graded": bool(graded.get("available"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="public")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--actors", type=int, default=150)
    ap.add_argument("--tor", default="127.0.0.1:9050")
    ap.add_argument("--live-address", default="")
    ap.add_argument("--skip-live", action="store_true")
    a = ap.parse_args()

    out = ROOT / a.out
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)

    print("exporting static build to %s" % out)

    # the page itself
    web = ROOT / "anekanta" / "web"
    for name in ("index.html", "app.js", "style.css"):
        shutil.copy2(web / name, out / name)

    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    summary["benchmark"] = export_benchmark(data, a.seed, a.actors)

    address = a.live_address
    if not address and not a.skip_live:
        try:
            address = subprocess.run(
                ["docker", "exec", "onionlab-tor", "cat",
                 "/srv/onion-addresses/market"],
                capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            address = ""
    if address and not a.skip_live:
        try:
            summary["live"] = export_live(data, address, a.tor, a.seed, a.actors)
        except Exception as exc:
            summary["live"] = {"skipped": "%s: %s" % (type(exc).__name__, exc)}
    else:
        summary["live"] = {"skipped": "no lab address available"}

    rw = ROOT / "realworld-report.json"
    if rw.exists():
        shutil.copy2(rw, data / "realworld.json")
        summary["realworld"] = json.loads(rw.read_text(encoding="utf-8")).get(
            "crawl", {})
    else:
        summary["realworld"] = {"skipped": "no realworld-report.json"}

    (data / "manifest.json").write_text(_json(summary), encoding="utf-8")

    print("\nexported:")
    for f in sorted(data.glob("*.json")):
        print("  %-20s %8.1f KB" % (f.name, f.stat().st_size / 1024))
    print("\n%s" % _json(summary)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
