"""Scoring the system against ground truth.

Accuracy is a useless statistic here. With a 1.2% base rate, a system that
answers "different actors" to every question scores 98.8%. Four families of
metric are reported instead, each answering a question a reviewer would
actually ask.

Discrimination  ROC AUC and average precision: can the system tell the two
                populations apart at all, independent of any threshold.

Operating point Precision, recall and F1 at the deployed threshold, plus the
                precision-at-k that reflects how an analyst really works --
                they open the top of the queue, not the whole queue.

Calibration     Cllr, the log-likelihood-ratio cost from the forensic
                literature. It penalises confidence in proportion to how wrong
                it was, so a system that says "10,000:1" about a false link is
                punished far harder than one that says "3:1". Reported next to
                Cllr_min, the value achievable after perfect recalibration of
                the same scores. The gap between them separates a discrimination
                problem from a calibration problem, which is the single most
                useful diagnostic when a system underperforms. Below 1.0 means
                the system is more use than saying nothing.

Clustering      B-Cubed precision and recall over resolved identities. Pairwise
                metrics flatter a system that gets many easy pairs right inside
                one obvious cluster; B-Cubed weights per persona and does not.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score


def _safe_auc(y: np.ndarray, s: np.ndarray) -> float:
    if len(set(y.tolist())) < 2:
        return float("nan")
    return float(roc_auc_score(y, s))


def discrimination(y: np.ndarray, log10_lr: np.ndarray) -> dict:
    return {
        "roc_auc": round(_safe_auc(y, log10_lr), 4),
        "average_precision": round(float(average_precision_score(y, log10_lr)), 4)
        if len(set(y.tolist())) > 1 else float("nan"),
        "n_same_actor": int(y.sum()),
        "n_different_actor": int(len(y) - y.sum()),
    }


def operating_point(y: np.ndarray, log10_lr: np.ndarray, threshold: float) -> dict:
    pred = log10_lr >= threshold
    tp = int(np.sum(pred & (y == 1)))
    fp = int(np.sum(pred & (y == 0)))
    fn = int(np.sum(~pred & (y == 1)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    order = np.argsort(-log10_lr)
    at_k = {}
    for k in (10, 25, 50, 100):
        if k <= len(order):
            at_k["precision_at_%d" % k] = round(float(y[order[:k]].mean()), 4)

    return {"threshold_log10_lr": threshold, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), **at_k}


def choose_threshold(y: np.ndarray, log10_lr: np.ndarray,
                     min_precision: float = 0.95,
                     floor: float = 1.0) -> float:
    """Pick the operating threshold on the TRAINING split.

    Not the F1-maximising point. An attribution system feeds an analyst queue,
    and a false link there costs far more than a missed one -- it sends a
    person down a wrong investigative path and, if it reaches a filing, it is
    the error that discredits the tool. So we take the most permissive
    threshold that still holds precision at or above the stated floor, and fall
    back to maximising F1 only if no threshold can meet it.

    `floor` is a hard evidential minimum, independent of what the data would
    permit. At log10 LR = 1 the observation is ten times more probable under
    same-actor than under different-actor, which is the weakest claim the
    verbal scale in schema.py is willing to call support at all. Letting the
    optimiser drop below that would emit "linkages" the system itself grades as
    insufficient -- a threshold can be statistically optimal and still be the
    wrong thing to put in front of an analyst.
    """
    if y.sum() == 0:
        return max(2.0, floor)
    cands = np.unique(np.round(log10_lr, 2))
    best_f1, best_f1_t = -1.0, 2.0
    feasible = []
    for t in cands:
        pred = log10_lr >= t
        tp = float(np.sum(pred & (y == 1)))
        fp = float(np.sum(pred & (y == 0)))
        fn = float(np.sum(~pred & (y == 1)))
        if tp == 0:
            continue
        prec, rec = tp / (tp + fp), tp / (tp + fn)
        f1 = 2 * prec * rec / (prec + rec)
        if f1 > best_f1:
            best_f1, best_f1_t = f1, float(t)
        if prec >= min_precision:
            feasible.append((rec, float(t)))
    if feasible:
        return max(floor, max(feasible)[1])   # most recall among precise points
    return max(floor, best_f1_t)


def review_queue(pairs: list, y: np.ndarray, log10_lr: np.ndarray,
                 per_channel_llr: dict, threshold: float,
                 lead_floor: float = 0.5,
                 behavioural: tuple = ("temporal", "stylometry", "authorship")) -> dict:
    """The band below the assertion threshold, reported as leads.

    Disciplined operators sit here. The system ranks them well -- fused AUC
    stays high within that tier -- but cannot assert them at the precision an
    accusation requires. Discarding them would throw away the cases the tool
    exists for; promoting them would put unsupported claims in a file.

    So they are emitted as a separate, explicitly weaker product: an ordered
    queue of leads for an analyst to work by hand, never a linkage. What makes
    the band worth an analyst's time is measured here rather than assumed --
    its precision, and how much of it rests on behavioural evidence, which is
    what survives when an operator rotates their artefacts.
    """
    band = (log10_lr >= lead_floor) & (log10_lr < threshold)
    n = int(band.sum())
    if n == 0:
        return {"leads": 0}
    yy = y[band]

    # Share of the *supporting* evidence that is behavioural. Only positive
    # contributions are counted: a channel arguing against the link is not part
    # of the case for it, and including the capped negatives here made the
    # denominator go negative and drove the whole statistic to zero.
    def positive(chans):
        return np.sum([np.maximum(per_channel_llr[c][band], 0.0) for c in chans],
                      axis=0)

    beh = positive(behavioural)
    tot = positive(list(per_channel_llr))
    share = np.where(tot > 1e-9, beh / np.maximum(tot, 1e-9), 0.0)

    return {
        "lead_floor_log10_lr": round(lead_floor, 3),
        "leads": n,
        "true_links_in_band": int(yy.sum()),
        "band_precision": round(float(yy.mean()), 4),
        # Enrichment is quoted against the pool the analyst would otherwise be
        # working -- the scored candidates -- not against the whole corpus.
        # The corpus base rate is much lower, so quoting against it inflates
        # the figure several-fold by silently taking credit for the blocking
        # stage a second time.
        "candidate_pool_base_rate": round(float(y.mean()), 4),
        "enrichment_vs_candidate_pool": round(
            float(yy.mean()) / max(1e-9, float(y.mean())), 1),
        "median_behavioural_share": round(float(np.median(share)), 3),
        "note": ("recovered as leads, not assertions; these are the pairs the "
                 "assertion threshold deliberately refuses"),
    }


def choose_lead_floor(y: np.ndarray, log10_lr: np.ndarray, threshold: float,
                      min_band_precision: float = 0.20,
                      max_margin: float = 2.0) -> float:
    """Pick how deep the lead queue goes, on the TRAINING split.

    A lead queue is worth an analyst's time only while it stays enriched enough
    to be worth opening. Extending it further does technically surface more
    true links, but it does so by burying them, and an analyst who works three
    dead ends in a row stops working the queue at all.

    So the floor descends from the assertion threshold only as far as the band
    still holds the stated precision. Fixing the depth instead -- an absolute
    score, or a constant margin -- means it silently changes meaning every time
    the engines shift the LR scale, which is exactly what happened before this
    function existed.
    """
    best = threshold
    for margin in np.arange(0.1, max_margin + 1e-9, 0.05):
        floor = threshold - margin
        band = (log10_lr >= floor) & (log10_lr < threshold)
        if band.sum() < 5:
            best = floor
            continue
        if float(y[band].mean()) >= min_band_precision:
            best = floor
        else:
            break
    return round(max(0.0, best), 3)


def by_opsec(pairs: list, y: np.ndarray, log10_lr: np.ndarray,
             opsec: dict, threshold: float) -> dict:
    """Recall broken down by how careful the operator was.

    The headline number of the whole project. A system that only catches
    careless operators is a system that catches the people who were going to be
    caught anyway.
    """
    out = {}
    for tier in ("sloppy", "mixed", "disciplined"):
        idx = [i for i, (a, b) in enumerate(pairs)
               if y[i] == 1 and opsec.get(a) == tier and opsec.get(b) == tier]
        if not idx:
            out[tier] = {"true_pairs": 0, "recovered": 0, "recall": None}
            continue
        rec = [i for i in idx if log10_lr[i] >= threshold]
        out[tier] = {
            "true_pairs": len(idx),
            "recovered": len(rec),
            "recall": round(len(rec) / len(idx), 4),
            "median_log10_lr": round(float(np.median(log10_lr[idx])), 2),
        }
    return out


def channel_by_opsec(pairs: list, y: np.ndarray, per_channel_llr: dict,
                     channels: list, opsec: dict) -> dict:
    """Per-channel discrimination within each opsec tier.

    This is the table that makes the argument: as discipline rises, the
    artefact channels (pgp, crypto, infra, device, handle) fall toward 0.5
    while the behavioural channels (temporal, stylometry) hold up, because a
    sleep cycle is not a credential you can rotate.
    """
    out = {}
    for tier in ("sloppy", "mixed", "disciplined"):
        keep = np.array([opsec.get(a) == tier and opsec.get(b) == tier
                         for a, b in pairs])
        yy = y[keep]
        if keep.sum() < 10 or yy.sum() < 2 or (len(yy) - yy.sum()) < 2:
            out[tier] = None
            continue
        row = {}
        for c in channels:
            row[c] = round(_safe_auc(yy, per_channel_llr[c][keep]), 3)
        row["FUSED"] = round(_safe_auc(
            yy, np.sum([per_channel_llr[c][keep] for c in channels], axis=0)), 3)
        row["n_true_pairs"] = int(yy.sum())
        out[tier] = row
    return out


def cllr(y: np.ndarray, log10_lr: np.ndarray) -> dict:
    """Log-likelihood-ratio cost, and the value after ideal recalibration."""
    lr = np.power(10.0, np.clip(log10_lr, -12, 12))
    same, diff = lr[y == 1], lr[y == 0]
    if len(same) == 0 or len(diff) == 0:
        return {"cllr": float("nan"), "cllr_min": float("nan")}

    c = 0.5 * (np.mean(np.log2(1 + 1 / same)) + np.mean(np.log2(1 + diff)))

    # Cllr_min via the pool-adjacent-violators solution: isotonic regression on
    # the scores gives the optimally calibrated posterior, from which the best
    # achievable cost for this discrimination follows.
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6)
    p = iso.fit_transform(log10_lr, y)
    prior_odds = y.mean() / (1 - y.mean())
    lr_min = np.clip(p / (1 - p), 1e-12, 1e12) / prior_odds
    c_min = 0.5 * (np.mean(np.log2(1 + 1 / lr_min[y == 1])) +
                   np.mean(np.log2(1 + lr_min[y == 0])))

    return {"cllr": round(float(c), 4), "cllr_min": round(float(c_min), 4),
            "calibration_loss": round(float(c - c_min), 4)}


def bcubed(predicted: dict, truth: dict) -> dict:
    """B-Cubed precision/recall over cluster assignments, keyed by persona."""
    ids = [p for p in truth if p in predicted]
    if not ids:
        return {"bcubed_precision": 0.0, "bcubed_recall": 0.0, "bcubed_f1": 0.0}
    pred_members = defaultdict(set)
    true_members = defaultdict(set)
    for p in ids:
        pred_members[predicted[p]].add(p)
        true_members[truth[p]].add(p)

    precs, recs = [], []
    for p in ids:
        pc, tc = pred_members[predicted[p]], true_members[truth[p]]
        inter = len(pc & tc)
        precs.append(inter / len(pc))
        recs.append(inter / len(tc))
    pr, rc = float(np.mean(precs)), float(np.mean(recs))
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return {"bcubed_precision": round(pr, 4), "bcubed_recall": round(rc, 4),
            "bcubed_f1": round(f1, 4),
            "predicted_clusters": len(pred_members),
            "true_actors": len(true_members)}


def trap_report(pairs: list[tuple], y: np.ndarray, log10_lr: np.ndarray,
                truth: dict, traps: dict, threshold: float) -> dict:
    """Did the planted adversarial cases actually fool us."""
    idx = {p: i for i, p in enumerate(pairs)}
    out = {}

    # T1/T4-style: unrelated actors that share a host, and whether we linked them
    shared_pairs = []
    for a, b, _host in traps.get("shared_host", []):
        pa = [p for p, act in truth.items() if act == a]
        pb = [p for p, act in truth.items() if act == b]
        for x in pa:
            for yy in pb:
                key = tuple(sorted((x, yy)))
                if key in idx:
                    shared_pairs.append(key)
    fired = [p for p in shared_pairs if log10_lr[idx[p]] >= threshold]
    out["shared_host"] = {
        "adversarial_pairs_scored": len(shared_pairs),
        "false_links_emitted": len(fired),
        "survived": len(fired) == 0,
    }

    # T2: verbatim copy-paste between unrelated personas
    cp = [tuple(sorted(t)) for t in traps.get("copypaste", [])]
    cp = [p for p in cp if p in idx and truth.get(p[0]) != truth.get(p[1])]
    fired = [p for p in cp if log10_lr[idx[p]] >= threshold]
    out["copypaste"] = {
        "adversarial_pairs_scored": len(cp),
        "false_links_emitted": len(fired),
        "survived": len(fired) == 0,
    }

    # T5: unrelated actors wearing confusably similar handles
    coll = []
    for a, b in traps.get("handle_collision", []):
        pa = [p for p, act in truth.items() if act == a]
        pb = [p for p, act in truth.items() if act == b]
        for x in pa:
            for yy in pb:
                key = tuple(sorted((x, yy)))
                if key in idx:
                    coll.append(key)
    fired = [p for p in coll if log10_lr[idx[p]] >= threshold]
    out["handle_collision"] = {
        "adversarial_pairs_scored": len(coll),
        "false_links_emitted": len(fired),
        "survived": len(fired) == 0,
    }

    # T3: key rotation, a false-negative trap -- can we still recover the link
    rotated = set(traps.get("key_rotation", []))
    rot_pairs = [p for i, p in enumerate(pairs)
                 if y[i] == 1 and (p[0] in rotated or p[1] in rotated)]
    caught = [p for p in rot_pairs if log10_lr[idx[p]] >= threshold]
    out["key_rotation"] = {
        "true_pairs_with_rotated_key": len(rot_pairs),
        "still_recovered": len(caught),
        "recall": round(len(caught) / max(1, len(rot_pairs)), 4),
    }
    return out


def channel_ablation(pairs: list[tuple], y: np.ndarray, per_channel_llr: dict,
                     channels: list[str]) -> dict:
    """AUC of each channel alone, and of the fusion without it. The second
    column is the one that matters: a channel with mediocre solo AUC can still
    be the one carrying the hard cases."""
    full = np.sum([per_channel_llr[c] for c in channels], axis=0)
    rows = {}
    for c in channels:
        solo = _safe_auc(y, per_channel_llr[c])
        without = np.sum([per_channel_llr[o] for o in channels if o != c], axis=0)
        rows[c] = {
            "solo_auc": round(solo, 4) if not math.isnan(solo) else None,
            "auc_without_it": round(_safe_auc(y, without), 4),
            "mean_abs_log10_lr": round(float(np.mean(np.abs(per_channel_llr[c]))), 4),
        }
    return {"all_channels_auc": round(_safe_auc(y, full), 4), "channels": rows}
