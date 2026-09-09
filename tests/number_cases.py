# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Literal JSON vectors and independent-core assertions; never decode input tokens."""

import json
import copy
import math
from pathlib import Path
import struct

from error_cases import admitted_missing_envelope, decode_error, raises
from support import api, fixture, invoke

LITERALS = json.loads((Path(__file__).parent / "fixtures/adaptation/numbers.json").read_bytes())


def document(token):
    raw = fixture("state-scalars")
    raw["state"]["extension_state"]["example.adaptation"] = {"number": "NUMBER_TOKEN"}
    template = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    assert template.count('"NUMBER_TOKEN"') == 1
    return template.replace('"NUMBER_TOKEN"', token)


def reference_cases():
    from admission_vectors import Case
    for token, kind in LITERALS:
        if kind in ("int", "float"):
            yield Case("number/" + token, "numeric_json", {"text": document(token)})


def assert_number(test, exported, expected, kind, token):
    value = exported["state"]["extension_state"]["example.adaptation"]["number"]
    test.assertIs(type(value), float if kind == "float" else int)
    test.assertEqual(expected["number_kind"], kind)
    if kind == "float":
        test.assertEqual(struct.pack(">d", value).hex(), expected["number_bits"])
        test.assertEqual(math.copysign(1.0, value) < 0, expected["negative"])
        if token in ("-0", "-0.0", "-0e0", "-0E+00", "-0e-999"):
            test.assertEqual(value, 0.0)
            test.assertLess(math.copysign(1.0, value), 0)
    else:
        test.assertEqual(value, int(token))
        test.assertEqual(str(value), expected["number_decimal"])


def literal_parity(test):
    oracles = json.loads((Path(__file__).parent / "fixtures/recorded/admission-oracles.json").read_bytes())
    basis = bytes.fromhex(oracles["number/-0"]["value"]["semantic_bytes_hex"])
    json_basis = oracles["number/-0"]["value"]["json"]
    observed = set()
    for token, kind in LITERALS:
        text = document(token)
        with test.subTest(literal=token):
            if kind == "overflow":
                raises(test, OverflowError, "integer outside supported range", api().Artifact.from_json, text)
            elif kind in ("nonfinite", "syntax"):
                decode_error(test, text, "non_finite_json_number" if kind == "nonfinite" else "invalid_json")
            else:
                expected = oracles["number/" + token]["value"]
                expected_json = copy.deepcopy(json_basis)
                if token != "-0":
                    expected_json["state"]["extension_state"]["example.adaptation"]["number"] = expected["json_number"]
                value = invoke(api().Artifact.from_json, text)
                exported = invoke(value.to_dict)
                test.assertEqual(exported, expected_json)
                assert_number(test, exported, expected, kind, token)
                # Decoding OUTPUT is intentional; the literal INPUT goes directly to native.
                encoded = json.loads(invoke(value.to_json))
                test.assertEqual(encoded, expected_json)
                assert_number(test, encoded, expected, kind, token)
                encoded_bytes = expected["semantic_bytes_hex"]
                if isinstance(encoded_bytes, str):
                    semantic_bytes = bytes.fromhex(encoded_bytes)
                else:
                    test.assertEqual(set(encoded_bytes), {"prefix_bytes", "tail_hex"})
                    prefix = encoded_bytes["prefix_bytes"]
                    test.assertIs(type(prefix), int)
                    test.assertTrue(0 <= prefix <= len(basis))
                    semantic_bytes = basis[:prefix] + bytes.fromhex(encoded_bytes["tail_hex"])
                test.assertEqual(invoke(value.semantic_bytes), semantic_bytes)
                test.assertEqual(invoke(value.semantic_hash), expected["semantic_hash"])
                observed.add("number/" + token)
    test.assertEqual(observed, {case.name for case in reference_cases()})
    cap = 16_777_216
    for size in (cap - 1, cap, cap + 1):
        text = '{"n":[-0,-0,-0,-0,-0,-0,-0,-0],"p":"' + 'a' * (size - 66) + '"}'
        test.assertLessEqual(len(text), cap)
        if size > cap:
            raises(test, ValueError, "argument budget exceeded", api().Artifact.from_json, text)
        else:
            admitted_missing_envelope(test, api().Artifact.from_json, text)
