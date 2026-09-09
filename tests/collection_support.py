# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit collection fixtures and named harness observation scopes."""

import json
import os
from pathlib import Path
import threading

from collection_inputs import write_corpora
import support

ROOT = Path("/work/collection")
DATA = json.loads((Path(__file__).parent / "fixtures/collection/core-reference.json").read_bytes())
SCOPES = {"REPLAY", "CONFIG", "STATE", "SURVEY", "PATH", "PROVIDER", "OPTIONAL"}


def prepare():
    if not ROOT.exists():
        write_corpora(ROOT)
    return ROOT


def collect(scope, function, *args, **kwargs):
    if scope not in SCOPES:
        raise AssertionError("unknown collection observation scope")
    descriptor = support.TRACE_FD
    if descriptor is None:
        return function(*args, **kwargs)
    thread = threading.get_native_id()
    os.write(descriptor, f"FITCTL_{scope}_BEGIN {thread}\n".encode("ascii"))
    try:
        return function(*args, **kwargs)
    finally:
        os.write(descriptor, f"FITCTL_END {thread}\n".encode("ascii"))


def replay(name):
    kind = name.split("/")[0]
    return collect("REPLAY", getattr(support.api(), "replay_" + kind), str(prepare() / name), "sample")


def core_error(test, error, expected, operation):
    test.assertEqual(set(vars(error)), {*expected, "message"})
    for name, value in expected.items():
        test.assertIs(type(getattr(error, name)), type(value))
        test.assertEqual(getattr(error, name), value)
    message = operation + ": " + expected["reason_code"]
    test.assertEqual(error.args, (message,))
    test.assertEqual(error.message, message)
    test.assertIsNone(error.__cause__)
    test.assertIsNone(error.__context__)
