# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Public synthetic fixtures and optional harness-owned call observation."""

import copy
import importlib
import json
import os
from pathlib import Path
import threading

DATA = json.loads((Path(__file__).parent / "fixtures/recorded/core-reference.json").read_bytes())
AT = "2026-01-01T00:00:00Z"
FAMILIES = ("survey", "contract", "profile", "state", "thermal", "report")
PROFILES = ("local", "fleet", "auditor", "external")
ASSETS = {"policy": "general_compute_default.v1.json",
          "service_profiles": "general_compute_contract_only.v2.json",
          "extensions": "fitctl_runtime_python.v1.json",
          "invocation_contexts": "core_default.v1.json"}
TRACE_FD = None


def api():
    return importlib.import_module("fitctl")


def invoke(function, *args, **kwargs):
    """Markers are test harness effects, outside the native call they delimit."""
    descriptor = TRACE_FD
    if descriptor is None:
        return function(*args, **kwargs)
    thread = threading.get_native_id()
    os.write(descriptor, f"FITCTL_BEGIN {thread}\n".encode("ascii"))
    try:
        return function(*args, **kwargs)
    finally:
        os.write(descriptor, f"FITCTL_END {thread}\n".encode("ascii"))


def fixture(name):
    return copy.deepcopy(DATA["fixtures"][name])


def asset(category):
    return copy.deepcopy(DATA["observations"][f"builtin/{category}/{ASSETS[category]}"]["value"])


def artifact(name):
    return invoke(api().Artifact.from_dict, fixture(name))


def outcome(test, function, expected, *args, **kwargs):
    if "error" in expected:
        with test.assertRaises(api().CoreError) as caught:
            invoke(function, *args, **kwargs)
        for name, value in expected["error"].items():
            test.assertEqual(getattr(caught.exception, name), value)
        return caught.exception
    result = invoke(function, *args, **kwargs)
    test.assertEqual(invoke(result.to_dict), expected["value"])
    return result
