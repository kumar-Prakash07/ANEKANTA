"""Alias correlation across sites.

People are bad at inventing names. An operator opening a second account under
the same brand, a leet variant, or the same root with a different suffix is one
of the oldest and most reliable OSINT signals, and it is the one an analyst can
verify by eye in a courtroom.

The engine normalises away the transformations operators actually apply
(leetspeak, separators, numeric suffixes, camel casing) and then compares what
is left. Two safeguards keep this from being naive string matching:

  substring rarity   "moth" matching inside "mothership" means nothing if the
                     token is common across the corpus, so agreement is
                     weighted by how unusual the shared root is;
  length floor       three-character roots collide by chance constantly and are
                     scored down accordingly.

Contact identifiers (XMPP/Jabber, Session, Telegram) are folded in here rather
than given their own channel, because they are the same kind of evidence: a
string the operator chose and then reused.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from .base import CorpusView, Engine, RawScore, NULL, rarity_weight

LEET_UNMAP = str.maketrans({"4": "a", "3": "e", "0": "o", "1": "i", "5": "s",
                            "7": "t", "8": "b", "$": "s", "@": "a"})

# Handle decorations that carry no identity information.
NOISE_AFFIX = re.compile(
    r"^(?:the|mr|mrs|dr|x|xx|official)|(?:official|hq|v\d|alt|real|x|xx|\d{1,4})$"
)


def normalise(handle: str) -> str:
    """Strip decoration, then undo leetspeak. Order matters.

    Doing it the other way round translates the digits of a numeric suffix
    into letters before anything can recognise them as a suffix, so
    `nightowl_42` normalises to `nightowla` and stops matching `nightowl`.
    Numeric suffixes are the single most common handle decoration there is, so
    that ordering silently costs real linkages.
    """
    h = re.sub(r"[^a-z0-9]+", "", handle.lower())
    prev = None
    while prev != h:                       # strip stacked decorations
        prev = h
        h = NOISE_AFFIX.sub("", h)
    return h.translate(LEET_UNMAP)


class HandleEngine(Engine):
    channel = "handle"

    MIN_ROOT_LEN = 4

    def __init__(self) -> None:
        self.norm: dict[str, str] = {}
        self.raw: dict[str, str] = {}
        self.contacts: dict[str, set[str]] = {}
        self.ngram_df: Counter = Counter()
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.n_personas = len(view.personas)
        for p in view.personas:
            self.raw[p.persona_id] = p.handle
            self.norm[p.persona_id] = normalise(p.handle)
            self.contacts[p.persona_id] = {c.lower() for c in p.contact_handles}

        # document frequency of character 4-grams, so we can tell a distinctive
        # shared root from a common one
        for n in self.norm.values():
            for g in {n[i:i + 4] for i in range(max(0, len(n) - 3))}:
                self.ngram_df[g] += 1

    def _root_rarity(self, s: str) -> float:
        """1.0 when the shared substring is unique to these two personas."""
        grams = {s[i:i + 4] for i in range(max(0, len(s) - 3))}
        if not grams:
            return 0.0
        worst = max(self.ngram_df.get(g, 1) for g in grams)
        return rarity_weight(worst, self.n_personas)

    def score(self, a: str, b: str) -> RawScore:
        na, nb = self.norm.get(a), self.norm.get(b)
        if not na or not nb:
            return NULL

        # contact identifiers first: an exact reuse is much stronger than any
        # fuzzy handle resemblance
        shared_contacts = self.contacts.get(a, set()) & self.contacts.get(b, set())
        if shared_contacts:
            c = sorted(shared_contacts)[0]
            return RawScore(0.98, "identical contact identifier %s" % c,
                            ["contact=%s" % c])

        jw = JaroWinkler.similarity(na, nb)
        pr = fuzz.partial_ratio(na, nb) / 100.0

        # containment, the most common real pattern (root plus decoration)
        short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
        contained = short in long_ and len(short) >= self.MIN_ROOT_LEN

        base = max(jw, 0.9 * pr) if not contained else max(0.9, jw)
        rarity = self._root_rarity(short if contained else na)
        length_penalty = min(1.0, math.log1p(min(len(na), len(nb))) / math.log(9))

        score = base * (0.35 + 0.65 * rarity) * length_penalty

        why = []
        if contained:
            why.append("normalised root %s contained in %s" % (short, long_))
        why.append("Jaro-Winkler %.3f on %s vs %s" % (jw, na, nb))
        if rarity < 0.5:
            why.append("shared substring is common in the corpus, discounted")

        return RawScore(min(1.0, score), "; ".join(why),
                        ["handle_a=%s" % self.raw[a], "handle_b=%s" % self.raw[b],
                         "norm_a=%s" % na, "norm_b=%s" % nb,
                         "root_rarity=%.2f" % rarity])
