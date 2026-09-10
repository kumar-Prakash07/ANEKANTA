"""Tests for the Dark2Clear stage: harvest, context setting, and pivots.

Implements the framework of Wangchuk & Rathod (2023). The tests that matter
most here are the *negative* ones. A harvester that finds every e-mail address
on a hidden service is trivial to write and useless: their own run produced
4,068 addresses, of which a handful were worth following. What makes the output
usable is refusing to promote the other 4,000, so most of what is asserted
below is about things the pipeline must NOT do -- not report a mail provider as
a Telegram username, not rank a footer above a vendor's private mailbox, not
treat a wallet as a clear-web pivot.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anveshak.osint import context as ctx
from anveshak.osint import mentions as mn
from anveshak.osint import pivot as pv

VENDOR_PAGE = """<!doctype html><html><body>
<div class="card"><h2>kavach_supply</h2>
<p>joined 2025-02-01 - 412 sales</p></div>
<div class="card"><h2>Contact</h2>
<p>For bulk orders and escrow disputes reach me directly at
kavach.supply@gmail.example - faster than the on-site messages.</p></div>
<div class="card"><h2>Payment</h2>
<div>1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2</div></div>
<footer>Abuse: abuse@torproject.example - Postmaster: postmaster@example.net</footer>
</body></html>"""

ADVISORY_PAGE = """<!doctype html><html><body>
<div class="card"><p>PSA: beware of phishing. Staff will never contact you from
support@example.org and there are 4 fake mirrors circulating.</p></div>
</body></html>"""


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.found = mn.extract(VENDOR_PAGE, onion="abc.onion",
                                url="http://abc.onion/vendor/kavach_supply",
                                persona_id="abc:kavach_supply",
                                handle="kavach_supply")
        self.by_kind = {}
        for m in self.found:
            self.by_kind.setdefault(m.kind, []).append(m.value)

    def test_finds_the_leaked_address(self):
        self.assertIn("kavach.supply@gmail.example", self.by_kind.get("email", []))

    def test_finds_the_boilerplate_too(self):
        """Collect everything; ranking is a separate job from harvesting."""
        self.assertIn("abuse@torproject.example", self.by_kind.get("email", []))

    def test_classifies_the_provider(self):
        m = next(x for x in self.found
                 if x.value == "kavach.supply@gmail.example")
        self.assertEqual(m.provider, "gmail.example")
        self.assertEqual(m.provider_class, "mainstream")

    def test_records_provenance(self):
        m = next(x for x in self.found
                 if x.value == "kavach.supply@gmail.example")
        self.assertEqual(m.handle, "kavach_supply")
        self.assertIn("bulk orders", m.context)

    def test_does_not_report_mail_providers_as_telegram_usernames(self):
        """Regression: the bare "@handle" branch matched the "@" inside every
        e-mail address, so a page with one address produced findings like
        "telegram: gmail". A false positive shaped like a finding is worse than
        a miss, because an analyst will spend time on it."""
        self.assertNotIn("gmail", self.by_kind.get("telegram", []))
        self.assertNotIn("protonmail", self.by_kind.get("telegram", []))
        self.assertNotIn("yandex", self.by_kind.get("telegram", []))

    def test_real_telegram_handle_still_found(self):
        found = mn.extract("<p>reach me on telegram: @nightfreight_ops</p>")
        self.assertIn("nightfreight_ops",
                      [m.value for m in found if m.kind == "telegram"])

    def test_onion_addresses_are_not_clear_web_mentions(self):
        page = "<p>mirror at %s.onion and mail me at a@b.example</p>" % ("a" * 56)
        kinds = {m.kind: m.value for m in mn.extract(page)}
        self.assertNotIn(".onion", str(kinds.get("domain", "")))

    def test_script_bodies_are_ignored(self):
        page = ('<script>var a="tracker.evil.example";</script>'
                '<p>mail me at v@shop.example</p>')
        domains = [m.value for m in mn.extract(page) if m.kind == "domain"]
        self.assertNotIn("tracker.evil.example", domains)

    def test_sanitiser_drops_duplicates_within_a_page(self):
        page = "<p>a@b.example</p><p>a@b.example</p>"
        emails = [m for m in mn.extract(page, url="u") if m.kind == "email"]
        self.assertEqual(len(emails), 1)


class TestContextSetting(unittest.TestCase):
    """The step the paper performs by hand, and the reason the harvest is
    usable rather than merely large."""

    def _score(self, page, **kw):
        found = mn.extract(page, **kw)
        ctx.score_all(found)
        return {m.value: m for m in found}

    def test_solicitation_outranks_boilerplate(self):
        got = self._score(VENDOR_PAGE, url="http://a.onion/vendor/kavach_supply",
                          persona_id="p1", handle="kavach_supply")
        leak = got["kavach.supply@gmail.example"]
        decoy = got["abuse@torproject.example"]
        self.assertGreater(leak.priority, decoy.priority + 0.3)
        self.assertEqual(ctx.band(leak.priority)[0], "high")

    def test_boilerplate_is_kept_but_demoted(self):
        got = self._score(VENDOR_PAGE, url="u", persona_id="p1", handle="h")
        self.assertIn("postmaster@example.net", got)
        self.assertIn(ctx.band(got["postmaster@example.net"].priority)[0],
                      ("low", "noise"))

    def test_generic_mailbox_names_are_demoted(self):
        got = self._score('<p>contact me directly at info@shop.example</p>',
                          url="u", persona_id="p1", handle="h")
        m = got["info@shop.example"]
        self.assertTrue(any("generic mailbox" in r for r in m.reasons))

    def test_advisory_text_is_not_treated_as_a_leak(self):
        """An address quoted inside a phishing warning is an example, not the
        author's own identifier."""
        got = self._score(ADVISORY_PAGE, url="u")
        m = got["support@example.org"]
        self.assertLess(m.priority, 0.5)

    def test_ubiquity_demotes_site_furniture(self):
        """The same rarity argument the linkage engines use: an identifier on
        every page belongs to the platform."""
        found = []
        for i in range(6):
            found.extend(mn.extract(
                "<footer>reach me directly: everywhere@example.com</footer>",
                url="http://a.onion/page%d" % i))
        ctx.score_all(found)
        self.assertTrue(any("crawled pages" in r
                            for r in found[0].reasons), found[0].reasons)

    def test_bands_are_ordered(self):
        self.assertEqual(ctx.band(0.95)[0], "high")
        self.assertEqual(ctx.band(0.60)[0], "medium")
        self.assertEqual(ctx.band(0.35)[0], "low")
        self.assertEqual(ctx.band(0.05)[0], "noise")


class TestPivot(unittest.TestCase):
    class FakePersona:
        def __init__(self, pid, handle):
            self.persona_id = pid
            self.handle = handle

    def setUp(self):
        self.personas = [
            self.FakePersona("s:kavach_supply", "kavach_supply"),
            self.FakePersona("s:kavach.supply2", "kavach.supply2"),
            self.FakePersona("s:harbor_light", "harbor_light"),
            self.FakePersona("s:brasstack", "brasstack"),
        ]
        self.cluster_of = {"s:kavach_supply": "CL000",
                           "s:kavach.supply2": "CL000",
                           "s:harbor_light": "CL001",
                           "s:brasstack": "CL002"}

    def test_identity_correlation_finds_the_altoid_mistake(self):
        """Ulbricht's error, automated: a leaked address whose local part is
        the operator's handle."""
        hits = pv.correlate_with_personas("kavach.supply@gmail.example",
                                          "email", self.personas)
        self.assertTrue(hits)
        self.assertIn("kavach", hits[0][0].handle)

    def test_correlation_uses_the_same_normaliser_as_the_handle_engine(self):
        from anveshak.engines.handle import normalise
        self.assertEqual(normalise("kavach.supply"), normalise("kavach_supply"))

    def test_unrelated_identifier_does_not_correlate(self):
        self.assertEqual(
            pv.correlate_with_personas("totallyunrelated@x.example", "email",
                                       self.personas), [])

    def test_short_local_parts_are_not_correlated(self):
        """Three characters match by chance constantly."""
        self.assertEqual(
            pv.correlate_with_personas("abc@x.example", "email", self.personas),
            [])

    def test_one_correlation_lead_per_cluster(self):
        """Regression: two accounts of one operator normalise to the same
        string, which emitted the identical finding twice."""
        m = mn.Mention(kind="email", value="kavach.supply@gmail.example",
                       persona_id="s:kavach_supply", handle="kavach_supply",
                       provider="gmail.example", provider_class="mainstream")
        leads = pv.develop(m, self.personas, self.cluster_of)
        corr = [l for l in leads if l.method == "identity correlation"]
        self.assertEqual(len(corr), 1)
        self.assertEqual(corr[0].linked_cluster, "CL000")

    def test_leak_attaches_to_the_whole_cluster(self):
        """The composition neither system achieves alone: a mistake on one
        account implicates every account the linkage engines tied to it."""
        m = mn.Mention(kind="email", value="kavach.supply@gmail.example",
                       persona_id="s:kavach_supply", handle="kavach_supply")
        leads = pv.develop(m, self.personas, self.cluster_of)
        corr = next(l for l in leads if l.method == "identity correlation")
        self.assertIn("s:kavach.supply2", corr.linked_personas)

    def test_gravatar_follows_the_published_scheme(self):
        import hashlib
        url = pv.gravatar_url("  Person@Example.COM ")
        digest = hashlib.md5(b"person@example.com").hexdigest()
        self.assertIn(digest, url)

    def test_nothing_is_fetched_by_default(self):
        m = mn.Mention(kind="email", value="a@b.example")
        for lead in pv.develop(m, self.personas, {}):
            self.assertEqual(lead.confidence, "unverified")

    def test_wallets_are_not_clear_web_pivots(self):
        """Regression: a wallet block sits inside the context window of a
        "contact me directly" paragraph and inherited its solicitation score,
        so BTC addresses outranked the e-mail the paragraph was about."""
        self.assertIn("btc", pv.NON_PIVOT_KINDS)
        m = mn.Mention(kind="btc", value="1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
                       persona_id="s:kavach_supply", handle="kavach_supply",
                       priority=0.9)
        out = pv.develop_all([m], self.personas, self.cluster_of)
        self.assertEqual(out, {})

    def test_actor_exposure_names_the_silent_accounts(self):
        m = mn.Mention(kind="email", value="kavach.supply@gmail.example",
                       persona_id="s:kavach_supply", handle="kavach_supply",
                       priority=0.9)
        exp = pv.actor_exposure([m], self.personas, self.cluster_of)
        entry = exp["CL000"]
        self.assertEqual(entry["leaking_personas"], ["s:kavach_supply"])
        self.assertEqual(entry["exposed_by_association"], ["s:kavach.supply2"])

    def test_username_candidates_strip_decoration(self):
        cands = pv.username_candidates("kavach.supply12@gmail.example", "email")
        self.assertIn("kavachsupply12", cands)
        self.assertIn("kavach.supply", cands)


class TestOnionSanitiser(unittest.TestCase):
    def test_accepts_v3_only(self):
        from anveshak.collect.crawler import sanitise_onions
        good = "a" * 56 + ".onion"
        self.assertEqual(sanitise_onions([good]), [good])
        self.assertEqual(sanitise_onions(["short.onion"]), [])
        self.assertEqual(sanitise_onions(["b" * 16 + ".onion"]), [])

    def test_normalises_and_deduplicates(self):
        from anveshak.collect.crawler import sanitise_onions
        a = "c" * 56 + ".onion"
        self.assertEqual(
            sanitise_onions(["http://%s/path" % a, a.upper(), "https://%s" % a]),
            [a])


if __name__ == "__main__":
    unittest.main(verbosity=2)
