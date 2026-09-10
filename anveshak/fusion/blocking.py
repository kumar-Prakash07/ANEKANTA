"""Candidate generation.

Comparing every persona against every other is quadratic. At the 114 personas
of the benchmark that is 6,441 comparisons and nobody notices; at the scale
NTRO would actually run this -- millions of scraped accounts -- it is
10^12 comparisons and the system does not exist.

So scoring is preceded by blocking: cheap indexes that propose a small
candidate set, which the expensive engines then adjudicate. Two families:

  exact-match indexes   invert the corpus on PGP fingerprint, wallet cluster,
                        onion address, image hash, contact identifier and rare
                        infrastructure prints. O(n) to build, O(1) to probe.
                        High-value buckets are capped, since a fingerprint held
                        by 10,000 personas is a service artefact, not a lead.

  approximate neighbours  stylometry and handles have no exact key, so we take
                        top-k nearest neighbours in the respective vector
                        spaces. This is the part that would become LSH or a
                        vector index in production; the interface does not
                        change.

The measure that matters is not how few candidates we produce but the pair of
numbers reported together: reduction ratio (how much work we avoided) and pair
completeness (how many true links we would have thrown away). A blocker that
discards true links is buying speed with cases.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..engines.base import CorpusView

# A bucket bigger than this is a shared artefact, not a lead. Emitting its
# O(k^2) pairs would both flood the scorer and, per the rarity argument,
# produce only weak evidence anyway.
MAX_BUCKET = 25

TOPK_STYLE = 34
TOPK_HANDLE = 12


def _pairs_from_buckets(buckets: dict[str, set[str]], out: set, why: dict) -> None:
    for key, members in buckets.items():
        if len(members) < 2 or len(members) > MAX_BUCKET:
            continue
        ms = sorted(members)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                pair = (ms[i], ms[j])
                out.add(pair)
                why.setdefault(pair, set()).add(key.split(":", 1)[0])


def generate_candidates(view: CorpusView, engines: dict) -> tuple[set, dict, dict]:
    """Return (candidate_pairs, reasons_by_pair, diagnostics)."""
    pairs: set = set()
    why: dict = {}

    # ---- exact-match indexes ----------------------------------------------
    buckets: dict[str, set[str]] = defaultdict(set)
    for p in view.personas:
        if p.pgp_fingerprint:
            buckets["pgp:" + p.pgp_fingerprint].add(p.persona_id)
        for o in p.onion_services:
            buckets["onion:" + o].add(p.persona_id)
        for h in p.image_hashes:
            buckets["phash:" + h].add(p.persona_id)
        for c in p.contact_handles:
            buckets["contact:" + c.lower()].add(p.persona_id)
        for kind in ("ssh_hostkey", "jarm"):
            v = p.infra_fingerprints.get(kind)
            if v:
                buckets["infra:%s=%s" % (kind, v)].add(p.persona_id)

    crypto = engines.get("crypto")
    if crypto is not None:
        for pid, clusters in crypto.persona_clusters.items():
            for c in clusters:
                buckets["wallet:" + c].add(pid)

    _pairs_from_buckets(buckets, pairs, why)

    # ---- approximate neighbours: stylometry -------------------------------
    style = engines.get("stylometry")
    if style is not None and style.char_vecs:
        ids = sorted(style.char_vecs)
        m = np.array([style.char_vecs[i] for i in ids])
        norms = np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
        sim = (m / norms) @ (m / norms).T
        np.fill_diagonal(sim, -np.inf)
        k = min(TOPK_STYLE, len(ids) - 1)
        for i, pid in enumerate(ids):
            for j in np.argpartition(-sim[i], k - 1)[:k]:
                pair = tuple(sorted((pid, ids[j])))
                pairs.add(pair)
                why.setdefault(pair, set()).add("style")

    # ---- behavioural bucket: inferred timezone ----------------------------
    # Disciplined operators rotate every artefact index above and fall out of
    # all of them. Bucketing on the estimated UTC offset is the one cheap key
    # that still catches them, which is why it is here and not treated as an
    # afterthought.
    temporal = engines.get("temporal")
    if temporal is not None and temporal.offset:
        tz_buckets: dict[str, set[str]] = defaultdict(set)
        for pid, off in temporal.offset.items():
            if temporal.offset_conf.get(pid, 0.0) < 0.35:
                continue                      # no rhythm, no claim
            for delta in (-0.5, 0.0, 0.5):    # tolerate estimation error
                tz_buckets["tz:%g" % (round((off + delta) * 2) / 2)].add(pid)
        _pairs_from_buckets(tz_buckets, pairs, why)

    # ---- approximate neighbours: handles ----------------------------------
    handle = engines.get("handle")
    if handle is not None and handle.norm:
        gram_index: dict[str, set[str]] = defaultdict(set)
        for pid, n in handle.norm.items():
            for g in {n[i:i + 3] for i in range(max(0, len(n) - 2))}:
                gram_index[g].add(pid)
        overlap: dict[tuple, int] = defaultdict(int)
        for g, members in gram_index.items():
            if len(members) > MAX_BUCKET:
                continue
            ms = sorted(members)
            for i in range(len(ms)):
                for j in range(i + 1, len(ms)):
                    overlap[(ms[i], ms[j])] += 1
        by_pid: dict[str, list] = defaultdict(list)
        for (x, y), c in overlap.items():
            by_pid[x].append((c, y))
            by_pid[y].append((c, x))
        for pid, cand in by_pid.items():
            for _, other in sorted(cand, reverse=True)[:TOPK_HANDLE]:
                pair = tuple(sorted((pid, other)))
                pairs.add(pair)
                why.setdefault(pair, set()).add("handle")

    n = len(view.personas)
    total = n * (n - 1) // 2
    diagnostics = {
        "personas": n,
        "all_pairs": total,
        "candidate_pairs": len(pairs),
        "reduction_ratio": round(1 - len(pairs) / max(1, total), 4),
    }
    return pairs, {k: sorted(v) for k, v in why.items()}, diagnostics


def pair_completeness(candidates: set, truth: dict) -> dict:
    """What fraction of genuine links survived blocking. The number that decides
    whether the speed-up was free or was paid for in missed cases."""
    by_actor: dict[str, list[str]] = defaultdict(list)
    for pid, actor in truth.items():
        by_actor[actor].append(pid)
    true_pairs = set()
    for members in by_actor.values():
        ms = sorted(members)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                true_pairs.add((ms[i], ms[j]))
    kept = len(true_pairs & candidates)
    return {
        "true_pairs": len(true_pairs),
        "true_pairs_retained": kept,
        "pair_completeness": round(kept / max(1, len(true_pairs)), 4),
        "missed": sorted(true_pairs - candidates)[:10],
    }
