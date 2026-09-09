# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""The shared conversion contract exercised through the batch report loaders."""

import json

from error_cases import pad, raises
from support import api, invoke


def admitted(test, function, value):
    with test.assertRaises(api().CoreError) as caught:
        invoke(function, value)
    test.assertEqual(caught.exception.error_model_id, "fitctl.batch_classification.v2")
    test.assertEqual(caught.exception.error_model_version, 2)
    test.assertEqual(caught.exception.reason_code, "batch_input_invalid")
    test.assertEqual(caught.exception.checkpoint_id, "batch_input_load")


def exercise(test):
    cls = api().BatchReport
    for bad in (None, 0, [], False):
        raises(test, TypeError, "invalid argument type", cls.from_dict, bad)
        raises(test, TypeError, "invalid argument type", cls.from_json, bad)
    for text, reason in (("{", "invalid_json"), ('{"k":0,"k":1}', "duplicate_json_key"),
                          ('{"k":NaN}', "non_finite_json_number"),
                          ('{"k":"\\ud800"}', "invalid_json_unicode")):
        error = raises(test, api().DecodeError, "JSON decode failed: " + reason, cls.from_json, text)
        test.assertEqual((error.error_model_id, error.error_model_version, error.reason_code, error.checkpoint_id),
                         ("fitctl.python.decode.v1", 1, reason, "json_decode"))
    cyclic = {}; cyclic["k"] = cyclic
    raises(test, ValueError, "cyclic input", cls.from_dict, cyclic)
    raises(test, ValueError, "invalid Unicode scalar", cls.from_dict, {"k": "\ud800"})
    raises(test, ValueError, "non-finite input number", cls.from_dict, {"k": float("inf")})
    for number in (-(2**63)-1, 2**64):
        raises(test, OverflowError, "integer outside supported range", cls.from_dict, {"k": number})
    for delta in (-1, 0, 1):
        bound = 16777216 + delta
        for function, value in ((cls.from_json, '{"k":"' + pad(bound - 8, True) + '"}'),
                                (cls.from_dict, {"k": pad(bound - 1, True)})):
            if delta <= 0:
                admitted(test, function, value)
            else:
                raises(test, ValueError, "argument budget exceeded", function, value)
    for depth in (62, 63, 64):
        value = None
        for _ in range(depth):
            value = [value]
        raw = {"k": value}
        for function, value in ((cls.from_dict, raw), (cls.from_json, json.dumps(raw))):
            if depth <= 63:
                admitted(test, function, value)
            else:
                raises(test, ValueError, "argument budget exceeded", function, value)
    for count in (99996, 99997, 99998):
        raw = {"k": [None] * count}
        for function, value in ((cls.from_dict, raw), (cls.from_json, json.dumps(raw))):
            if count <= 99997:
                admitted(test, function, value)
            else:
                raises(test, ValueError, "argument budget exceeded", function, value)
