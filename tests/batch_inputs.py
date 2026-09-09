# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Synthetic finite requests, shared by the independent core client and tests."""

import copy
import hashlib
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import AT, fixture


def identified(name, identity):
    value = fixture(name)
    value["envelope"]["artifact_id"] = identity
    return value


def request(contracts=None, profiles=None, states=None, *, mode="contract_only", at=AT, age=None):
    return {"contracts": [fixture("contract")] if contracts is None else contracts,
            "profiles": [fixture("profile")] if profiles is None else profiles,
            "states": [] if states is None else states, "mode": mode, "at": at,
            "max_state_age_seconds": age}


def grid(contracts, profiles):
    return request([identified("contract", f"batch-contract-{i:02}") for i in range(contracts)],
                   [identified("profile", f"batch-profile-{i:02}") for i in range(profiles)])


def requests():
    matrix = request([identified("contract", name) for name in ("batch-contract-b", "batch-contract-a")],
                     [identified(name, identity) for name, identity in (
                         ("profile-unfit", "batch-profile-z"), ("profile", "batch-profile-a"),
                         ("profile-degraded", "batch-profile-m"))])
    reversed_matrix = copy.deepcopy(matrix)
    reversed_matrix["contracts"].reverse(); reversed_matrix["profiles"].reverse()
    quoted = copy.deepcopy(matrix)
    quoted["contracts"][0]["display_name"] = 'Compute, "alpha"\nλ'
    quoted["profiles"][0]["profile"]["display_name"] = 'Workload, "beta"\r\nλ'
    values = {"minimal": request(), "matrix": matrix, "reversed": reversed_matrix, "quoted": quoted,
              "empty_contracts": request(contracts=[]), "empty_profiles": request(profiles=[]),
              "duplicate_contracts": request(contracts=[fixture("contract"), fixture("contract")]),
              "duplicate_profiles": request(profiles=[fixture("profile"), fixture("profile")]),
              "contract_only_state": request(states=[fixture("state")]),
              "contract_only_age": request(age=0), "age_without_state": request(mode="state_advisory", age=0)}
    duplicate = identified("state", "batch-state-duplicate")
    values["duplicate_alias"] = request(states=[fixture("state"), duplicate], mode="state_advisory")
    duplicate = copy.deepcopy(duplicate); duplicate["state"]["host_alias"] = "batch-other-alias"
    values["duplicate_identity"] = request(states=[fixture("state"), duplicate], mode="state_advisory")
    mismatch = fixture("state"); mismatch["state"]["local_identity"]["local_stable_id"] = "a" * 64
    values["identity_mismatch"] = request(states=[mismatch], mode="state_advisory")
    values["unmatched_state"] = request(states=[fixture("state-other-host")], mode="state_advisory")
    fallback = fixture("state"); fallback["state"].pop("local_identity")
    values["alias_fallback"] = request(states=[fallback], mode="state_advisory", age=60)
    renamed = fixture("state"); renamed["state"]["host_alias"] = "batch-renamed-host"
    values["identity_priority"] = request(states=[renamed], mode="state_advisory", age=60)
    for mode in ("state_advisory", "state_required"):
        values[mode + "_missing"] = request(mode=mode)
        values["runtime_" + mode + "_missing"] = request(profiles=[fixture("profile-runtime")], mode=mode)
        for name in ("state", "state-stale", "state-future", "state-unknown-cpu"):
            values[mode + "_" + name] = request(states=[fixture(name)], mode=mode, age=60)
            values["runtime_" + mode + "_" + name] = request(
                profiles=[fixture("profile-runtime")], states=[fixture(name)], mode=mode, age=60)
    values["runtime_contract_only"] = request(profiles=[fixture("profile-runtime")])
    for seconds in (59, 60, 61):
        at = f"2026-01-01T00:00:{seconds:02}Z" if seconds < 60 else f"2026-01-01T00:01:{seconds - 60:02}Z"
        values[f"age_{seconds}"] = request(profiles=[fixture("profile-runtime")],
                                          states=[fixture("state")], mode="state_required", at=at, age=60)
    for age in (0, 2**64 - 1):
        values[f"max_age_{age}"] = request(profiles=[fixture("profile-runtime")],
                                          states=[fixture("state")], mode="state_advisory", age=age)
    for label, at in (("empty", ""), ("invalid", "invalid"), ("negative", "unix:-1"),
                      ("unix", "unix:1767225600"), ("63", "a" * 63), ("64", "a" * 64),
                      ("utf8_63", "é" * 31 + "a"), ("utf8_64", "é" * 32)):
        values["at_" + label] = request(at=at)
    for n in (15, 16):
        values[f"contracts_{n}"] = grid(n, 1)
        values[f"profiles_{n}"] = grid(1, n)
    values["pairs_63"] = grid(7, 9)
    values["pairs_64"] = grid(8, 8)
    # Distinct states with matching contracts exercise state-count admission;
    # remove optional local identity so core uses explicit alias fallback.
    for n in (15, 16):
        contracts, states = [], []
        for i in range(n):
            contract = identified("contract", f"batch-contract-{i:02}")
            state = identified("state", f"batch-state-{i:02}")
            alias = f"batch-host-{i:02}"
            contract["host_alias"] = alias
            state["state"]["host_alias"] = alias
            state["state"].pop("local_identity")
            contracts.append(contract); states.append(state)
        values[f"states_{n}"] = request(contracts=contracts, states=states, mode="state_advisory", age=60)
    return values


def encoded():
    return (json.dumps(requests(), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


if __name__ == "__main__":
    assert len(sys.argv) == 2
    data = encoded()
    assert len(data) <= 2 * 1024**2
    with Path(sys.argv[1]).open("xb") as stream:
        stream.write(data)
    print(json.dumps({"input_bytes": len(data), "input_sha256": hashlib.sha256(data).hexdigest(),
                      "cases": sorted(requests())}))
