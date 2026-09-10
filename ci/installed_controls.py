# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the authoritative installed verifier controls against a portable wheel."""

import shutil

from recorded_failures import RecordedFailure
from .distribution_contract import require
from .installed_process import execute
from .portable_runtime import command, ROOTS

IDENTITY = ("source", "origin", "standin", "forged", "elf", "canary", "descriptor", "closure",
            "core_version", "semantic_encoding", "typing", "marker", "hook", "free_threaded", "soabi",
            "python311", "platform", "machine")
EFFECTS = tuple(prefix + name for prefix in ("effect:", "import_effect:")
                for name in ("open", "stat", "write", "memfd", "exec", "fork", "socket", "connect"))


def controls(package, version, runner, phase):
    label = "portable-direct-" + version
    env, tests = runner.owned / (label + "-env"), runner.owned / (label + "-tests")
    canary = tests / "isolation-canary.txt"
    shutil.copyfile(tests / "fixtures/adaptation/isolation-canary.txt", canary)
    results = []
    for variant in (*IDENTITY, *EFFECTS):
        suffix = "control-" + variant.replace(":", "-")
        def transform(argv):
            if variant not in ("source", "canary", "closure"):
                return argv
            source, destination = {"source": (package, "/source"),
                "canary": (canary, "/outside/isolation-canary.txt"),
                "closure": (canary, "/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-control-source")}[variant]
            position = argv.index("--chdir")
            return argv[:position] + ["--ro-bind", str(source), destination] + argv[position:]
        try:
            try:
                result, trace = execute(env, tests, list(ROOTS), "control:" + variant, runner, phase,
                    suffix=suffix, transform=transform, command_builder=command)
            except RecordedFailure as error:
                require(variant in EFFECTS and error.code == "effect_forbidden")
                results.append({"control": variant, "outcome": "rejected"})
            else:
                require(variant in IDENTITY and trace["complete"] is True)
                results.append({**result, "trace": trace})
        finally:
            temporary = runner.owned / (env.name + "-" + suffix)
            require(not temporary.is_symlink() and temporary.resolve().parent == runner.owned)
            shutil.rmtree(temporary)
    require(len(results) == 34)
    return results
