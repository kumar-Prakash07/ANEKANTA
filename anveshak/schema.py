"""Core data model for ANEKANTA.

Everything the platform reasons about is one of four things:

  Persona   an account/handle observed on one site (what we can see)
  Actor     the human behind one or more personas (what we want to find)
  Signal    a typed observable attached to a persona (post text, wallet, PGP key, ...)
  Evidence  the output of one engine comparing two personas, expressed as a
            likelihood ratio so that channels can be fused honestly.

The Evidence type is deliberately the narrow waist of the system: every engine,
no matter how different its internals, must reduce its finding to
(score, likelihood_ratio, human-readable rationale, supporting signal ids).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


# --------------------------------------------------------------------------
# Observables
# --------------------------------------------------------------------------

@dataclass
class Post:
    """A unit of authored text observed on a dark-web forum or market."""

    post_id: str
    persona_id: str
    site: str
    timestamp: datetime          # always stored UTC
    text: str
    thread: str = ""

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class Persona:
    """An observed identity on a single site. This is the node we cluster."""

    persona_id: str
    handle: str
    site: str
    first_seen: datetime
    last_seen: datetime

    # --- signals -----------------------------------------------------------
    pgp_fingerprint: str | None = None
    pgp_uid: str | None = None
    pgp_created: datetime | None = None
    btc_addresses: list[str] = field(default_factory=list)
    onion_services: list[str] = field(default_factory=list)
    infra_fingerprints: dict[str, str] = field(default_factory=dict)   # jarm/ssh/header
    # Richer service fingerprint: TLS certificate metadata, CSS class
    # vocabulary, asset hashes, perceptual favicon hash. Kept separate from
    # `infra_fingerprints` because those are exact-match strings compared by
    # equality, whereas these need structured or fuzzy comparison -- a
    # perceptual hash is compared by Hamming distance, a class vocabulary by
    # Jaccard overlap, a validity window by how far apart two dates are.
    service: dict = field(default_factory=dict)
    image_hashes: list[str] = field(default_factory=list)              # perceptual hashes
    exif_devices: list[str] = field(default_factory=list)
    contact_handles: list[str] = field(default_factory=list)           # jabber/telegram/session

    # --- ground truth, only populated for benchmark corpora ----------------
    true_actor: str | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("first_seen", "last_seen", "pgp_created"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------

# Cap applied to every channel's log10 LR. No single observable may on its own
# assert near-certainty; this is both statistically honest (our LR estimates are
# themselves uncertain in the tails) and a legal safeguard.
LOG10_LR_CAP = 4.0

# Floor on how much a *rotatable artefact* is allowed to argue against a link
# when it simply is not there.
#
# The reasoning is a reference-population problem, and it is the subtlest issue
# in the system. P(no shared PGP key | same actor) depends almost entirely on
# how disciplined that actor is, which is a latent variable we never observe.
# Calibrating it against a mixed population yields one number that is too
# negative for the careful operator and not negative enough for the careless
# one -- and the careful operator is the case that matters. Left uncapped, an
# operator who rotates every key, wallet, host and handle accumulates negative
# evidence from each rotation and is pushed *below* two strangers, which
# rewards tradecraft precisely where it should not.
#
# So a null observation on something an operator can rotate at will is allowed
# to count only weakly against them. Behavioural channels are not capped: a
# genuine mismatch in circadian rhythm or writing style is real evidence of
# difference, because those are not switches an operator can simply flip.
LOG10_LR_ARTEFACT_NEG_CAP = 0.5

ROTATABLE_ARTEFACT_CHANNELS = frozenset(
    {"pgp", "crypto", "handle", "infra", "device", "verbatim",
     "favicon", "tls", "template"})


@dataclass
class Evidence:
    """One engine's comparison of a persona pair.

    score            raw engine similarity, comparable only within a channel
    log10_lr         log10 P(score | same actor) / P(score | different actors)
    rationale        analyst-facing sentence explaining the finding
    supporting       ids/values the analyst can go and verify by hand
    """

    channel: str
    persona_a: str
    persona_b: str
    score: float
    log10_lr: float
    rationale: str
    supporting: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.log10_lr = max(-LOG10_LR_CAP, min(LOG10_LR_CAP, float(self.log10_lr)))

    @property
    def verbal(self) -> str:
        """ENFSI-style verbal scale. Judges and courts read words, not logs."""
        v = abs(self.log10_lr)
        if v < 0.3:
            return "uninformative"
        band = ("weak" if v < 1 else
                "moderate" if v < 2 else
                "strong" if v < 3 else
                "very strong")
        return f"{band} support for {'same' if self.log10_lr > 0 else 'different'} actor"

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["verbal"] = self.verbal
        return d


@dataclass
class LinkHypothesis:
    """Fused claim that two personas are operated by the same actor."""

    persona_a: str
    persona_b: str
    log10_lr: float
    posterior: float
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def channels(self) -> list[str]:
        return [e.channel for e in self.evidence if abs(e.log10_lr) >= 0.3]

    @property
    def verbal(self) -> str:
        v = self.log10_lr
        if v < 1:
            return "insufficient"
        if v < 2:
            return "investigative lead"
        if v < 3:
            return "corroborated linkage"
        return "high-confidence linkage"

    def to_json(self) -> dict[str, Any]:
        return {
            "persona_a": self.persona_a,
            "persona_b": self.persona_b,
            "log10_lr": round(self.log10_lr, 3),
            "posterior": round(self.posterior, 5),
            "verbal": self.verbal,
            "channels": self.channels,
            "evidence": [e.to_json() for e in self.evidence],
        }


def posterior_from_log10_lr(log10_lr: float, prior_odds: float) -> float:
    """Bayes in odds form. prior_odds is the analyst's stated prior, and it is
    an explicit input rather than a hidden constant precisely because the
    defensibility of the output depends on it being stated."""
    log_odds = math.log10(prior_odds) + log10_lr
    log_odds = max(-12.0, min(12.0, log_odds))
    odds = 10.0 ** log_odds
    return odds / (1.0 + odds)
