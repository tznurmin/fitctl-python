# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete independent-core replay comparisons and a recorded consumer."""

import shutil
import unittest

from collection_support import DATA, ROOT, core_error, prepare, replay
from support import AT, api, artifact, asset, invoke


class CollectionTests(unittest.TestCase):
    def setUp(self):
        prepare()

    def test_replay_values_match_core(self):
        count = 0
        for name, expected in DATA["observations"].items():
            if "value" not in expected:
                continue
            with self.subTest(name=name):
                value = replay(name)
                self.assertIs(type(value), api().Artifact)
                self.assertEqual(invoke(value.to_dict), expected["value"])
                count += 1
        self.assertEqual(count, 8)

    def test_replay_errors_match_core(self):
        count = 0
        for name, expected in DATA["observations"].items():
            if "error" not in expected:
                continue
            with self.subTest(name=name):
                with self.assertRaises(api().CoreError) as caught:
                    replay(name)
                core_error(self, caught.exception, expected["error"], "replay_" + name.split("/")[0])
                count += 1
        self.assertEqual(count, 30)

    def test_replay_provenance_and_unknowns(self):
        for name in ("survey/complete", "survey/unknown", "survey/restricted", "state/stale", "state/unknown"):
            raw = invoke(replay(name).to_dict)
            kind = name.split("/")[0]
            self.assertEqual(raw, DATA["observations"][name]["value"])
            self.assertEqual(raw["envelope"]["provenance"]["collected_at"], AT)
            self.assertEqual(raw[kind]["collection_mode"], "replay")
            self.assertEqual(raw[kind]["source_ref"], "fixture_corpus:collection-synthetic-v1")
            self.assertEqual(raw[kind]["host_alias"], "collection-host")
        unknown = invoke(replay("state/unknown").to_dict)["state"]["core_state"]
        self.assertEqual(unknown["resources"]["allocatable_cpu_logical_cores"], {"state": "unknown", "value": None})
        stale = invoke(replay("state/stale").to_dict)["state"]["core_state"]
        self.assertEqual(stale["freshness"], {"freshness_state": "stale", "observed_at": AT})
        self.assertNotIn("local_identity", invoke(replay("state/complete").to_dict)["state"])
        survey = invoke(replay("survey/machine_identity").to_dict)["survey"]["core_evidence"]["identity_summary"]
        state = invoke(replay("state/machine_identity").to_dict)["state"]["local_identity"]
        self.assertEqual(survey["local_stable_id"], state["local_stable_id"])
        self.assertEqual(state["local_stable_anchor_source"], "etc_machine_id")

    def test_replay_feeds_recorded_workflow(self):
        survey, state = replay("survey/complete"), replay("state/complete")
        original = invoke(survey.to_dict)
        policy = invoke(api().Policy.from_dict, asset("policy"))
        contract = invoke(api().derive_contract, survey, policy, at=AT)
        profile = artifact("profile")
        result = invoke(api().validate, contract, profile, state=state, mode="state_required", at=AT)
        self.assertEqual(invoke(lambda: result.verdict), "fit")
        batch = invoke(api().classify_batch, [contract], [profile], states=[state], mode="state_required", at=AT)
        self.assertEqual([row["verdict"] for row in invoke(lambda: batch.rows)], ["fit"])
        shutil.rmtree(ROOT)
        exported = invoke(survey.to_dict)
        exported.clear()
        self.assertEqual(invoke(survey.to_dict), original)
        restored = invoke(api().Artifact.from_json, invoke(survey.to_json))
        self.assertEqual(invoke(restored.to_dict), original)
