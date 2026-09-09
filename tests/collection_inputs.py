# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Selected synthetic corpus inputs; core observations are recorded separately."""

import copy
import hashlib
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import AT, DATA


def snapshots():
    survey = DATA["fixtures"]["survey"]["survey"]
    evidence = survey["core_evidence"]
    state = DATA["fixtures"]["state"]["state"]["core_state"]
    return {
        "survey": {"schema_id": "fitctl.fixture.host_survey.snapshot.v1", "schema_version": 1,
                   "fixture_id": "sample", "collected_at": AT, "host_alias": "collection-host",
                   "execution_context": copy.deepcopy(evidence["execution_context"]),
                   "collectors": [row["collector_id"] for row in evidence["collectors"]],
                   "observations": copy.deepcopy(evidence["observations"])},
        "state": {"schema_id": "fitctl.fixture.host_state.snapshot.v1", "schema_version": 1,
                  "fixture_id": "sample", "collected_at": AT, "host_alias": "collection-host",
                  "collectors": [row["collector_id"] for row in state["collectors"]],
                  **{key: copy.deepcopy(state[key]) for key in
                     ("freshness", "resources", "path_resources", "boundaries", "topology", "operability")}},
    }


def document(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def corpus(kind, snapshot):
    entry = {"fixture_id": "sample", "path": "snapshot.json"}
    if kind == "survey":
        entry["execution_context"] = snapshot["execution_context"]["visibility_scope"]
    manifest = {"schema_id": f"fitctl.fixture.host_{kind}.corpus.v1", "schema_version": 1,
                "corpus_id": "collection-synthetic-v1", "fixtures": [entry]}
    return manifest, copy.deepcopy(snapshot)


def corpora():
    """One authoritative selected byte definition, including malformed files."""
    result = {}
    for kind, original in snapshots().items():
        variants = ("complete", "unknown", "missing_manifest", "malformed_manifest",
                    "schema_manifest", "empty_manifest", "duplicate_id", "absolute_path",
                    "escape_path", "missing_snapshot", "malformed_snapshot", "schema_snapshot",
                    "version_snapshot", "mismatched_id", "empty_collectors", "blank_alias")
        variants += ("restricted", "mismatched_scope", "machine_identity") if kind == "survey" else (
            "stale", "zero", "machine_identity")
        for variant in variants:
            manifest, snapshot = corpus(kind, original)
            entry = manifest["fixtures"][0]
            if variant == "schema_manifest":
                manifest["schema_id"] = "unsupported"
            elif variant == "empty_manifest":
                manifest["fixtures"] = []
            elif variant == "duplicate_id":
                manifest["fixtures"].append(copy.deepcopy(entry))
            elif variant == "absolute_path":
                entry["path"] = "/outside.json"
            elif variant == "escape_path":
                entry["path"] = "../outside.json"
            elif variant == "schema_snapshot":
                snapshot["schema_id"] = "unsupported"
            elif variant == "version_snapshot":
                snapshot["schema_version"] = 99
            elif variant == "mismatched_id":
                snapshot["fixture_id"] = "different"
            elif variant == "empty_collectors":
                snapshot["collectors"] = []
            elif variant == "blank_alias":
                snapshot["host_alias"] = " "
            elif variant == "machine_identity":
                snapshot["local_stable_identity_inputs_v2"] = {"etc_machine_id": "a" * 32}
            elif variant in {"restricted", "mismatched_scope"}:
                snapshot["execution_context"].update(visibility_scope="container_restricted",
                                                     privilege_level="limited", container_runtime="fixture")
                if variant == "restricted":
                    entry["execution_context"] = "container_restricted"
            elif variant == "stale":
                snapshot["freshness"]["freshness_state"] = "stale"
            elif variant == "zero":
                snapshot["resources"]["memory_used_excluding_cache_bytes"] = {"state": "observed", "value": 0}
            elif variant == "unknown":
                target = snapshot["observations"] if kind == "survey" else snapshot["resources"]
                field = "cpu" if kind == "survey" else "allocatable_cpu_logical_cores"
                target[field] = {"state": "unknown", "value": None}
            files = {"manifest.v1.json": document(manifest), "snapshot.json": document(snapshot)}
            for target in ("manifest", "snapshot"):
                name = "manifest.v1.json" if target == "manifest" else "snapshot.json"
                if variant == "missing_" + target:
                    files.pop(name)
                elif variant == "malformed_" + target:
                    files[name] = "{invalid\n"
            result[f"{kind}/{variant}"] = {"kind": kind, "fixture_id": "sample", "files": files}
    return result


def write_corpora(root):
    """Harness setup only, before collection; caller supplies its owned directory."""
    root = Path(root)
    root.mkdir()
    selected = corpora()
    for name, value in selected.items():
        directory = root / name
        directory.mkdir(parents=True)
        for relative, text in value["files"].items():
            (directory / relative).write_text(text, encoding="utf-8")
    for kind in ("survey", "state"):
        (root / kind / "outside.json").write_text('{"outside":"not a snapshot"}\n', encoding="utf-8")
    return selected


if __name__ == "__main__":
    assert len(sys.argv) == 3
    selected = write_corpora(Path(sys.argv[2]))
    data = document(selected).encode("utf-8")
    assert len(data) <= 2 * 1024**2
    with Path(sys.argv[1]).open("xb") as stream:
        stream.write(data)
    print(json.dumps({"input_bytes": len(data), "input_sha256": hashlib.sha256(data).hexdigest(),
                      "cases": sorted(selected)}))
