# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute native tests in isolated children and the independent core example."""

import ast
import hashlib
import json
from pathlib import Path
import re

from .distribution_contract import require


def selectors(package):
    found = []
    for path in sorted((package / "tests").glob("test_*.py")):
        for cls in ast.parse(path.read_bytes()).body:
            if isinstance(cls, ast.ClassDef):
                found.extend(path.stem + "." + cls.name + "." + method.name for method in cls.body
                             if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"))
    require(len(found) == 82 and len(set(found)) == 82)
    return sorted(found)


def native(package, runner, phase):
    rust = package / "rust"
    runner.run(["cargo", "clippy", "--release", "--offline", "--locked", "--all-targets",
                "--no-default-features", "--", "-D", "warnings"], cwd=rust, phase=phase)
    text = runner.run(["cargo", "test", "--release", "--offline", "--locked", "--no-default-features",
                       "--lib", "--no-run", "--message-format=json"], cwd=rust, phase=phase, limit=1024**2)
    messages = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    binaries = [Path(row["executable"]) for row in messages if row.get("reason") == "compiler-artifact"
                and row.get("profile", {}).get("test") and row.get("executable")]
    require(len(binaries) == 1 and binaries[0].is_relative_to(runner.owned / "target"))
    binary = binaries[0]
    inventory = runner.run([str(binary), "--list", "--format", "terse"], cwd=runner.owned, phase=phase)
    tests = [line.removesuffix(": test") for line in inventory.splitlines() if line.endswith(": test")]
    require(len(tests) == 25 and len(set(tests)) == 25 and not any(line.endswith(": benchmark") for line in inventory.splitlines()))
    results = []
    for test in tests:
        output = runner.run([str(binary), "--exact", test, "--test-threads=1", "--nocapture"],
                            cwd=runner.owned, phase=runner.phase(5))
        require(output.splitlines().count("running 1 test") == 1 and test in output
                and len(re.findall(r"^test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9.]+s$", output, re.M)) == 1)
        if test == "failure_tests::panic_hook_scope":
            require(output.count("CALLER_HOOK ADAPTER_INPUT_SENTINEL synthetic.rs:1") == 1
                    and output.count("ADAPTER_INPUT_SENTINEL") == 1)
        elif test == "failure_tests::caught_panic":
            require("ADAPTER_INPUT_SENTINEL" not in output)
        results.append({"selector": test, "outcome": "passed"})
    return {"binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "tests": results}


def admission(package, runner, phase):
    inputs = runner.owned / "admission-inputs.jsonl"
    manifest = json.loads(runner.run([runner.env["PYO3_PYTHON"], "-I", "-B", str(package / "tests/admission_inputs.py"), str(inputs)],
                                     cwd=runner.owned, phase=phase))
    require(inputs.stat().st_size <= 126 * 1024**2)
    with inputs.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == manifest["input_sha256"])
    runner.run(["cargo", "build", "--release", "--offline", "--locked", "--no-default-features",
                "--example", "admission_reference"], cwd=package / "rust", phase=phase)
    command = [str(runner.owned / "target/release/examples/admission_reference"),
               str(package / "tests/fixtures/recorded/core-reference.json"), str(inputs)]
    first = runner.run(command, cwd=runner.owned, phase=phase, limit=1024**2)
    second = runner.run(command, cwd=runner.owned, phase=phase, limit=1024**2)
    expected = json.loads((package / "tests/fixtures/recorded/admission-oracles.json").read_bytes())
    require(first == second and json.loads(first) == expected)
    inputs.unlink()
    return {**manifest, "repeated": True, "oracle_equal": True}
