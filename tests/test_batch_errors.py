# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Batch adaptation failures preserve typed core errors and safe admission."""

import copy
import json
import unittest

import batch_conversion_cases
from batch_inputs import requests
from batch_support import DATA, arguments, compare, report
from error_cases import Sentinel, pad, raises
from support import AT, api, artifact, asset, invoke, outcome


class BatchErrorTests(unittest.TestCase):
    def test_empty_inputs(self):
        for name in ("empty_contracts", "empty_profiles"):
            compare(self, name)

    def test_duplicate_inputs(self):
        for name, key in (("duplicate_contracts", "contracts"), ("duplicate_profiles", "profiles")):
            compare(self, name)
            supplied = arguments(requests()[name])
            supplied[key][1] = supplied[key][0]
            outcome(self, api().classify_batch, DATA["observations"][name], **supplied)

    def test_duplicate_state_identity(self):
        for name in ("duplicate_alias", "duplicate_identity"):
            compare(self, name)

    def test_unmatched_and_mismatched_state(self):
        for name in ("unmatched_state", "identity_mismatch"):
            compare(self, name)

    def test_validated_report_loader(self):
        for name, control in DATA["loaders"].items():
            for factory, value in ((api().BatchReport.from_dict, copy.deepcopy(control["input"])),
                                    (api().BatchReport.from_json, json.dumps(control["input"]))):
                with self.subTest(name=name):
                    outcome(self, factory, control["outcome"], value)

    def test_exact_types_and_roles(self):
        class Items(list):
            __iter__ = __len__ = Sentinel.forbidden
        class Text(str):
            __str__ = Sentinel.forbidden
        class Number(int):
            __int__ = Sentinel.forbidden
        supplied = arguments(requests()["minimal"])
        Sentinel.calls = 0
        for key in ("contracts", "profiles", "states"):
            bad_values = [(), iter(()), Items(), Sentinel(), {}]
            if key != "states":
                bad_values.append(None)
            for value in bad_values:
                raises(self, TypeError, "invalid argument type", api().classify_batch, **(supplied | {key: value}))
            for item in ({}, invoke(api().Policy.from_dict, asset("policy")), Sentinel()):
                raises(self, TypeError, "invalid argument type", api().classify_batch, **(supplied | {key: [item]}))
            wrong = artifact("survey")
            raises(self, ValueError, "incompatible artifact kind", api().classify_batch, **(supplied | {key: [wrong]}))
        for key, value in (("at", Text(AT)), ("mode", Text("contract_only")),
                           ("max_state_age_seconds", Number(0)), ("at", Sentinel()), ("mode", None)):
            raises(self, TypeError, "invalid argument type", api().classify_batch, **(supplied | {key: value}))
        self.assertEqual(Sentinel.calls, 0)
        for states in (None, []):
            value = invoke(api().classify_batch, **(supplied | {"states": states}))
            self.assertEqual(invoke(value.to_dict), DATA["observations"]["minimal"]["value"])

    def test_control_boundaries(self):
        for name in DATA["observations"]:
            if name.startswith("at_"):
                compare(self, name)
        supplied = arguments(requests()["minimal"])
        for multibyte in (False, True):
            raises(self, ValueError, "argument budget exceeded", api().classify_batch, **(supplied | {"at": pad(65, multibyte)}))
            for length in (31, 32, 33):
                text = pad(length, multibyte)
                message = "argument budget exceeded" if length == 33 else "unsupported validation mode"
                raises(self, ValueError, message, api().classify_batch, **(supplied | {"mode": text}))
                message = "argument budget exceeded" if length == 33 else "unsupported batch export view"
                raises(self, ValueError, message, report().export_csv, text)
        for value in (-1, 2**64):
            raises(self, OverflowError, "integer outside supported range", api().classify_batch,
                   **(supplied | {"max_state_age_seconds": value}))
        raises(self, TypeError, "invalid argument type", api().classify_batch, **(supplied | {"max_state_age_seconds": True}))
        raises(self, TypeError, "invalid argument type", report().export_csv, None)
        raises(self, ValueError, "unsupported batch export view", report().export_csv, "")

    def test_collection_boundaries(self):
        for name in DATA["observations"]:
            if name.startswith(("contracts_", "profiles_", "states_", "pairs_")):
                compare(self, name)
        supplied = arguments(requests()["minimal"])
        for key, role in (("contracts", "contract"), ("profiles", "profile"), ("states", "state")):
            value = [artifact(role)] * 17
            raises(self, ValueError, "argument budget exceeded", api().classify_batch, **(supplied | {key: value}))
            self.assertEqual(len(value), 17)
        raises(self, ValueError, "argument budget exceeded", api().classify_batch,
               [artifact("contract")] * 5, [artifact("profile")] * 13, at=AT)

    def test_loader_conversion_contract(self):
        batch_conversion_cases.exercise(self)

    def test_safe_failure_fields_and_signatures(self):
        fn, cls = api().classify_batch, api().BatchReport
        contract, profile = artifact("contract"), artifact("profile")
        for args, kwargs in (((), {}), (([contract], [profile]), {}),
                (([contract], [profile], AT), {}), (([contract], [profile]), {"at": AT, "contracts": []}),
                (([contract], [profile]), {"at": AT, "SECRET_KEY": None})):
            raises(self, TypeError, "invalid arguments", fn, *args, **kwargs)
        raises(self, TypeError, "native value requires a loader", cls)
        raises(self, TypeError, "invalid arguments", cls, SECRET_KEY=True)
        for method in (report().to_dict, report().to_json):
            raises(self, TypeError, "invalid arguments", method, SECRET_KEY=True)
        for method in (cls.from_dict, cls.from_json, report().export_csv):
            raises(self, TypeError, "invalid arguments", method)
            raises(self, TypeError, "invalid arguments", method, SECRET_KEY=True)
        raw = requests()["duplicate_contracts"]
        for value in raw["contracts"]:
            value["envelope"]["artifact_id"] = "SECRET_INPUT"
        error = outcome(self, fn, DATA["observations"]["duplicate_contracts"], **arguments(raw))
        message = "classify_batch: batch_input_invalid"
        self.assertEqual(error.args, (message,))
        self.assertEqual(error.message, message)
        self.assertEqual(set(vars(error)), {"message", "error_model_id", "error_model_version", "reason_code", "checkpoint_id"})
        self.assertIs(type(error.error_model_version), int)
        for name in ("message", "error_model_id", "reason_code", "checkpoint_id"):
            self.assertIs(type(getattr(error, name)), str)
        self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)
        self.assertNotIn("SECRET", repr(error))
