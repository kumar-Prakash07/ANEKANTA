"""End-to-end orchestration.

    corpus -> engines -> blocking -> scoring -> calibration -> fusion
           -> pairwise links -> identity clusters -> actor dossiers

The one rule this module exists to enforce is that no label ever reaches a
component that will later be evaluated. Engines are fit unsupervised on the
whole corpus (feature extraction only, no labels exist for them to see);
calibration and fusion are fit on a disjoint set of *actors*, not a random
sample of pairs. Splitting on pairs would leak, because a persona in the
training half would also appear in test pairs and the model could learn that
specific persona rather than the general phenomenon.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from .corpus.generator import Corpus, generate
from .engines.base import CorpusView
from .engines.crypto import CryptoEngine
from .engines.handle import HandleEngine
from .engines.infra import DeviceEngine, InfraEngine
from .engines.neural import NeuralAuthorshipEngine
from .engines.service import FaviconEngine, TemplateEngine, TLSEngine
from .engines.pgp import PGPEngine
from .engines.stylometry import StylometryEngine, VerbatimEngine
from .engines.temporal import TemporalEngine
from .ai.tradecraft import (TradecraftClassifier, build_indexes,
                            persona_features)
from .evaluation import metrics
from .fusion import blocking, graph
from .fusion.lr import FusionModel
from .schema import Evidence, LinkHypothesis, posterior_from_log10_lr

CHANNELS = ["stylometry", "temporal", "crypto", "pgp", "handle", "infra",
            "device", "verbatim", "favicon", "tls", "template",
            "authorship"]

# The analyst's stated prior that two arbitrary personas are one actor. Made
# explicit because posterior probability is meaningless without it, and a
# report that hides its prior is not reviewable.
DEFAULT_PRIOR_ODDS = 1 / 500.0

# How far below the assertion threshold a pair may fall and still be emitted
# as a lead for manual review rather than discarded. This is where disciplined
# operators live: rankable, but not assertable at the precision a linkage claim
# demands.
#
# The depth is fitted on the training split rather than fixed, because any
# change to the engines shifts the whole LR scale and a constant would silently
# change meaning. The queue descends only as far as it stays this precise --
# below that it is burying leads rather than surfacing them.
MIN_LEAD_BAND_PRECISION = 0.20


@dataclass
class Result:
    corpus: Corpus
    engines: dict
    model: FusionModel
    links: list[LinkHypothesis]
    clusters: list[dict]
    dossiers: list[dict]
    report: dict = field(default_factory=dict)
    scores_by_pair: dict = field(default_factory=dict)
    tradecraft: dict = field(default_factory=dict)


def _build_engines() -> dict:
    return {
        "stylometry": StylometryEngine(),
        "verbatim": VerbatimEngine(),
        "temporal": TemporalEngine(),
        "crypto": CryptoEngine(),
        "pgp": PGPEngine(),
        "handle": HandleEngine(),
        "infra": InfraEngine(),
        "device": DeviceEngine(),
        "favicon": FaviconEngine(),
        "tls": TLSEngine(),
        "template": TemplateEngine(),
        "authorship": NeuralAuthorshipEngine(),
    }


def run(seed: int = 1337, n_actors: int = 150,
        threshold: float | None = None,
        prior_odds: float = DEFAULT_PRIOR_ODDS,
        train_fraction: float = 0.5,
        corpus: Corpus | None = None) -> Result:
    corpus = corpus or generate(seed=seed, n_actors=n_actors)
    view = CorpusView(personas=corpus.personas,
                      posts_by_persona=corpus.posts_by_persona(),
                      transactions=corpus.transactions)

    engines = _build_engines()
    for e in engines.values():
        e.fit(view)

    # ---- candidate generation ---------------------------------------------
    candidates, reasons, block_diag = blocking.generate_candidates(view, engines)
    truth = corpus.truth()
    opsec = corpus.opsec_of()
    block_diag.update(blocking.pair_completeness(candidates, truth))
    # which index proposed each candidate; tells you where the recall is
    # actually coming from, and which index you could afford to drop
    by_reason: dict = {}
    for rs in reasons.values():
        for rsn in rs:
            by_reason[rsn] = by_reason.get(rsn, 0) + 1
    block_diag["candidates_by_index"] = dict(
        sorted(by_reason.items(), key=lambda kv: -kv[1]))

    pairs = sorted(candidates)
    rows, raw_by_pair = [], {}
    for a, b in pairs:
        scored = {}
        detail = {}
        for name, eng in engines.items():
            rs = eng.score(a, b)
            scored[name] = rs.score
            detail[name] = rs
        rows.append(scored)
        raw_by_pair[(a, b)] = detail

    y = np.array([1 if truth[a] == truth[b] else 0 for a, b in pairs], dtype=int)

    # ---- actor-disjoint split ---------------------------------------------
    rng = random.Random(seed + 7)
    actor_ids = sorted({truth[p] for p in truth})
    rng.shuffle(actor_ids)
    cut = int(len(actor_ids) * train_fraction)
    train_actors = set(actor_ids[:cut])

    is_train = np.array([truth[a] in train_actors and truth[b] in train_actors
                         for a, b in pairs])
    is_test = np.array([truth[a] not in train_actors and truth[b] not in train_actors
                        for a, b in pairs])

    model = FusionModel(CHANNELS)
    model.fit([r for r, m in zip(rows, is_train) if m], y[is_train])

    # ---- score every candidate --------------------------------------------
    fused = np.array([model.fused(r) for r in rows])
    naive = np.array([model.naive_sum(r) for r in rows])
    per_channel = {c: np.array([model.calibrators[c].log10_lr(r.get(c, 0.0))
                                for r in rows]) for c in CHANNELS}

    # The operating threshold is fitted on the training split like any other
    # parameter. Choosing it by looking at test performance would be the
    # quietest and most common way to overstate a result like this.
    if threshold is None:
        threshold = metrics.choose_threshold(y[is_train], fused[is_train])
    floor = metrics.choose_lead_floor(y[is_train], fused[is_train], threshold,
                                      MIN_LEAD_BAND_PRECISION)

    links: list[LinkHypothesis] = []
    for i, (a, b) in enumerate(pairs):
        if fused[i] < floor:                # keep leads, drop the rest
            continue
        ev = []
        llrs = model.channel_llrs(rows[i])
        for c in CHANNELS:
            rs = raw_by_pair[(a, b)][c]
            if abs(llrs[c]) < 0.3 and rs.score <= 0:
                continue
            ev.append(Evidence(channel=c, persona_a=a, persona_b=b,
                               score=round(rs.score, 4), log10_lr=llrs[c],
                               rationale=rs.rationale, supporting=rs.supporting))
        ev.sort(key=lambda e: -e.log10_lr)
        links.append(LinkHypothesis(
            persona_a=a, persona_b=b, log10_lr=float(fused[i]),
            posterior=posterior_from_log10_lr(float(fused[i]), prior_odds),
            evidence=ev))
    links.sort(key=lambda l: -l.log10_lr)

    # ---- identity resolution ----------------------------------------------
    all_ids = [p.persona_id for p in corpus.personas]
    clusters = graph.resolve(links, all_ids, threshold=threshold)
    pbid = {p.persona_id: p for p in corpus.personas}
    dossiers = [graph.build_dossier(c, pbid, engines["temporal"])
                for c in clusters if c["size"] > 1]

    # ---- tradecraft classifier --------------------------------------------
    # Predicts operator discipline from observable persona features alone, so
    # an analyst knows before starting whether the artefact channels are worth
    # trusting on this target. Trained on training actors only, like everything
    # else that gets scored.
    tc_indexes = build_indexes(corpus.personas)
    temporal = engines["temporal"]
    post_counts = {pid: len(v) for pid, v in view.posts_by_persona.items()}
    tc_x, tc_y, tc_ids = [], [], []
    for p in corpus.personas:
        tc_x.append(persona_features(
            p, tc_indexes, post_counts.get(p.persona_id, 0),
            temporal.offset_conf.get(p.persona_id, 0.0),
            [q.timestamp for q in view.posts_by_persona.get(p.persona_id, [])]))
        tc_y.append(corpus.actors[p.true_actor].opsec)
        tc_ids.append(p.persona_id)
    tc_x = np.array(tc_x, dtype=float)
    tc_y = np.array(tc_y)
    tc_train = np.array([truth[i] in train_actors for i in tc_ids])

    tradecraft = TradecraftClassifier(seed=seed)
    tradecraft.fit(tc_x[tc_train], tc_y[tc_train])
    tc_eval = tradecraft.evaluate(tc_x[~tc_train], tc_y[~tc_train])
    tc_pred, tc_proba = tradecraft.predict(tc_x)
    tradecraft_by_persona = {}
    if tc_pred is not None:
        classes = list(tradecraft.model.classes_)
        for i, pid in enumerate(tc_ids):
            tradecraft_by_persona[pid] = {
                "predicted": tc_pred[i],
                "confidence": round(float(tc_proba[i].max()), 3),
                "probabilities": {c: round(float(tc_proba[i][j]), 3)
                                  for j, c in enumerate(classes)},
            }

    # ---- evaluation, on held-out actors only ------------------------------
    ty, tf, tn = y[is_test], fused[is_test], naive[is_test]
    test_pairs = [p for p, m in zip(pairs, is_test) if m]
    test_channel = {c: per_channel[c][is_test] for c in CHANNELS}

    predicted_clusters = graph.cluster_truth_map(clusters)
    report = {
        "corpus": corpus.stats(),
        "blocking": block_diag,
        "split": {"train_actors": len(train_actors),
                  "test_actors": len(actor_ids) - len(train_actors),
                  "train_pairs": int(is_train.sum()),
                  "test_pairs": int(is_test.sum())},
        "discrimination": metrics.discrimination(ty, tf),
        "operating_point": metrics.operating_point(ty, tf, threshold),
        "calibration": metrics.cllr(ty, tf),
        "ablation": metrics.channel_ablation(test_pairs, ty, test_channel, CHANNELS),
        "fusion_vs_naive": {
            "fused_auc": metrics.discrimination(ty, tf)["roc_auc"],
            "naive_sum_auc": metrics.discrimination(ty, tn)["roc_auc"],
            "fused_cllr": metrics.cllr(ty, tf)["cllr"],
            "naive_sum_cllr": metrics.cllr(ty, tn)["cllr"],
        },
        "traps": metrics.trap_report(test_pairs, ty, tf, truth, corpus.traps, threshold),
        "by_opsec": metrics.by_opsec(test_pairs, ty, tf, opsec, threshold),
        "review_queue": metrics.review_queue(
            test_pairs, ty, tf, test_channel, threshold, floor),
        "channel_auc_by_opsec": metrics.channel_by_opsec(
            test_pairs, ty, test_channel, CHANNELS, opsec),
        "clustering": metrics.bcubed(predicted_clusters, truth),
        "crypto_diagnostics": engines["crypto"].diagnostics(),
        "model": model.summary(),
        "neural": engines["authorship"].summary(),
        "tradecraft": tc_eval,
        "channel_load": graph.actor_summary(links),
        "settings": {"threshold_log10_lr": round(float(threshold), 2),
                     "threshold_selected_on": "training split; most recall subject to >=95% precision and a hard floor of log10 LR 1.0",
                     "lead_floor_log10_lr": round(float(floor), 2),
                     "lead_floor_selected_on":
                         "training split; deepest band holding >=%.0f%% precision"
                         % (100 * MIN_LEAD_BAND_PRECISION),
                     "prior_odds": prior_odds,
                     "seed": seed},
    }

    return Result(corpus=corpus, engines=engines, model=model, links=links,
                  clusters=clusters, dossiers=dossiers, report=report,
                  scores_by_pair={p: rows[i] for i, p in enumerate(pairs)},
                  tradecraft=tradecraft_by_persona)
