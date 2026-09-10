"""Authorship attribution from writing style.

Three views of a persona corpus, because no single one is robust on its own:

  1. character 4-grams   catches sub-lexical habit: spelling, leet, spacing,
                         punctuation runs. Survives topic change and is the
                         strongest single feature in the authorship literature.
  2. function words      the classic Burrows approach. Content-independent, so
                         it does not collapse when two personas sell different
                         things on different boards.
  3. structural markers  sentence length, comma rate, casing, contraction and
                         British/American spelling preference. Cheap, and very
                         legible to an analyst in a report.

Defusing the copy-paste trap
----------------------------
Verbatim reposting is common on these forums (mirror lists, scam warnings,
canned vendor replies). If persona B pastes persona A text, a naive stylometric
comparison reports a near-perfect match between two unrelated people. We
therefore split the signal in two:

  * `style`     computed only over each persona's *non-duplicated* posts, so
                pasted text cannot manufacture a style match;
  * `verbatim`  reported separately as its own weak channel, because copied
                text genuinely is ambiguous evidence: it happens both when one
                person runs two accounts and when one stranger quotes another.

Keeping them apart is the difference between an engine that fails the trap and
one that reports it accurately.
"""

from __future__ import annotations

import hashlib
import math
import re

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from .base import CorpusView, Engine, RawScore, NULL

FUNCTION_WORDS = [
    "the", "a", "an", "of", "and", "to", "in", "that", "it", "is", "was", "for",
    "with", "as", "but", "so", "just", "really", "actually", "however",
    "though", "anyway", "basically", "honestly", "obviously", "still", "yet",
    "i", "my", "me", "you", "your", "we", "they", "this", "these", "there",
    "not", "no", "now", "then", "when", "if", "or", "on", "at", "by", "from",
    "has", "have", "had", "been", "will", "would", "can", "cannot", "do", "did",
]

BRITISH = re.compile(r"\b\w+(?:ise|isation|our)\b")
AMERICAN = re.compile(r"\b\w+(?:ize|ization|or)\b")
CONTRACTED = re.compile(r"\b(?:dont|cant|hasnt|isnt|wasnt|ive|its|thats|wont)\b")


def _structural(text: str) -> np.ndarray:
    """Twelve interpretable habit features, all rates so length cancels out."""
    n = max(1, len(text))
    words = text.split()
    nw = max(1, len(words))
    sents = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    lens = [len(s.split()) for s in sents] or [0]
    alpha = [c for c in text if c.isalpha()] or ["a"]
    return np.array([
        len(lens) / nw,                                  # sentence density
        float(np.mean(lens)),                            # mean sentence length
        float(np.std(lens)),                             # burstiness
        text.count(",") / nw,
        text.count("...") / nw,
        text.count("!") / nw,
        text.count("?") / nw,
        text.count("  ") / n,                            # double spacing habit
        sum(c.isupper() for c in alpha) / len(alpha),     # casing habit
        sum(c.isdigit() for c in text) / n,               # digits vs number words
        len(CONTRACTED.findall(text)) / nw,
        (len(BRITISH.findall(text)) - len(AMERICAN.findall(text))) / nw,
    ], dtype=float)


def _cosine(u: np.ndarray, v: np.ndarray) -> float:
    du, dv = np.linalg.norm(u), np.linalg.norm(v)
    if du == 0 or dv == 0:
        return 0.0
    return float(np.dot(u, v) / (du * dv))


class StylometryEngine(Engine):
    channel = "stylometry"

    MIN_WORDS = 120   # below this a style profile is noise, so we abstain

    def __init__(self) -> None:
        self.char_vecs: dict[str, np.ndarray] = {}
        self.fw_vecs: dict[str, np.ndarray] = {}
        self.struct: dict[str, np.ndarray] = {}
        self.word_counts: dict[str, int] = {}

    def fit(self, view: CorpusView) -> None:
        # --- strip verbatim duplicates shared across personas ---------------
        seen: dict[str, set[str]] = {}
        for pid, posts in view.posts_by_persona.items():
            for p in posts:
                h = hashlib.md5(p.text.strip().lower().encode()).hexdigest()
                seen.setdefault(h, set()).add(pid)
        shared = {h for h, owners in seen.items() if len(owners) > 1}

        docs, ids = [], []
        for pid, posts in view.posts_by_persona.items():
            kept = [p.text for p in posts
                    if hashlib.md5(p.text.strip().lower().encode()).hexdigest() not in shared]
            blob = "\n".join(kept)
            docs.append(blob)
            ids.append(pid)
            self.word_counts[pid] = len(blob.split())

        # --- character n-grams ----------------------------------------------
        char_tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                     min_df=3, max_features=20000, sublinear_tf=True)
        cm = char_tfidf.fit_transform(docs)

        # Project to a few hundred latent dimensions before comparing. Two
        # reasons, and the second is the important one: densifying a 20k-column
        # matrix costs O(personas x 20000) memory and does not survive contact
        # with a real corpus, whereas the truncated SVD is computed once and
        # leaves every downstream comparison cheap. It also denoises -- most of
        # those columns are n-grams seen in a handful of posts.
        k = max(2, min(200, min(cm.shape) - 1))
        cm = TruncatedSVD(n_components=k, random_state=0).fit_transform(cm)
        # centre on the corpus mean: what matters is deviation from how the
        # *population* writes, not vocabulary shared across the whole domain
        cm = cm - cm.mean(axis=0, keepdims=True)

        # --- function words, z-scored (this is Burrows Delta) ---------------
        fw = np.zeros((len(docs), len(FUNCTION_WORDS)))
        for i, d in enumerate(docs):
            toks = re.findall(r"[a-z]+", d.lower())
            total = max(1, len(toks))
            counts = {w: 0 for w in FUNCTION_WORDS}
            for t in toks:
                if t in counts:
                    counts[t] += 1
            fw[i] = [counts[w] / total for w in FUNCTION_WORDS]
        mu, sd = fw.mean(axis=0), fw.std(axis=0) + 1e-9
        fwz = (fw - mu) / sd

        st = np.array([_structural(d) for d in docs])
        smu, ssd = st.mean(axis=0), st.std(axis=0) + 1e-9
        stz = (st - smu) / ssd

        for i, pid in enumerate(ids):
            self.char_vecs[pid] = cm[i]
            self.fw_vecs[pid] = fwz[i]
            self.struct[pid] = stz[i]

        self._build_impostor_index(cm, ids)

    def _build_impostor_index(self, cm: np.ndarray, ids: list[str]) -> None:
        """Rank-normalise every similarity against a background cohort.

        The impostors method, and the single most useful idea in authorship
        verification. A raw cosine of 0.65 is uninterpretable: some personas
        write so blandly that they sit close to everybody, and for them 0.65 is
        unremarkable, while for a distinctive writer it would be extraordinary.

        So instead of asking how similar A and B are, we ask where B ranks
        among everyone A could have been compared against. A pair only scores
        highly if each is the other's *standout* match, not merely a close one.
        This is what stops bland writers generating a wall of false positives,
        and it is why the channel keeps working against operators who have
        deliberately varied their style.

        Held here as a full matrix, which is fine at benchmark scale; in
        production the cohort would be the blocking candidate set, and the
        method is unchanged.
        """
        norms = np.linalg.norm(cm, axis=1, keepdims=True) + 1e-12
        unit = cm / norms
        sim = unit @ unit.T
        np.fill_diagonal(sim, -np.inf)
        self._sim = sim
        self._index = {pid: i for i, pid in enumerate(ids)}

    def _impostor_rank(self, a: str, b: str) -> float:
        """Fraction of the cohort that `a` resembles less than it resembles `b`.
        1.0 means b is a's closest match in the entire corpus."""
        ia, ib = self._index[a], self._index[b]
        row = self._sim[ia]
        target = row[ib]
        valid = np.isfinite(row)
        n = int(valid.sum()) - 1
        if n <= 0:
            return 0.0
        return float(np.sum(row[valid] < target) / n)

    def score(self, a: str, b: str) -> RawScore:
        if a not in self.char_vecs or b not in self.char_vecs:
            return NULL
        if min(self.word_counts.get(a, 0), self.word_counts.get(b, 0)) < self.MIN_WORDS:
            return RawScore(0.0, "insufficient unique text to profile style", [])

        c = _cosine(self.char_vecs[a], self.char_vecs[b])
        # Burrows Delta is a distance; map to a similarity on a comparable scale
        delta = float(np.mean(np.abs(self.fw_vecs[a] - self.fw_vecs[b])))
        d_sim = math.exp(-delta)
        s_dist = float(np.linalg.norm(self.struct[a] - self.struct[b]))
        s_sim = math.exp(-s_dist / len(self.struct[a]) ** 0.5)

        # mutual rank: both directions must agree, so a persona that is close
        # to everyone cannot carry a pair on its own
        rank = math.sqrt(max(0.0, self._impostor_rank(a, b))
                         * max(0.0, self._impostor_rank(b, a)))

        score = 0.45 * rank + 0.25 * c + 0.2 * d_sim + 0.1 * s_sim

        # name the two habits that agreed most, so the analyst sees *what*
        # matched rather than an unexplained number
        labels = ["sentence density", "sentence length", "length variance",
                  "comma rate", "ellipsis use", "exclamation use", "question use",
                  "double spacing", "capitalisation", "digit vs word numerals",
                  "contraction rate", "British/American spelling"]
        diffs = np.abs(self.struct[a] - self.struct[b])
        agree = [labels[i] for i in np.argsort(diffs)[:2]]

        return RawScore(
            score,
            "mutual impostor rank %.3f (each is the other's standout match "
            "against the corpus), char n-gram cos %.3f, Burrows delta %.3f, "
            "structural agreement on %s"
            % (rank, c, delta, " and ".join(agree)),
            ["impostor_rank=%.4f" % rank, "char_cosine=%.4f" % c,
             "burrows_delta=%.4f" % delta, "struct_dist=%.4f" % s_dist],
        )


class VerbatimEngine(Engine):
    """Exact reuse of whole posts between two personas.

    Reported separately from style precisely because it is weak evidence: the
    calibration step will learn from data that this channel is roughly as
    common among unrelated personas as among the same actor, and assign it a
    log LR near zero rather than letting it contaminate stylometry.
    """

    channel = "verbatim"

    def __init__(self) -> None:
        self.hashes: dict[str, set[str]] = {}

    def fit(self, view: CorpusView) -> None:
        for pid, posts in view.posts_by_persona.items():
            self.hashes[pid] = {
                hashlib.md5(p.text.strip().lower().encode()).hexdigest() for p in posts
            }

    def score(self, a: str, b: str) -> RawScore:
        ha, hb = self.hashes.get(a, set()), self.hashes.get(b, set())
        if not ha or not hb:
            return NULL
        inter = len(ha & hb)
        if inter == 0:
            return RawScore(0.0, "no verbatim post reuse", [])
        jac = inter / len(ha | hb)
        return RawScore(jac,
                        "%d posts reproduced verbatim (Jaccard %.3f); note that "
                        "reposting is also normal forum behaviour" % (inter, jac),
                        ["shared_posts=%d" % inter])
