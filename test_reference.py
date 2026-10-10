"""Freeze all aggregate responses without requiring the source image-level CSV."""

import hashlib
import json
import math
import unittest

from reference import COHORTS, SOURCE, get_reference


SOURCE_SHA256 = "d6bb68a18b99aa47346a82fd37498330b1a020f75fd8fddf0d6b83e37ff73d8d"
# Computed directly from the original application's responses during migration.
# These cover every float in the KDE curves, quantiles, ranges, and metadata.
FROZEN_RESPONSES = {
    "cfp/internal_test": "e0c0c807603f97e31c3a43c25ef19f04e8acf890ac3fdb34c7806ef7eb75cc78",
    "cfp/prospective": "535df0e0a68b19ed600413d1ab1f93acba03507e0e8bc8619ac87ba0b310ac4c",
    "cfp/shanghai": "0bcf6e8769438a6d1c07a288661fb38b663bfa8c51ff04c939d7e011cb80493e",
    "cfp/zhengzhou": "5f46cd6aec5bfc8b3837a31c574668f1c2a83d409f48c23f7617fe4cad2a4006",
    "cfp/jilin": "2c1784ac4f00936c7b1b670b18f077973949a722e18904b5218d9064f58959c1",
    "cfp/proton": "322f969819db0b76dd13f66bd1bb634924efbccc77be14da7a6f76bab5ed89db",
    "oct/internal_test": "7c580757a7b62e588db24f560f17f3e9261e6bd4b263f0e5ec0492ef963b6963",
    "oct/prospective": "44398df037d4cd6271a2c43183c5e28c6f8fac7b4356fa21cc61eda949065aff",
    "oct/shanghai": "3c8587608fe6680d9a6a7e6966b55ba2f471c60a452b05e695542f3283b3c292",
    "oct/zhengzhou": "00f3bd0dd6b4ed56dc21d23154d31ae99fd651ebbfc709acbfb7b04e6ecb02aa",
    "oct/jilin": "edff3155bb0a158c52faa26707da0004aea4b08852c832e5be28073c02b0fdc7",
    "oct/proton": "455b14d4f9eb6993ffc9175fc543ecbb745b381b721978381e4e0c1e4e332d0d",
}
EXPECTED_COUNTS = {
    "cfp": [(1943, 962), (247, 124), (385, 179), (309, 205), (49, 0), (120, 21)],
    "oct": [(5864, 3704), (376, 262), (712, 322), (492, 368), (11, 0), (107, 20)],
}


class ReferenceTests(unittest.TestCase):
    def test_every_response_matches_original_application_exactly(self):
        for selection, expected in FROZEN_RESPONSES.items():
            with self.subTest(selection=selection):
                reference = get_reference(*selection.split("/"))
                payload = json.dumps(reference, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)
                self.assertEqual(reference["source_sha256"], SOURCE_SHA256)

    def test_all_cohort_denominators_and_provenance(self):
        totals = {}
        for modality, counts in EXPECTED_COUNTS.items():
            totals[modality] = 0
            for cohort, expected in zip(COHORTS, counts):
                reference = get_reference(modality, cohort)
                self.assertEqual([g["n"] for g in reference["groups"]], list(expected))
                self.assertEqual(reference["n"], sum(expected))
                totals[modality] += reference["n"]
        self.assertEqual(totals, {"cfp": 4544, "oct": 12238})
        bundle = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(bundle["provenance"]["source_sha256"], SOURCE_SHA256)
        self.assertEqual(bundle["provenance"]["image_counts"], totals)

    def test_curves_remain_within_observed_ranges(self):
        for modality in EXPECTED_COUNTS:
            for cohort in COHORTS:
                reference = get_reference(modality, cohort)
                observed = [g for g in reference["groups"] if g["n"]]
                self.assertEqual(reference["range"], [min(g["min"] for g in observed),
                                                      max(g["max"] for g in observed)])
                for group in observed:
                    quantiles = [group[k] for k in ("min", "q1", "median", "q3", "max")]
                    self.assertEqual(quantiles, sorted(quantiles))
                    self.assertEqual(len(group["x"]), 256)
                    self.assertEqual(len(group["density"]), 256)
                    self.assertEqual(group["x"][0], group["min"])
                    self.assertEqual(group["x"][-1], group["max"])
                    self.assertTrue(all(a < b for a, b in zip(group["x"], group["x"][1:])))
                    self.assertTrue(all(math.isfinite(d) and 0 < d <= 1 for d in group["density"]))
                    self.assertEqual(max(group["density"]), 1)

    def test_internal_test_quantiles_are_frozen(self):
        expected = {
            "cfp": [[-13.7929687, 3.953125, 11.28125, 14.0390624, 16.296875],
                    [-14.8515624, -10.255859300000001, -5.4121094, -1.79272462, 15.3828124]],
            "oct": [[-5.2089844, 1.4680175825000001, 3.7304688, 5.29980475, 7.9804688],
                    [-5.2519532, -3.2934570749999996, -2.5097656500000003, -1.228515615, 6.2890625]],
        }
        for modality, quantiles in expected.items():
            actual = [[g[k] for k in ("min", "q1", "median", "q3", "max")]
                      for g in get_reference(modality)["groups"]]
            self.assertEqual(actual, quantiles)

    def test_missing_negative_class_is_not_invented(self):
        for modality in EXPECTED_COUNTS:
            positive, negative = get_reference(modality, "jilin")["groups"]
            self.assertGreater(positive["n"], 0)
            self.assertEqual(negative, {"label": 0, "n": 0, "min": None, "q1": None,
                                       "median": None, "q3": None, "max": None,
                                       "x": [], "density": []})

    def test_payload_contains_only_aggregate_fields(self):
        bundle = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(set(bundle), {"format_version", "provenance", "references"})
        self.assertEqual(set(bundle["references"]), {"cfp", "oct"})
        for references in bundle["references"].values():
            self.assertEqual(set(references), set(COHORTS))
            for reference in references.values():
                self.assertEqual(set(reference), {"modality", "cohort", "cohort_label", "source",
                                                 "source_sha256", "n", "groups", "range"})
                self.assertEqual(len(reference["groups"]), 2)
                for group in reference["groups"]:
                    self.assertEqual(set(group), {"label", "n", "min", "q1", "median", "q3",
                                                   "max", "x", "density"})

    def test_callers_cannot_mutate_cached_reference(self):
        reference = get_reference()
        reference["groups"][0]["density"][0] = -1
        self.assertGreater(get_reference()["groups"][0]["density"][0], 0)

    def test_rejects_unknown_selection(self):
        for modality, cohort in (("fundus", "internal_test"), ("cfp", "all")):
            with self.assertRaises(ValueError):
                get_reference(modality, cohort)


if __name__ == "__main__":
    unittest.main()
