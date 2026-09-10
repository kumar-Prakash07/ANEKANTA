"""End-to-end test against the live ONIONLAB hidden service.

Skips cleanly when the lab is not running, so the ordinary test run needs
neither Docker nor Tor. When the lab *is* up, this is the test that matters
most: it exercises the real path -- SOCKS, a real HTTP server, a real
certificate, real extraction -- rather than fixtures that agree with the code
because the same person wrote both.

The scoring assertions are deliberately loose. The lab is small (ten accounts,
four true pairs), so a perfect score there is not evidence of much; what is
being guarded is that the pipeline runs against live data at all and does not
silently start producing nothing.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRUTH = ROOT / "onionlab" / "ground_truth.json"


def _lab_address(role="market"):
    """Ask the running Tor container for an address, or give up quietly."""
    import subprocess
    try:
        out = subprocess.run(
            ["docker", "exec", "onionlab-tor", "cat",
             "/srv/onion-addresses/%s" % role],
            capture_output=True, text=True, timeout=20)
        addr = out.stdout.strip()
        return addr if addr.endswith(".onion") else None
    except Exception:
        return None


def _tor_up(host="127.0.0.1", port=9050) -> bool:
    import socket
    try:
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        return True
    except Exception:
        return False


ADDRESS = _lab_address()
TOR = _tor_up()


@unittest.skipUnless(ADDRESS and TOR,
                     "ONIONLAB not running (start it: cd onionlab && "
                     "docker compose up -d)")
class TestLiveOnion(unittest.TestCase):
    crawl = None

    @classmethod
    def setUpClass(cls):
        from anveshak.collect.crawler import TorCrawler
        crawler = TorCrawler(delay=0.3, max_pages=90)
        # follow discovered onions: the second service must be found, not given
        cls.crawl = crawler.crawl(ADDRESS, max_onions=3)

    def test_personas_extracted(self):
        self.assertGreaterEqual(len(self.crawl.personas), 15)

    def test_second_service_is_discovered_not_supplied(self):
        """The recursive stage of the paper's framework: one seed in, further
        services found by reading the pages."""
        self.assertGreaterEqual(len(self.crawl.onions), 2,
                                "peer service was not discovered")
        self.assertTrue(self.crawl.discovered_from,
                        "no service was recorded as discovered")
        for found, via in self.crawl.discovered_from.items():
            self.assertNotEqual(found, via)

    def test_shared_stack_across_two_services(self):
        """Both services run the same software, which is the rebrand pivot the
        service-fingerprint channels exist to detect."""
        fps = list(self.crawl.fingerprints.values())
        self.assertGreaterEqual(len(fps), 2)
        self.assertEqual(len({f.favicon_sha256 for f in fps}), 1)
        self.assertEqual(len({f.tls.get("spki_sha256") for f in fps}), 1)

    def test_posts_extracted(self):
        self.assertGreater(len(self.crawl.posts), 100)

    def test_favicon_fingerprinted(self):
        fp = self.crawl.fingerprint
        self.assertTrue(fp.favicon_mmh3)
        self.assertTrue(fp.favicon_sha256)
        self.assertEqual(len(fp.favicon_dhash), 16)

    def test_tls_certificate_captured(self):
        tls = self.crawl.fingerprint.tls
        self.assertTrue(tls.get("present"), tls.get("error"))
        self.assertEqual(len(tls["spki_sha256"]), 64)
        self.assertTrue(tls["self_signed"])

    def test_structural_fingerprints_present(self):
        fp = self.crawl.fingerprint
        for field in ("header_order_hash", "dom_skeleton_hash",
                      "css_vocab_hash", "error_page_hash"):
            self.assertTrue(getattr(fp, field), field)

    def test_no_server_version_leaked(self):
        """The default BaseHTTPRequestHandler banner names the Python version.
        A hidden service should not advertise its runtime."""
        self.assertNotIn("Python", self.crawl.fingerprint.server_banner)

    def test_artefacts_parsed_from_profiles(self):
        with_pgp = [p for p in self.crawl.personas if p.pgp_fingerprint]
        with_wallets = [p for p in self.crawl.personas if p.btc_addresses]
        self.assertGreaterEqual(len(with_pgp), 5)
        self.assertGreaterEqual(len(with_wallets), 5)

    def test_recovers_the_operator_structure(self):
        """The end-to-end claim: crawl a live onion, recover which accounts
        share an operator, graded against a map the crawler never saw."""
        from anveshak import live as live_mod
        from anveshak import pipeline

        bench = pipeline.run(seed=1337, n_actors=60)
        thr = bench.report["settings"]["threshold_log10_lr"]
        floor = bench.report["settings"]["lead_floor_log10_lr"]
        result = live_mod.analyse(self.crawl, bench.model, thr, floor)

        ev = live_mod.score_against_truth(result, TRUTH)
        self.assertTrue(ev.get("available"), ev.get("reason"))
        self.assertGreaterEqual(ev["true_pairs"], 8)
        # Precision is what is guarded. Recall is deliberately not: most true
        # pairs here span two services under unrelated handles, which is the
        # hard case, and those surface as leads rather than assertions. A
        # recall floor would tempt exactly the wrong fix.
        self.assertGreaterEqual(ev["precision"], 0.75)
        self.assertGreater(ev["roc_auc"], 0.6)

        osint_ev = live_mod.score_osint_against_truth(result, TRUTH)
        self.assertTrue(osint_ev.get("available"))
        self.assertGreaterEqual(osint_ev["recall"], 0.85)
        self.assertTrue(osint_ev["ranking_separates_leaks_from_decoys"])
        self.assertGreaterEqual(
            osint_ev["identifiers_with_identity_correlation"], 2)

    def test_leak_widens_to_accounts_that_leaked_nothing(self):
        """The composition of the two halves: an operator careless on one
        account is exposed across every account resolved to them."""
        from anveshak import live as live_mod
        from anveshak import pipeline

        bench = pipeline.run(seed=1337, n_actors=60)
        result = live_mod.analyse(
            self.crawl, bench.model,
            bench.report["settings"]["threshold_log10_lr"],
            bench.report["settings"]["lead_floor_log10_lr"])
        widened = sum(len(e["exposed_by_association"])
                      for e in result.exposure.values())
        self.assertGreater(widened, 0,
                           "no account was implicated through its cluster")

    def test_clear_web_leaks_are_harvested(self):
        """The Dark2Clear harvest, against deliberately planted identifiers."""
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        planted = {k for k in truth["clear_web_leaks"] if not k.startswith("_")}
        found = {m.value.lower() for m in self.crawl.mentions}
        missing = {p for p in planted if p.lower() not in found}
        self.assertFalse(missing, "planted leaks not harvested: %s" % missing)

    def test_context_setting_ranks_leaks_above_decoys(self):
        """The step the paper performs by hand. If the ranking does not
        separate a vendor's mailbox from an abuse@ footer address, the harvest
        is a pile of addresses rather than a queue of leads."""
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        planted = {k.lower() for k in truth["clear_web_leaks"]
                   if not k.startswith("_")}
        decoys = {k.lower() for k in truth["decoys"] if not k.startswith("_")}

        best = {}
        for m in self.crawl.mentions:
            key = m.value.lower()
            best[key] = max(best.get(key, 0.0), m.priority)

        real = [best[p] for p in planted if p in best]
        noise = [best[d] for d in decoys if d in best]
        self.assertTrue(real)
        if noise:
            self.assertGreater(min(real), max(noise),
                               "a decoy outranked a real leak")

    def test_leak_attributed_to_the_publishing_account(self):
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        leaks = {k: v for k, v in truth["clear_web_leaks"].items()
                 if not k.startswith("_")}
        by_value = {}
        for m in self.crawl.mentions:
            k = m.value.lower()
            if k not in by_value or m.priority > by_value[k].priority:
                by_value[k] = m
        for value, meta in leaks.items():
            m = by_value.get(value.lower())
            if m is None:
                continue
            self.assertEqual(m.handle, meta["leaked_by"], value)

    def test_ground_truth_matches_the_site(self):
        """The operator map and the site's vendor table must not drift apart,
        or every live score silently becomes meaningless."""
        truth = json.loads(TRUTH.read_text(encoding="utf-8"))
        mapped = set(truth["operators"])
        crawled = {p.handle for p in self.crawl.personas}
        self.assertEqual(mapped, crawled,
                         "ground_truth.json is out of sync with market.py")


@unittest.skipUnless(ADDRESS, "ONIONLAB not running")
class TestIsolation(unittest.TestCase):
    def test_site_publishes_no_host_port(self):
        """The single guarantee the whole safety argument rests on."""
        import subprocess
        out = subprocess.run(
            ["docker", "inspect", "onionlab-site", "--format",
             "{{json .NetworkSettings.Ports}}"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        ports = json.loads(out) if out else {}
        published = {k: v for k, v in ports.items() if v}
        self.assertEqual(published, {},
                         "site container is publishing ports to the host")

    def test_forum_container_publishes_no_host_port(self):
        import subprocess
        out = subprocess.run(
            ["docker", "inspect", "onionlab-forum", "--format",
             "{{json .NetworkSettings.Ports}}"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        ports = json.loads(out) if out else {}
        self.assertEqual({k: v for k, v in ports.items() if v}, {})

    def test_private_keys_are_not_mounted_into_the_sites(self):
        """The address volume and the key volume are deliberately separate, so
        a site container cannot reach the hidden service private keys even by
        accident."""
        import subprocess
        for container in ("onionlab-site", "onionlab-forum"):
            out = subprocess.run(
                ["docker", "inspect", container, "--format",
                 "{{json .Mounts}}"],
                capture_output=True, text=True, timeout=20).stdout.strip()
            for mount in json.loads(out) if out else []:
                self.assertNotIn("hs_keys", mount.get("Name", ""),
                                 "%s mounts the key volume" % container)
                if mount.get("Name", "").endswith("onion_pub"):
                    self.assertEqual(mount.get("RW"), False,
                                     "address volume is writable by the site")

    def test_backend_network_is_internal(self):
        """Every network the site container is on must be internal.

        The network name is discovered from the container rather than
        hardcoded: Compose prefixes it with the project name, so the lab is on
        `onionlab_backend` when started from onionlab/ and `anekanta_backend`
        when started from the root compose. Asserting a fixed name tests which
        directory you happened to run `up` from, not whether the isolation
        holds -- and it passes for the wrong reason as easily as it fails.
        """
        import subprocess
        out = subprocess.run(
            ["docker", "inspect", "onionlab-site", "--format",
             "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        networks = list(json.loads(out) if out else {})
        self.assertTrue(networks, "site container is on no network")
        for name in networks:
            internal = subprocess.run(
                ["docker", "network", "inspect", name, "--format", "{{.Internal}}"],
                capture_output=True, text=True, timeout=20).stdout.strip()
            self.assertEqual(internal, "true",
                             "site is on routable network %s" % name)

    def test_tor_socks_is_loopback_only(self):
        import subprocess
        out = subprocess.run(
            ["docker", "inspect", "onionlab-tor", "--format",
             "{{json .NetworkSettings.Ports}}"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        for _port, bindings in (json.loads(out) if out else {}).items():
            for b in bindings or []:
                self.assertEqual(b.get("HostIp"), "127.0.0.1",
                                 "Tor port bound to %s" % b.get("HostIp"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
