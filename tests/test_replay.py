# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit supplied-time, state and thermal replay, without collection."""

import unittest

from support import AT, DATA, api, artifact, fixture, invoke, outcome

MODES = ("contract_only", "state_advisory", "state_required")
TIMES = {"before": "2025-12-31T23:59:59Z", "zero": AT,
         "below": "2026-01-01T00:00:59Z", "at": "2026-01-01T00:01:00Z",
         "above": "2026-01-01T00:01:01Z"}


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.api = api()
        self.contract, self.profile, self.state = (artifact(name) for name in ("contract", "profile", "state"))

    def test_mode_age_boundary_matrix(self):
        for mode in MODES:
            for label, at in TIMES.items():
                for present in (False, True):
                    expected = DATA["observations"][f"freshness/{mode}/{label}/{str(present).lower()}"]
                    outcome(self, self.api.validate, expected, self.contract, self.profile,
                            at=at, mode=mode, state=self.state if present else None, max_state_age_seconds=60)
                expected = DATA["observations"][f"runtime/{mode}/{label}"]
                outcome(self, self.api.validate, expected, self.contract, artifact("profile-runtime"),
                        at=at, mode=mode, state=self.state, max_state_age_seconds=60)
        self.assertEqual(invoke(self.state.to_dict), fixture("state"))

    def test_missing_stale_future_matrix(self):
        for mode in MODES:
            missing = outcome(self, self.api.validate, DATA["observations"][f"freshness/{mode}/default"],
                    self.contract, self.profile, at=AT, mode=mode)
            if mode != "contract_only":
                self.assertEqual((invoke(getattr, missing, "verdict"), invoke(getattr, missing, "primary_reason_code")),
                                 ("indeterminate", "state_missing"))
            for present in (False, True):
                outcome(self, self.api.validate,
                        DATA["observations"][f"runtime/{mode}/default/{str(present).lower()}"],
                        self.contract, artifact("profile-runtime"), at=AT, mode=mode,
                        state=self.state if present else None)
            for label in ("stale", "future", "unknown-cpu", "other-host"):
                for prefix, profile in (("freshness", self.profile), ("runtime", artifact("profile-runtime"))):
                    outcome(self, self.api.validate, DATA["observations"][f"{prefix}/{mode}/{label}"],
                            self.contract, profile, at=AT, mode=mode,
                            state=artifact(f"state-{label}"), max_state_age_seconds=60)

    def test_thermal_target_binding(self):
        for target in ("python-recorded-host-v1", "other-synthetic-host"):
            thermal = fixture("thermal")
            for group in ("providers", "readings"):
                for row in thermal["thermal_evidence"][group]:
                    row["evidence_target"]["host_id"] = target
            expected = DATA["observations"][f"thermal/{target}"]
            outcome(self, self.api.validate, expected, self.contract, artifact("profile-thermal"),
                    at=AT, mode="state_required", state=self.state, max_state_age_seconds=60,
                    thermal_evidence=[invoke(self.api.Artifact.from_dict, thermal)])

    def test_recorded_path_has_no_live_effects(self):
        # Every invoke is observed by the installed harness; no successful-effect-only trap.
        for _ in range(3):
            outcome(self, self.api.validate, {"value": fixture("report")}, self.contract, self.profile, at=AT)
            self.assertEqual(invoke(self.contract.to_dict), fixture("contract"))
