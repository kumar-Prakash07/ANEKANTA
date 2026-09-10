"""Identity resolution: from pairwise links to actor clusters and dossiers.

Pairwise linkage is not the deliverable. An analyst wants to know how many
distinct humans are behind a set of accounts and what can be said about each
one, which means turning an edge list into disjoint identities.

The naive route -- threshold the edges and take connected components -- chains
badly. Persona A links to B on stylometry, B links to C on a shared host, and
suddenly A and C are declared the same person on the strength of no evidence
between them at all. Because the traps in the benchmark are designed to create
exactly those bridges, we guard against it in two ways:

  1. a component is accepted only if its internal evidence is dense enough,
     measured as the share of possible internal pairs that actually carry
     support;
  2. below that density the component is split at its weakest link, repeatedly,
     until every surviving cluster is cohesive.

The result is a set of clusters plus, for each, a dossier: the aggregate of
everything the channels learned, including a timezone estimate pooled across
the cluster, which is more precise than any single persona estimate because it
averages more observations of the same underlying rhythm.
"""

from __future__ import annotations

import math
from collections import defaultdict

import networkx as nx

from ..schema import LinkHypothesis


MIN_DENSITY = 0.34   # share of internal pairs that must carry support


def _density(g: nx.Graph, nodes: set) -> float:
    k = len(nodes)
    if k < 3:
        return 1.0
    possible = k * (k - 1) / 2
    return g.subgraph(nodes).number_of_edges() / possible


def resolve(links: list[LinkHypothesis], all_personas: list[str],
            threshold: float = 2.0) -> list[dict]:
    """Cluster personas into actors. `threshold` is in log10 LR."""
    g = nx.Graph()
    g.add_nodes_from(all_personas)
    for l in links:
        if l.log10_lr >= threshold:
            g.add_edge(l.persona_a, l.persona_b, weight=l.log10_lr, link=l)

    clusters: list[set] = []
    queue = [set(c) for c in nx.connected_components(g)]
    while queue:
        comp = queue.pop()
        if len(comp) <= 2 or _density(g, comp) >= MIN_DENSITY:
            clusters.append(comp)
            continue
        # split at the weakest bridge: the edge whose removal disconnects the
        # component at the lowest evidential cost
        sub = g.subgraph(comp).copy()
        bridges = list(nx.bridges(sub))
        if not bridges:
            # no single weak point; fall back to the globally weakest edge
            u, v, _ = min(sub.edges(data=True), key=lambda e: e[2]["weight"])
            sub.remove_edge(u, v)
        else:
            u, v = min(bridges, key=lambda e: sub[e[0]][e[1]]["weight"])
            sub.remove_edge(u, v)
        parts = [set(c) for c in nx.connected_components(sub)]
        if len(parts) == 1:
            clusters.append(comp)
        else:
            g.remove_edge(u, v)
            queue.extend(parts)

    out = []
    for i, members in enumerate(sorted(clusters, key=lambda c: (-len(c), sorted(c)))):
        ms = sorted(members)
        sub = g.subgraph(ms)
        edges = [d["weight"] for _, _, d in sub.edges(data=True)]
        out.append({
            "cluster_id": "CL%03d" % i,
            "personas": ms,
            "size": len(ms),
            "internal_links": sub.number_of_edges(),
            "density": round(_density(g, set(ms)), 3),
            # the chain is only as strong as its weakest link, so cohesion is
            # reported as the minimum rather than the mean
            "cohesion_log10_lr": round(min(edges), 2) if edges else 0.0,
            "peak_log10_lr": round(max(edges), 2) if edges else 0.0,
        })
    return out


def build_dossier(cluster: dict, personas_by_id: dict, temporal) -> dict:
    """Aggregate everything known about one resolved actor."""
    members = [personas_by_id[p] for p in cluster["personas"] if p in personas_by_id]
    if not members:
        return {}

    sites = sorted({m.site for m in members})
    keys = sorted({m.pgp_fingerprint for m in members if m.pgp_fingerprint})
    wallets = sorted({a for m in members for a in m.btc_addresses})
    onions = sorted({o for m in members for o in m.onion_services})
    devices = sorted({d for m in members for d in m.exif_devices})
    contacts = sorted({c for m in members for c in m.contact_handles})

    # Pool the timezone estimate. Weighting by (confidence x post count) means
    # a chatty, strongly diurnal persona dominates a sparse one, which is the
    # correct behaviour: it carries more information about the same rhythm.
    num = den = 0.0
    est = []
    for m in members:
        geo = temporal.geolocation(m.persona_id)
        if geo["offset"] is None:
            continue
        w = geo["confidence"] * math.log1p(geo["n_posts"])
        num += geo["offset"] * w
        den += w
        est.append(geo)
    pooled = round(num / den, 2) if den > 0 else None
    spread = (max(e["offset"] for e in est) - min(e["offset"] for e in est)) if est else 0.0

    return {
        "cluster_id": cluster["cluster_id"],
        "personas": [{"id": m.persona_id, "handle": m.handle, "site": m.site,
                      "first_seen": m.first_seen.isoformat()[:10],
                      "last_seen": m.last_seen.isoformat()[:10]} for m in members],
        "sites": sites,
        "active_from": min(m.first_seen for m in members).isoformat()[:10],
        "active_to": max(m.last_seen for m in members).isoformat()[:10],
        "pgp_keys": keys,
        "key_rotation_observed": len(keys) > 1,
        "btc_addresses": wallets,
        "onion_services": onions,
        "exif_devices": devices,
        "contact_identifiers": contacts,
        "timezone": {
            "pooled_utc_offset": pooled,
            "per_persona_spread_hours": round(spread, 2),
            "regions": sorted({r for e in est for r in e["regions"]}),
            "note": ("consistent rhythm across personas" if spread <= 1.5
                     else "personas disagree on timezone; possible shared account "
                          "or travel"),
        },
        "cohesion_log10_lr": cluster["cohesion_log10_lr"],
    }


def cluster_truth_map(clusters: list[dict]) -> dict:
    m = {}
    for c in clusters:
        for p in c["personas"]:
            m[p] = c["cluster_id"]
    return m


def actor_summary(links: list[LinkHypothesis]) -> dict:
    """Which channels are actually carrying the case load."""
    counts: dict[str, int] = defaultdict(int)
    for l in links:
        for c in l.channels:
            counts[c] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
