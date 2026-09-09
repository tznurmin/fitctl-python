# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare an isolated wheel build from a source distribution."""

import json
from pathlib import Path
import shutil

from native_process import run_bounded
from .distribution_contract import require
from .portable_audit import wheel_command


def prepare(package, source, root, destination, runner, phase, tools):
    target, home, temporary = [runner.owned / name for name in ("sdist-target", "sdist-home", "sdist-tmp")]
    for path in (target, home, temporary, destination):
        path.mkdir()
    env = {name: runner.env[name] for name in (
        "PATH", "CARGO_HOME", "CARGO_BUILD_JOBS", "RUST_TEST_THREADS", "RUSTFLAGS", "PYO3_PYTHON",
        "SOURCE_DATE_EPOCH", "FITCTL_EMBED_VCS", "ZIG_GLOBAL_CACHE_DIR", "LD_LIBRARY_PATH")}
    env.update(HOME=str(home), TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary),
               CARGO_TARGET_DIR=str(target), CARGO_NET_OFFLINE="true", PYTHONDONTWRITEBYTECODE="1",
               LANG="C.UTF-8", LC_ALL="C.UTF-8", TZ="UTC0")
    probe = runner.owned / "sdist-probe.py"
    shutil.copyfile(source / "ci/build_probe.py", probe)
    config = runner.owned / "sdist-probe.json"
    python = runner.env["PYO3_PYTHON"]
    command = wheel_command(python, destination)
    forbidden = [str(source / "rust/src/lib.rs"), str(root / "rust/src/lib.rs"),
                 str(root / ".git/config"), str(runner.owned / "target")]
    configuration = {"command": [python, "-I", "-B", "-c", "print('BUILD_PROBE_BACKEND=complete')"],
                     "cwd": str(package), "target": str(target), "forbidden": forbidden,
                     "required": [str(package / name) for name in ("pyproject.toml", "rust/src/lib.rs", "rust/Cargo.lock")]}
    readonly = [Path("/usr"), Path("/etc/ld.so.cache"), *tools, probe, config]
    writable = [package, destination, target, home, temporary, runner.owned / "cargo", runner.owned / "zig-cache"]
    argv = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
            *[item for key, value in sorted(env.items()) for item in ("--setenv", key, value)],
            *[item for path in readonly for item in ("--ro-bind", str(path), str(path))],
            *[item for path in writable for item in ("--bind", str(path), str(path))],
            *[item for name in ("bin", "sbin", "lib", "lib64") for item in ("--symlink", "usr/" + name, "/" + name)],
            "--ro-bind", str(package / "rust/Cargo.lock"), str(package / "rust/Cargo.lock"),
            "--bind", str(temporary), "/tmp", "--proc", "/proc",
            "--dev-bind", "/dev/null", "/dev/null", "--dev-bind", "/dev/urandom", "/dev/urandom",
            "--chdir", str(package), python, "-I", "-B", str(probe), str(config)]
    config.write_text(json.dumps(configuration))
    output = runner.run(argv, cwd=runner.owned, phase=phase)
    require(output.splitlines().count("BUILD_SOURCE_ISOLATION=verified") == 1
            and output.splitlines().count("BUILD_PROBE_BACKEND=complete") == 1)
    outcomes = [{"control": "source_hidden", "outcome": "passed"}]
    position = argv.index("--chdir")
    for name, exposed in (("source_exposed", forbidden[0]), ("target_exposed", forbidden[-1]),
                          ("target_populated", None)):
        contaminated = argv[:position] + (["--ro-bind", exposed, exposed] if exposed else []) + argv[position:]
        canary = target / "compiled-artifact-control"
        if exposed is None:
            canary.write_bytes(b"not a build input")
        try:
            result = run_bounded(contaminated, cwd=runner.owned, env=runner.env,
                                 timeout=min(5, phase.seconds()), output_limit=65536, watch=runner.watch)
            message = "original or undeclared source visible" if exposed else "sdist target must start empty"
            require(result.returncode == 1 and not result.truncated and message in result.output
                    and "BUILD_PROBE_BACKEND=complete" not in result.output)
            outcomes.append({"control": name, "outcome": "rejected"})
        finally:
            if exposed is None:
                canary.unlink()
    configuration["command"] = command
    config.write_text(json.dumps(configuration))
    return argv, outcomes
