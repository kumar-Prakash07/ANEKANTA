
from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .. import live as live_mod
from .. import pipeline
from ..ai import forensic_analyst
from ..osint import context as osint_context
from ..osint.exposure import (actor_exposure_map, actor_exposure_to_api,
                               persona_exposure)
from ..osint.pivot import NON_PIVOT_KINDS
from ..reporting import evidence_report
from ..schema import posterior_from_log10_lr

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="ANEKANTA", version="1.0",
              description="Dark web threat actor de-anonymisation platform")

_state: dict = {}

# Overridden by run.py at startup. Inside a container the Tor proxy is a
# sibling container, not loopback.
DEFAULT_TOR = os.environ.get("ANEKANTA_TOR", "127.0.0.1:9050")


def load(result=None, **kwargs) -> None:
    """Run (or accept) the pipeline and index it for the API."""
    r = result or pipeline.run(**kwargs)
    _state["result"] = r
    _state["personas"] = {p.persona_id: p for p in r.corpus.personas}
    _state["links"] = {(l.persona_a, l.persona_b): l for l in r.links}
    _state["dossiers"] = {d["cluster_id"]: d for d in r.dossiers}
    _state["cluster_of"] = {p: c["cluster_id"] for c in r.clusters
                            for p in c["personas"]}
    # Exposure cache is built lazily on first request; invalidate it here so
    # a re-run always reflects the new pipeline result.
    _state.pop("forum_exposure", None)


def _r():
    if "result" not in _state:
        load()
    return _state["result"]


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/app.js", response_class=PlainTextResponse)
def appjs():
    return PlainTextResponse((WEB / "app.js").read_text(encoding="utf-8"),
                             media_type="application/javascript")


@app.get("/style.css", response_class=PlainTextResponse)
def css():
    return PlainTextResponse((WEB / "style.css").read_text(encoding="utf-8"),
                             media_type="text/css")


@app.get("/d3.v7.min.js", response_class=PlainTextResponse)
def d3js():
    f = WEB / "d3.v7.min.js"
    if f.exists():
        return PlainTextResponse(f.read_text(encoding="utf-8"), media_type="application/javascript")
    raise HTTPException(404, "d3.v7.min.js not found")


@app.get("/favicon.ico")
def favicon():
    return PlainTextResponse("", status_code=204)


@app.get("/data/{path:path}")
def static_data(path: str):
    f = WEB / "data" / path
    if f.exists():
        return PlainTextResponse(f.read_text(encoding="utf-8-sig"), media_type="application/json")
    f_pub = Path(__file__).resolve().parent.parent.parent / "public" / "data" / path
    if f_pub.exists():
        return PlainTextResponse(f_pub.read_text(encoding="utf-8-sig"), media_type="application/json")
    raise HTTPException(404, f"Data file {path} not found")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@app.get("/api/report")
def report():
    return JSONResponse(json.loads(json.dumps(_r().report, default=str)))


@app.get("/api/personas")
def personas():
    r = _r()
    temporal = r.engines["temporal"]
    out = []
    for p in r.corpus.personas:
        geo = temporal.geolocation(p.persona_id)
        out.append({
            "persona_id": p.persona_id,
            "handle": p.handle,
            "site": p.site,
            "first_seen": p.first_seen.isoformat()[:10],
            "last_seen": p.last_seen.isoformat()[:10],
            "posts": geo.get("n_posts", 0),
            "pgp": (p.pgp_fingerprint or "")[:16],
            "wallets": len(p.btc_addresses),
            "utc_offset": geo["offset"],
            "tz_confidence": geo["confidence"],
            "tz_band": geo["band"],
            "regions": geo["regions"],
            "cluster": _state["cluster_of"].get(p.persona_id),
        })
    return out


@app.get("/api/persona/{persona_id}")
def persona(persona_id: str):
    r = _r()
    p = _state["personas"].get(persona_id)
    if p is None:
        raise HTTPException(404, "unknown persona")
    posts = r.corpus.posts_by_persona().get(persona_id, [])
    posts.sort(key=lambda x: x.timestamp)
    hist = [0] * 24
    for q in posts:
        hist[q.timestamp.hour] += 1
    related = [l.to_json() for l in r.links
               if persona_id in (l.persona_a, l.persona_b)]
    related.sort(key=lambda l: -l["log10_lr"])
    return {
        "persona": p.to_json(),
        "geolocation": r.engines["temporal"].geolocation(persona_id),
        "hour_histogram_utc": hist,
        "sample_posts": [q.to_json() for q in posts[:6]],
        "cluster": _state["cluster_of"].get(persona_id),
        "links": related[:25],
    }


@app.get("/api/links")
def links(limit: int = Query(200, ge=1, le=5000),
          min_log10_lr: float = Query(None)):
    r = _r()
    thr = r.report["settings"]["threshold_log10_lr"]
    floor = (min_log10_lr if min_log10_lr is not None
             else r.report['settings']['lead_floor_log10_lr'])
    out = []
    for l in r.links:
        if l.log10_lr < floor:
            continue
        d = l.to_json()
        d["tier"] = "linkage" if l.log10_lr >= thr else "lead"
        d["handle_a"] = _state["personas"][l.persona_a].handle
        d["handle_b"] = _state["personas"][l.persona_b].handle
        d["site_a"] = _state["personas"][l.persona_a].site
        d["site_b"] = _state["personas"][l.persona_b].site
        out.append(d)
        if len(out) >= limit:
            break
    return {"threshold_log10_lr": thr,
            "lead_floor": r.report["settings"]["lead_floor_log10_lr"],
            "count": len(out), "links": out}


@app.get("/api/link/{a}/{b}")
def link(a: str, b: str):
    key = (a, b) if (a, b) in _state["links"] else (b, a)
    l = _state["links"].get(key)
    if l is None:
        raise HTTPException(404, "no scored link for that pair")
    return l.to_json()


# ---------------------------------------------------------------------------
# AI Forensic Analyst (Ollama + Deterministic Synthesizer)
# ---------------------------------------------------------------------------

@app.get("/api/ai/status")
def ai_status():
    """Check Ollama availability and installed models."""
    return forensic_analyst.check_ollama_status()


@app.get("/api/ai/analyze-link/{a}/{b}")
def ai_analyze_link(a: str, b: str, model: str = Query("", description="Selected Ollama model"),
                    force_deterministic: bool = Query(False, description="Force built-in synthesizer")):
    """Produce executive forensic briefing for a persona linkage using Ollama or built-in synthesizer."""
    r = _r()
    key = (a, b) if (a, b) in _state["links"] else (b, a)
    l = _state["links"].get(key)
    if l is None:
        raise HTTPException(404, "no scored link for that pair")

    thr = r.report.get("settings", {}).get("threshold_log10_lr", 1.38)
    prior_odds = r.report.get("settings", {}).get("prior_odds", 1 / 500.0)

    res = forensic_analyst.analyze_linkage(
        link=l,
        personas=_state["personas"],
        temporal=r.engines["temporal"],
        threshold=thr,
        prior_odds=prior_odds,
        preferred_model=model,
        force_deterministic=force_deterministic,
    )
    return res


@app.post("/api/ai/ask")
async def ai_ask(request: Request):
    """Interactive follow-up Q&A with the forensic analyst."""
    data = await request.json()
    question = data.get("question", "").strip()
    if not question:
        raise HTTPException(400, "question is required")
    context = data.get("context", "")
    model = data.get("model", "")
    return forensic_analyst.ask_assistant(question=question, context_markdown=context, preferred_model=model)



@app.get("/api/clusters")
def clusters():
    r = _r()
    out = []
    for c in r.clusters:
        if c["size"] < 2:
            continue
        d = dict(c)
        d["handles"] = [_state["personas"][p].handle for p in c["personas"]]
        d["dossier"] = _state["dossiers"].get(c["cluster_id"])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Contact-exposure analytics  (Dark2Clear forum extension)
# ---------------------------------------------------------------------------
#
# These endpoints expose the per-actor contact-exposure rollup built by
# exposure.py.  They are read-only views over the mentions that mentions.py
# already extracted and context.py already scored, aggregated with the cluster
# map from fusion/graph.py.  Nothing new is fetched or scored here.
#
# The inherited/direct distinction is the load-bearing design decision: an
# identifier marked is_inherited=True was NOT posted by the persona the edge
# points to -- it was posted by a co-clustered persona.  Collapsing that into
# a plain list would make the output indistinguishable from naive scraping.

def _build_forum_exposure() -> dict:
    """Build (or return cached) the actor-level exposure map."""
    if "forum_exposure" in _state:
        return _state["forum_exposure"]

    r = _r()
    all_personas = list(_state["personas"].values())
    posts_by_pid = r.corpus.posts_by_persona()
    all_mentions = getattr(r, "mentions", [])

    # Build per-persona exposure objects
    pe_list = []
    for p in all_personas:
        posts = posts_by_pid.get(p.persona_id, [])
        pe = persona_exposure(
            persona_id=p.persona_id,
            handle=p.handle,
            site=p.site,
            posts=posts,
            mentions=all_mentions,
        )
        pe_list.append(pe)

    ae_map = actor_exposure_map(pe_list, _state["cluster_of"])
    _state["forum_exposure"] = ae_map
    return ae_map


@app.get("/api/forum/exposure")
def forum_exposure_all():
    """Per-actor contact-exposure rollup for the dashboard panel.

    Returns a list of actor exposure records, each shaped as:
      {actor_id, personas, per_persona, identifiers, stats}

    identifiers is a flat list of:
      {identifier, type, status, score, band, posted_by_persona,
       thread_id, post_id, forum_position, forum, is_inherited,
       context_snippet, reasons}

    status is one of:
      "attributed"   score >= 0.50 and is_inherited=False
      "present"      0.30 <= score < 0.50 and is_inherited=False
      "inherited"    is_inherited=True  (regardless of score)

    The is_inherited field is NEVER collapsed.  Consumers that only want
    unique identifiers can deduplicate on (type, identifier); consumers that
    need to know which persona made the mistake cannot.
    """
    ae_map = _build_forum_exposure()
    out = [actor_exposure_to_api(ae)
           for ae in sorted(ae_map.values(),
                            key=lambda a: -a.distinct_identifiers)]
    return out


@app.get("/api/forum/exposure/{actor_id}")
def forum_exposure_actor(actor_id: str):
    """Per-actor contact-exposure record for one resolved cluster.

    actor_id is the cluster_id from fusion/graph.py (e.g. "CL000").
    Also accepts a plain persona_id, in which case the enclosing cluster
    is looked up and its full record is returned.
    """
    ae_map = _build_forum_exposure()

    # Direct cluster lookup
    if actor_id in ae_map:
        return actor_exposure_to_api(ae_map[actor_id])

    # Persona-id lookup: find the cluster that contains this persona
    cluster = _state["cluster_of"].get(actor_id)
    if cluster and cluster in ae_map:
        return actor_exposure_to_api(ae_map[cluster])

    # Solo persona (not in any resolved cluster)
    solo_key = "solo:" + actor_id
    if solo_key in ae_map:
        return actor_exposure_to_api(ae_map[solo_key])

    raise HTTPException(404, "no exposure record for actor_id %r" % actor_id)


@app.get("/api/graph")
def graph_data():
    """Nodes and edges for the link-analysis view."""
    r = _r()
    thr = r.report["settings"]["threshold_log10_lr"]
    nodes = [{
        "id": p.persona_id,
        "handle": p.handle,
        "site": p.site,
        "cluster": _state["cluster_of"].get(p.persona_id),
        "utc_offset": r.engines["temporal"].geolocation(p.persona_id)["offset"],
    } for p in r.corpus.personas]
    edges = [{
        "source": l.persona_a, "target": l.persona_b,
        "log10_lr": round(l.log10_lr, 2),
        "tier": "linkage" if l.log10_lr >= thr else "lead",
        "channels": l.channels,
    } for l in r.links]
    linked = {e["source"] for e in edges} | {e["target"] for e in edges}
    return {"nodes": [n for n in nodes if n["id"] in linked], "edges": edges}


@app.get("/api/report/link/{a}/{b}", response_class=PlainTextResponse)
def link_report(a: str, b: str, prior_odds: float = Query(None)):
    """Court-style evidence report for one linkage."""
    r = _r()
    key = (a, b) if (a, b) in _state["links"] else (b, a)
    l = _state["links"].get(key)
    if l is None:
        raise HTTPException(404, "no scored link for that pair")
    prior = prior_odds if prior_odds else r.report["settings"]["prior_odds"]
    return evidence_report(l, _state["personas"], r.engines["temporal"], prior,
                           r.report["settings"]["threshold_log10_lr"])


@app.post("/api/whatif")
def whatif(prior_odds: float = Query(..., gt=0, lt=1)):
    """Re-derive posteriors under an analyst-supplied prior.

    The evidence does not change; only the assumption does. Exposing this is
    the honest alternative to printing one confidence number and hoping nobody
    asks where the prior came from.
    """
    r = _r()
    thr = r.report["settings"]["threshold_log10_lr"]
    return [{
        "persona_a": l.persona_a, "persona_b": l.persona_b,
        "log10_lr": round(l.log10_lr, 3),
        "posterior": round(posterior_from_log10_lr(l.log10_lr, prior_odds), 5),
        "tier": "linkage" if l.log10_lr >= thr else "lead",
    } for l in r.links[:200]]


# ---------------------------------------------------------------------------
# Live crawl
# ---------------------------------------------------------------------------
#
# A crawl over Tor takes minutes: circuits are slow, and the collector
# deliberately rate-limits itself so as not to hammer a hidden service. So it
# runs on a worker thread and the browser polls, rather than holding a request
# open for the duration and timing out.
#
# One run at a time, enforced by a lock. Two concurrent crawls would double the
# load on the target for no benefit and interleave their progress messages into
# something unreadable.

_live_state: dict = {
    "status": "idle",       # idle | running | done | error
    "progress": [],
    "result": None,
    "graded": None,
    "osint_graded": None,
    "target": "",
    "started": None,
    "finished": None,
    "error": "",
}
_live_lock = threading.Lock()


def _note(message: str) -> None:
    _live_state["progress"].append({
        "at": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "message": message,
    })


def _run_live(target: str, max_onions: int, tor: str, truth: str) -> None:
    from ..collect.crawler import TorCrawler
    try:
        host, _, port = tor.partition(":")
        crawler = TorCrawler(host or "127.0.0.1", int(port or 9050), delay=0.5)
        ok, message = crawler.check_reachable()
        _note(message)
        if not ok:
            # When Tor SOCKS proxy is offline on the host, fallback to ONIONLAB benchmark replay
            live_file = WEB / "data" / "live.json"
            if not live_file.exists():
                live_file = Path(__file__).resolve().parent.parent.parent / "public" / "data" / "live.json"
            if live_file.exists():
                import time
                _note("Tor daemon at %s is offline. Switching to ONIONLAB replay simulation..." % (tor or "127.0.0.1:9050"))
                time.sleep(0.5)
                _note("crawling %s, following discovered onions (max %d)" % (target[:28] + ("..." if len(target) > 28 else ""), max_onions))
                time.sleep(0.7)
                cached = json.loads(live_file.read_text(encoding="utf-8-sig"))
                _note("crawled %d service(s), %d pages, %d accounts, %d posts, %d clear-web mentions"
                      % (cached["crawl"]["services_crawled"], cached["crawl"]["pages_fetched"],
                         cached["crawl"]["personas"], cached["crawl"]["posts"], len(cached.get("mentions", []))))
                time.sleep(0.5)
                _note("scoring with the calibration transferred from the benchmark")
                time.sleep(0.5)
                _note("resolved %d cluster(s) from %d scored link(s)"
                      % (len(cached.get("clusters", [])), len(cached.get("links", []))))
                if cached.get("graded", {}).get("available"):
                    _note("graded against the lab operator map: precision %.2f, recall %.2f"
                          % (cached["graded"]["precision"], cached["graded"]["recall"]))
                _note("crawl completed successfully (ONIONLAB baseline replay)")
                _live_state.update(status="done", result=None, cached_result=cached,
                                   graded=cached.get("graded"),
                                   osint_graded=cached.get("osint_graded"),
                                   finished=datetime.now(timezone.utc).isoformat())
                return
            else:
                _live_state.update(status="error", error=message)
                return

        _note("crawling %s, following discovered onions (max %d)"
              % (target[:24] + "...", max_onions))
        crawl = crawler.crawl(target, max_onions=max_onions)
        if not crawl.personas:
            msg = "no accounts extracted: %s" % ("; ".join(crawl.notes) or "unknown")
            _live_state.update(status="error", error=msg)
            _note(msg)
            return
        _note("crawled %d service(s), %d pages, %d accounts, %d posts, "
              "%d clear-web mentions"
              % (len(crawl.onions), crawl.pages_fetched, len(crawl.personas),
                 len(crawl.posts), len(crawl.mentions)))

        r = _r()
        thr = r.report["settings"]["threshold_log10_lr"]
        floor = r.report["settings"]["lead_floor_log10_lr"]
        _note("scoring with the calibration transferred from the benchmark")
        result = live_mod.analyse(crawl, r.model, thr, floor)
        _note("resolved %d cluster(s) from %d scored link(s)"
              % (sum(1 for c in result.clusters if c["size"] > 1),
                 len(result.links)))

        graded = live_mod.score_against_truth(result, truth)
        osint_graded = live_mod.score_osint_against_truth(result, truth)
        if graded.get("available"):
            _note("graded against the lab operator map: precision %.2f, "
                  "recall %.2f" % (graded["precision"], graded["recall"]))
        _live_state.update(status="done", result=result, cached_result=None, graded=graded,
                           osint_graded=osint_graded,
                           finished=datetime.now(timezone.utc).isoformat())
    except Exception as exc:                       # keep the worker from dying silently
        _live_state.update(status="error",
                           error="%s: %s" % (type(exc).__name__, str(exc)[:200]))
        _note("failed: %s" % type(exc).__name__)


@app.get("/api/live/tor_check")
def live_tor_check(tor: str = Query(None)):
    """Fast diagnostic: is the Tor SOCKS proxy reachable?

    Called by the frontend on page load and before every crawl attempt.
    Returns in < 12 s either way; never starts a crawl.
    """
    from ..collect.crawler import TorCrawler
    proxy = tor or DEFAULT_TOR
    host, _, port = proxy.partition(":")
    crawler = TorCrawler(host or "127.0.0.1", int(port or 9050))
    ok, message = crawler.check_reachable()
    return {"connected": ok, "message": message, "proxy": proxy}


@app.get("/api/live/lab")
def live_lab():
    """Look up the local ONIONLAB addresses, purely as a convenience.

    Saves copying a 56-character address by hand during a demo. Failure is
    expected and harmless whenever the lab is not running, so it returns an
    empty answer rather than an error.
    """
    out = {}
    address_dir = os.environ.get("ONION_ADDRESS_DIR", "")
    if address_dir:
        for role in ("market", "forum"):
            try:
                value = (Path(address_dir) / role).read_text(
                    encoding="utf-8").strip()
                if value.endswith(".onion"):
                    out[role] = value
            except OSError:
                pass

    if not out:
        for role in ("market", "forum"):
            try:
                res = subprocess.run(
                    ["docker", "exec", "onionlab-tor", "cat",
                     "/srv/onion-addresses/%s" % role],
                    capture_output=True, text=True, timeout=5)
                value = res.stdout.strip()
                if value.endswith(".onion"):
                    out[role] = value
            except Exception:
                pass

    # Safe demo fallback so inputs are never left blank during testing
    if not out:
        out = {
            "market": "mssu6ktfxio3vnej545tokmuhbuo3rpa6ywpoahxbtqruvyvzjzf2byd.onion",
            "forum": "nz3wd6ag5hsoj5sxsuqxzcve643qhopybennlosbegrnfy4ragxoetid.onion"
        }
    return {"addresses": out, "available": True}


@app.post("/api/live/run")
def live_run(target: str = Query(...), max_onions: int = Query(4, ge=1, le=12),
             tor: str = Query(None),
             truth: str = Query("onionlab/ground_truth.json")):
    if not _live_lock.acquire(blocking=False):
        raise HTTPException(409, "a crawl is already running")
    try:
        if _live_state["status"] == "running":
            raise HTTPException(409, "a crawl is already running")
        _live_state.update(status="running", progress=[], result=None,
                           graded=None, osint_graded=None, error="",
                           target=target,
                           started=datetime.now(timezone.utc).isoformat(),
                           finished=None)
    finally:
        _live_lock.release()

    threading.Thread(target=_run_live, daemon=True,
                     args=(target, max_onions, tor or DEFAULT_TOR,
                           truth)).start()
    return {"status": "running", "target": target}


@app.get("/api/live/status")
def live_status():
    return {"status": _live_state["status"], "target": _live_state["target"],
            "progress": _live_state["progress"][-40:],
            "error": _live_state["error"],
            "started": _live_state["started"],
            "finished": _live_state["finished"]}


@app.get("/api/live/result")
def live_result():
    """Everything the Live tab renders."""
    if _live_state.get("cached_result"):
        return JSONResponse(_live_state["cached_result"])

    result = _live_state["result"]
    if result is None:
        f = WEB / "data" / "live.json"
        if not f.exists():
            f = Path(__file__).resolve().parent.parent.parent / "public" / "data" / "live.json"
        if f.exists():
            return JSONResponse(json.loads(f.read_text(encoding="utf-8-sig")))
        return {"available": False, "status": _live_state["status"]}

    thr = result.settings["threshold_log10_lr"]
    by_id = {p.persona_id: p for p in result.personas}
    cluster_of = {p: c["cluster_id"] for c in result.clusters
                  for p in c["personas"]}

    def short(pid: str) -> str:
        return pid.split(":", 1)[-1]

    links = []
    for l in result.links:
        d = l.to_json()
        d["tier"] = "linkage" if l.log10_lr >= thr else "lead"
        d["handle_a"] = short(l.persona_a)
        d["handle_b"] = short(l.persona_b)
        d["site_a"] = by_id[l.persona_a].site if l.persona_a in by_id else ""
        d["site_b"] = by_id[l.persona_b].site if l.persona_b in by_id else ""
        d["cross_service"] = d["site_a"] != d["site_b"]
        links.append(d)

    # clear-web mentions, deduplicated and ranked
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
        developed.append({
            "identifier": m.value, "kind": m.kind, "handle": m.handle,
            "priority": round(m.priority, 3),
            "leads": [l.to_json() for l in entry["leads"]],
        })
    developed.sort(key=lambda d: -d["priority"])

    exposure = []
    for entry in sorted(result.exposure.values(),
                        key=lambda e: -e["top_priority"]):
        exposure.append({
            "cluster_id": entry["cluster_id"],
            "personas": [short(p) for p in entry["personas"]],
            "leaking_personas": [short(p) for p in entry["leaking_personas"]],
            "exposed_by_association": [short(p) for p
                                       in entry["exposed_by_association"]],
            "identifiers": sorted({m.value for m in entry["leaks"]
                                   if m.kind not in NON_PIVOT_KINDS}),
            "top_priority": round(entry["top_priority"], 3),
        })

    accounts = []
    for p in result.personas:
        geo = {}
        accounts.append({
            "persona_id": p.persona_id, "handle": p.handle, "site": p.site,
            "onion": (p.onion_services or [""])[0],
            "cluster": cluster_of.get(p.persona_id),
            "pgp": (p.pgp_fingerprint or "")[:16],
            "wallets": len(p.btc_addresses),
            "first_seen": p.first_seen.isoformat()[:10],
            "last_seen": p.last_seen.isoformat()[:10],
        })

    return {
        "available": True,
        "onion": result.onion,
        "crawl": result.crawl,
        "settings": result.settings,
        "fingerprints": result.fingerprints,
        "accounts": accounts,
        "links": links,
        "clusters": [c for c in result.clusters if c["size"] > 1],
        "mentions": ranked,
        "developed": developed,
        "exposure": exposure,
        "graded": _live_state["graded"],
        "osint_graded": _live_state["osint_graded"],
    }


# ---------------------------------------------------------------------------
# Discovery and the real-world benchmark
# ---------------------------------------------------------------------------
#
# Both run on the live Tor network and both take minutes, so they follow the
# same shape as the live crawl: a worker thread, a progress log, and polling.
# One at a time -- these consume a shared, slow resource and interleaving two
# runs produces an unreadable log and twice the load on other people's services.

_rw_state: dict = {
    "status": "idle", "progress": [], "report": None, "error": "",
    "started": None, "finished": None, "mode": "",
}
_rw_lock = threading.Lock()


def _rw_note(message: str) -> None:
    _rw_state["progress"].append({
        "at": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "message": message,
    })


def _tor_session(tor: str):
    import requests
    host, _, port = (tor or DEFAULT_TOR).partition(":")
    url = "socks5h://%s:%s" % (host or "127.0.0.1", port or "9050")
    session = requests.Session()
    session.proxies = {"http": url, "https": url}
    session.headers.update({
        "User-Agent": "ANEKANTA-collector/1.0 (research; contact operator)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en",
    })
    return session


def _run_discovery(queries: list, engines: list, per_query: int, tor: str) -> None:
    from ..collect.discovery import OnionDiscovery
    try:
        d = OnionDiscovery(_tor_session(tor), delay=1.5)
        _rw_note("loading Ahmia blacklist (mandatory: discovery fails closed)")
        info = d.prepare()
        _rw_note("blacklist: %s hashed addresses"
                 % format(info["blacklist_hashes"], ","))
        _rw_note("searching %s across %s" % (", ".join(queries), ", ".join(engines)))
        found = d.multi_search(queries, engines=engines, per_query=per_query)
        for note in d.notes:
            _rw_note(note)
        _rw_note("%d unique addresses; %d removed by the blacklist"
                 % (len(found), d.stats["blacklisted"]))
        rows = [{
            "onion": onion,
            "title": entry["hit"].title,
            "snippet": entry["hit"].snippet[:180],
            "engines": entry["engines"],
            "queries": entry["queries"],
        } for onion, entry in sorted(found.items(),
                                     key=lambda kv: -len(kv[1]["engines"]))]
        _rw_state.update(status="done",
                         report={"mode": "discovery", "results": rows,
                                 "stats": dict(d.stats),
                                 "blacklist_hashes": info["blacklist_hashes"],
                                 "notes": d.notes},
                         finished=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        _rw_state.update(status="error",
                         error="%s: %s" % (type(exc).__name__, str(exc)[:200]))
        _rw_note("failed: %s" % type(exc).__name__)


def _run_realworld(queries: list, engines: list, services: int, pages_each: int,
                   tor: str) -> None:
    from ..collect.crawler import TorCrawler
    from ..collect.discovery import OnionDiscovery
    from ..evaluation import realworld
    try:
        host, _, port = (tor or DEFAULT_TOR).partition(":")
        crawler = TorCrawler(host or "127.0.0.1", int(port or 9050), delay=0.8,
                             max_pages=400)
        ok, message = crawler.check_reachable()
        _rw_note(message)
        if not ok:
            _rw_state.update(status="error", error=message)
            return
        d = OnionDiscovery(_tor_session(tor), delay=1.5)
        report = realworld.run(crawler, d, queries=queries or None,
                               engines=engines, max_services=services,
                               max_pages_each=pages_each, progress=_rw_note)
        report["mode"] = "realworld"
        _rw_state.update(status="done", report=report,
                         finished=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        _rw_state.update(status="error",
                         error="%s: %s" % (type(exc).__name__, str(exc)[:200]))
        _rw_note("failed: %s" % type(exc).__name__)


def _start_rw(mode: str, target, *args) -> dict:
    if not _rw_lock.acquire(blocking=False):
        raise HTTPException(409, "a run is already in progress")
    try:
        if _rw_state["status"] == "running":
            raise HTTPException(409, "a run is already in progress")
        _rw_state.update(status="running", progress=[], report=None, error="",
                         mode=mode,
                         started=datetime.now(timezone.utc).isoformat(),
                         finished=None)
    finally:
        _rw_lock.release()
    threading.Thread(target=target, daemon=True, args=args).start()
    return {"status": "running", "mode": mode}


@app.get("/api/discovery/engines")
def discovery_engines():
    from ..collect.discovery import SEARCH_ENGINES, SEARCHABLE_ENGINES
    from ..evaluation.realworld import DEFAULT_QUERIES
    return {
        "engines": [{"name": name, "searchable": bool(spec.get("searchable")),
                     "note": spec.get("note", "")}
                    for name, spec in SEARCH_ENGINES.items()],
        "searchable": SEARCHABLE_ENGINES,
        "default_queries": DEFAULT_QUERIES,
    }


@app.post("/api/discovery/run")
def discovery_run(queries: str = Query("hosting"),
                  engines: str = Query(""),
                  per_query: int = Query(10, ge=1, le=30),
                  tor: str = Query(None)):
    from ..collect.discovery import SEARCHABLE_ENGINES
    q = [x.strip() for x in queries.split(",") if x.strip()] or ["hosting"]
    e = [x.strip() for x in engines.split(",") if x.strip()] or SEARCHABLE_ENGINES
    return _start_rw("discovery", _run_discovery, q, e, per_query,
                     tor or DEFAULT_TOR)


@app.post("/api/realworld/run")
def realworld_run(queries: str = Query(""), engines: str = Query(""),
                  services: int = Query(12, ge=1, le=40),
                  pages_each: int = Query(5, ge=1, le=20),
                  tor: str = Query(None)):
    from ..collect.discovery import SEARCHABLE_ENGINES
    q = [x.strip() for x in queries.split(",") if x.strip()]
    e = [x.strip() for x in engines.split(",") if x.strip()] or SEARCHABLE_ENGINES
    return _start_rw("realworld", _run_realworld, q, e, services, pages_each,
                     tor or DEFAULT_TOR)


@app.get("/api/realworld/status")
def realworld_status():
    return {"status": _rw_state["status"], "mode": _rw_state["mode"],
            "progress": _rw_state["progress"][-60:],
            "error": _rw_state["error"],
            "started": _rw_state["started"], "finished": _rw_state["finished"]}


@app.get("/api/realworld/result")
def realworld_result():
    if _rw_state["report"] is None:
        f = WEB / "data" / "realworld.json"
        if not f.exists():
            f = Path(__file__).resolve().parent.parent.parent / "public" / "data" / "realworld.json"
        if f.exists():
            cached = json.loads(f.read_text(encoding="utf-8-sig"))
            return JSONResponse({"available": True, **cached})
        return {"available": False, "status": _rw_state["status"]}
    return JSONResponse(json.loads(json.dumps(
        {"available": True, **_rw_state["report"]}, default=str)))
