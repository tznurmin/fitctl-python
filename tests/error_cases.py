# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Concrete conversion vectors, independent of adapter implementation details."""

import collections.abc
import json
import math

from support import AT, DATA, FAMILIES, api, artifact, asset, fixture, invoke, outcome


def raises(test, kind, message, function, *args, **kwargs):
    with test.assertRaises(kind) as caught:
        invoke(function, *args, **kwargs)
    test.assertEqual(caught.exception.args, (message,))
    return caught.exception


def loader(family):
    return api().Policy.from_dict if family == "policy" else api().Artifact.from_dict


def omission(test):
    for family in ("policy", "profile"):
        raw = asset("policy" if family == "policy" else "service_profiles")
        target = raw if family == "policy" else raw["profile"]
        del target["display_name"]
        value = invoke(loader(family), raw)
        test.assertNotIn("display_name", invoke(value.to_dict) if family == "policy" else invoke(value.to_dict)["profile"])
        del target["policy_id" if family == "policy" else "profile_id"]
        outcome(test, loader(family), DATA["observations"][f"loader/{family}/missing_required"], raw)


def supplied_null(test):
    for family in ("policy", "profile"):
        raw = asset("policy" if family == "policy" else "service_profiles")
        target = raw if family == "policy" else raw["profile"]
        target["display_name"] = None
        outcome(test, loader(family), DATA["observations"][f"loader/{family}/null"], raw)


def unknown_fields(test):
    for family in FAMILIES:
        for label, nested in (("root_unknown", False), ("provenance_unknown", True)):
            raw = fixture(family)
            (raw["envelope"]["provenance"] if nested else raw)["unexpected"] = "sentinel"
            outcome(test, api().Artifact.from_dict, DATA["observations"][f"artifact/{family}/{label}"], raw)
    for family, category in (("policy", "policy"), ("profile", "service_profiles"),
                             ("pack", "extensions"), ("context", "invocation_contexts")):
        for nested in (False, True):
            raw = asset(category)
            if not nested:
                raw["unknown"] = True
            elif family == "policy":
                raw["layers"][0]["rules"]["unknown"] = True
            elif family == "profile":
                raw["profile"]["core_requirements"]["unknown"] = True
            elif family == "pack":
                raw["emitted_sections"][0]["unknown"] = True
            else:
                raw["enabled_extension_namespaces"] = [{"unknown": True}]
            expected = DATA["observations"][f"loader/{family}/{'nested_unknown' if nested else 'unknown'}"]
            if family in ("policy", "profile"):
                outcome(test, loader(family), expected, raw)
            else:
                kwargs = {"extension_packs": [raw]} if family == "pack" else {"invocation_context": raw}
                outcome(test, api().derive_contract, expected, artifact("survey"),
                        invoke(api().Policy.from_dict, asset("policy")), at=AT, **kwargs)


def schemas(test):
    for family in FAMILIES:
        for field, value, label in (("schema_id", "unsupported.synthetic.v1", "wrong_schema"),
                                    ("schema_version", 999, "bad_version")):
            raw = fixture(family)
            raw["envelope"][field] = value
            outcome(test, api().Artifact.from_dict, DATA["observations"][f"artifact/{family}/{label}"], raw)


def wrong_types(test):
    for cls in (api().Artifact, api().Policy):
        for bad in (0, None, [], False):
            raises(test, TypeError, "invalid argument type", cls.from_dict, bad)
            raises(test, TypeError, "invalid argument type", cls.from_json, bad)
        for bad in ('null', '0', '[]', '"text"'):
            raises(test, TypeError, "invalid argument type", cls.from_json, bad)


def bool_age(test):
    for value in (True, False):
        raises(test, TypeError, "invalid argument type", api().validate,
               artifact("contract"), artifact("profile"), at=AT, max_state_age_seconds=value)


def integers(test):
    for number in (-(2 ** 63), 2 ** 64 - 1):
        raw = fixture("state-scalars")
        raw["state"]["extension_state"]["example.adaptation"]["number"] = number
        for function, data in ((api().Artifact.from_dict, raw), (api().Artifact.from_json, json.dumps(raw))):
            result = invoke(function, data)
            actual = invoke(result.to_dict)["state"]["extension_state"]["example.adaptation"]["number"]
            test.assertEqual(actual, number)
            test.assertIs(type(actual), int)
    for number in (-(2 ** 63) - 1, 2 ** 64):
        for function, data in ((api().Artifact.from_dict, {"k": number}),
                               (api().Artifact.from_json, '{"k":' + str(number) + '}')):
            raises(test, OverflowError, "integer outside supported range", function, data)


def decode_error(test, text, reason):
    error = raises(test, api().DecodeError, "JSON decode failed: " + reason, api().Artifact.from_json, text)
    test.assertEqual(error.error_model_id, "fitctl.python.decode.v1")
    test.assertEqual(error.error_model_version, 1)
    test.assertEqual(error.reason_code, reason)
    test.assertEqual(error.checkpoint_id, "json_decode")


def nonfinite(test):
    for value in (math.nan, math.inf, -math.inf):
        raises(test, ValueError, "non-finite input number", api().Artifact.from_dict, {"k": value})
    for value in ("NaN", "Infinity", "-Infinity", "1e400"):
        decode_error(test, '{"k":' + value + '}', "non_finite_json_number")


def malformed(test):
    for text in ("", "{", "{}{}", "\ufeff{}", '{"k":"\x01"}'):
        decode_error(test, text, "invalid_json")
    for text in ('{"k":0,"k":1}', '{"outer":{"k":0,"k":1}}', '{"k":0,"\\u006b":1}'):
        decode_error(test, text, "duplicate_json_key")


class Sentinel:
    calls = 0

    def forbidden(self, *args):
        Sentinel.calls += 1
        raise AssertionError("coercion callback called")

    __str__ = __repr__ = __iter__ = __int__ = forbidden


def custom_types(test):
    Sentinel.calls = 0
    subclasses = [type("Subclass", (base,), {}) for base in (int, str, list, dict)]
    class Mapping(collections.abc.Mapping):
        __getitem__ = __iter__ = __len__ = Sentinel.forbidden
    class Sequence(collections.abc.Sequence):
        __getitem__ = __len__ = Sentinel.forbidden
    for value in (Sentinel(), Mapping(), Sequence(), (), *[cls() for cls in subclasses]):
        raises(test, TypeError, "invalid argument type", api().Artifact.from_dict, {"k": value})
    for key in (0, Sentinel(), subclasses[1]("key")):
        raises(test, TypeError, "invalid argument type", api().Artifact.from_dict, {key: None})
    test.assertEqual(Sentinel.calls, 0)


def admitted_missing_envelope(test, function, value):
    outcome(test, function, DATA["observations"]["loader/artifact/no_envelope"], value)


def pad(size, multibyte=False):
    return "é" * (size // 2) + "a" * (size % 2) if multibyte else "a" * size


def byte_budgets(test):
    bound = 16777216
    for multibyte in (False, True):
        for delta in (-1, 0, 1):
            text = '{"k":"' + pad(bound + delta - 8, multibyte) + '"}'
            raw = {"k": pad(bound + delta - 1, multibyte)}
            for function, value in ((api().Artifact.from_json, text), (api().Artifact.from_dict, raw)):
                if delta <= 0:
                    admitted_missing_envelope(test, function, value)
                else:
                    raises(test, ValueError, "argument budget exceeded", function, value)


def depth_nodes(test):
    for depth in (62, 63, 64):
        value = None
        for _ in range(depth):
            value = [value]
        raw = {"k": value}
        for function, value in ((api().Artifact.from_dict, raw), (api().Artifact.from_json, json.dumps(raw))):
            if depth <= 63:
                admitted_missing_envelope(test, function, value)
            else:
                raises(test, ValueError, "argument budget exceeded", function, value)
    for count in (99996, 99997, 99998):
        raw = {"k": [None] * count}
        for function, value in ((api().Artifact.from_dict, raw), (api().Artifact.from_json, json.dumps(raw))):
            if count <= 99997:
                admitted_missing_envelope(test, function, value)
            else:
                raises(test, ValueError, "argument budget exceeded", function, value)


def cycles(test):
    one = []; one.append(one)
    first = {}; second = [first]; first["k"] = second
    for value in (one, first):
        raises(test, ValueError, "cyclic input", api().Artifact.from_dict, {"k": value})


def unicode_scalars(test):
    for text in ("\ud800", "\udc00"):
        for raw in ({"k": text}, {text: None}):
            raises(test, ValueError, "invalid Unicode scalar", api().Artifact.from_dict, raw)
    for text in ('{"k":"\\ud800"}', '{"k":"\\udc00"}'):
        decode_error(test, text, "invalid_json_unicode")
    for text in ('{"k":"\\ud83d\\ude00"}', '{"é":0,"e\\u0301":1}'):
        admitted_missing_envelope(test, api().Artifact.from_json, text)


def aliases(test):
    shared = [None]
    admitted_missing_envelope(test, api().Artifact.from_dict, {"a": shared, "b": shared})
    raw = {"k": [shared] * 49998 + [None]}
    admitted_missing_envelope(test, api().Artifact.from_dict, raw)
    raw["k"].append(None)
    raises(test, ValueError, "argument budget exceeded", api().Artifact.from_dict, raw)
