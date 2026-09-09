# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Request and exception assertions for the public recorded interface."""

import inspect
import json
from pathlib import Path

from error_cases import decode_error, pad, raises
from support import AT, DATA, api, artifact, asset, invoke, outcome


def validation_args():
    return artifact("contract"), artifact("profile")


def modes_and_roles(test):
    for value in (None, 0):
        raises(test, TypeError, "invalid argument type", api().validate, *validation_args(), at=AT, mode=value)
    for value in ("", "state_aware", "unknown"):
        raises(test, ValueError, "unsupported validation mode", api().validate, *validation_args(), at=AT, mode=value)
    raises(test, TypeError, "invalid argument type", api().validate, {}, artifact("profile"), at=AT)
    raises(test, ValueError, "incompatible artifact kind", api().validate, artifact("survey"), artifact("profile"), at=AT)
    outcome(test, api().validate, DATA["observations"]["freshness/state_required/other-host"],
            *validation_args(), at=AT, mode="state_required", state=artifact("state-other-host"), max_state_age_seconds=60)


def safe_errors(test):
    sentinel = "ADAPTER_INPUT_SENTINEL/hidden/synthetic/source"
    for function, value, kind in ((api().Artifact.from_dict, {sentinel: None}, api().CoreError),
                                   (api().Artifact.from_json, '{"' + sentinel, api().DecodeError)):
        with test.assertRaises(kind) as caught:
            invoke(function, value)
        error = caught.exception
        for text in (str(error), repr(error), repr(error.args), repr(vars(error))):
            test.assertNotIn(sentinel, text)
        test.assertIsNone(error.__cause__)
        test.assertIsNone(error.__context__)


def exception_fields(test):
    for kind in (api().CoreError, api().DecodeError, api().SerializationError, api().NativeError):
        test.assertTrue(issubclass(kind, api().FitctlError))
        test.assertTrue(issubclass(kind, Exception))
    for text, reason in (("{", "invalid_json"), ('{"k":0,"k":1}', "duplicate_json_key"),
                         ('{"k":NaN}', "non_finite_json_number"), ('{"k":"\\ud800"}', "invalid_json_unicode")):
        decode_error(test, text, reason)
    error = outcome(test, api().Artifact.from_dict, DATA["observations"]["loader/artifact/no_envelope"], {})
    test.assertEqual(set(vars(error)), {"error_model_id", "error_model_version", "reason_code", "checkpoint_id", "message"})
    for field in ("error_model_id", "reason_code", "checkpoint_id", "message"):
        test.assertIs(type(getattr(error, field)), str)
    test.assertIs(type(error.error_model_version), int)
    test.assertEqual(error.args, ("Artifact.from_dict: artifact_decode_invalid",))
    test.assertEqual(error.message, str(error))
    test.assertIsNone(error.__cause__)
    test.assertIsNone(error.__context__)
    for kind, message, function, args in (
        (TypeError, "invalid argument type", api().Artifact.from_dict, ([],)),
        (ValueError, "non-finite input number", api().Artifact.from_dict, ({"k": float("inf")},)),
        (OverflowError, "integer outside supported range", api().Artifact.from_dict, ({"k": 2 ** 64},)),
        (KeyError, "unknown builtin configuration", api().builtin_config, ("absent", "absent")),
    ):
        error = raises(test, kind, message, function, *args)
        test.assertEqual(vars(error), {})
        test.assertFalse(hasattr(error, "error_model_id"))


def max_age(test):
    arguments = validation_args()
    outcome(test, api().validate, {"value": DATA["fixtures"]["report"]}, *arguments, at=AT, max_state_age_seconds=None)
    for value in (0, 2 ** 64 - 1):
        outcome(test, api().validate, DATA["observations"][f"freshness/contract_only/max_age/{value}"],
                *arguments, at=AT, max_state_age_seconds=value)
    for value in (-1, 2 ** 64):
        raises(test, OverflowError, "integer outside supported range", api().validate,
               *arguments, at=AT, max_state_age_seconds=value)
    for value in (1.0, "0"):
        raises(test, TypeError, "invalid argument type", api().validate, *arguments, at=AT, max_state_age_seconds=value)


def builtin_budgets(test):
    for multibyte in (False, True):
        for category_size in (63, 64, 65):
            for id_size in (127, 128, 129):
                over = category_size > 64 or id_size > 128
                raises(test, ValueError if over else KeyError,
                       "argument budget exceeded" if over else "unknown builtin configuration",
                       api().builtin_config, pad(category_size, multibyte), pad(id_size, multibyte))


def signatures(test):
    value = artifact("survey")
    policy = invoke(api().Policy.from_dict, asset("policy"))
    functions = [
        (api().Artifact.from_dict, (DATA["fixtures"]["survey"],), {}, "data"),
        (api().Artifact.from_json, (json.dumps(DATA["fixtures"]["survey"]),), {}, "text"),
        (api().Policy.from_dict, (asset("policy"),), {}, "data"),
        (api().Policy.from_json, (json.dumps(asset("policy")),), {}, "text"),
        (value.to_dict, (), {}, None), (value.to_json, (), {}, None),
        (value.semantic_hash, (), {}, None), (value.semantic_bytes, (), {}, None),
        (policy.to_dict, (), {}, None), (policy.to_json, (), {}, None),
        (value.redact, ("local",), {"at": AT}, "profile"),
        (api().builtin_config, ("policy", "general_compute_default.v1.json"), {}, "category"),
        (api().derive_contract, (value, policy), {"at": AT}, "survey"),
        (api().validate, validation_args(), {"at": AT}, "contract"),
    ]
    for function, args, kwargs, duplicate in functions:
        invoke(function, *args, **kwargs)
        signature = inspect.signature(function)
        signature.bind(*args, **kwargs)
        raises(test, TypeError, "invalid arguments", function, *args, **kwargs, ADAPTER_INPUT_SENTINEL=None)
        raises(test, TypeError, "invalid arguments", function, *args, None, **kwargs)
        if args:
            raises(test, TypeError, "invalid arguments", function, *args[:-1], **kwargs)
        if "at" in kwargs:
            raises(test, TypeError, "invalid arguments", function, *args)
        if duplicate:
            raises(test, TypeError, "invalid arguments", function, *args, **kwargs, **{duplicate: args[0]})
    for cls in (api().Artifact, api().Policy):
        raises(test, TypeError, "invalid arguments", cls, None)
        raises(test, TypeError, "invalid arguments", cls, ADAPTER_INPUT_SENTINEL=None)


def unadvertised(test):
    for schema in ("fitctl.config-bundle.v2", "fitctl.decision-bundle.v2"):
        raw = {"envelope": {"schema_id": schema, "schema_version": 2}}
        for function, value in ((api().Artifact.from_dict, raw), (api().Artifact.from_json, json.dumps(raw))):
            raises(test, ValueError, "incompatible artifact kind", function, value)
        raw["padding"] = "a" * 16777216
        for function, value in ((api().Artifact.from_dict, raw), (api().Artifact.from_json, json.dumps(raw))):
            raises(test, ValueError, "argument budget exceeded", function, value)


def admission(test):
    from admission_vectors import Sentinel, bind, cases
    # Generated by the independent Rust caller in the bounded fixture-preparation phase.
    oracle = json.loads((Path(__file__).parent / "fixtures/recorded/admission-oracles.json").read_bytes())
    handles = {name: artifact(name) for name in ("survey", "contract", "profile", "thermal")}
    handles["thermal-copy"] = artifact("thermal")  # Distinct wrapper for the same validated input.
    handles["policy"] = invoke(api().Policy.from_dict, asset("policy"))
    observed, referenced = set(), set()
    Sentinel.calls = 0
    for case in cases():
        test.assertNotIn(case.name, observed)
        observed.add(case.name)
        if case.reference:
            referenced.add(case.name)
        function, args, kwargs = bind(case, api(), handles)
        with test.subTest(vector=case.name):
            if case.error is None:
                if case.operation == "builtin":
                    test.assertEqual(invoke(function, *args, **kwargs), oracle[case.name]["value"])
                else:
                    outcome(test, function, oracle[case.name], *args, **kwargs)
            else:
                raises(test, case.error[0], case.error[1], function, *args, **kwargs)
                if case.reference:
                    test.assertEqual(oracle[case.name], {"selection": False})
    from number_cases import reference_cases
    test.assertEqual(referenced | {case.name for case in reference_cases()}, set(oracle))
    test.assertEqual(Sentinel.calls, 0)
