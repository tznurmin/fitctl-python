# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed core configuration errors and explicit local provider outcomes."""

import unittest

from collection_provider_inputs import ROOT, invalid_configs, provider, write_config
from collection_support import collect, core_error
from support import api, invoke


def state(providers):
    path = write_config(providers)
    value = collect("PROVIDER", api().collect_state, thermal_provider_config_paths=[path])
    return invoke(value.to_dict)["state"]["core_state"]["thermal_resources"]


class CollectionProviderTests(unittest.TestCase):
    def test_config_errors_are_core_failures(self):
        ROOT.mkdir(exist_ok=True)
        for name, (path, checkpoint) in invalid_configs().items():
            with self.subTest(name=name):
                with self.assertRaises(api().CoreError) as caught:
                    collect("CONFIG", api().collect_state, thermal_provider_config_paths=[path])
                core_error(self, caught.exception, {"error_model_id": "fitctl.state.v1",
                    "error_model_version": 1, "reason_code": "state_payload_malformed",
                    "checkpoint_id": "thermal_provider_config_" + checkpoint}, "collect_state")

    def test_provider_outcomes_and_bounds(self):
        for mode, outcome, reason in (
            ("good", "success", None), ("empty", "partial", "no_temperature_readings"),
            ("malformed", "malformed", "output_malformed"), ("exit7", "command_failed", "command_failed"),
            ("missing", "unavailable", "unavailable"), ("denied", "permission_denied", "permission_denied"),
            ("sleep2", "command_failed", "command_timeout"), ("oversized", "malformed", "output_too_large"),
        ):
            with self.subTest(mode=mode):
                thermal = state([provider(mode)])
                self.assertEqual(len(thermal["providers"]), 1)
                row = thermal["providers"][0]
                self.assertEqual(row["provider_id"], "fixture")
                self.assertEqual(row["outcome"], outcome)
                self.assertEqual(row.get("error_code"), None if reason is None else "thermal_provider_" + reason)
                self.assertEqual(len(thermal["readings"]), 1 if mode == "good" else 0)
                if mode == "good":
                    self.assertEqual(thermal["readings"][0]["temperature_millidegrees_celsius"], 55000)

    def test_targets_mappings_and_partial_composition(self):
        first = provider()
        first["evidence_target"] = {"target_kind": "host_id", "host_id": "selected-host",
                                    "collection_path": "local_process"}
        first["sensor_mappings"] = [{"raw_label": "Core 0", "sensor_role": "cpu", "sensor_alias": "package0"}]
        thermal = state([first, provider("malformed", name="bad")])
        self.assertEqual([row["outcome"] for row in thermal["providers"]], ["success", "malformed"])
        self.assertEqual(thermal["providers"][0]["evidence_target"], first["evidence_target"])
        self.assertIs(type(thermal["collector_host"]["host_alias"]), str)
        self.assertTrue(thermal["collector_host"]["host_alias"])
        self.assertNotEqual(thermal["collector_host"]["host_alias"], "selected-host")
        reading = thermal["readings"][0]
        self.assertEqual((reading["sensor_role"], reading["sensor_alias"], reading["temperature_millidegrees_celsius"]),
                         ("cpu", "package0", 55000))
