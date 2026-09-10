"""Neural authorship embedding, trained self-supervised.

The hand-crafted stylometry engine compares personas on features somebody chose
in advance: character n-grams, function words, twelve structural habits. It
works, but it can only measure what it was told to look for.

This model learns the representation instead. It is trained to answer a
question whose answer is already visible in the data -- "did these two posts
come from the same account?" -- and the embedding it needs in order to do that
turns out to transfer to the question we actually care about, which is whether
two accounts share an author.

Why this is self-supervised, and why that matters
------------------------------------------------
The training signal is persona identity, which is printed next to every post.
No actor labels are used, so there is nothing to leak: the model can be trained
on the full corpus, or on live crawled data with no ground truth whatsoever,
and the evaluation on held-out actors stays honest. That property is what makes
this deployable. A supervised author-linking model would need labelled
investigations to train on, which is precisely what nobody has.

It also solves the data problem. There are only a few dozen same-actor persona
pairs in the benchmark -- far too few to fit a network. There are tens of
thousands of same-persona *post* pairs. Training at the post level and pooling
to personas turns an impossible sample size into an ample one.

Architecture is deliberately small: a two-layer projection over character
n-gram features, trained with InfoNCE and in-batch negatives. A larger model
would overfit this corpus, and a transformer would need pretraining data we do
not have and could not obtain lawfully for this domain.
"""

from __future__ import annotations

import math

import numpy as np


class AuthorNet:
    """Contrastive post-level author embedding with mean pooling to personas."""

    def __init__(self, dim: int = 128, feat_dim: int = 256, epochs: int = 6,
                 batch: int = 256, lr: float = 2e-3, seed: int = 0,
                 min_posts: int = 6) -> None:
        self.dim = dim
        self.feat_dim = feat_dim
        self.epochs = epochs
        self.batch = batch
        self.lr = lr
        self.seed = seed
        self.min_posts = min_posts
        self.available = False
        self.embeddings: dict = {}
        self.history: list = []
        self._sim = None
        self._index: dict = {}

    # -- training -----------------------------------------------------------

    def fit(self, posts_by_persona: dict) -> "AuthorNet":
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            return self          # degrade silently; the pipeline works without it

        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        # personas with too little text cannot supply a stable positive pair
        usable = {pid: [p.text for p in posts]
                  for pid, posts in posts_by_persona.items()
                  if len(posts) >= self.min_posts}
        if len(usable) < 8:
            return self

        texts, owner = [], []
        for pid, msgs in usable.items():
            for t in msgs:
                texts.append(t)
                owner.append(pid)
        if len(texts) < 200:
            return self

        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3,
                              max_features=30000, sublinear_tf=True)
        x = vec.fit_transform(texts)
        k = max(2, min(self.feat_dim, min(x.shape) - 1))
        svd = TruncatedSVD(n_components=k, random_state=self.seed)
        feats = svd.fit_transform(x).astype("float32")
        feats /= (np.linalg.norm(feats, axis=1, keepdims=True) + 1e-9)

        pids = sorted(usable)
        pid_index = {p: i for i, p in enumerate(pids)}
        labels = np.array([pid_index[o] for o in owner], dtype=np.int64)
        by_label: dict = {}
        for i, l in enumerate(labels):
            by_label.setdefault(int(l), []).append(i)
        # a positive pair needs two posts from the same account
        eligible = [l for l, idxs in by_label.items() if len(idxs) >= 2]
        if len(eligible) < 8:
            return self

        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        device = "cpu"

        net = nn.Sequential(
            nn.Linear(feats.shape[1], 256), nn.ReLU(),
            nn.Linear(256, self.dim),
        ).to(device)
        opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=1e-4)
        xt = torch.from_numpy(feats).to(device)

        # InfoNCE with in-batch negatives. Temperature is low because the
        # feature space is already L2-normalised and the task is fine-grained:
        # many different authors write about the same six topics.
        temperature = 0.07
        steps = max(20, len(texts) // self.batch)

        for epoch in range(self.epochs):
            total = 0.0
            for _ in range(steps):
                chosen = rng.choice(eligible,
                                    size=min(self.batch // 2, len(eligible)),
                                    replace=False)
                ai, bi = [], []
                for l in chosen:
                    i, j = rng.choice(by_label[int(l)], size=2, replace=False)
                    ai.append(i)
                    bi.append(j)
                za = net(xt[ai])
                zb = net(xt[bi])
                za = za / (za.norm(dim=1, keepdim=True) + 1e-9)
                zb = zb / (zb.norm(dim=1, keepdim=True) + 1e-9)

                logits = za @ zb.T / temperature
                target = torch.arange(len(ai), device=device)
                # symmetric: each side must pick the other out of the batch
                loss = 0.5 * (nn.functional.cross_entropy(logits, target)
                              + nn.functional.cross_entropy(logits.T, target))
                opt.zero_grad()
                loss.backward()
                opt.step()
                total += float(loss.item())
            self.history.append(round(total / steps, 4))

        # -- pool posts to personas -----------------------------------------
        net.eval()
        with torch.no_grad():
            z = net(xt)
            z = z / (z.norm(dim=1, keepdim=True) + 1e-9)
            z = z.cpu().numpy()

        for pid in pids:
            idxs = by_label.get(pid_index[pid], [])
            if not idxs:
                continue
            v = z[idxs].mean(axis=0)
            n = np.linalg.norm(v)
            if n > 0:
                self.embeddings[pid] = v / n

        if len(self.embeddings) >= 8:
            self._build_index()
            self.available = True
        return self

    def _build_index(self) -> None:
        """Cohort similarity matrix, for the same rank normalisation the
        hand-crafted engine uses: being close to everyone is not evidence."""
        ids = sorted(self.embeddings)
        m = np.array([self.embeddings[i] for i in ids])
        sim = m @ m.T
        np.fill_diagonal(sim, -np.inf)
        self._sim = sim
        self._index = {pid: i for i, pid in enumerate(ids)}

    # -- inference ----------------------------------------------------------

    def rank(self, a: str, b: str) -> float:
        ia, ib = self._index.get(a), self._index.get(b)
        if ia is None or ib is None or self._sim is None:
            return 0.0
        row = self._sim[ia]
        valid = np.isfinite(row)
        n = int(valid.sum()) - 1
        if n <= 0:
            return 0.0
        return float(np.sum(row[valid] < row[ib]) / n)

    def similarity(self, a: str, b: str) -> float:
        ea, eb = self.embeddings.get(a), self.embeddings.get(b)
        if ea is None or eb is None:
            return 0.0
        return float(np.dot(ea, eb))

    def summary(self) -> dict:
        return {
            "available": self.available,
            "personas_embedded": len(self.embeddings),
            "dim": self.dim,
            "epochs": self.epochs,
            "loss_curve": self.history,
            "training": "self-supervised on persona identity; no actor labels used",
        }
