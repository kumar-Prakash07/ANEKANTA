"""Turning engine scores into likelihood ratios, and fusing them.

This module is the reason the platform can defend its numbers.

An engine score of 0.83 means nothing on its own -- 0.83 on the handle channel
and 0.83 on the crypto channel are not comparable quantities, and neither tells
you how much to update your belief. The forensic-science answer, and the one
courts in several jurisdictions now expect, is the likelihood ratio:

    LR = P(observed score | the two personas are one actor)
         ---------------------------------------------------
         P(observed score | they are different actors)

An LR of 1000 means the evidence is a thousand times more probable under the
same-actor hypothesis. Crucially it says nothing about whether they *are* the
same actor -- that requires a prior, which the analyst supplies explicitly and
which the report prints. Keeping those two separable is what stops the system
from committing the prosecutor's fallacy on the analyst's behalf.

We estimate LRs empirically (a score-based LR) by logistic calibration:
fit P(same | score) on held-out labelled pairs, then divide out the training
base rate to recover the ratio. Two properties make this the right choice here:
it needs no assumption that scores are Gaussian, and it degrades gracefully to
LR = 1 on channels that turn out to carry no information, which is exactly what
should happen to the verbatim channel once the copy-paste trap is in the data.

Fusion combines the per-channel log LRs. Simply adding them assumes the
channels are conditionally independent, and they are not: infrastructure and
crypto correlate through hosting arrangements, handle and PGP-UID correlate
through the operator's naming habits. A second logistic layer can absorb that
redundancy -- but only if it has enough positive examples to estimate its
weights, and at a 1% base rate it often does not. So the two are compared by
cross-validation on the training split and the loser is discarded. On this
benchmark the naive sum frequently wins, which is a result worth reporting
rather than hiding behind the more impressive-sounding option.
"""

from __future__ import annotations

import math

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold

from ..schema import (LOG10_LR_ARTEFACT_NEG_CAP, LOG10_LR_CAP,
                      ROTATABLE_ARTEFACT_CHANNELS)


def _cllr(y: np.ndarray, log10_lr: np.ndarray) -> float:
    """Log-likelihood-ratio cost. 1.0 is the score of saying nothing at all."""
    lr = np.power(10.0, np.clip(log10_lr, -12, 12))
    same, diff = lr[y == 1], lr[y == 0]
    if len(same) == 0 or len(diff) == 0:
        return 9.9
    return float(0.5 * (np.mean(np.log2(1 + 1 / same))
                        + np.mean(np.log2(1 + diff))))


class ChannelCalibrator:
    """Maps one channel's raw scores to log10 likelihood ratios."""

    def __init__(self, channel: str, artefact_neg_cap: bool = True) -> None:
        self.channel = channel
        # a rotatable artefact may only weakly argue against a link; see
        # LOG10_LR_ARTEFACT_NEG_CAP in schema.py for why
        self.neg_cap = (-LOG10_LR_ARTEFACT_NEG_CAP
                        if (artefact_neg_cap and channel in ROTATABLE_ARTEFACT_CHANNELS)
                        else -LOG10_LR_CAP)
        self.model: LogisticRegression | None = None
        self.train_log_prior_odds = 0.0
        self.informative = False
        self.n_pos = 0
        self.n_neg = 0

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> "ChannelCalibrator":
        self.n_pos = int(labels.sum())
        self.n_neg = int(len(labels) - self.n_pos)
        if self.n_pos < 5 or self.n_neg < 5 or np.std(scores) < 1e-9:
            return self                      # leave uninformative: LR = 1

        # Two features, not one: the score itself and an indicator for "the
        # engine produced anything at all". Without the indicator, abstaining
        # (score 0) is indistinguishable from a confident zero similarity.
        x = np.column_stack([scores, (scores > 0).astype(float)])
        self.model = LogisticRegression(C=1.0, class_weight=None, max_iter=2000)
        self.model.fit(x, labels)
        prior = self.n_pos / (self.n_pos + self.n_neg)
        self.train_log_prior_odds = math.log10(prior / (1 - prior))
        self.informative = True
        return self

    def log10_lr(self, score: float) -> float:
        if not self.informative or self.model is None:
            return 0.0
        x = np.array([[score, 1.0 if score > 0 else 0.0]])
        p = float(self.model.predict_proba(x)[0, 1])
        p = min(max(p, 1e-9), 1 - 1e-9)
        # posterior odds observed in training, minus the training base rate,
        # leaves the likelihood ratio contributed by the score itself
        llr = math.log10(p / (1 - p)) - self.train_log_prior_odds
        return max(self.neg_cap, min(LOG10_LR_CAP, llr))

    def summary(self) -> dict:
        return {"channel": self.channel, "informative": self.informative,
                "negative_floor": round(self.neg_cap, 2),
                "train_pos": self.n_pos, "train_neg": self.n_neg}


class FusionModel:
    """Combines per-channel log LRs into one calibrated log LR."""

    def __init__(self, channels: list[str], artefact_neg_cap: bool = True) -> None:
        self.channels = channels
        self.calibrators = {c: ChannelCalibrator(c, artefact_neg_cap)
                            for c in channels}
        self.fuser: LogisticRegression | None = None
        self.fuse_log_prior_odds = 0.0
        self.cv_report: dict = {}
        self.dropped: list = []
        self.active_channels: list = list(channels)

    # -- training -----------------------------------------------------------

    def fit(self, score_rows: list[dict], labels: np.ndarray) -> "FusionModel":
        y = np.asarray(labels, dtype=int)
        for c in self.channels:
            s = np.array([row.get(c, 0.0) for row in score_rows], dtype=float)
            self.calibrators[c].fit(s, y)

        x = self._llr_matrix(score_rows)
        if y.sum() >= 5 and (len(y) - y.sum()) >= 5:
            self._select_channels(self._llr_matrix(score_rows,
                                                   self.channels), y)
            x = self._llr_matrix(score_rows)
            self._fit_fuser(x, y)
        return self

    def _select_channels(self, x: np.ndarray, y: np.ndarray,
                         max_drops: int = 4, margin: float = 0.004) -> None:
        """Backward elimination: drop channels that do not earn their place.

        Adding an informative channel can still make the system worse. Channels
        are correlated -- a learned author embedding and hand-crafted stylometry
        measure much the same thing -- and with only a few dozen positive pairs
        the fusion has to spend parameters distinguishing them. The result is a
        model that fits the training split's idiosyncrasies and generalises
        less well than the smaller one would have.

        So each channel is tested by removing it and re-measuring
        cross-validated average precision on the training split. A channel is
        dropped only if its removal *improves* the score by more than a margin,
        which keeps this from chasing noise, and at most a few are dropped so a
        single unlucky fold cannot strip the model bare.

        This is the same rule the fusion model itself is held to. A component
        does not stay in the pipeline because it is fashionable or because it
        was expensive to build; it stays because removing it makes things
        worse.
        """
        active = list(self.channels)
        base = self._cv_cllr(x, y, active)
        for _ in range(max_drops):
            if len(active) <= 4:
                break
            best_gain, best_drop = 0.0, None
            for c in active:
                trial = [k for k in active if k != c]
                improvement = base - self._cv_cllr(x, y, trial)   # lower is better
                if improvement > best_gain:
                    best_gain, best_drop = improvement, c
            if best_drop is None or best_gain <= margin:
                break
            active.remove(best_drop)
            self.dropped.append({"channel": best_drop,
                                 "cv_cllr_improvement": round(best_gain, 4)})
            base -= best_gain
        self.active_channels = active

    def _cv_cllr(self, x: np.ndarray, y: np.ndarray, subset: list) -> float:
        """Cross-validated Cllr for a subset of channels. Lower is better.

        Deliberately not average precision. AP scores the *ordering* of pairs
        and nothing else, and by that measure adding a channel that duplicates
        one already present looks free -- the ranking barely moves. But the
        deployed system does not consume an ordering, it consumes the magnitude
        of a likelihood ratio: the threshold is an LR, the report prints an LR,
        and the analyst is told how many times more probable the evidence is.

        Double-counting correlated evidence inflates that magnitude while
        leaving the ranking almost untouched. AP cannot see that; Cllr punishes
        it directly, because Cllr charges for confidence in proportion to how
        wrong it turns out to be. Selecting on the metric the product actually
        depends on is the difference between a system that ranks well and one
        whose numbers can be quoted.
        """
        cols = [self.channels.index(c) for c in subset]
        if not cols:
            return 9.9
        folds = min(5, int(y.sum()), int(len(y) - y.sum()))
        if folds < 3:
            return 9.9
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
        xs = x[:, cols]
        scores = []
        for tr, te in cv.split(xs, y):
            if y[tr].sum() < 2 or y[te].sum() < 1:
                continue
            m = LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000)
            m.fit(xs[tr], y[tr])
            # balanced weighting implies a 50/50 training prior, so the
            # calibrated log-odds IS the log LR; convert base e to base 10
            llr = m.decision_function(xs[te]) / math.log(10)
            scores.append(_cllr(y[te], llr))
        return float(np.mean(scores)) if scores else 9.9

    def _fit_fuser(self, x: np.ndarray, y: np.ndarray) -> None:
        """Fit the second stage, and refuse to use it if it cannot beat the
        naive sum.

        With a 1% base rate there are only a few dozen positive pairs to fit
        eight weights against, which is enough to overfit badly. So the
        regularisation strength is chosen by cross-validation on the training
        split, and the winner is then compared against the parameter-free naive
        sum on the same folds. If the learned layer does not actually improve
        average precision it is discarded and the sum is used. A fusion model
        that loses to adding numbers up should not be in the pipeline just
        because it is more sophisticated.
        """
        folds = min(5, int(y.sum()), int(len(y) - y.sum()))
        if folds < 3:
            self.fuser = None
            return
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
        naive = x.sum(axis=1)

        def cv_score(make) -> float:
            scores = []
            for tr, te in cv.split(x, y):
                if y[tr].sum() < 2 or y[te].sum() < 1:
                    continue
                m = make()
                m.fit(x[tr], y[tr])
                scores.append(_cllr(y[te],
                                    m.decision_function(x[te]) / math.log(10)))
            return float(np.mean(scores)) if scores else 9.9

        naive_cv = []
        for _, te in cv.split(x, y):
            if y[te].sum() >= 1:
                naive_cv.append(_cllr(y[te], naive[te]))
        naive_cllr = float(np.mean(naive_cv)) if naive_cv else 9.9

        best_c, best_cllr = None, 9.9
        for c in (0.03, 0.1, 0.3, 1.0, 3.0):
            val = cv_score(lambda c=c: LogisticRegression(
                C=c, class_weight="balanced", max_iter=5000))
            if val < best_cllr:
                best_c, best_cllr = c, val

        self.cv_report = {"criterion": "cross-validated Cllr, lower is better",
                          "naive_sum_cllr": round(naive_cllr, 4),
                          "best_learned_cllr": round(best_cllr, 4),
                          "chosen_C": best_c}
        if best_cllr >= naive_cllr:
            self.fuser = None
            self.cv_report["selected"] = "naive_sum"
            return

        self.fuser = LogisticRegression(C=best_c, class_weight="balanced",
                                        max_iter=5000)
        self.fuser.fit(x, y)
        self.cv_report["selected"] = "learned_fusion"

    def _llr_matrix(self, rows: list[dict], subset: list | None = None) -> np.ndarray:
        cols = subset if subset is not None else self.active_channels
        return np.array([[self.calibrators[c].log10_lr(r.get(c, 0.0))
                          for c in cols] for r in rows], dtype=float)

    # -- inference ----------------------------------------------------------

    def channel_llrs(self, scores: dict) -> dict:
        return {c: self.calibrators[c].log10_lr(scores.get(c, 0.0))
                for c in self.channels}

    def naive_sum(self, scores: dict) -> float:
        """Ablation: assume conditional independence and add the logs."""
        return sum(self.calibrators[c].log10_lr(scores.get(c, 0.0))
                   for c in self.active_channels)

    def fused(self, scores: dict) -> float:
        if self.fuser is None:
            return self.naive_sum(scores)
        x = self._llr_matrix([scores])
        p = float(self.fuser.predict_proba(x)[0, 1])
        p = min(max(p, 1e-12), 1 - 1e-12)
        # The balanced fit implies a 50/50 training prior, so the calibrated
        # log-odds it emits *is* the log LR; no base-rate term to remove.
        return max(-LOG10_LR_CAP * 2, min(LOG10_LR_CAP * 2,
                                          math.log10(p / (1 - p))))

    def weights(self) -> dict:
        if self.fuser is None:
            return {c: 1.0 for c in self.active_channels}
        return {c: round(float(w), 3)
                for c, w in zip(self.active_channels, self.fuser.coef_[0])}

    def summary(self) -> dict:
        return {
            "channels": [self.calibrators[c].summary() for c in self.channels],
            "fusion_selection": self.cv_report,
            "active_channels": self.active_channels,
            "dropped_channels": self.dropped,
            "fusion_weights": self.weights(),
            "note": ("weights below 1.0 indicate a channel whose evidence is "
                     "partly redundant with others already in the model"),
        }
