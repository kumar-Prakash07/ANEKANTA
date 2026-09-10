"""Tradecraft classifier: how careful is the operator behind this persona?

Everything else in this system compares two personas. This model looks at one,
and predicts how disciplined its operator is -- whether they are the kind who
reuses a PGP key across accounts, or the kind who rotates everything.

Why that is worth predicting
----------------------------
The whole platform rests on a finding: against a disciplined operator the
artefact channels fall to chance and only behaviour survives. That finding is
actionable only if you can tell, *before* you have the answer, which kind of
operator you are looking at. Knowing it changes what an analyst should do:

  low discipline    the artefact channels will resolve this quickly; expect an
                    assertable linkage.
  high discipline   PGP, wallets, handles and hosting will be uninformative.
                    Do not read their silence as evidence of innocence -- it is
                    evidence of care. Expect leads rather than assertions, and
                    weight the behavioural channels.

It is also an honesty mechanism. A system that says "no linkage found" means
something very different for a careless operator than for a careful one, and
this is what lets the report say which case it is in.

Features are strictly observable
--------------------------------
Every feature is something an analyst could read off the persona: does it
publish a contact address, how many wallets, does its favicon appear on many
other services, how rare is its hosting, how regular is its posting rhythm.
None of them is derived from a link, so the prediction is available before any
attribution work is done -- which is the only time it would be useful.

The tier labels come from the benchmark. Applied to live data the model is
extrapolating from simulated tradecraft to real tradecraft, and the honest
status of its output there is a hypothesis, not a measurement. The dashboard
labels it accordingly.
"""

from __future__ import annotations

import numpy as np

FEATURE_NAMES = [
    "n_wallets",              # publishing many addresses is a careless habit
    "has_contact",            # an off-platform contact handle is an extra hook
    "has_tls",
    "favicon_holders",        # stock icon => shared with many services
    "host_holders",           # busy tenancy vs a private box
    "pgp_holders",            # key published under more than one persona
    "template_holders",
    "n_images",               # reusing images across accounts is careless
    "has_exif",               # not stripping EXIF is the classic tell
    "tz_confidence",          # a jittered posting schedule lowers this
    "post_count",
    "handle_len",
    "handle_is_decorated",    # root plus a numeric suffix, a naming habit
    "active_days",
    # Behavioural regularity. Deliberate schedule jitter is one of the few
    # tradecraft choices visible from a single persona, and unlike every
    # artefact feature above it does not require the operator to have a second
    # account for us to compare against.
    "hour_entropy",           # a jittered poster looks closer to uniform
    "interval_regularity",    # coefficient of variation of gaps between posts
]

TIERS = ["sloppy", "mixed", "disciplined"]


def _holders(index: dict, key: str) -> int:
    return len(index.get(key, ())) if key else 0


def _rhythm(timestamps: list) -> tuple:
    """Hour-of-day entropy and inter-post interval regularity."""
    if len(timestamps) < 6:
        return 1.0, 0.0
    hours = np.zeros(24)
    for t in timestamps:
        hours[t.hour] += 1
    pdist = hours / hours.sum()
    nz = pdist[pdist > 0]
    # normalised so 1.0 is a perfectly flat (fully jittered) schedule
    entropy = float(-(nz * np.log(nz)).sum() / np.log(24))

    order = sorted(timestamps)
    gaps = np.array([(order[i + 1] - order[i]).total_seconds()
                     for i in range(len(order) - 1)], dtype=float)
    gaps = gaps[gaps > 0]
    if len(gaps) < 3:
        return entropy, 0.0
    cv = float(gaps.std() / (gaps.mean() + 1e-9))
    return entropy, cv


def persona_features(p, indexes: dict, n_posts: int, tz_conf: float,
                     timestamps: list | None = None) -> list:
    from ..engines.handle import normalise
    inf = p.infra_fingerprints or {}
    svc = p.service or {}
    norm = normalise(p.handle or "")
    return [
        len(p.btc_addresses),
        1.0 if p.contact_handles else 0.0,
        1.0 if svc.get("tls", {}).get("present") else 0.0,
        _holders(indexes.get("favicon", {}), inf.get("favicon_sha256", "")),
        _holders(indexes.get("host", {}), inf.get("host", "")),
        _holders(indexes.get("pgp", {}), p.pgp_fingerprint or ""),
        _holders(indexes.get("template", {}), inf.get("dom_skeleton", "")),
        len(p.image_hashes),
        1.0 if p.exif_devices else 0.0,
        tz_conf,
        n_posts,
        len(norm),
        1.0 if norm != (p.handle or "").lower() else 0.0,
        max(0.0, (p.last_seen - p.first_seen).days),
        *_rhythm(timestamps or []),
    ]


class TradecraftClassifier:
    def __init__(self, seed: int = 0) -> None:
        self.model = None
        self.available = False
        self.report: dict = {}
        self.seed = seed

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TradecraftClassifier":
        if len(x) < 40 or len(set(y.tolist())) < 2:
            return self
        from sklearn.ensemble import RandomForestClassifier
        # A forest rather than a network: fourteen tabular features and a few
        # hundred rows is exactly the regime where a small ensemble beats a
        # neural model and, unlike one, will report which features it used.
        self.model = RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_leaf=3,
            class_weight="balanced", random_state=self.seed, n_jobs=-1)
        self.model.fit(x, y)
        self.available = True
        return self

    def predict(self, x: np.ndarray):
        if not self.available:
            return None, None
        proba = self.model.predict_proba(x)
        idx = proba.argmax(axis=1)
        return [self.model.classes_[i] for i in idx], proba

    def evaluate(self, x: np.ndarray, y: np.ndarray) -> dict:
        if not self.available or len(x) == 0:
            return {"available": False}
        pred, _ = self.predict(x)
        pred = np.array(pred)
        acc = float((pred == y).mean())

        # Accuracy alone hides the failure that matters. Calling a disciplined
        # operator careless tells an analyst to trust artefact channels that
        # are about to return nothing, and to read that silence as exoneration.
        # That error is reported separately.
        disc = y == "disciplined"
        missed = float((pred[disc] != "disciplined").mean()) if disc.any() else 0.0

        per_class = {}
        for t in TIERS:
            m = y == t
            if m.any():
                per_class[t] = {"n": int(m.sum()),
                                "recall": round(float((pred[m] == t).mean()), 3)}

        importance = sorted(
            zip(FEATURE_NAMES, self.model.feature_importances_),
            key=lambda kv: -kv[1])[:6]

        return {
            "available": True,
            "accuracy": round(acc, 4),
            "majority_class_baseline": round(
                float(max((y == t).mean() for t in TIERS)), 4),
            "disciplined_missed_rate": round(missed, 3),
            "per_class": per_class,
            "top_features": [{"feature": f, "importance": round(float(v), 3)}
                             for f, v in importance],
            "note": ("trained on benchmark tradecraft tiers; on live data this "
                     "is an extrapolation and should be read as a hypothesis"),
        }


def build_indexes(personas: list) -> dict:
    """Population counts, so 'how common is this artefact' is a feature."""
    from ..engines.base import index_values
    return {
        "favicon": index_values(
            {p.persona_id: [(p.infra_fingerprints or {}).get("favicon_sha256", "")]
             for p in personas}),
        "host": index_values(
            {p.persona_id: [(p.infra_fingerprints or {}).get("host", "")]
             for p in personas}),
        "pgp": index_values(
            {p.persona_id: [p.pgp_fingerprint or ""] for p in personas}),
        "template": index_values(
            {p.persona_id: [(p.infra_fingerprints or {}).get("dom_skeleton", "")]
             for p in personas}),
    }
