# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Finite batch reports, immutable views and exact core CSV exports."""

import copy
import json
import unittest

from batch_inputs import requests
from batch_support import DATA, arguments, compare, property_value, report
from error_cases import raises
from support import api, invoke


class BatchTests(unittest.TestCase):
    def test_core_matrix(self):
        for name, count in (("minimal", 1), ("matrix", 6)):
            value = compare(self, name)
            self.assertEqual(len(property_value(value, "rows")), count)
        self.assertEqual({row["verdict"] for row in property_value(value, "rows")},
                         {"fit", "fit_with_degradation", "unfit"})

    def test_core_ordering(self):
        first = compare(self, "matrix")
        raw = requests()["reversed"]
        supplied = arguments(raw)
        original = {key: list(supplied[key]) for key in ("contracts", "profiles", "states")}
        second = invoke(api().classify_batch, **supplied)
        self.assertEqual(invoke(first.to_dict), invoke(second.to_dict))
        self.assertEqual(property_value(first, "artifact_id"), property_value(second, "artifact_id"))
        for key, values in original.items():
            self.assertEqual(supplied[key], values)

    def test_report_roundtrip_and_copies(self):
        original = DATA["observations"]["matrix"]["value"]
        raw = copy.deepcopy(original)
        value = invoke(api().BatchReport.from_dict, raw)
        raw.clear()
        for factory, source in ((api().BatchReport.from_dict, invoke(value.to_dict)),
                                (api().BatchReport.from_json, invoke(value.to_json))):
            self.assertEqual(invoke(invoke(factory, source).to_dict), original)
        self.assertEqual(json.loads(invoke(value.to_json)), original)
        for name in ("schema_id", "schema_version", "artifact_id"):
            self.assertEqual(property_value(value, name), original["envelope"][name])
        for name in ("rows", "contract_summaries", "service_profile_summaries"):
            exported = property_value(value, name)
            self.assertEqual(exported, original["report"][name])
            exported[0].clear(); exported.clear()
            self.assertEqual(property_value(value, name), original["report"][name])
        exported = invoke(value.to_dict)
        exported["classification_basis"].clear()
        self.assertEqual(invoke(value.to_dict), original)
        for name in ("rows", "artifact_id", "unknown"):
            raises(self, AttributeError, "native value is immutable", setattr, value, name, None)
            raises(self, AttributeError, "native value is immutable", delattr, value, name)
        with self.assertRaises(TypeError):
            type("DerivedBatch", (api().BatchReport,), {})

    def test_core_csv_views(self):
        for name, views in DATA["csv"].items():
            value = report(name)
            for view, expected in views.items():
                self.assertEqual(invoke(value.export_csv, view), expected)
