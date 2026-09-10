"""Common contract for evidence engines.

Every engine sees the same corpus view and must answer one question about a
pair of personas: how similar are they on my channel, and why. Engines return
raw scores only. Converting a score into a likelihood ratio is deliberately
*not* an engine responsibility -- that happens once, centrally, in
fusion.lr, against held-out data. Engines that invent their own confidence
numbers are how attribution systems end up uncalibrated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from ..schema import Persona, Post


@dataclass
class CorpusView:
    """Everything an engine is allowed to see. Notably absent: true_actor."""

    personas: list[Persona]
    posts_by_persona: dict[str, list[Post]]
    transactions: list[dict]

    @property
    def ids(self) -> list[str]:
        return [p.persona_id for p in self.personas]

    def by_id(self) -> dict[str, Persona]:
        return {p.persona_id: p for p in self.personas}


@dataclass
class RawScore:
    score: float
    rationale: str
    supporting: list[str]


NULL = RawScore(0.0, "no comparable data on this channel", [])


class Engine:
    """Base class. Subclasses set `channel` and implement fit/score."""

    channel: str = "base"

    def fit(self, view: CorpusView) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def score(self, a: str, b: str) -> RawScore:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Rarity weighting
# ---------------------------------------------------------------------------
#
# The single most important idea in this system. Two personas sharing a value
# is only interesting in proportion to how *unusual* that value is in the
# population. A PGP fingerprint held by one other persona is near-conclusive; a
# JARM hash shared by forty personas on the same bulletproof host says nothing
# about who runs them. Formally this is the typicality term of a likelihood
# ratio, and implementing it is what makes the shared-host and mixer traps
# survivable.

def rarity_weight(n_holders: int, population: int) -> float:
    """Return a value in [0, 1]: 1 when a value is unique to the pair, decaying
    toward 0 as more of the population shares it.

    Derivation: if k personas out of N share a value, then picking a second
    persona at random that also has it has probability ~(k-1)/(N-1). The
    informativeness of the coincidence is the surprisal of that probability,
    normalised against the most surprising case (k = 2).
    """
    if n_holders <= 1 or population <= 2:
        return 0.0
    p_chance = (n_holders - 1) / (population - 1)
    p_best = 1 / (population - 1)
    return max(0.0, min(1.0, math.log(p_chance) / math.log(p_best)))


def index_values(values_by_id: dict[str, Iterable[str]]) -> dict[str, set[str]]:
    """Invert {persona: values} into {value: {personas}} for rarity lookups."""
    idx: dict[str, set[str]] = {}
    for pid, vals in values_by_id.items():
        for v in vals:
            if v:
                idx.setdefault(v, set()).add(pid)
    return idx
