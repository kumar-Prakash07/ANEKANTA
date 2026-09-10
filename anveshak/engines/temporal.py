"""Circadian analysis: when a persona posts, and what that says about where.

An actor has one body and one sleep cycle. Personas are cheap; a diurnal rhythm
is not. Two accounts driven by the same human tend to share a posting phase
even when the operator is careful about every other channel, because staying
awake on a fake schedule for a year is harder than rotating a PGP key.

Two products come out of this engine:

  linkage    similarity of two personas hour-of-day profiles, which feeds the
             fusion stage like any other channel;
  geolocation  an estimated UTC offset per persona, which is an intelligence
             product in its own right and is what an analyst actually wants to
             read in the report.

The offset estimate uses the sleep-gap method: find the contiguous eight-hour
window with the least activity, call its centre the middle of the local night,
and solve for the offset. It is deliberately reported with an uncertainty band
derived from how pronounced the gap is, because an actor with a weak or absent
diurnal signal (shift work, automation, deliberate jitter) must not be assigned
a confident location.
"""

from __future__ import annotations

import math

import numpy as np

from .base import CorpusView, Engine, RawScore, NULL

# Empirical anchor: the middle of the local night for a population of
# night-leaning forum users. Shifting this constant shifts every estimate
# uniformly, so it is stated explicitly rather than buried.
SLEEP_CENTRE_LOCAL_HOUR = 3.5

VALID_OFFSETS = [-11, -10, -9.5, -9, -8, -7, -6, -5, -4, -3.5, -3, -2, -1, 0,
                 1, 2, 3, 3.5, 4, 4.5, 5, 5.5, 5.75, 6, 6.5, 7, 8, 8.75, 9,
                 9.5, 10, 10.5, 11, 12, 12.75, 13, 14]


def _circular_distance(a: float, b: float, period: float = 24.0) -> float:
    d = abs(a - b) % period
    return min(d, period - d)


class TemporalEngine(Engine):
    channel = "temporal"

    MIN_POSTS = 15

    def __init__(self) -> None:
        self.hist: dict[str, np.ndarray] = {}      # 24-bin UTC hour profile
        self.dow: dict[str, np.ndarray] = {}       # 7-bin day-of-week profile
        self.offset: dict[str, float] = {}         # inferred UTC offset
        self.offset_conf: dict[str, float] = {}    # 0..1, from gap contrast
        self.n_posts: dict[str, int] = {}

    def fit(self, view: CorpusView) -> None:
        for pid, posts in view.posts_by_persona.items():
            self.n_posts[pid] = len(posts)
            h = np.zeros(24)
            d = np.zeros(7)
            for p in posts:
                h[p.timestamp.hour] += 1
                d[p.timestamp.weekday()] += 1
            if h.sum() == 0:
                continue
            # light circular smoothing: an hour bin is not a hard boundary and
            # unsmoothed histograms make the gap search jumpy on sparse data
            k = np.array([0.25, 0.5, 1.0, 0.5, 0.25])
            hs = np.convolve(np.concatenate([h[-2:], h, h[:2]]), k, mode="same")[2:-2]
            self.hist[pid] = hs / hs.sum()
            self.dow[pid] = d / d.sum()
            off, conf = self._infer_offset(self.hist[pid])
            self.offset[pid] = off
            self.offset_conf[pid] = conf

    # -- geolocation --------------------------------------------------------

    def _infer_offset(self, hist: np.ndarray) -> tuple[float, float]:
        """Sleep-gap estimator. Returns (utc_offset, confidence in 0..1)."""
        # Search several window lengths rather than assuming everyone sleeps
        # exactly eight hours, and score by contrast against what a flat
        # poster would put in a window that size.
        best = None
        for length in (6, 7, 8, 9):
            for start in range(24):
                window = [(start + i) % 24 for i in range(length)]
                mass = float(hist[window].sum())
                contrast = (length / 24 - mass) / (length / 24)
                if best is None or contrast > best[0]:
                    best = (contrast, start, length, mass)
        contrast, best_start, length, best_mass = best
        gap_centre_utc = (best_start + length / 2.0) % 24

        raw = (SLEEP_CENTRE_LOCAL_HOUR - gap_centre_utc) % 24
        if raw > 14:
            raw -= 24
        # snap to a real-world offset; nobody lives at UTC+6.13
        offset = min(VALID_OFFSETS, key=lambda o: _circular_distance(o, raw))

        # confidence is the contrast itself: how much quieter the quiet window
        # is than a flat poster would make it. A perfectly flat poster scores 0
        # and is given no location claim at all.
        return offset, max(0.0, min(1.0, contrast))

    def geolocation(self, pid: str) -> dict:
        """Analyst-facing summary, with an honest uncertainty band."""
        if pid not in self.offset:
            return {"offset": None, "confidence": 0.0, "band": None, "regions": []}
        conf = self.offset_conf[pid]
        band = round(1.0 + 5.0 * (1.0 - conf), 1)     # hours, +/- either side
        off = self.offset[pid]
        regions = {
            5.5: "India / Sri Lanka", 5.75: "Nepal", 6: "Bangladesh",
            4: "Gulf states", 3: "Moscow / East Africa", 3.5: "Iran",
            2: "Central Europe", 1: "Western Europe", 0: "UK / Portugal",
            -5: "US Eastern", -6: "US Central", -8: "US Pacific",
            8: "China / Singapore", 9: "Japan / Korea", 7: "SE Asia",
            -3: "Brazil / Argentina", 11: "Eastern Australia",
        }
        near = [name for o, name in regions.items() if _circular_distance(o, off) <= band]
        return {"offset": off, "confidence": round(conf, 3), "band": band,
                "regions": near, "n_posts": self.n_posts.get(pid, 0)}

    # -- linkage ------------------------------------------------------------

    def score(self, a: str, b: str) -> RawScore:
        if a not in self.hist or b not in self.hist:
            return NULL
        if min(self.n_posts.get(a, 0), self.n_posts.get(b, 0)) < self.MIN_POSTS:
            return RawScore(0.0, "too few posts for a stable circadian profile", [])

        ha, hb = self.hist[a], self.hist[b]
        # shape agreement, corrected for the fact that any two human profiles
        # overlap somewhat; subtracting the uniform baseline removes that floor
        u = np.full(24, 1 / 24)
        ca, cb = ha - u, hb - u
        denom = np.linalg.norm(ca) * np.linalg.norm(cb)
        shape = float(np.dot(ca, cb) / denom) if denom > 0 else 0.0

        oa, ob = self.offset[a], self.offset[b]
        tz_gap = _circular_distance(oa, ob)
        tz_agree = math.exp(-tz_gap / 3.0)
        # a shared timezone only counts to the extent both estimates are solid
        tz_agree *= min(self.offset_conf[a], self.offset_conf[b])

        dw = float(np.dot(self.dow[a], self.dow[b]) /
                   (np.linalg.norm(self.dow[a]) * np.linalg.norm(self.dow[b]) + 1e-12))

        score = 0.55 * max(0.0, shape) + 0.30 * tz_agree + 0.15 * max(0.0, dw - 0.9) * 10

        return RawScore(
            max(0.0, min(1.0, score)),
            "circadian shape corr %.3f; inferred offsets UTC%+g vs UTC%+g "
            "(%.1fh apart)" % (shape, oa, ob, tz_gap),
            ["shape_corr=%.4f" % shape, "offset_a=%+g" % oa, "offset_b=%+g" % ob,
             "offset_conf=%.2f/%.2f" % (self.offset_conf[a], self.offset_conf[b])],
        )
