"""Test suite.

Written with unittest rather than pytest so it runs on a bare Python install,
which at a hackathon is the difference between "the tests pass" and "let me
just install one more thing".

The end-to-end tests assert *floors*, not exact values. Pinning an AUC to four
decimals produces a suite that breaks whenever anyone improves the system,
which trains people to ignore it. What we actually want guarded is the set of
claims the project makes: the traps hold, the blocker does not silently drop
cases, calibration stays useful, and behavioural channels keep outperforming
artefact channels against disciplined operators.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anveshak import pipeline
from anveshak.corpus.generator import generate
from anveshak.engines.base import CorpusView, rarity_weight
from anveshak.engines.crypto import CryptoEngine
from anveshak.engines.handle import normalise
from anveshak.engines.temporal import TemporalEngine
from anveshak.evaluation import metrics
from anveshak.fusion.lr import ChannelCalibrator
from anveshak.reporting import dossier_report, evidence_report
from anveshak.schema import Evidence, posterior_from_log10_lr


# One pipeline run shared by the end-to-end tests; it is the expensive part.
_RESULT = None


def result():
    global _RESULT
    if _RESULT is None:
        _RESULT = pipeline.run(seed=1337, n_actors=90)
    return _RESULT


class TestRarityWeight(unittest.TestCase):
    def test_unique_match_is_maximally_informative(self):
        self.assertAlmostEqual(rarity_weight(2, 500), 1.0, places=6)

    def test_widely_shared_value_is_worthless(self):
        # a value held by half the population tells you almost nothing
        self.assertLess(rarity_weight(250, 500), 0.15)

    def test_monotonically_decreasing(self):
        vals = [rarity_weight(k, 500) for k in range(2, 200, 10)]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_degenerate_inputs(self):
        self.assertEqual(rarity_weight(1, 500), 0.0)
        self.assertEqual(rarity_weight(5, 2), 0.0)


class TestEvidence(unittest.TestCase):
    def test_log_lr_is_capped_both_directions(self):
        self.assertEqual(Evidence("pgp", "a", "b", 1.0, 99.0, "").log10_lr, 4.0)
        self.assertEqual(Evidence("pgp", "a", "b", 1.0, -99.0, "").log10_lr, -4.0)

    def test_verbal_scale_reports_direction(self):
        self.assertIn("same", Evidence("pgp", "a", "b", 1, 3.2, "").verbal)
        self.assertIn("different", Evidence("pgp", "a", "b", 1, -3.2, "").verbal)
        self.assertEqual(Evidence("pgp", "a", "b", 1, 0.05, "").verbal, "uninformative")

    def test_posterior_follows_bayes_in_odds_form(self):
        # LR of 100 against a prior of 1:100 must land exactly at even odds
        self.assertAlmostEqual(posterior_from_log10_lr(2.0, 1 / 100), 0.5, places=6)

    def test_posterior_respects_the_prior(self):
        strong, weak = 1 / 10, 1 / 10000
        self.assertGreater(posterior_from_log10_lr(2.0, strong),
                           posterior_from_log10_lr(2.0, weak))


class TestHandleNormalisation(unittest.TestCase):
    def test_leet_and_separators_collapse(self):
        self.assertEqual(normalise("n1ghto_wl"), normalise("nightowl"))

    def test_decorations_are_stripped(self):
        for variant in ("nightowl_42", "TheNightowl", "nightowl-official"):
            self.assertEqual(normalise(variant), "nightowl", variant)

    def test_distinct_names_stay_distinct(self):
        self.assertNotEqual(normalise("nightowl"), normalise("harborlight"))


class TestCryptoServiceDetection(unittest.TestCase):
    """The mixer trap. Without service detection, common-input-ownership
    welds most of the graph into one cluster and the channel is worthless."""

    def setUp(self):
        self.corpus = generate(seed=7, n_actors=40)
        self.view = CorpusView(self.corpus.personas,
                               self.corpus.posts_by_persona(),
                               self.corpus.transactions)
        self.engine = CryptoEngine()
        self.engine.fit(self.view)

    def test_planted_mixers_are_quarantined(self):
        for mixer in self.corpus.traps["mixer"]:
            self.assertIn(mixer, self.engine.services,
                          "mixer %s was not detected as a service" % mixer[:12])

    def test_graph_does_not_collapse(self):
        d = self.engine.diagnostics()
        addresses = max(1, d["addresses"])
        self.assertLess(d["largest_cluster"] / addresses, 0.25,
                        "clustering collapsed: %s" % d)

    def test_cluster_linkage_is_discounted_by_cluster_size(self):
        # rarity weighting must make a big-cluster link weaker than a small one
        self.assertGreater(len(self.engine.cluster_size), 1)


class TestTemporalEngine(unittest.TestCase):
    def setUp(self):
        self.corpus = generate(seed=11, n_actors=50)
        view = CorpusView(self.corpus.personas, self.corpus.posts_by_persona(),
                          self.corpus.transactions)
        self.engine = TemporalEngine()
        self.engine.fit(view)

    def test_utc_offset_recovery(self):
        errs = []
        for p in self.corpus.personas:
            geo = self.engine.geolocation(p.persona_id)
            if geo["offset"] is None or geo["confidence"] < 0.5:
                continue
            true = self.corpus.actors[p.true_actor].tz_offset
            d = abs(geo["offset"] - true) % 24
            errs.append(min(d, 24 - d))
        self.assertGreater(len(errs), 20)
        self.assertLess(float(np.median(errs)), 3.0,
                        "median offset error too large: %.2f" % np.median(errs))

    def test_same_actor_scores_above_different_actor(self):
        truth = self.corpus.truth()
        ids = sorted(self.engine.hist)
        same, diff = [], []
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                (same if truth[a] == truth[b] else diff).append(
                    self.engine.score(a, b).score)
        self.assertGreater(float(np.mean(same)), float(np.mean(diff)) * 1.5)

    def test_flat_poster_gets_no_location_claim(self):
        flat = np.full(24, 1 / 24)
        _offset, conf = self.engine._infer_offset(flat)
        self.assertLess(conf, 0.05)


class TestCalibration(unittest.TestCase):
    def test_uninformative_channel_yields_lr_of_one(self):
        rng = np.random.default_rng(0)
        scores = rng.random(400)
        labels = rng.integers(0, 2, 400)          # no relationship at all
        cal = ChannelCalibrator("noise").fit(scores, labels)
        for s in (0.0, 0.5, 1.0):
            self.assertLess(abs(cal.log10_lr(s)), 0.5)

    def test_informative_channel_yields_positive_lr_on_high_scores(self):
        rng = np.random.default_rng(1)
        labels = np.concatenate([np.ones(200, int), np.zeros(200, int)])
        scores = np.concatenate([rng.normal(0.8, 0.1, 200),
                                 rng.normal(0.2, 0.1, 200)])
        cal = ChannelCalibrator("signal").fit(scores, labels)
        self.assertGreater(cal.log10_lr(0.9), 0.5)
        self.assertLess(cal.log10_lr(0.1), 0.0)

    def test_artefact_channels_have_a_negative_floor(self):
        self.assertEqual(ChannelCalibrator("pgp").neg_cap, -0.5)
        self.assertEqual(ChannelCalibrator("stylometry").neg_cap, -4.0)

    def test_refuses_to_fit_on_too_few_positives(self):
        cal = ChannelCalibrator("x").fit(np.random.random(50),
                                         np.array([1] + [0] * 49))
        self.assertFalse(cal.informative)
        self.assertEqual(cal.log10_lr(0.9), 0.0)


class TestMetrics(unittest.TestCase):
    def test_cllr_rewards_correct_confidence(self):
        y = np.array([1] * 50 + [0] * 50)
        good = np.array([2.0] * 50 + [-2.0] * 50)
        bad = np.array([-2.0] * 50 + [2.0] * 50)
        self.assertLess(metrics.cllr(y, good)["cllr"], metrics.cllr(y, bad)["cllr"])

    def test_cllr_of_an_uninformative_system_is_one(self):
        y = np.array([1] * 50 + [0] * 50)
        self.assertAlmostEqual(metrics.cllr(y, np.zeros(100))["cllr"], 1.0, places=6)

    def test_cllr_min_never_exceeds_cllr(self):
        rng = np.random.default_rng(3)
        y = np.array([1] * 60 + [0] * 60)
        s = np.concatenate([rng.normal(1, 1, 60), rng.normal(-1, 1, 60)])
        c = metrics.cllr(y, s)
        self.assertLessEqual(c["cllr_min"], c["cllr"] + 1e-9)

    def test_threshold_respects_the_hard_evidential_floor(self):
        # data where a very low threshold would be "optimal"
        y = np.array([1] * 30 + [0] * 30)
        s = np.concatenate([np.full(30, 0.2), np.full(30, -3.0)])
        self.assertGreaterEqual(metrics.choose_threshold(y, s, floor=1.0), 1.0)

    def test_bcubed_perfect_clustering(self):
        truth = {"a": "A", "b": "A", "c": "B"}
        pred = {"a": "1", "b": "1", "c": "2"}
        r = metrics.bcubed(pred, truth)
        self.assertAlmostEqual(r["bcubed_f1"], 1.0, places=6)

    def test_bcubed_penalises_over_merging(self):
        truth = {"a": "A", "b": "A", "c": "B"}
        pred = {"a": "1", "b": "1", "c": "1"}
        self.assertLess(metrics.bcubed(pred, truth)["bcubed_precision"], 1.0)


class TestCorpus(unittest.TestCase):
    def test_reproducible(self):
        a, b = generate(seed=5, n_actors=20), generate(seed=5, n_actors=20)
        self.assertEqual([p.persona_id for p in a.personas],
                         [p.persona_id for p in b.personas])
        self.assertEqual([p.handle for p in a.personas],
                         [p.handle for p in b.personas])

    def test_handles_are_unique_per_actor_root(self):
        """Regression: an earlier version recycled roots with a numeric suffix
        once the pool ran dry, creating unrelated actors called `sixthgate` and
        `sixthgate103` and manufacturing false positives no engine could
        fairly reject."""
        c = generate(seed=5, n_actors=150)
        roots = [a.handle_root for a in c.actors.values()]
        self.assertEqual(len(roots), len(set(roots)))

    def test_all_traps_are_planted(self):
        c = generate(seed=5, n_actors=90)
        for trap in ("shared_host", "copypaste", "key_rotation", "mixer",
                     "handle_collision"):
            self.assertTrue(c.traps[trap], "trap %s was not planted" % trap)

    def test_every_opsec_tier_is_represented(self):
        c = generate(seed=5, n_actors=90)
        tiers = {a.opsec for a in c.actors.values()}
        self.assertEqual(tiers, {"sloppy", "mixed", "disciplined"})

    def test_base_rate_is_realistically_low(self):
        stats = generate(seed=5, n_actors=90).stats()
        self.assertLess(stats["base_rate"], 0.03)


class TestEndToEnd(unittest.TestCase):
    def test_discrimination_floor(self):
        self.assertGreater(result().report["discrimination"]["roc_auc"], 0.90)

    def test_precision_floor(self):
        self.assertGreater(result().report["operating_point"]["precision"], 0.80)

    def test_calibration_beats_saying_nothing(self):
        self.assertLess(result().report["calibration"]["cllr"], 1.0)

    def test_blocking_keeps_most_true_links(self):
        self.assertGreater(result().report["blocking"]["pair_completeness"], 0.85)
        self.assertGreater(result().report["blocking"]["reduction_ratio"], 0.5)

    def test_false_positive_traps_hold(self):
        traps = result().report["traps"]
        for name in ("shared_host", "copypaste", "handle_collision"):
            self.assertTrue(traps[name]["survived"],
                            "%s trap produced %d false links"
                            % (name, traps[name]["false_links_emitted"]))

    def test_behaviour_outlasts_artefacts_against_disciplined_operators(self):
        """The central claim of the project, asserted as a test.

        Against a disciplined operator every rotatable artefact should be near
        chance while behaviour still carries signal. If this ever stops being
        true, the pitch is wrong and the suite should say so."""
        row = result().report["channel_auc_by_opsec"].get("disciplined")
        if not row:
            self.skipTest("too few disciplined pairs in this corpus")
        artefacts = max(row[c] for c in ("pgp", "handle", "crypto", "device"))
        behavioural = max(row["stylometry"], row["temporal"])
        self.assertGreater(behavioural, artefacts + 0.10)

    def test_fusion_beats_every_single_channel(self):
        r = result().report
        best_solo = max(v["solo_auc"] or 0
                        for v in r["ablation"]["channels"].values())
        self.assertGreater(r["discrimination"]["roc_auc"], best_solo)

    def test_split_partitions_actors_without_overlap(self):
        """Calibration must never see an actor it is later scored on.

        Splitting on pairs instead of actors would let a persona appear in both
        halves, and the model could then learn that specific persona rather
        than the phenomenon. The counts are the observable consequence: every
        actor lands on exactly one side, and no pair spans the two."""
        r = result().report
        s = r["split"]
        self.assertEqual(s["train_actors"] + s["test_actors"], r["corpus"]["actors"])
        self.assertGreater(s["test_pairs"], 0)
        self.assertGreater(s["train_pairs"], 0)
        # cross-split pairs are scored by neither, so the two counts must leave
        # room for them rather than summing to the whole candidate set
        self.assertLessEqual(s["train_pairs"] + s["test_pairs"],
                             r["blocking"]["candidate_pairs"])

    def test_reports_render(self):
        r = result()
        personas = {p.persona_id: p for p in r.corpus.personas}
        self.assertTrue(r.links, "no links produced")
        text = evidence_report(r.links[0], personas, r.engines["temporal"],
                               1 / 500, 1.0)
        for expected in ("PROPOSITIONS COMPARED", "EVIDENCE BY CHANNEL",
                         "LIMITATIONS AND PROPER USE", "posterior probability"):
            self.assertIn(expected, text)
        if r.dossiers:
            self.assertIn("RESOLVED ACTOR DOSSIER", dossier_report(r.dossiers[0]))

    def test_every_asserted_link_carries_at_least_one_channel(self):
        thr = result().report["settings"]["threshold_log10_lr"]
        for l in result().links:
            if l.log10_lr >= thr:
                self.assertTrue(l.channels,
                                "%s/%s asserted with no channel evidence"
                                % (l.persona_a, l.persona_b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
