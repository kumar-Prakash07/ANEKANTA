"""Tests for onion discovery, the safety gate, and the real-world benchmark.

The safety tests are the ones that matter. A keyword search across dark-web
indexes will eventually be handed a result pointing at material that is illegal
to fetch, and the difference between a tool that is usable and one that is not
is entirely in what happens next. Those paths are therefore tested directly,
including the failure modes: a blacklist that cannot be loaded, an engine that
has quietly stopped returning results, and a page that trips the gate after it
has already been fetched.

Nothing here needs Tor or the network; the live paths are covered in
`test_live.py`, which skips when the lab is not running.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anveshak.collect import discovery as disc
from anveshak.collect.safety import SafetyGate
from anveshak.evaluation import realworld


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP %d" % self.status_code)


class FakeSession:
    """Serves canned responses by URL substring."""

    def __init__(self, routes: dict, fail: bool = False):
        self.routes = routes
        self.fail = fail
        self.requested: list = []

    def get(self, url, **kw):
        self.requested.append(url)
        if self.fail:
            raise OSError("network down")
        for needle, response in self.routes.items():
            if needle in url:
                return response
        return FakeResponse("", 404)


def _blacklist_of(*onions) -> str:
    return "\n".join(hashlib.md5(o.encode()).hexdigest() for o in onions)


A = "a" * 56 + ".onion"
B = "b" * 56 + ".onion"
BANNED = "c" * 56 + ".onion"


class TestSafetyGate(unittest.TestCase):
    def setUp(self):
        self.gate = SafetyGate()

    def test_ordinary_content_passes(self):
        for text in ("Bitcoin escrow marketplace",
                     "Bulletproof hosting, 99% uptime",
                     "Carding forum and dumps shop",
                     "Weapons and ammunition listings"):
            self.assertTrue(self.gate.check_text(text).allowed, text)

    def test_subject_matter_of_investigations_is_not_filtered(self):
        """Drugs, weapons and fraud are what this tool investigates. Filtering
        them would defeat its purpose; only material whose retrieval is itself
        an offence is excluded."""
        self.assertTrue(self.gate.check_text("cocaine vendor, escrow only").allowed)
        self.assertTrue(self.gate.check_text("stolen credit card dumps").allowed)

    def test_each_vocabulary_alone_is_harmless(self):
        self.assertTrue(self.gate.check_text(
            "child health clinic and school directory").allowed)
        self.assertTrue(self.gate.check_text(
            "adult xxx explicit video archive").allowed)

    def test_conjunction_is_blocked(self):
        v = self.gate.check_text("teen porn collection")
        self.assertFalse(v.allowed)
        self.assertEqual(v.category, "csam")

    def test_standalone_indicator_is_blocked(self):
        self.assertFalse(self.gate.check_text("CSAM archive mirror").allowed)

    def test_reason_does_not_echo_the_matched_vocabulary(self):
        """The audit trail should record that an exclusion happened without
        reproducing the terms in logs, reports and the dashboard."""
        v = self.gate.check_text("teen porn collection")
        self.assertNotIn("porn", v.reason.lower())
        self.assertNotIn("teen", v.reason.lower())

    def test_proximity_is_bounded(self):
        """Two vocabularies far apart in a long page are not a conjunction."""
        far = "child " + ("filler " * 40) + "porn"
        self.assertTrue(self.gate.check_text(far).allowed)

    def test_check_page_strips_markup_first(self):
        html = "<div data-x='" + ("z" * 200) + "'>teen</div><p>porn</p>"
        self.assertFalse(self.gate.check_page(html).allowed)

    def test_empty_input(self):
        self.assertTrue(self.gate.check_text("").allowed)
        self.assertTrue(self.gate.check_page("").allowed)


class TestBlacklist(unittest.TestCase):
    def test_loads_and_matches(self):
        session = FakeSession({"blacklist": FakeResponse(_blacklist_of(BANNED))})
        bl = disc.AhmiaBlacklist()
        self.assertEqual(bl.load(session), 1)
        self.assertTrue(bl.is_banned(BANNED))
        self.assertFalse(bl.is_banned(A))

    def test_normalises_before_hashing(self):
        session = FakeSession({"blacklist": FakeResponse(_blacklist_of(BANNED))})
        bl = disc.AhmiaBlacklist()
        bl.load(session)
        for variant in ("http://" + BANNED, BANNED.upper(),
                        "http://" + BANNED + "/some/path"):
            self.assertTrue(bl.is_banned(variant), variant)

    def test_fails_closed_when_unreachable(self):
        """The single most important property. A filter that silently stops
        filtering leaves the operator believing they are protected."""
        bl = disc.AhmiaBlacklist()
        with self.assertRaises(Exception):
            bl.load(FakeSession({}, fail=True))
        self.assertEqual(bl.size, 0)

    def test_fails_closed_on_empty_list(self):
        bl = disc.AhmiaBlacklist()
        with self.assertRaises(RuntimeError):
            bl.load(FakeSession({"blacklist": FakeResponse("")}))


class TestDiscovery(unittest.TestCase):
    def _results_page(self, *onions) -> str:
        return "".join('<h4><a href="/r">Result %d</a></h4><p>%s some text</p>'
                       % (i, o) for i, o in enumerate(onions))

    def _discovery(self, page: str, banned=()):
        session = FakeSession({
            "blacklist": FakeResponse(_blacklist_of(*banned) or "0" * 32),
            "search": FakeResponse(page),
        })
        d = disc.OnionDiscovery(session, delay=0)
        d.prepare()
        return d

    def test_search_requires_the_blacklist(self):
        d = disc.OnionDiscovery(FakeSession({}), delay=0)
        with self.assertRaises(RuntimeError):
            d.search("x", engine="tordex")

    def test_extracts_and_filters(self):
        d = self._discovery(self._results_page(A, B, BANNED), banned=[BANNED])
        hits = d.search("hosting", engine="tordex", limit=10)
        found = {h.onion for h in hits}
        self.assertIn(A, found)
        self.assertIn(B, found)
        self.assertNotIn(BANNED, found)
        self.assertEqual(d.stats["blacklisted"], 1)

    def test_safety_gate_filters_result_metadata(self):
        page = ('<h4><a href="/r">teen porn videos</a></h4><p>%s</p>' % A)
        d = self._discovery(page)
        hits = d.search("x", engine="tordex", limit=10)
        self.assertEqual(hits, [])
        self.assertEqual(d.stats["safety_excluded"], 1)

    def test_engine_own_address_is_not_a_result(self):
        """An index links to itself on every page; without this it is the top
        hit for every query."""
        own = disc.SEARCH_ENGINES["tordex"]["host"]
        d = self._discovery(self._results_page(own, A))
        found = {h.onion for h in d.search("x", engine="tordex", limit=10)}
        self.assertNotIn(own, found)
        self.assertIn(A, found)

    def test_javascript_gate_is_reported_not_silently_empty(self):
        """Ahmia's search became JavaScript-only. Returning [] with no
        explanation would look identical to a query with no results."""
        d = self._discovery(
            "<p>Unfortunately we have not deployd non-JavaScript version</p>")
        self.assertEqual(d.search("x", engine="ahmia"), [])
        self.assertTrue(any("JavaScript-only" in n for n in d.notes))

    def test_ahmia_is_not_the_default_but_is_still_the_filter(self):
        self.assertNotEqual(disc.DEFAULT_ENGINE, "ahmia")
        self.assertFalse(disc.SEARCH_ENGINES["ahmia"]["searchable"])
        self.assertIn("ahmia.fi", disc.BLACKLIST_URL)

    def test_unknown_engine_rejected(self):
        d = self._discovery(self._results_page(A))
        with self.assertRaises(ValueError):
            d.search("x", engine="not-an-engine")

    def test_multi_search_records_provenance(self):
        d = self._discovery(self._results_page(A))
        found = d.multi_search(["one", "two"], engines=["tordex", "tor66"],
                               per_query=5)
        self.assertIn(A, found)
        self.assertEqual(sorted(found[A]["queries"]), ["one", "two"])
        self.assertEqual(sorted(found[A]["engines"]), ["tor66", "tordex"])


class FakeFingerprint:
    def __init__(self, favicon="", mmh3="", dom="", css="", headers="",
                 err="", spki=""):
        self.favicon_sha256 = favicon
        self.favicon_mmh3 = mmh3
        self.dom_skeleton_hash = dom
        self.css_vocab_hash = css
        self.header_order_hash = headers
        self.error_page_hash = err
        self.tls = {"present": bool(spki), "spki_sha256": spki} if spki else {}


class TestInfrastructureClusters(unittest.TestCase):
    def test_shared_favicon_forms_a_cluster(self):
        fps = {
            "a.onion": FakeFingerprint(favicon="deadbeef", dom="x1"),
            "b.onion": FakeFingerprint(favicon="deadbeef", dom="x2"),
            "c.onion": FakeFingerprint(favicon="other", dom="x3"),
            "d.onion": FakeFingerprint(favicon="another", dom="x4"),
        }
        clusters = realworld.infrastructure_clusters(fps)
        favicon = [c for c in clusters if c["artefact"] == "favicon_sha256"]
        self.assertEqual(len(favicon), 1)
        self.assertEqual(favicon[0]["services"], ["a.onion", "b.onion"])
        self.assertFalse(favicon[0]["generic"])

    def test_ubiquitous_value_is_marked_generic(self):
        """A header ordering shared by everything identifies nginx, not an
        operator."""
        fps = {("%d.onion" % i): FakeFingerprint(headers="same", dom="d%d" % i)
               for i in range(6)}
        clusters = realworld.infrastructure_clusters(fps)
        headers = [c for c in clusters if c["artefact"] == "header_order"]
        self.assertTrue(headers[0]["generic"])

    def test_singletons_are_not_clusters(self):
        fps = {"a.onion": FakeFingerprint(favicon="one"),
               "b.onion": FakeFingerprint(favicon="two")}
        self.assertEqual(realworld.infrastructure_clusters(fps), [])

    def test_tls_key_only_counted_when_present(self):
        fps = {"a.onion": FakeFingerprint(spki="key1", dom="d1"),
               "b.onion": FakeFingerprint(spki="key1", dom="d2"),
               "c.onion": FakeFingerprint(dom="d3"),
               "d.onion": FakeFingerprint(dom="d4")}
        clusters = realworld.infrastructure_clusters(fps)
        tls = [c for c in clusters if c["artefact"] == "tls_spki"]
        self.assertEqual(len(tls), 1)
        self.assertEqual(tls[0]["size"], 2)

    def test_default_queries_are_neutral(self):
        """The benchmark's job is to measure crawl and correlation behaviour.
        Steering the query set toward illicit subject matter would not improve
        the measurement and would increase what the safety gate has to reject."""
        gate = SafetyGate()
        for q in realworld.DEFAULT_QUERIES:
            self.assertTrue(gate.check_text(q).allowed, q)


if __name__ == "__main__":
    unittest.main(verbosity=2)
