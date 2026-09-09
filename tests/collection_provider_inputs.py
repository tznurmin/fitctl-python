# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Real caller configuration files, prepared before observed core calls."""

import copy
import json
from pathlib import Path

ROOT = Path("/work/collection-configs")
TOOLS = Path("/work/collection-tools")


def provider(mode="good", *, name="fixture"):
    command = ["/env/bin/python", "-I", "-B", "/tests/collection_provider.py", mode]
    if mode in ("missing", "denied"):
        command = [str(TOOLS / mode)]
    return {"provider_id": name, "provider_kind": "lm_sensors_json", "command": command,
            "timeout_seconds": 1 if mode == "sleep2" else 5,
            "evidence_target": {"target_kind": "current_host", "collection_path": "local_process"}}


def write_config(providers, name="selected"):
    ROOT.mkdir(exist_ok=True)
    TOOLS.mkdir(exist_ok=True)
    denied = TOOLS / "denied"
    denied.write_text("not executable\n")
    denied.chmod(0o600)
    path = ROOT / (name + ".json")
    path.write_text(json.dumps({"schema_id": "fitctl.thermal-provider-config.v1",
                                "schema_version": 1, "providers": providers}))
    return str(path)


def invalid_configs():
    initial = {"schema_id": "fitctl.thermal-provider-config.v1", "schema_version": 1,
               "providers": [provider()]}
    rows = {}
    for name in ("unknown", "schema", "version", "empty", "duplicate", "argv", "shell",
                 "timeout0", "timeout61", "target", "mapping"):
        value = copy.deepcopy(initial)
        entry = value["providers"][0]
        if name == "unknown":
            value["unknown"] = True
        elif name == "schema":
            value["schema_id"] = "unsupported"
        elif name == "version":
            value["schema_version"] = 99
        elif name == "empty":
            value["providers"] = []
        elif name == "duplicate":
            value["providers"].append(copy.deepcopy(entry))
        elif name == "argv":
            entry["command"] = []
        elif name == "shell":
            entry["command"] = ["sh", "-c", "exit 0"]
        elif name.startswith("timeout"):
            entry["timeout_seconds"] = int(name.removeprefix("timeout"))
        elif name == "target":
            entry["evidence_target"] = {"target_kind": "host_id", "collection_path": "local_process"}
        elif name == "mapping":
            entry["sensor_mappings"] = [{"raw_label": "Core 0", "sensor_role": "cpu"}] * 2
        path = ROOT / (name + ".json")
        path.write_text(json.dumps(value))
        rows[name] = (str(path), "load" if name == "unknown" else "validate")
    malformed, denied = ROOT / "malformed.json", ROOT / "denied.json"
    malformed.write_text("{invalid\n")
    denied.write_text("{}")
    denied.chmod(0)
    rows.update(missing=(str(ROOT / "missing.json"), "load"),
                malformed=(str(malformed), "load"), denied=(str(denied), "load"))
    return rows
