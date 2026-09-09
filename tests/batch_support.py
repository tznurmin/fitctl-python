# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Concrete batch requests and independent observed core outcomes."""

import json
from pathlib import Path

from batch_inputs import requests
from support import api, invoke, outcome

DATA = json.loads((Path(__file__).parent / "fixtures/batch/core-reference.json").read_bytes())


def arguments(raw):
    return {name: [invoke(api().Artifact.from_dict, item) for item in raw[name]]
            for name in ("contracts", "profiles", "states")} | {
                name: raw[name] for name in ("at", "mode", "max_state_age_seconds")}


def compare(test, name):
    expected = DATA["observations"][name]
    return outcome(test, api().classify_batch, expected, **arguments(requests()[name]))


def report(name="matrix"):
    return invoke(api().BatchReport.from_dict, DATA["observations"][name]["value"])


def property_value(value, name):
    return invoke(getattr, value, name)
