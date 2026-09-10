"""Live analysis of a crawled hidden service.

Runs the full attribution pipeline against a real onion service instead of the
generated benchmark. The engines, fusion, resolution and reporting are the same
objects used in `pipeline.run`; only the source of the personas changes.

Two things have to come from different places, and getting this split right is
the whole design:

  rarity statistics -> the LIVE population
      "How unusual is this favicon?" is a question about the population you are
      actually looking at. A stock icon on half of one market is uninformative
      there regardless of how rare it was in the benchmark. So the engines are
      re-fit on the crawled corpus.

  likelihood ratios -> the BENCHMARK
      Converting a score into an LR needs labelled pairs, and live data has
      none. The calibration is therefore transferred from the benchmark, which
      is exactly the reference-population assumption printed on every report:
      the numbers are valid to the extent the benchmark resembles the target.
      Stating that plainly is better than pretending a number is unconditional.

The honest status of a live LR is "calibrated against a simulated population of
similar shape". Before this were used operationally, the calibration would need
refitting on labelled pairs from the real target population -- which is a data
collection problem, not a modelling one, and no amount of extra machinery here
would substitute for it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .engines.base import CorpusView
from .fusion import graph
from .osint import mentions as osint_mentions
from .osint import pivot as osint_pivot
from .pipeline import CHANNELS, DEFAULT_PRIOR_ODDS, _build_engines
from .schema import Evidence, LinkHypothesis, posterior_from_log10_lr


@dataclass
class LiveResult:
    onion: str
    personas: list
    posts: list
    links: list
    clusters: list
    dossiers: list
    fingerprint: dict = field(default_factory=dict)
    fingerprints: dict = field(default_factory=dict)
    crawl: dict = field(default_factory=dict)
    evaluation: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    # Dark2Clear stage
    mentions: list = field(default_factory=list)
    osint: dict = field(default_factory=dict)
    exposure: dict = field(default_factory=dict)


def analyse(crawl_result, model, threshold: float, lead_floor: float,
            prior_odds: float = DEFAULT_PRIOR_ODDS) -> LiveResult:
    """Score a crawl with a calibration transferred from the benchmark."""
    personas = crawl_result.personas
    posts_by_persona: dict = {}
    for p in crawl_result.posts:
        posts_by_persona.setdefault(p.persona_id, []).append(p)

    view = CorpusView(personas=personas, posts_by_persona=posts_by_persona,
                      transactions=[])
    engines = _build_engines()
    for e in engines.values():
        e.fit(view)

    ids = [p.persona_id for p in personas]
    links: list = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            raw = {}
            detail = {}
            for name, eng in engines.items():
                rs = eng.score(a, b)
                raw[name] = rs.score
                detail[name] = rs
            fused = model.fused(raw)
            if fused < lead_floor:
                continue
            llrs = model.channel_llrs(raw)
            ev = []
            for c in CHANNELS:
                rs = detail.get(c)
                if rs is None:
                    continue
                if abs(llrs.get(c, 0.0)) < 0.3 and rs.score <= 0:
                    continue
                ev.append(Evidence(channel=c, persona_a=a, persona_b=b,
                                   score=round(rs.score, 4),
                                   log10_lr=llrs.get(c, 0.0),
                                   rationale=rs.rationale,
                                   supporting=rs.supporting))
            ev.sort(key=lambda e: -e.log10_lr)
            links.append(LinkHypothesis(
                persona_a=a, persona_b=b, log10_lr=float(fused),
                posterior=posterior_from_log10_lr(float(fused), prior_odds),
                evidence=ev))
    links.sort(key=lambda l: -l.log10_lr)

    clusters = graph.resolve(links, ids, threshold=threshold)
    pbid = {p.persona_id: p for p in personas}
    dossiers = [graph.build_dossier(c, pbid, engines["temporal"])
                for c in clusters if c["size"] > 1]

    # ---- Dark2Clear: develop the harvested clear-web mentions -------------
    # Deliberately after resolution, not before. A leak found on one account
    # becomes a lead against every account in that account's cluster, which is
    # the composition the paper cannot perform on its own: it harvests from
    # pages, and this attributes the harvest to an operator.
    cluster_of = graph.cluster_truth_map(clusters)
    mentions = list(getattr(crawl_result, "mentions", []))
    developed = osint_pivot.develop_all(mentions, personas, cluster_of,
                                        min_priority=0.5)
    exposure = osint_pivot.actor_exposure(mentions, personas, cluster_of,
                                          min_priority=0.5)

    return LiveResult(
        onion=crawl_result.onion,
        personas=personas, posts=crawl_result.posts,
        links=links, clusters=clusters, dossiers=dossiers,
        fingerprint=crawl_result.fingerprint.to_json(),
        fingerprints={k: v.to_json()
                      for k, v in getattr(crawl_result, "fingerprints", {}).items()},
        mentions=mentions,
        osint={"developed": developed,
               "groups": osint_mentions.collapse(mentions)},
        exposure=exposure,
        crawl=crawl_result.summary(),
        settings={"threshold_log10_lr": threshold, "lead_floor": lead_floor,
                  "prior_odds": prior_odds,
                  "calibration": "transferred from the synthetic benchmark; "
                                 "see reference-population caveat"},
    )


def score_against_truth(result: LiveResult, truth_path: str | Path) -> dict:
    """Score a live run against the lab's held-out operator map.

    Only meaningful for ONIONLAB, where the operator behind each vendor account
    is known because we generated it. The crawler never sees this file; it is
    read here purely to grade what the crawler produced. Against a genuine
    third-party service no such file exists, and the correct output is a set of
    hypotheses with no accuracy figure attached.
    """
    path = Path(truth_path)
    if not path.exists():
        return {"available": False, "reason": "no ground-truth file"}
    truth = json.loads(path.read_text(encoding="utf-8"))
    operator = truth.get("operators", {})

    def op_of(pid: str):
        return operator.get(pid.split(":", 1)[-1])

    ids = [p.persona_id for p in result.personas]
    known = [i for i in ids if op_of(i)]
    if len(known) < 3:
        return {"available": False, "reason": "handles did not match the map"}

    pairs, y = [], []
    for i in range(len(known)):
        for j in range(i + 1, len(known)):
            pairs.append((known[i], known[j]))
            y.append(1 if op_of(known[i]) == op_of(known[j]) else 0)
    y = np.array(y)

    scored = {(l.persona_a, l.persona_b): l.log10_lr for l in result.links}
    lr = np.array([scored.get(p, scored.get((p[1], p[0]), -1.0)) for p in pairs])

    thr = result.settings["threshold_log10_lr"]
    pred = lr >= thr
    tp = int(np.sum(pred & (y == 1)))
    fp = int(np.sum(pred & (y == 0)))
    fn = int(np.sum(~pred & (y == 1)))

    predicted = graph.cluster_truth_map(result.clusters)
    from .evaluation import metrics
    bc = metrics.bcubed({k: v for k, v in predicted.items() if op_of(k)},
                        {i: op_of(i) for i in known})

    return {
        "available": True,
        "personas_matched": len(known),
        "pairs_scored": len(pairs),
        "true_pairs": int(y.sum()),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
        "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
        "roc_auc": round(float(metrics.discrimination(y, lr)["roc_auc"]), 4)
        if 0 < y.sum() < len(y) else None,
        "bcubed_f1": bc["bcubed_f1"],
        "note": ("ground truth is the lab's own operator map; the crawler never "
                 "saw it. Calibration was transferred from the benchmark."),
    }


def score_osint_against_truth(result: "LiveResult", truth_path) -> dict:
    """Grade the clear-web harvest against the lab's planted leaks.

    Three things are measured, because the paper's pipeline can fail in three
    different ways and only the first is usually reported:

      recall      did the harvest find the planted identifiers at all
      ranking     did context setting put the real leaks above the decoys --
                  the step Wangchuk & Rathod performed by hand, and the one
                  that decides whether the output is usable
      correlation did the pivot connect a leak back to the account that
                  published it, and onward to that operator's other accounts
    """
    from pathlib import Path
    path = Path(truth_path)
    if not path.exists():
        return {"available": False, "reason": "no ground-truth file"}
    truth = json.loads(path.read_text(encoding="utf-8"))
    # Keys beginning with an underscore are documentation inside the map, not
    # data. Counting them as planted leaks understates recall and invents a
    # missed finding that never existed.
    planted = {k: v for k, v in truth.get("clear_web_leaks", {}).items()
               if not k.startswith("_")}
    decoys = {k: v for k, v in truth.get("decoys", {}).items()
              if not k.startswith("_")}
    if not planted:
        return {"available": False, "reason": "no planted leaks in the map"}

    found = {}
    for m in result.mentions:
        key = m.value.lower()
        if key not in found or m.priority > found[key].priority:
            found[key] = m

    recovered, missed = [], []
    for value, meta in planted.items():
        m = found.get(value.lower())
        if m is None:
            missed.append(value)
            continue
        recovered.append({
            "value": value,
            "kind": m.kind,
            "leaked_by": meta.get("leaked_by"),
            "attributed_to": m.handle or None,
            "attribution_correct": (m.handle or "") == meta.get("leaked_by"),
            "priority": round(m.priority, 3),
            "category": m.category,
            "expected_band": meta.get("should_rank"),
        })

    decoy_scores = [found[d.lower()].priority for d in decoys
                    if d.lower() in found]
    real_scores = [r["priority"] for r in recovered]

    # The separation test. Every real leak should outrank every decoy; the
    # margin between the worst real leak and the best decoy is the headroom.
    separated = bool(real_scores and decoy_scores
                     and min(real_scores) > max(decoy_scores))

    correlated = 0
    for entry in result.osint.get("developed", {}).values():
        if any(l.method == "identity correlation" for l in entry["leads"]):
            correlated += 1

    widened = sum(len(e["exposed_by_association"])
                  for e in result.exposure.values())

    return {
        "available": True,
        "planted": len(planted),
        "recovered": len(recovered),
        "recall": round(len(recovered) / max(1, len(planted)), 4),
        "missed": missed,
        "attribution_correct": sum(1 for r in recovered
                                   if r["attribution_correct"]),
        "decoys_present": len(decoys),
        "decoys_collected": len(decoy_scores),
        "worst_real_leak_priority": round(min(real_scores), 3) if real_scores else None,
        "best_decoy_priority": round(max(decoy_scores), 3) if decoy_scores else None,
        "ranking_separates_leaks_from_decoys": separated,
        "identifiers_with_identity_correlation": correlated,
        "accounts_exposed_by_association": widened,
        "note": ("recall is over deliberately planted identifiers; ranking is "
                 "the context-setting step the paper performs manually"),
    }
