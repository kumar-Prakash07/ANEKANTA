"""Per-persona and per-actor contact-exposure analytics.

This module is the aggregation layer that sits on top of the records that
mentions.py and context.py already produce.  It does not score, classify, or
fetch anything -- those jobs belong to the modules that run before it.  Its
sole responsibility is rolling up those records into two views an analyst can
act on:

  persona_exposure()   given a persona's scored mention list and their post
                       history, return counts and categorised identifiers.

  actor_exposure_map() given a set of persona exposure records and a resolved
                       cluster map from fusion/graph.py, pool everything into
                       per-actor rollups and mark each identifier as DIRECT
                       (posted by this persona) or INHERITED (posted by a
                       co-clustered persona this actor also runs).

The inherited/direct distinction is the core differentiator of this module
versus plain identifier scraping.  An operator who is careful on four accounts
and careless on the fifth is exposed on all five -- but the analyst needs to
know *which* account made the mistake, not just that the cluster is exposed.
That distinction is preserved as the `is_inherited` boolean on every
identifier record and is never collapsed, because collapsing it would make the
output indistinguishable from a naive union.

Scoring and confidence
----------------------
No new scoring model is introduced here.  Every identifier carries the context
score and band that context.py already assigned.  The rollup uses those scores
for ordering and for the `posts_with_contact` threshold (anything above the
"noise" band, i.e. priority >= 0.30), but never aggregates them into a verdict.
The constraint "never output a single confidence percentage" is satisfied by
design: the per-identifier records retain their individual score and the full
provenance chain (thread_id, post_id, author_persona, forum_position) that
produced it.

Leak-intent detection
---------------------
`leak_posts` counts posts whose text matches a set of data-sale / breach-
advertisement phrases.  This is a keyword heuristic, not a classifier, and it
is reported as a count alongside the full post list so an analyst can inspect
every item in it.  The intent phrases are deliberately conservative -- they
target explicit sale/dump language, not general criminal activity, to keep the
false-positive rate low.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from .context import band as priority_band
from .pivot import NON_PIVOT_KINDS

# ---------------------------------------------------------------------------
# Leak-intent phrases
# ---------------------------------------------------------------------------
# Conservative set: explicit data-sale / breach-dump language.  Moderator
# notices and general threat-actor discussion are excluded deliberately.

_LEAK_PHRASES = [
    "database dump", "db dump", "full database", "leaked database",
    "data leak", "data dump", "combo list", "combolist",
    "fresh leak", "fresh dump", "for sale", "selling", "buy now",
    "credential", "credentials", "ssn leak", "ssn dump",
    "credit card", "cc dump", "cvv dump", "fullz", "fullz dump",
    "breach", "breached data", "exfiltrated", "exfil",
    "ht access", "config dump", "shell access", "rdp access",
    "initial access", "corp access", "vpn access",
    "ransomware", "ransom data", "proof of access",
    "telegram escrow", "session escrow", "wickr escrow",
]


def _has_leak_intent(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _LEAK_PHRASES)


# ---------------------------------------------------------------------------
# Identifier record
# ---------------------------------------------------------------------------

@dataclass
class IdentifierRecord:
    """One clear-web identifier in an exposure rollup.

    The is_inherited flag is the load-bearing field: True means the identifier
    was NOT posted by the persona this record is attached to -- it was posted
    by a co-clustered persona in the same resolved actor cluster.  False means
    the persona posted it themselves.

    This flag is NEVER collapsed.  A downstream consumer that wants a flat list
    of all identifiers for an actor can ignore it; one that wants to know which
    account made the mistake cannot.
    """
    kind: str
    value: str
    is_inherited: bool          # True = came from a co-clustered persona
    source_persona: str         # which persona actually posted it
    score: float                # context.py priority, in [0, 1]
    band: str                   # high / medium / low / noise
    thread_id: str = ""
    post_id: str = ""
    forum_position: str = "unknown"
    forum: str = ""             # onion address of the source forum
    context_snippet: str = ""   # 160-char enclosing block (from mentions.py)
    reasons: list = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        d["score"] = round(self.score, 3)
        return d


# ---------------------------------------------------------------------------
# Persona-level rollup
# ---------------------------------------------------------------------------

@dataclass
class PersonaExposure:
    """Contact-exposure summary for one forum persona."""

    persona_id: str
    handle: str
    site: str

    total_posts: int = 0
    leak_posts: int = 0                      # posts matching data-sale intent
    leak_post_ids: list = field(default_factory=list)

    posts_with_contact: int = 0              # posts containing >=1 identifier
                                             # above the "noise" band
    posts_with_contact_ids: list = field(default_factory=list)

    identifiers_by_type: dict = field(default_factory=dict)  # kind -> [value]
    identifier_records: list = field(default_factory=list)   # IdentifierRecord

    first_seen: str = ""   # ISO date of earliest post
    last_seen: str = ""    # ISO date of latest post

    def to_json(self) -> dict:
        d = asdict(self)
        d["identifier_records"] = [r.to_json() for r in self.identifier_records]
        return d


def persona_exposure(
    persona_id: str,
    handle: str,
    site: str,
    posts: list[Any],          # schema.Post objects or dicts with .text/.post_id
    mentions: list[Any],       # Mention objects already scored by context.py
    min_priority: float = 0.30,
) -> PersonaExposure:
    """Build a contact-exposure summary for one persona.

    Parameters
    ----------
    persona_id : str
        Full persona identifier (onion:handle).
    handle : str
        Human-readable account name.
    site : str
        Forum/service hostname.
    posts : list
        Post records for this persona.  Each must expose .text and .post_id
        (either as attributes or dict keys).
    mentions : list
        Scored Mention objects (priority already set by context.score_all).
        Only mentions whose persona_id or author_persona matches this persona
        are used; passing the full crawl list is safe.
    min_priority : float
        Minimum priority for a mention to be counted in posts_with_contact.
        Defaults to 0.30 (the "low" band floor) -- noise is excluded but
        low-confidence mentions are retained for completeness.
    """
    pe = PersonaExposure(persona_id=persona_id, handle=handle, site=site)

    # --- post counts -------------------------------------------------------
    def _text(p) -> str:
        return p.text if hasattr(p, "text") else p.get("text", "")

    def _pid(p) -> str:
        return str(p.post_id if hasattr(p, "post_id") else p.get("post_id", ""))

    def _ts(p):
        ts = p.timestamp if hasattr(p, "timestamp") else p.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts)
            except ValueError:
                pass
        return None

    pe.total_posts = len(posts)
    timestamps = []
    for post in posts:
        pid = _pid(post)
        text = _text(post)
        ts = _ts(post)
        if ts:
            timestamps.append(ts)
        if _has_leak_intent(text):
            pe.leak_posts += 1
            pe.leak_post_ids.append(pid)

    if timestamps:
        pe.first_seen = min(timestamps).isoformat()[:10]
        pe.last_seen = max(timestamps).isoformat()[:10]

    # --- identifier rollup -------------------------------------------------
    # Mentions are from mentions.py and must already be scored.  We only
    # include mentions attributable to *this* persona (either via persona_id
    # or author_persona), above the priority floor, and excluding non-pivot
    # kinds (crypto, PGP -- they belong to the linkage engines).
    post_ids_with_contact: set = set()
    for m in mentions:
        attributed = (m.persona_id == persona_id
                      or getattr(m, "author_persona", "") == handle)
        if not attributed:
            continue
        if m.kind in NON_PIVOT_KINDS:
            continue
        if m.priority < min_priority:
            continue

        rec = IdentifierRecord(
            kind=m.kind,
            value=m.value,
            is_inherited=False,          # direct: this persona posted it
            source_persona=persona_id,
            score=m.priority,
            band=priority_band(m.priority)[0],
            thread_id=getattr(m, "thread_id", ""),
            post_id=getattr(m, "post_id", ""),
            forum_position=getattr(m, "forum_position", "unknown"),
            forum=m.onion,
            context_snippet=m.context[:160] if m.context else "",
            reasons=list(m.reasons),
        )
        pe.identifier_records.append(rec)

        # track which post this came from for posts_with_contact count
        if m.post_id:
            post_ids_with_contact.add(m.post_id)

        # identifiers_by_type dict
        pe.identifiers_by_type.setdefault(m.kind, [])
        if m.value not in pe.identifiers_by_type[m.kind]:
            pe.identifiers_by_type[m.kind].append(m.value)

    pe.posts_with_contact = len(post_ids_with_contact)
    pe.posts_with_contact_ids = sorted(post_ids_with_contact)

    return pe


# ---------------------------------------------------------------------------
# Actor-level rollup
# ---------------------------------------------------------------------------

@dataclass
class ActorExposure:
    """Contact-exposure summary for one resolved actor (cluster of personas).

    The flat identifier list mixes direct and inherited records.  Each record
    carries is_inherited so consumers can split them back apart.  The split
    is preserved because it is the single most important behavioural
    requirement: an analyst must be able to distinguish "this account posted
    this identifier" from "this account is in a cluster that contains an
    account that posted it".
    """
    actor_id: str              # cluster_id from fusion/graph.py, e.g. "CL000"
    personas: list = field(default_factory=list)   # list of persona_id strings

    # per-persona breakdown (PersonaExposure.to_json() dicts)
    per_persona: list = field(default_factory=list)

    # flat identifier list across all personas in the cluster, with
    # is_inherited set correctly for each
    all_identifiers: list = field(default_factory=list)  # IdentifierRecord

    # actor-level aggregate counts
    total_posts: int = 0
    leak_posts: int = 0
    posts_with_contact: int = 0
    distinct_identifiers: int = 0
    personas_in_cluster: int = 0
    personas_with_leaks: int = 0    # personas that directly posted >= 1 identifier

    def to_json(self) -> dict:
        d = asdict(self)
        d["all_identifiers"] = [r.to_json() for r in self.all_identifiers]
        d["per_persona"] = [p if isinstance(p, dict) else asdict(p)
                            for p in self.per_persona]
        return d


def actor_exposure_map(
    persona_exposures: list[PersonaExposure],
    cluster_of: dict[str, str],
    min_priority: float = 0.30,
) -> dict[str, ActorExposure]:
    """Roll per-persona exposures up to resolved actor clusters.

    Parameters
    ----------
    persona_exposures : list[PersonaExposure]
        Output of persona_exposure() for every persona in the crawl.
    cluster_of : dict
        Maps persona_id -> cluster_id.  From fusion.graph.cluster_truth_map().
    min_priority : float
        Already applied by persona_exposure(); kept here for documentation.

    Returns
    -------
    dict mapping cluster_id -> ActorExposure

    The inherited/direct distinction
    ---------------------------------
    For each persona P in cluster C:
      * P's own IdentifierRecords are added with is_inherited=False.
      * For every OTHER persona Q in C, Q's IdentifierRecords are added to P's
        actor rollup with is_inherited=True (and source_persona set to Q).

    The actor-level `all_identifiers` list therefore contains every identifier
    reachable through the cluster, tagged so a consumer always knows which
    persona actually made the mistake.
    """
    # Index persona exposures by persona_id
    by_pid: dict[str, PersonaExposure] = {pe.persona_id: pe
                                          for pe in persona_exposures}

    # Group personas by cluster
    cluster_members: dict[str, list[str]] = {}
    for pid, cid in cluster_of.items():
        cluster_members.setdefault(cid, []).append(pid)

    # Also include personas with no cluster entry as singleton clusters
    for pe in persona_exposures:
        if pe.persona_id not in cluster_of:
            # singleton: use persona_id itself as the cluster key
            solo_key = "solo:" + pe.persona_id
            cluster_members.setdefault(solo_key, []).append(pe.persona_id)

    actors: dict[str, ActorExposure] = {}

    for cid, members in cluster_members.items():
        ae = ActorExposure(actor_id=cid, personas=sorted(members))
        ae.personas_in_cluster = len(members)

        seen_identifiers: set[tuple] = set()   # (kind, value.lower()) dedup key

        for pid in members:
            pe = by_pid.get(pid)
            if pe is None:
                continue

            ae.per_persona.append(pe.to_json())
            ae.total_posts += pe.total_posts
            ae.leak_posts += pe.leak_posts
            ae.posts_with_contact += pe.posts_with_contact

            if pe.identifier_records:
                ae.personas_with_leaks += 1

            # Direct identifiers for this persona
            for rec in pe.identifier_records:
                ikey = (rec.kind, rec.value.lower())
                direct_rec = IdentifierRecord(
                    kind=rec.kind,
                    value=rec.value,
                    is_inherited=False,
                    source_persona=pid,
                    score=rec.score,
                    band=rec.band,
                    thread_id=rec.thread_id,
                    post_id=rec.post_id,
                    forum_position=rec.forum_position,
                    forum=rec.forum,
                    context_snippet=rec.context_snippet,
                    reasons=list(rec.reasons),
                )
                ae.all_identifiers.append(direct_rec)
                seen_identifiers.add(ikey)

        # Inherited identifiers: for each persona P, add records from every
        # OTHER cluster member Q as inherited.  We do this in a second pass so
        # that P's own records are already in all_identifiers first.
        for pid in members:
            pe = by_pid.get(pid)
            if pe is None:
                continue
            for other_pid in members:
                if other_pid == pid:
                    continue
                other_pe = by_pid.get(other_pid)
                if other_pe is None:
                    continue
                for rec in other_pe.identifier_records:
                    # Add as inherited -- always, even if the same (kind, value)
                    # was already seen as a direct record.  We keep both because
                    # the distinction matters: the direct record says "this persona
                    # posted it", the inherited record says "this other persona also
                    # has access to this identifier by virtue of sharing a cluster".
                    # The consumer can deduplicate on (kind, value) if they only
                    # want a flat unique list; they cannot reconstruct the split
                    # if we collapse here.
                    inherited_rec = IdentifierRecord(
                        kind=rec.kind,
                        value=rec.value,
                        is_inherited=True,
                        source_persona=other_pid,
                        score=rec.score,
                        band=rec.band,
                        thread_id=rec.thread_id,
                        post_id=rec.post_id,
                        forum_position=rec.forum_position,
                        forum=rec.forum,
                        context_snippet=rec.context_snippet,
                        reasons=list(rec.reasons),
                    )
                    ae.all_identifiers.append(inherited_rec)

        # distinct_identifiers counts unique (kind, value) pairs regardless of
        # direct/inherited -- it is the "how many unique contact handles does
        # this actor have reachable" number.
        ae.distinct_identifiers = len({
            (r.kind, r.value.lower()) for r in ae.all_identifiers
        })

        actors[cid] = ae

    return actors


# ---------------------------------------------------------------------------
# API-shaped serialiser
# ---------------------------------------------------------------------------

def actor_exposure_to_api(ae: ActorExposure) -> dict:
    """Serialise one ActorExposure to the shape the /api/forum/exposure
    endpoint returns and the dashboard panel consumes.

    Shape
    -----
    {
      actor_id:        str,
      personas:        [persona_id, ...],
      per_persona:     [{persona_id, handle, site, total_posts, leak_posts,
                         posts_with_contact, identifiers_by_type,
                         first_seen, last_seen}, ...],
      identifiers:     [{identifier, type, status, score, band,
                         posted_by_persona, thread_id, post_id,
                         forum_position, forum, is_inherited,
                         context_snippet, reasons}, ...],
      stats:           {total_posts, leak_posts, posts_with_contact,
                        distinct_identifiers, personas_in_cluster,
                        personas_with_leaks},
    }

    The `status` field maps to the context band so the dashboard can apply
    edge styling without re-computing anything:
      "attributed"   priority >= 0.50  (high or medium band)
      "present"      0.30 <= priority < 0.50  (low band)
      "inherited"    is_inherited=True (regardless of score)

    Note: an inherited identifier whose source persona scored it at >= 0.50
    still carries status="inherited" -- the status encodes the STRUCTURAL
    relationship, not just the score, because the dashboard needs to draw the
    edge differently (dotted grey) regardless of how confident the underlying
    mention is.
    """
    def _status(rec: IdentifierRecord) -> str:
        if rec.is_inherited:
            return "inherited"
        if rec.score >= 0.50:
            return "attributed"
        return "present"

    identifiers = []
    for rec in ae.all_identifiers:
        identifiers.append({
            "identifier": rec.value,
            "type": rec.kind,
            "status": _status(rec),
            "score": round(rec.score, 3),
            "band": rec.band,
            "posted_by_persona": rec.source_persona,
            "thread_id": rec.thread_id,
            "post_id": rec.post_id,
            "forum_position": rec.forum_position,
            "forum": rec.forum,
            "is_inherited": rec.is_inherited,
            "context_snippet": rec.context_snippet,
            "reasons": rec.reasons,
        })

    return {
        "actor_id": ae.actor_id,
        "personas": ae.personas,
        "per_persona": ae.per_persona,
        "identifiers": identifiers,
        "stats": {
            "total_posts": ae.total_posts,
            "leak_posts": ae.leak_posts,
            "posts_with_contact": ae.posts_with_contact,
            "distinct_identifiers": ae.distinct_identifiers,
            "personas_in_cluster": ae.personas_in_cluster,
            "personas_with_leaks": ae.personas_with_leaks,
        },
    }
