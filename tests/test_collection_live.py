# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit live calls observe only their qualified visible context."""

import inspect
from pathlib import Path
import types
import unittest

import installed_support
from collection_support import collect, replay
from support import api, invoke


class CollectionLiveTests(unittest.TestCase):
    def test_default_state_has_no_optional_probes(self):
        for kwargs in ({}, {"path_checks": None, "link_pairs": None, "thermal_provider_config_paths": None},
                       {"path_checks": [], "link_pairs": [], "thermal_provider_config_paths": [],
                        "memory_reliability": False, "gpu_reliability": False, "hardware_sensors": False}):
            raw = invoke(collect("STATE", api().collect_state, **kwargs).to_dict)["state"]
            self.assertEqual(raw["collection_mode"], "live")
            self.assertEqual(raw["source_ref"], "live:linux_runtime_v1")
            core = raw["core_state"]
            self.assertEqual(core["freshness"]["freshness_state"], "fresh")
            self.assertTrue(core["freshness"]["observed_at"].startswith("unix:"))
            self.assertEqual(core["path_resources"], {"paths": [], "link_pairs": []})
            for name in ("thermal_resources", "hardware_sensor_resources", "memory_reliability", "gpu_reliability"):
                self.assertNotIn(name, core)

    def test_survey_describes_visible_context(self):
        raw = invoke(collect("SURVEY", api().collect_survey).to_dict)["survey"]
        self.assertEqual(raw["collection_mode"], "live")
        self.assertEqual(raw["source_ref"], "live:linux_core_v1")
        evidence = raw["core_evidence"]
        self.assertIn(evidence["execution_context"]["visibility_scope"],
                      ("bare_metal_like", "vm_like", "container_restricted", "unknown"))
        self.assertIn("cpu", evidence["observations"])
        self.assertIn("memory", evidence["observations"])
        self.assertIn("network", evidence["observations"])
        self.assertTrue(evidence["collectors"])

    def test_installed_collection_surface(self):
        module = api()
        self.assertEqual(installed_support.inspect_installation(module), installed_support.IDENTITY)
        for name in ("collect_survey", "collect_state", "replay_survey", "replay_state"):
            function = getattr(module, name)
            self.assertIsInstance(function, types.BuiltinFunctionType)
            self.assertIs(function, getattr(module._native, name))
            self.assertNotIn("**kwargs", str(inspect.signature(function)))
        stub = (Path(module.__file__).parent / "__init__.pyi").read_text()
        for name in ("PathCheck", "LinkPair"):
            self.assertIn("class " + name + "(TypedDict):", stub)
        for name in ("path_checks", "link_pairs", "thermal_provider_config_paths",
                     "memory_reliability", "gpu_reliability", "hardware_sensors"):
            self.assertIn(name, str(inspect.signature(module.collect_state)))
            self.assertIn(name + ":", stub)
        self.assertIs(type(replay("survey/complete")), module.Artifact)

    def test_optional_probes_preserve_unavailable_outcomes(self):
        fields = {"memory_reliability": "memory_reliability", "gpu_reliability": "gpu_reliability",
                  "hardware_sensors": "hardware_sensor_resources"}
        for names in (["memory_reliability"], ["gpu_reliability"], ["hardware_sensors"], list(fields)):
            raw = invoke(collect("OPTIONAL", api().collect_state, **dict.fromkeys(names, True)).to_dict)["state"]["core_state"]
            self.assertNotIn("thermal_resources", raw)
            for option, field in fields.items():
                self.assertEqual(field in raw, option in names)
            if "hardware_sensors" in names:
                hardware = raw["hardware_sensor_resources"]
                self.assertEqual(hardware["readings"], [])
                self.assertEqual(hardware["providers"][0]["outcome"], "unavailable")
                self.assertEqual(hardware["providers"][0]["reason_code"], "hardware_sensor_source_unavailable")
            if "gpu_reliability" in names:
                gpu = raw["gpu_reliability"]
                self.assertEqual(gpu["devices"], [])
                self.assertEqual(gpu["providers"][0]["outcome"], "unavailable")
                self.assertEqual(gpu["providers"][0]["error_code"], "nvidia_smi_unavailable")
            if "memory_reliability" in names:
                memory = raw["memory_reliability"]
                self.assertEqual(memory["providers"][0]["outcome"], "unavailable")
                self.assertEqual(memory["providers"][0]["error_code"], "edac_sysfs_unavailable")
                for field in ("controller_count", "dimm_count", "corrected_error_count", "uncorrected_error_count"):
                    self.assertEqual(memory[field], {"state": "unknown", "value": None})
