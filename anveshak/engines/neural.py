"""Neural authorship channel.

Wraps AuthorNet in the standard engine contract so the learned representation
competes on exactly the same terms as every hand-crafted channel: it produces a
raw score, gets calibrated against held-out actors, and earns whatever weight
the fusion gives it. Nothing about it is privileged for being a neural network.

It is kept as a separate channel from `stylometry` rather than replacing it,
for two reasons. The ablation then shows what the learned model adds over
hand-crafted features, which is the honest comparison. And the hand-crafted
channel remains explainable to a court in a way an embedding is not -- an
analyst can point at a comma rate, but "cosine 0.71 in a learned space" is not
an argument anyone can cross-examine. Having both means the system does not
have to choose between accuracy and defensibility.
"""

from __future__ import annotations

import math

from ..ai.author_net import AuthorNet
from .base import CorpusView, Engine, RawScore, NULL


class NeuralAuthorshipEngine(Engine):
    channel = "authorship"

    def __init__(self, epochs: int = 6, seed: int = 0) -> None:
        self.net = AuthorNet(epochs=epochs, seed=seed)
        self.enabled = False

    def fit(self, view: CorpusView) -> None:
        self.net.fit(view.posts_by_persona)
        self.enabled = self.net.available

    def score(self, a: str, b: str) -> RawScore:
        if not self.enabled:
            return NULL
        if a not in self.net.embeddings or b not in self.net.embeddings:
            return NULL

        cos = self.net.similarity(a, b)
        rank = math.sqrt(max(0.0, self.net.rank(a, b))
                         * max(0.0, self.net.rank(b, a)))
        # The rank dominates for the same reason it does in the hand-crafted
        # engine: raw cosine is inflated for bland writers who sit near
        # everybody, and mutual rank asks the sharper question of whether each
        # is the other's standout match.
        score = 0.65 * rank + 0.35 * max(0.0, cos)

        return RawScore(
            min(1.0, score),
            "learned author embedding: cosine %.3f, mutual cohort rank %.3f "
            "(self-supervised on persona identity, no actor labels)"
            % (cos, rank),
            ["neural_cosine=%.4f" % cos, "neural_rank=%.4f" % rank],
        )

    def summary(self) -> dict:
        return self.net.summary()
