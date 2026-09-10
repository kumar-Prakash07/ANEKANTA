"""PGP key correlation.

Vendors publish a public key so buyers can encrypt to them, which makes the key
the one artefact an operator cannot hide and often cannot afford to change: a
rotated key breaks trust with every existing customer and is publicly visible
as a break in continuity. That commercial pressure is what makes this channel
strong.

It is not automatic, though. Disciplined actors do rotate per persona, and this
engine must return an honest "no signal" in that case rather than reaching for
something weaker. So beyond the fingerprint we look at two softer traces that
survive rotation:

  uid similarity   the name and address a key is bound to, which operators
                   reuse out of habit even when they generate fresh keys;
  creation timing  keys generated in the same sitting, which is what setting up
                   several personas at once actually looks like.

Both are weak individually and are scored as such; the fusion stage decides
what they are worth.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .base import CorpusView, Engine, RawScore, NULL, index_values, rarity_weight

# Free/anonymous mail providers are near-universal here, so a domain match
# between two personas carries essentially no information and is excluded from
# the UID comparison.
COMMON_DOMAINS = {"protonmail.com", "tutanota.com", "cock.li", "riseup.net",
                  "danwin1210.de", "elude.in", "onionmail.org", "mail2tor.com"}

# Two keys made within this window look like one setup session rather than two
# unrelated people happening to generate keys the same week.
SAME_SESSION_HOURS = 48


def _uid_parts(uid: str | None) -> tuple[str, str, str]:
    if not uid:
        return "", "", ""
    m = re.match(r"\s*(.*?)\s*<([^@>]+)@([^>]+)>", uid)
    if m:
        return m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
    return uid.strip().lower(), "", ""


class PGPEngine(Engine):
    channel = "pgp"

    def __init__(self) -> None:
        self.by_id: dict = {}
        self.fp_index: dict[str, set[str]] = {}
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.by_id = view.by_id()
        self.n_personas = len(view.personas)
        self.fp_index = index_values(
            {p.persona_id: [p.pgp_fingerprint] for p in view.personas}
        )

    def score(self, a: str, b: str) -> RawScore:
        pa, pb = self.by_id.get(a), self.by_id.get(b)
        if pa is None or pb is None or not pa.pgp_fingerprint or not pb.pgp_fingerprint:
            return NULL

        if pa.pgp_fingerprint == pb.pgp_fingerprint:
            holders = len(self.fp_index.get(pa.pgp_fingerprint, ()))
            # a key published by half the market is a shared team key, not an
            # individual; rarity weighting catches that automatically
            w = rarity_weight(holders, self.n_personas)
            return RawScore(min(1.0, 0.8 + 0.2 * w),
                            "identical PGP fingerprint %s (held by %d personas)"
                            % (pa.pgp_fingerprint[:16], holders),
                            ["fingerprint=%s" % pa.pgp_fingerprint,
                             "holders=%d" % holders])

        # --- rotated keys: fall back to the softer traces -------------------
        na, la, da = _uid_parts(pa.pgp_uid)
        nb, lb, db = _uid_parts(pb.pgp_uid)
        bits, notes = [], []

        if la and lb:
            s = fuzz.ratio(la, lb) / 100.0
            bits.append(0.6 * s)
            if s > 0.7:
                notes.append("key UID local-parts %s / %s similar (%.2f)" % (la, lb, s))
        if na and nb:
            s = fuzz.token_sort_ratio(na, nb) / 100.0
            bits.append(0.25 * s)
        if da and db and da == db and da not in COMMON_DOMAINS:
            bits.append(0.15)
            notes.append("shared uncommon key domain %s" % da)

        if pa.pgp_created and pb.pgp_created:
            gap = abs((pa.pgp_created - pb.pgp_created).total_seconds()) / 3600.0
            if gap <= SAME_SESSION_HOURS:
                bits.append(0.35 * (1 - gap / SAME_SESSION_HOURS))
                notes.append("keys generated %.1fh apart, consistent with one "
                             "setup session" % gap)

        if not bits:
            return RawScore(0.0, "different PGP keys, no secondary key traces", [])

        score = min(0.75, sum(bits))     # capped: never as strong as a real match
        return RawScore(score,
                        "distinct fingerprints (key rotation); " +
                        ("; ".join(notes) if notes else "no secondary traces"),
                        ["fp_a=%s" % pa.pgp_fingerprint[:16],
                         "fp_b=%s" % pb.pgp_fingerprint[:16]])
