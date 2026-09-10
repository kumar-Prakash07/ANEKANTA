"""Blockchain clustering: linking personas through the wallets they expose.

The workhorse is common-input-ownership -- when several addresses are spent
together in one transaction, one key holder almost certainly signed for all of
them. Applied naively that heuristic is catastrophic on real chains, because
mixers, exchanges and payment processors co-spend with thousands of unrelated
customers and a single union-find pass welds most of the graph into one blob.

So the engine runs in three passes:

  1. build the co-spend graph;
  2. detect and quarantine service addresses, using counterparty diversity
     rather than a hardcoded blocklist, so it generalises to services nobody
     has labelled yet;
  3. cluster on the remaining edges, and discount any linkage by the size of
     the cluster that produced it.

Step 3 matters as much as step 2: being in a two-address cluster with someone
is strong evidence, being in a four-hundred-address cluster is not, and the
rarity weighting encodes that difference instead of leaving it to the analyst.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .base import CorpusView, Engine, RawScore, NULL, rarity_weight


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:            # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class CryptoEngine(Engine):
    channel = "crypto"

    # An address co-spending with more than this many distinct counterparties
    # is behaving like a service, not a personal wallet. Tuned as a multiple of
    # the corpus median so it adapts to graph density instead of being a magic
    # constant that only works on one dataset.
    SERVICE_DIVERSITY_MULTIPLE = 6.0
    SERVICE_DIVERSITY_FLOOR = 8

    def __init__(self) -> None:
        self.cluster_of: dict[str, str] = {}          # address -> cluster id
        self.persona_clusters: dict[str, set[str]] = {}
        self.cluster_size: dict[str, int] = {}
        self.services: set[str] = set()
        self.addr_owners: dict[str, set[str]] = {}    # address -> personas
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.n_personas = len(view.personas)

        # ---- pass 1: co-spend counterparty diversity -----------------------
        partners: dict[str, set[str]] = defaultdict(set)
        for tx in view.transactions:
            ins = tx.get("inputs", [])
            for a in ins:
                for b in ins:
                    if a != b:
                        partners[a].add(b)

        # ---- pass 2: quarantine service addresses --------------------------
        counts = sorted(len(v) for v in partners.values())
        median = counts[len(counts) // 2] if counts else 0
        threshold = max(self.SERVICE_DIVERSITY_FLOOR,
                        self.SERVICE_DIVERSITY_MULTIPLE * max(1, median))
        self.services = {a for a, ps in partners.items() if len(ps) >= threshold}

        # ---- pass 3: cluster on non-service edges --------------------------
        uf = _UnionFind()
        for tx in view.transactions:
            ins = [a for a in tx.get("inputs", []) if a not in self.services]
            for a in ins[1:]:
                uf.union(ins[0], a)

        for p in view.personas:
            for addr in p.btc_addresses:
                uf.find(addr)
                self.addr_owners.setdefault(addr, set()).add(p.persona_id)

        for addr in list(uf.parent):
            self.cluster_of[addr] = uf.find(addr)
        for c in self.cluster_of.values():
            self.cluster_size[c] = self.cluster_size.get(c, 0) + 1

        for p in view.personas:
            self.persona_clusters[p.persona_id] = {
                self.cluster_of[a] for a in p.btc_addresses
                if a in self.cluster_of and a not in self.services
            }

    def diagnostics(self) -> dict:
        """Shown in the UI: quantifies what quarantining the services bought us."""
        sizes = sorted(self.cluster_size.values(), reverse=True)
        return {
            "addresses": len(self.cluster_of),
            "clusters": len(self.cluster_size),
            "service_addresses_quarantined": len(self.services),
            "largest_cluster": sizes[0] if sizes else 0,
            "service_examples": sorted(self.services)[:5],
        }

    def score(self, a: str, b: str) -> RawScore:
        ca = self.persona_clusters.get(a, set())
        cb = self.persona_clusters.get(b, set())
        if not ca or not cb:
            return NULL

        # strongest case: the identical address is published by both personas
        pa = {addr for addr, own in self.addr_owners.items() if a in own}
        pb = {addr for addr, own in self.addr_owners.items() if b in own}
        direct = pa & pb
        if direct:
            addr = sorted(direct)[0]
            w = rarity_weight(len(self.addr_owners[addr]), self.n_personas)
            return RawScore(min(1.0, 0.85 + 0.15 * w),
                            "identical receiving address published by both "
                            "personas (%s...)" % addr[:12],
                            ["shared_address=%s" % addr])

        shared = ca & cb
        if not shared:
            return RawScore(0.0, "no shared wallet cluster", [])

        # a linkage through a huge cluster is a weak linkage
        best = min(self.cluster_size.get(c, 1) for c in shared)
        conf = 1.0 / (1.0 + math.log1p(max(0, best - 2)))
        return RawScore(min(0.95, 0.55 + 0.4 * conf),
                        "wallets fall in a common co-spend cluster of %d "
                        "addresses (service addresses excluded)" % best,
                        ["cluster_size=%d" % best,
                         "clusters=%s" % ",".join(sorted(shared)[:2])])
