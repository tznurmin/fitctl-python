# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact Python adaptation rejects before any core or filesystem effect."""

from pathlib import Path
import unittest

from collection_support import collect, core_error
from error_cases import Sentinel, pad, raises
from support import api


class CollectionAdmissionTests(unittest.TestCase):
    def test_signatures_and_exact_replay_types(self):
        Sentinel.calls = 0
        text = type("Text", (str,), {})
        for function in (api().replay_survey, api().replay_state):
            for args, kwargs in (((), {}), (("root",), {}), (("root", "sample", 0), {}),
                                 (("root", "sample"), {"fixtures_root": "other"}),
                                 (("root", "sample"), {"target": "selected-host"}),
                                 (("root", "sample"), {"runtime": "python"}),
                                 (("root", "sample"), {"collectors": []})):
                raises(self, TypeError, "invalid arguments", function, *args, **kwargs)
            for value in (b"root", 0, Path("root"), text("root"), Sentinel()):
                raises(self, TypeError, "invalid argument type", function, value, "sample")
                raises(self, TypeError, "invalid argument type", function, "root", value)
        raises(self, TypeError, "invalid arguments", api().collect_survey, 0)
        raises(self, TypeError, "invalid arguments", api().collect_survey, target="selected-host")
        self.assertEqual(Sentinel.calls, 0)

    def test_replay_string_boundaries(self):
        for kind in ("survey", "state"):
            function = getattr(api(), "replay_" + kind)
            expected = {"error_model_id": f"fitctl.{kind}.v1", "error_model_version": 1,
                        "reason_code": "fixture_corpus_invalid", "checkpoint_id": "fixture_load"}
            for multi in (False, True):
                for index, limit in ((0, 4096), (1, 128)):
                    for size in (limit - 1, limit, limit + 1):
                        args = ["/work/collection/missing-root", "sample"]
                        args[index] = pad(size, multi)
                        if size > limit:
                            raises(self, ValueError, "argument budget exceeded", function, *args)
                        else:
                            # A NUL prevents accidental traversal of an enormous relative root.
                            if index == 0:
                                args[index] = "\0" + pad(size - 1, multi)
                            with self.assertRaises(api().CoreError) as caught:
                                collect("REPLAY", function, *args)
                            core_error(self, caught.exception, expected, "replay_" + kind)
            raises(self, ValueError, "invalid Unicode scalar", function, "\ud800", "sample")
            raises(self, ValueError, "invalid Unicode scalar", function, "root", "\udc00")

    def test_state_types_counts_and_precedence(self):
        function = api().collect_state
        Sentinel.calls = 0
        for name in ("path_checks", "link_pairs", "thermal_provider_config_paths"):
            for value in ((), (x for x in ()), type("Items", (list,), {})(), 1, Sentinel()):
                raises(self, TypeError, "invalid argument type", function, **{name: value})
        for name in ("memory_reliability", "gpu_reliability", "hardware_sensors"):
            for value in (0, 1, None, "true"):
                raises(self, TypeError, "invalid argument type", function, **{name: value})
        for name, entry, message in (
            ("path_checks", [], "invalid argument type"),
            ("path_checks", {}, "invalid arguments"),
            ("path_checks", {"path_id": "a", "path": "a", "extra": 0}, "invalid arguments"),
            ("path_checks", {0: "a", "path": "a"}, "invalid argument type"),
            ("path_checks", {"path_id": 0, "path": "a"}, "invalid argument type"),
            ("path_checks", {"path_id": "a", "path": "a", "probe_links": None}, "invalid argument type"),
            ("path_checks", {"path_id": "a", "path": "a", "probe_health": 0}, "invalid argument type"),
            ("link_pairs", {"from_path_id": "a"}, "invalid arguments"),
            ("link_pairs", {"from_path_id": "a", "to_path_id": None}, "invalid argument type"),
            ("thermal_provider_config_paths", None, "invalid argument type"),
        ):
            raises(self, TypeError, message, function, **{name: [entry]})
        for name, count in (("path_checks", 17), ("link_pairs", 17), ("thermal_provider_config_paths", 5)):
            raises(self, ValueError, "argument budget exceeded", function, **{name: [None] * count})
        for kwargs in (
            {"path_checks": [{"path_id": "a" * 129, "path": "a"}]},
            {"path_checks": [{"path_id": "a", "path": "a" * 4097}]},
            {"link_pairs": [{"from_path_id": "a", "to_path_id": "a" * 129}]},
            {"thermal_provider_config_paths": ["a" * 4097]},
            {"path_checks": [{"path_id": "a", "path": "a" * 4096}] * 16},
        ):
            original = repr(kwargs)
            raises(self, ValueError, "argument budget exceeded", function, **kwargs)
            self.assertEqual(repr(kwargs), original)
        raises(self, TypeError, "invalid argument type", function, path_checks=[None] * 17, hardware_sensors=0)
        self.assertEqual(Sentinel.calls, 0)
