# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Core state selection and runtime-sensitive freshness remain unchanged."""

import unittest

from batch_support import DATA, compare, property_value
from support import invoke


class BatchStateTests(unittest.TestCase):
    def test_core_identity_selection(self):
        for name, basis in (("alias_fallback", "host_alias_fallback"), ("identity_priority", "local_stable_id")):
            value = compare(self, name)
            actual = invoke(value.to_dict)["classification_basis"]["ordered_contracts"][0]
            self.assertEqual(actual["matched_state"]["match_basis"], basis)

    def test_mode_and_state_matrix(self):
        names = [name for name in DATA["observations"] if name.startswith(("runtime_", "state_advisory_", "state_required_"))]
        names.extend(("contract_only_state", "contract_only_age", "age_without_state"))
        for name in names:
            with self.subTest(name=name):
                compare(self, name)
        for mode in ("state_advisory", "state_required"):
            value = compare(self, mode + "_missing")
            row = property_value(value, "rows")[0]
            self.assertEqual((row["verdict"], row["primary_reason_code"]),
                             ("indeterminate", "state_missing"))
            for suffix, verdict, reason in (("missing", "indeterminate", "state_missing"),
                    ("state-stale", "indeterminate", "state_stale"),
                    ("state-unknown-cpu", "indeterminate", "state_missing"),
                    ("state-future", "fit", "requirements_satisfied")):
                row = DATA["observations"][f"runtime_{mode}_{suffix}"]["value"]["report"]["rows"][0]
                self.assertEqual((row["verdict"], row["primary_reason_code"]), (verdict, reason))

    def test_freshness_boundaries(self):
        for name in ("age_59", "age_60", "age_61", "max_age_0", "max_age_18446744073709551615"):
            value = compare(self, name)
            row = property_value(value, "rows")[0]
            self.assertEqual(row["verdict"], "indeterminate" if name == "age_61" else "fit")
            if name == "age_61":
                self.assertEqual(row["primary_reason_code"], "state_stale")
