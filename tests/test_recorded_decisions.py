# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Recorded requests compared with core and CLI-derived fixture values."""

import copy
import unittest

from support import AT, ASSETS, DATA, api, artifact, asset, fixture, invoke, outcome


class RecordedDecisionTests(unittest.TestCase):
    def setUp(self):
        self.api = api()
        self.survey = artifact("survey")
        self.policy = invoke(self.api.Policy.from_dict, asset("policy"))

    def test_core_only_derivation(self):
        for packs in (None, []):
            result = invoke(self.api.derive_contract, self.survey, self.policy, at=AT, extension_packs=packs)
            self.assertEqual(invoke(result.to_dict), fixture("contract"))
            self.assertEqual(invoke(self.survey.to_dict), fixture("survey"))

    def test_all_verdicts_against_core(self):
        contract = artifact("contract")
        for name, expected in (("profile", {"value": fixture("report")}),
                               ("profile-unfit", DATA["observations"]["verdict/alternate/false"]),
                               ("profile-degraded", DATA["observations"]["verdict/alternate/true"])):
            result = outcome(self, self.api.validate, expected, contract, artifact(name), at=AT)
            self.assertEqual(invoke(getattr, result, "verdict"), expected["value"]["report"]["verdict"])
            self.assertNotIsInstance(result, self.api.FitctlError)
        expected = DATA["observations"]["thermal/other-synthetic-host"]
        thermal = fixture("thermal")
        for group in ("providers", "readings"):
            for row in thermal["thermal_evidence"][group]:
                row["evidence_target"]["host_id"] = "other-synthetic-host"
        result = outcome(self, self.api.validate, expected, contract, artifact("profile-thermal"),
                         at=AT, mode="state_required", state=artifact("state"),
                         thermal_evidence=[invoke(self.api.Artifact.from_dict, thermal)], max_state_age_seconds=60)
        self.assertEqual(invoke(getattr, result, "verdict"), "indeterminate")
        self.assertEqual({fixture("report")["report"]["verdict"],
                          DATA["observations"]["verdict/alternate/false"]["value"]["report"]["verdict"],
                          DATA["observations"]["verdict/alternate/true"]["value"]["report"]["verdict"],
                          expected["value"]["report"]["verdict"]},
                         {"fit", "unfit", "fit_with_degradation", "indeterminate"})

    def test_explicit_extension_derivation(self):
        packs, context = [asset("extensions")], fixture("context-python")
        before = copy.deepcopy((packs, context))
        outcome(self, self.api.derive_contract, DATA["observations"]["derive/python-present"],
                artifact("survey-python"), self.policy, at=AT,
                extension_packs=packs, invocation_context=context)
        self.assertEqual((packs, context), before)
        outcome(self, self.api.derive_contract, DATA["observations"]["derive/enabled"],
                self.survey, self.policy, at=AT, extension_packs=packs, invocation_context=context)

    def test_extension_selection_matrix(self):
        for label, packs, context in (
            ("disabled", [asset("extensions")], asset("invocation_contexts")),
            ("missing_pack", None, fixture("context-python")),
            ("duplicate", [asset("extensions"), asset("extensions")], None),
            ("empty", [], None),
            ("unknown-namespace", [asset("extensions")], fixture("context-unknown")),
        ):
            survey = artifact("survey-python") if label == "unknown-namespace" else self.survey
            outcome(self, self.api.derive_contract, DATA["observations"][f"derive/{label}"],
                    survey, self.policy, at=AT, extension_packs=packs, invocation_context=context)
        policy = invoke(self.api.Policy.from_dict, fixture("policy-disabled"))
        outcome(self, self.api.derive_contract, DATA["observations"]["derive/policy-disabled"],
                artifact("survey-python"), policy, at=AT,
                extension_packs=[asset("extensions")], invocation_context=fixture("context-python"))

    def test_builtin_selection_and_copy(self):
        for category, name in ASSETS.items():
            first = invoke(self.api.builtin_config, category, name)
            second = invoke(self.api.builtin_config, category, name)
            self.assertEqual(first, asset(category))
            first.clear()
            self.assertEqual(second, asset(category))
            self.assertEqual(invoke(self.api.builtin_config, category, name), second)
        for category, name in (("", ""), ("absent", "absent"), ("policy", ""),
                               ("policy", "absent"), ("trust", "absent")):
            with self.assertRaises(KeyError) as caught:
                invoke(self.api.builtin_config, category, name)
            self.assertEqual(caught.exception.args, ("unknown builtin configuration",))
