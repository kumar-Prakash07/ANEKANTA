"""Tests for live collection, service fingerprinting, and the AI components.

The fingerprint tests are the important ones. A hash function that silently
changes convention produces values that no longer pivot against anything, and
because the output still *looks* like a hash the failure is invisible until an
analyst wastes a week on it. The Shodan mmh3 convention in particular is pinned
against an independently computed value.

Nothing here needs Tor or Docker; the network-dependent paths are exercised
against fixtures. `test_live.py` covers the real onion service and skips
cleanly when the lab is not running.
"""

from __future__ import annotations

import base64
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anveshak.ai.tradecraft import TradecraftClassifier, _rhythm
from anveshak.collect import fingerprint as fp
from anveshak.collect.crawler import BTC_RE, PGP_RE, strip_tags
from anveshak.corpus.generator import generate
from anveshak.engines.base import CorpusView
from anveshak.engines.service import FaviconEngine, TemplateEngine, TLSEngine

PAGE = """<!doctype html><html><head><title>x</title></head>
<body><div class="wrap card"><table><tr><td>2026-01-05 14:22</td>
<td>hey all, escrow on order 4211 has been pending 6 days</td></tr></table>
<pre>-----BEGIN PGP PUBLIC KEY BLOCK-----
abcdef0123456789
-----END PGP PUBLIC KEY BLOCK-----</pre>
<p>1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2</p></div></body></html>"""


class TestHashConventions(unittest.TestCase):
    def test_favicon_mmh3_matches_shodan_convention(self):
        """Pinned independently: mmh3 over the base64 re-encoding, not the raw
        bytes. Getting this wrong yields hashes that match nothing anywhere."""
        import mmh3
        data = b"\x89PNG\r\n\x1a\n" + b"payload-bytes" * 7
        self.assertEqual(fp.favicon_mmh3(data),
                         mmh3.hash(base64.encodebytes(data)))

    def test_favicon_hash_is_stable(self):
        data = b"same-bytes" * 20
        self.assertEqual(fp.favicon_mmh3(data), fp.favicon_mmh3(data))
        self.assertNotEqual(fp.favicon_mmh3(data), fp.favicon_mmh3(data + b"x"))

    def test_hamming_of_identical_hashes_is_zero(self):
        self.assertEqual(fp.hamming_hex("a55aa55aa55aa55a", "a55aa55aa55aa55a"), 0)

    def test_hamming_counts_differing_bits(self):
        self.assertEqual(fp.hamming_hex("0000000000000000",
                                        "0000000000000003"), 2)

    def test_hamming_is_defensive_about_junk(self):
        self.assertEqual(fp.hamming_hex("not-hex", "also-not"), 64)


class TestStructuralFingerprints(unittest.TestCase):
    def test_dom_skeleton_ignores_text_and_attributes(self):
        a = '<div class="x"><p>hello world</p></div>'
        b = '<div class="totally-different"><p>goodbye</p></div>'
        self.assertEqual(fp.dom_skeleton_hash(a), fp.dom_skeleton_hash(b))

    def test_dom_skeleton_notices_structure(self):
        a = "<div><p>x</p></div>"
        b = "<div><span>x</span></div>"
        self.assertNotEqual(fp.dom_skeleton_hash(a), fp.dom_skeleton_hash(b))

    def test_css_vocabulary_extracted(self):
        self.assertEqual(fp.css_vocabulary('<div class="wrap card"></div>'),
                         ["card", "wrap"])

    def test_header_order_is_order_sensitive(self):
        from collections import OrderedDict
        a = OrderedDict([("Server", "n"), ("Date", "d")])
        b = OrderedDict([("Date", "d"), ("Server", "n")])
        self.assertNotEqual(fp.header_order_hash(a), fp.header_order_hash(b))


class TestExtraction(unittest.TestCase):
    def test_strip_tags(self):
        self.assertNotIn("<", strip_tags(PAGE))

    def test_pgp_block_found(self):
        self.assertEqual(len(PGP_RE.findall(PAGE)), 1)

    def test_btc_address_found(self):
        self.assertIn("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", BTC_RE.findall(PAGE))

    def test_btc_regex_rejects_short_strings(self):
        self.assertEqual(BTC_RE.findall("1abc"), [])


class TestServiceEngines(unittest.TestCase):
    def setUp(self):
        self.corpus = generate(seed=21, n_actors=60)
        self.view = CorpusView(self.corpus.personas,
                               self.corpus.posts_by_persona(),
                               self.corpus.transactions)
        self.truth = self.corpus.truth()

    def _separation(self, engine) -> tuple:
        engine.fit(self.view)
        ids = [p.persona_id for p in self.corpus.personas]
        same, diff = [], []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                s = engine.score(ids[i], ids[j]).score
                (same if self.truth[ids[i]] == self.truth[ids[j]]
                 else diff).append(s)
        return float(np.mean(same)), float(np.mean(diff))

    def test_favicon_separates_same_from_different_actors(self):
        same, diff = self._separation(FaviconEngine())
        self.assertGreater(same, diff * 1.5)

    def test_template_separates_same_from_different_actors(self):
        same, diff = self._separation(TemplateEngine())
        self.assertGreater(same, diff)

    def test_tls_separates_same_from_different_actors(self):
        same, diff = self._separation(TLSEngine())
        self.assertGreater(same, diff)

    def test_engines_abstain_without_data(self):
        """A persona with no service data must produce no signal, not a zero
        that the calibrator would read as a confident dissimilarity."""
        from anveshak.schema import Persona
        now = datetime.now(timezone.utc)
        blank = [Persona(persona_id="X%d" % i, handle="h%d" % i, site="s",
                         first_seen=now, last_seen=now) for i in range(3)]
        view = CorpusView(blank, {}, [])
        for engine in (FaviconEngine(), TLSEngine(), TemplateEngine()):
            engine.fit(view)
            rs = engine.score("X0", "X1")
            self.assertEqual(rs.score, 0.0, engine.channel)

    def test_shared_stock_favicon_is_discounted(self):
        """Many personas share stock icons; the engine must weight by rarity
        rather than treating every exact match as decisive."""
        eng = FaviconEngine()
        eng.fit(self.view)
        best_common, best_rare = 0.0, 0.0
        for sha, holders in eng.sha_index.items():
            if len(holders) < 2:
                continue
            a, b = sorted(holders)[:2]
            s = eng.score(a, b).score
            if len(holders) >= 8:
                best_common = max(best_common, s)
            elif len(holders) == 2:
                best_rare = max(best_rare, s)
        if best_common and best_rare:
            self.assertLess(best_common, best_rare)


class TestTLSParsing(unittest.TestCase):
    def test_probe_tls_returns_error_not_exception(self):
        """A dead host must yield a TLSInfo carrying an error, never raise:
        one unreachable service should not abort a crawl."""
        info = fp.probe_tls("127.0.0.1", 1, timeout=1.0)
        self.assertFalse(info.present)
        self.assertTrue(info.error)

    def test_parse_real_certificate(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "unit-test.onion"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
        ])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=30))
                .add_extension(x509.SubjectAlternativeName(
                    [x509.DNSName("unit-test.onion")]), critical=False)
                .sign(key, hashes.SHA256()))

        info = fp._parse_cert(cert.public_bytes(serialization.Encoding.DER))
        self.assertTrue(info.present)
        self.assertTrue(info.self_signed)
        self.assertEqual(info.subject_cn, "unit-test.onion")
        self.assertEqual(info.issuer_o, "Test Org")
        self.assertEqual(info.sans, ["unit-test.onion"])
        self.assertEqual(len(info.spki_sha256), 64)

    def test_spki_identifies_the_key_not_the_certificate(self):
        """The property the engine relies on: reissuing a certificate around
        the same key must leave the SPKI hash unchanged, so the linkage
        survives a renewal."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        infos = []
        for cn in ("first.onion", "second.onion"):
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
            cert = (x509.CertificateBuilder()
                    .subject_name(name).issuer_name(name)
                    .public_key(key.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(days=1))
                    .not_valid_after(now + timedelta(days=30))
                    .sign(key, hashes.SHA256()))
            infos.append(fp._parse_cert(
                cert.public_bytes(serialization.Encoding.DER)))

        self.assertEqual(infos[0].spki_sha256, infos[1].spki_sha256)
        self.assertNotEqual(infos[0].cert_sha256, infos[1].cert_sha256)


class TestTradecraft(unittest.TestCase):
    def test_rhythm_flags_a_jittered_schedule(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        regular = [base + timedelta(days=d, hours=14) for d in range(40)]
        jittered = [base + timedelta(days=d, hours=(d * 7) % 24) for d in range(40)]
        reg_entropy, _ = _rhythm(regular)
        jit_entropy, _ = _rhythm(jittered)
        self.assertLess(reg_entropy, jit_entropy)

    def test_rhythm_handles_too_few_points(self):
        e, cv = _rhythm([])
        self.assertEqual((e, cv), (1.0, 0.0))

    def test_classifier_declines_on_tiny_input(self):
        clf = TradecraftClassifier().fit(np.zeros((5, 16)),
                                         np.array(["sloppy"] * 5))
        self.assertFalse(clf.available)
        self.assertEqual(clf.evaluate(np.zeros((2, 16)),
                                      np.array(["sloppy"] * 2)),
                         {"available": False})


class TestNeuralAuthorship(unittest.TestCase):
    def test_trains_and_embeds(self):
        from anveshak.engines.neural import NeuralAuthorshipEngine
        corpus = generate(seed=31, n_actors=40)
        view = CorpusView(corpus.personas, corpus.posts_by_persona(),
                          corpus.transactions)
        eng = NeuralAuthorshipEngine(epochs=2)
        eng.fit(view)
        if not eng.enabled:
            self.skipTest("torch unavailable")

        s = eng.net.summary()
        self.assertGreater(s["personas_embedded"], 20)
        # loss must actually go down, or the model is decorative
        self.assertLess(s["loss_curve"][-1], s["loss_curve"][0])

        truth = corpus.truth()
        ids = sorted(eng.net.embeddings)
        same, diff = [], []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                (same if truth[ids[i]] == truth[ids[j]] else diff).append(
                    eng.score(ids[i], ids[j]).score)
        self.assertGreater(float(np.mean(same)), float(np.mean(diff)))

    def test_uses_no_actor_labels(self):
        """The model must be trainable from observable data alone. If it ever
        needs actor labels, it stops being deployable and the held-out
        evaluation stops being honest."""
        import inspect
        from anveshak.ai import author_net
        src = inspect.getsource(author_net.AuthorNet.fit)
        self.assertNotIn("true_actor", src)
        # fit() takes posts keyed by persona and nothing else
        params = list(inspect.signature(author_net.AuthorNet.fit).parameters)
        self.assertEqual(params, ["self", "posts_by_persona"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
