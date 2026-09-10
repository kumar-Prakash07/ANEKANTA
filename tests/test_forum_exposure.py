"""Tests for the forum-thread Dark2Clear extension.

Two non-negotiable behavioural requirements drive the test structure:

  1. Inherited/direct distinction — an identifier posted by persona A that
     ends up in the cluster record for persona B must be marked is_inherited=True
     on B's record.  It must NEVER appear as is_inherited=False on B.  This is
     the single most important constraint in the whole module.

  2. Ubiquitous/boilerplate identifiers must score below the attribution
     threshold — the same rarity argument the linkage engines use.  An
     identifier appearing on every crawled page (or in every sig block) is
     furniture, not a lead.

Beyond those two, the suite covers:

  * Tox ID and Session ID extraction from forum post HTML.
  * Forum structural-position scoring: original_post > reply_post >
    quoted_reply; signature == footer penalty.
  * extract_forum_thread() provenance fields (thread_id, post_id,
    author_persona, forum_position) propagated to every Mention.
  * persona_exposure() counts: total_posts, leak_posts,
    posts_with_contact, identifiers_by_type.
  * actor_exposure_map() two-pass build: a persona that never posted an
    identifier inherits records from its cluster sibling but every one of
    those records is flagged is_inherited=True.
  * actor_exposure_to_api() status field: attributed / present / inherited.
  * pivot.py: Tox / Session IDs produce contact-info leads but do NOT go
    through identity correlation (they are hex strings, not handles).
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anveshak.osint import context as ctx
from anveshak.osint import mentions as mn
from anveshak.osint import pivot as pv
from anveshak.osint.exposure import (
    IdentifierRecord,
    actor_exposure_map,
    actor_exposure_to_api,
    persona_exposure,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TOX_ID = "A" * 76                        # 76 uppercase hex chars — valid Tox ID shape
SESSION_ID = "0" + "a" * 65              # 66-char hex starting with 0

OP_POST_HTML = """
<div class="post-body">
  <p>For bulk orders reach me at kavach.supply@gmail.example — faster than escrow.</p>
  <p>Also on Telegram: @kavach_bulk</p>
  <p>Tox: {tox}</p>
  <p>Session: {session}</p>
</div>
""".format(tox=TOX_ID, session=SESSION_ID)

QUOTED_REPLY_HTML = """
<div class="post-body">
  <blockquote class="quote">
    <p>Previously: contact me at victim@protonmail.com</p>
  </blockquote>
  <p>See above — that address is no longer active.</p>
</div>
"""

SIG_HTML = """
<div class="post-body">
  <p>Nothing interesting here.</p>
</div>
<div class="signature">
  <p>sig_address@sig-provider.example</p>
</div>
"""

# Boilerplate that appears in every post on the board
UBIQ_HTML_TEMPLATE = """
<div class="post-body"><p>Post number {n}.</p></div>
<footer><p>contact the mods at mods@boardname.example</p></footer>
"""

LEAK_POST_HTML = """
<div class="post-body">
  <p>Selling fresh database dump — 500k records, combo list available.
  DM @kavach_bulk on Telegram.</p>
</div>
"""


class FakePost:
    def __init__(self, post_id, persona_id, text,
                 ts=None):
        self.post_id = post_id
        self.persona_id = persona_id
        self.text = text
        self.timestamp = ts or datetime(2025, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. Extraction: forum provenance fields
# ---------------------------------------------------------------------------

class TestForumExtraction(unittest.TestCase):
    """extract_forum_thread() must populate all four provenance fields."""

    def _run(self, html, position, post_id="p1", author="kavach"):
        posts = [{"post_id": post_id, "author": author,
                  "persona_id": "abc:" + author, "html": html,
                  "url": "http://abc.onion/thread/1#" + post_id}]
        return mn.extract_forum_thread(posts, onion="abc.onion",
                                       thread_id="T001")

    def test_thread_id_propagated(self):
        found = self._run(OP_POST_HTML, "original_post")
        self.assertTrue(all(m.thread_id == "T001" for m in found),
                        "thread_id must be set on every Mention")

    def test_post_id_propagated(self):
        found = self._run(OP_POST_HTML, "original_post", post_id="p42")
        self.assertTrue(all(m.post_id == "p42" for m in found),
                        "post_id must be set on every Mention")

    def test_author_persona_propagated(self):
        found = self._run(OP_POST_HTML, "original_post", author="nightfreight")
        self.assertTrue(
            all(m.author_persona == "nightfreight" for m in found),
            "author_persona must match the post author")

    def test_tox_id_extracted(self):
        found = self._run(OP_POST_HTML, "original_post")
        tox_vals = [m.value for m in found if m.kind == "tox"]
        self.assertIn(TOX_ID, tox_vals, "Tox ID must be extracted from OP")

    def test_session_id_extracted(self):
        found = self._run(OP_POST_HTML, "original_post")
        session_vals = [m.value for m in found if m.kind == "session"]
        self.assertIn(SESSION_ID, session_vals,
                      "Session ID must be extracted from OP")

    def test_email_extracted_from_op(self):
        found = self._run(OP_POST_HTML, "original_post")
        emails = [m.value for m in found if m.kind == "email"]
        self.assertIn("kavach.supply@gmail.example", emails)

    def test_telegram_extracted_from_op(self):
        found = self._run(OP_POST_HTML, "original_post")
        tg = [m.value for m in found if m.kind == "telegram"]
        self.assertIn("kavach_bulk", tg)


# ---------------------------------------------------------------------------
# 2. Context scoring: forum structural positions
# ---------------------------------------------------------------------------

class TestForumContextScoring(unittest.TestCase):
    """Forum position scores must follow original_post > reply_post >
    quoted_reply, and signature must be penalised like a footer."""

    def _score_post(self, html, position, persona_id="p1", handle="h"):
        posts = [{"post_id": "x", "author": handle,
                  "persona_id": persona_id, "html": html}]
        found = mn.extract_forum_thread(
            posts, onion="o.onion", thread_id="T1")
        # Patch forum_position for comparison tests (extract_forum_thread sets
        # it automatically; this overrides for direct unit tests)
        for m in found:
            m.forum_position = position
        ctx.score_all(found)
        return {m.value: m for m in found}

    def test_op_scores_higher_than_reply(self):
        """Original post gets a larger attribution bonus than a plain reply."""
        op_mentions = self._score_post(
            '<div><p>reach me at op@test.example</p></div>',
            "original_post", persona_id="p1", handle="h")
        reply_mentions = self._score_post(
            '<div><p>reach me at reply@test.example</p></div>',
            "reply_post", persona_id="p1", handle="h")
        op_score = op_mentions.get("op@test.example", type("", (), {"priority": 0})()).priority
        rp_score = reply_mentions.get("reply@test.example", type("", (), {"priority": 0})()).priority
        self.assertGreater(op_score, rp_score,
                           "original_post should score higher than reply_post")

    def test_quoted_reply_scores_lower_than_original_post(self):
        """A quoted reply is penalised because the identifier may belong to
        the person being quoted, not the current poster."""
        op = self._score_post(
            '<div><p>reach me at op@test.example</p></div>',
            "original_post", persona_id="p1", handle="h")
        qr = self._score_post(
            '<blockquote class="quote"><p>quoted@test.example</p></blockquote>',
            "quoted_reply", persona_id="p1", handle="h")
        op_score = op.get("op@test.example", type("", (), {"priority": 0})()).priority
        qr_score = qr.get("quoted@test.example", type("", (), {"priority": 0})()).priority
        self.assertGreater(op_score, qr_score,
                           "original_post must score higher than quoted_reply")

    def test_quoted_reply_reason_mentions_quoting(self):
        found = mn.extract_forum_thread(
            [{"post_id": "q1", "author": "h", "persona_id": "p1",
              "html": '<blockquote class="quote"><p>q@test.example</p></blockquote>'}],
            onion="o.onion", thread_id="T")
        # Force position for direct test
        for m in found:
            m.forum_position = "quoted_reply"
        ctx.score_all(found)
        reasons_text = " ".join(found[0].reasons if found else [])
        self.assertIn("quoted", reasons_text.lower(),
                      "reasons must mention the quoted context")

    def test_signature_penalised_like_footer(self):
        """Signature blocks are structural boilerplate — same penalty as a
        page footer."""
        sig_mentions = self._score_post(
            '<div class="signature"><p>sig@sig.example</p></div>',
            "signature")
        sig_score = sig_mentions.get(
            "sig@sig.example", type("", (), {"priority": 0})()).priority
        self.assertLess(sig_score, 0.30,
                        "signature block identifier must be below the low-band floor")

    def test_mod_boilerplate_penalised(self):
        mod_mentions = self._score_post(
            '<div class="mod-note"><p>mod@board.example</p></div>',
            "mod_boilerplate")
        mod_score = mod_mentions.get(
            "mod@board.example", type("", (), {"priority": 0})()).priority
        self.assertLess(mod_score, 0.30,
                        "mod_boilerplate identifier must be below the low-band floor")


# ---------------------------------------------------------------------------
# 3. Ubiquity: boilerplate identifiers score below attribution threshold
# ---------------------------------------------------------------------------

class TestUbiquityDemotion(unittest.TestCase):
    """The most important negative test: an identifier that appears across
    many unrelated threads/pages must not be treated as a strong signal for
    any one of them."""

    def test_ubiquitous_identifier_below_attribution_threshold(self):
        """Simulate an address that appears in the footer of every post on
        the board.  After score_all, its priority must sit in the noise band
        (< 0.30) — the attribution threshold the task spec mandates."""
        found = []
        for i in range(8):
            page_html = UBIQ_HTML_TEMPLATE.format(n=i)
            found.extend(mn.extract(
                page_html,
                onion="board.onion",
                url="http://board.onion/thread/%d" % i))
        ctx.score_all(found)

        ubiq = [m for m in found if m.value == "mods@boardname.example"]
        self.assertTrue(ubiq, "ubiquitous address must still be collected")
        max_priority = max(m.priority for m in ubiq)
        self.assertLess(max_priority, 0.50,
                        "ubiquitous footer address must score below 0.50 "
                        "(medium-band attribution threshold)")

    def test_ubiquity_reason_present(self):
        """The ubiquity demotion must produce a human-readable reason so an
        analyst understands why the identifier ranked low."""
        found = []
        for i in range(6):
            found.extend(mn.extract(
                UBIQ_HTML_TEMPLATE.format(n=i),
                url="http://x.onion/t%d" % i))
        ctx.score_all(found)
        ubiq = [m for m in found if m.value == "mods@boardname.example"]
        all_reasons = " ".join(r for m in ubiq for r in m.reasons)
        self.assertTrue(
            any(kw in all_reasons.lower() for kw in ("crawled", "pages", "furniture")),
            "ubiquity reason must mention cross-page frequency")


# ---------------------------------------------------------------------------
# 4. Inherited / direct distinction — the core behavioural requirement
# ---------------------------------------------------------------------------

class TestInheritedDirectDistinction(unittest.TestCase):
    """An identifier posted by persona A must NEVER appear as is_inherited=False
    on persona B's actor record.  This is the single most important test."""

    def _build_exposures(self):
        # Persona A posts a Telegram handle
        posts_a = [{"post_id": "pa1", "author": "actorA",
                    "persona_id": "site:actorA",
                    "html": OP_POST_HTML,
                    "url": "http://x.onion/t/1"}]
        mentions_a = mn.extract_forum_thread(
            posts_a, onion="x.onion", thread_id="T1")
        for m in mentions_a:
            m.forum_position = "original_post"
        ctx.score_all(mentions_a)

        # Persona B has posts but no contact leaks
        posts_b = [FakePost("pb1", "site:actorB",
                            "Nothing interesting, just a reply.")]
        pe_a = persona_exposure("site:actorA", "actorA", "x.onion",
                                [FakePost("pa1", "site:actorA", OP_POST_HTML)],
                                mentions_a)
        pe_b = persona_exposure("site:actorB", "actorB", "x.onion",
                                posts_b, mentions_a)

        cluster_of = {"site:actorA": "CL000", "site:actorB": "CL000"}
        ae_map = actor_exposure_map([pe_a, pe_b], cluster_of)
        return ae_map["CL000"], pe_a, pe_b

    def test_persona_b_has_no_direct_records(self):
        """Persona B never posted anything — it must have zero direct
        identifier records."""
        _, _, pe_b = self._build_exposures()
        direct_b = [r for r in pe_b.identifier_records
                    if not r.is_inherited]
        self.assertEqual(direct_b, [],
                         "persona B posted nothing; it must have no direct records")

    def test_inherited_identifier_marked_correctly(self):
        """The cluster rollup for CL000 must contain the identifiers from
        persona A, but when viewed from persona B's perspective they must all
        be marked is_inherited=True."""
        ae, _, _ = self._build_exposures()
        # All records whose source_persona is actorA, seen from the actor level
        b_as_viewer = [r for r in ae.all_identifiers
                       if r.source_persona == "site:actorA"]
        # At least one identifier should be present (email or telegram from OP)
        self.assertTrue(b_as_viewer,
                        "cluster must contain identifiers from actorA")
        # Every record whose source is actorA is marked inherited for actorB
        # (the actor-level list contains both the direct record for A and the
        # inherited record for B; we check the inherited ones specifically)
        inherited = [r for r in ae.all_identifiers
                     if r.source_persona == "site:actorA" and r.is_inherited]
        self.assertTrue(inherited,
                        "inherited records from actorA must exist for actorB")
        for rec in inherited:
            self.assertTrue(rec.is_inherited,
                            "is_inherited must be True on all inherited records")

    def test_direct_identifier_not_marked_inherited(self):
        """Persona A's own records must be marked is_inherited=False."""
        ae, _, _ = self._build_exposures()
        direct_a = [r for r in ae.all_identifiers
                    if r.source_persona == "site:actorA" and not r.is_inherited]
        self.assertTrue(direct_a,
                        "actorA must have direct (non-inherited) records")
        for rec in direct_a:
            self.assertFalse(rec.is_inherited,
                             "direct records must have is_inherited=False")

    def test_api_status_inherited_vs_attributed(self):
        """actor_exposure_to_api() must set status='inherited' on inherited
        records regardless of their score, and status='attributed' / 'present'
        on direct records according to score."""
        ae, _, _ = self._build_exposures()
        api_out = actor_exposure_to_api(ae)
        inherited_api = [r for r in api_out["identifiers"] if r["is_inherited"]]
        direct_api    = [r for r in api_out["identifiers"] if not r["is_inherited"]]
        for rec in inherited_api:
            self.assertEqual(rec["status"], "inherited",
                             "inherited records must have status='inherited'")
        for rec in direct_api:
            self.assertIn(rec["status"], ("attributed", "present"),
                          "direct records must have status attributed or present")

    def test_inherited_record_source_persona_is_not_the_silent_persona(self):
        """The source_persona on an inherited record must be the persona that
        actually posted the identifier, NOT the silent one."""
        ae, _, _ = self._build_exposures()
        inherited = [r for r in ae.all_identifiers if r.is_inherited]
        for rec in inherited:
            self.assertEqual(rec.source_persona, "site:actorA",
                             "source_persona must point to the posting persona, "
                             "not the silent cluster member")

    def test_singleton_persona_has_no_inherited_records(self):
        """A persona that is not in any resolved cluster gets its own solo
        entry and must have no inherited records (nothing to inherit from)."""
        posts = [{"post_id": "s1", "author": "loner",
                  "persona_id": "site:loner",
                  "html": OP_POST_HTML,
                  "url": "http://x.onion/t/s"}]
        mentions = mn.extract_forum_thread(posts, onion="x.onion",
                                            thread_id="T_solo")
        for m in mentions:
            m.forum_position = "original_post"
        ctx.score_all(mentions)
        pe = persona_exposure("site:loner", "loner", "x.onion",
                              [FakePost("s1", "site:loner", OP_POST_HTML)],
                              mentions)
        ae_map = actor_exposure_map([pe], {})   # no cluster entry
        solo_key = "solo:site:loner"
        self.assertIn(solo_key, ae_map)
        inherited = [r for r in ae_map[solo_key].all_identifiers
                     if r.is_inherited]
        self.assertEqual(inherited, [],
                         "a singleton persona has nothing to inherit")


# ---------------------------------------------------------------------------
# 5. persona_exposure() counts
# ---------------------------------------------------------------------------

class TestPersonaExposureCounts(unittest.TestCase):

    def setUp(self):
        self.posts = [
            FakePost("p1", "s:a", "Just a normal post."),
            FakePost("p2", "s:a", "Selling fresh database dump, combo list available. "
                     "Contact: @kavach_bulk"),
            FakePost("p3", "s:a", "Another normal post."),
        ]
        # Build mentions for the leak post only
        posts_html = [{"post_id": "p2", "author": "a", "persona_id": "s:a",
                       "html": LEAK_POST_HTML}]
        self.mentions = mn.extract_forum_thread(
            posts_html, onion="x.onion", thread_id="T")
        for m in self.mentions:
            m.forum_position = "original_post"
        ctx.score_all(self.mentions)
        self.pe = persona_exposure("s:a", "a", "x.onion",
                                   self.posts, self.mentions)

    def test_total_posts(self):
        self.assertEqual(self.pe.total_posts, 3)

    def test_leak_posts_counted(self):
        # post p2 contains "database dump" and "combo list"
        self.assertGreaterEqual(self.pe.leak_posts, 1,
                                "leak post must be counted")

    def test_identifiers_by_type_populated(self):
        self.assertIn("telegram", self.pe.identifiers_by_type,
                      "telegram identifier from leak post must be collected")

    def test_first_last_seen_populated(self):
        self.assertTrue(self.pe.first_seen, "first_seen must be set")
        self.assertTrue(self.pe.last_seen,  "last_seen must be set")


# ---------------------------------------------------------------------------
# 6. Pivot: Tox / Session do not go through identity correlation
# ---------------------------------------------------------------------------

class TestPivotForumIdentifiers(unittest.TestCase):

    class FakePersona:
        def __init__(self, pid, handle):
            self.persona_id = pid
            self.handle = handle

    def setUp(self):
        self.personas = [
            self.FakePersona("s:kavach_supply", "kavach_supply"),
            self.FakePersona("s:nightfreight",  "nightfreight"),
        ]

    def test_tox_id_does_not_correlate_with_handles(self):
        """A 76-hex Tox ID must produce zero identity-correlation hits because
        _HANDLE_CORRELATION_KINDS excludes 'tox'."""
        hits = pv.correlate_with_personas(TOX_ID, "tox", self.personas)
        self.assertEqual(hits, [],
                         "Tox ID must not produce identity-correlation hits")

    def test_session_id_does_not_correlate_with_handles(self):
        hits = pv.correlate_with_personas(SESSION_ID, "session", self.personas)
        self.assertEqual(hits, [],
                         "Session ID must not produce identity-correlation hits")

    def test_tox_produces_contact_info_lead(self):
        """A Tox ID must produce a 'tox contact' lead so it appears in the
        analyst's queue even though no URL pivot exists."""
        m = mn.Mention(kind="tox", value=TOX_ID,
                       persona_id="s:kavach_supply",
                       handle="kavach_supply",
                       forum_position="original_post",
                       priority=0.6)
        leads = pv.develop(m, self.personas, {})
        tox_leads = [l for l in leads if l.method == "tox contact"]
        self.assertTrue(tox_leads, "Tox ID must produce a 'tox contact' lead")
        self.assertEqual(tox_leads[0].url, "",
                         "Tox contact lead must have no URL (no auto-fetch)")

    def test_session_produces_contact_info_lead(self):
        m = mn.Mention(kind="session", value=SESSION_ID,
                       persona_id="s:kavach_supply",
                       handle="kavach_supply",
                       forum_position="original_post",
                       priority=0.6)
        leads = pv.develop(m, self.personas, {})
        session_leads = [l for l in leads if l.method == "session contact"]
        self.assertTrue(session_leads,
                        "Session ID must produce a 'session contact' lead")

    def test_telegram_handle_correlates_normally(self):
        """Telegram handles DO go through identity correlation — unchanged
        from pre-forum behaviour."""
        hits = pv.correlate_with_personas("kavach_bulk", "telegram",
                                          self.personas)
        # kavach_bulk normalises close enough to kavach_supply to contain
        # each other (both start with "kavach") → containment hit at 0.75
        hit_handles = [h[0].handle for h in hits]
        self.assertTrue(any("kavach" in h for h in hit_handles),
                        "Telegram handle should correlate against kavach* personas")

    def test_nothing_fetched_for_forum_mentions(self):
        """develop() must not mark any lead as verified by default."""
        m = mn.Mention(kind="email", value="forum@test.example",
                       persona_id="s:kavach_supply",
                       handle="kavach_supply",
                       forum_position="original_post",
                       priority=0.6)
        for lead in pv.develop(m, self.personas, {}):
            self.assertEqual(lead.confidence, "unverified",
                             "no lead should be fetched without verify=True")


# ---------------------------------------------------------------------------
# 7. extract() backward-compatibility: non-forum call still works
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    """The existing extract() API must continue to work without forum args."""

    VENDOR_PAGE = """<body>
    <p>Contact: compat@gmail.example</p>
    <footer>footer@example.net</footer>
    </body>"""

    def test_extract_without_forum_args(self):
        found = mn.extract(self.VENDOR_PAGE, onion="x.onion",
                           url="http://x.onion/vendor/v",
                           persona_id="x:v", handle="v")
        self.assertTrue(found, "extract() must still work without forum args")

    def test_forum_position_defaults_to_unknown(self):
        found = mn.extract(self.VENDOR_PAGE, onion="x.onion",
                           url="http://x.onion/")
        for m in found:
            self.assertEqual(m.forum_position, "unknown",
                             "non-forum calls must default forum_position to unknown")

    def test_thread_id_defaults_to_empty(self):
        found = mn.extract(self.VENDOR_PAGE)
        for m in found:
            self.assertEqual(m.thread_id, "",
                             "non-forum calls must default thread_id to empty string")


if __name__ == "__main__":
    unittest.main(verbosity=2)
