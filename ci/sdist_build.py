# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare an isolated wheel build from a source distribution."""

import json
from pathlib import Path
import shutil

from native_process import run_bounded
from .distribution_contract import require
from .portable_audit import wheel_command


def host_preflight(argv, configuration, config, runner, phase):
    """Link and execute a build script, load a proc macro, then run its consumer."""
    probe = runner.owned / "sdist-host-probe"
    probe.mkdir()
    try:
        fixtures = {
            "Cargo.toml": '[package]\nname="host-probe"\nversion="0.0.0"\nedition="2021"\n'
                          '[dependencies]\nhost-macro={path="macro"}\n[workspace]\n',
            "build.rs": 'fn main() { println!("cargo:rustc-env=HOST_BUILD_PROBE=executed"); }\n',
            "macro/Cargo.toml": '[package]\nname="host-macro"\nversion="0.0.0"\nedition="2021"\n'
                                '[lib]\nproc-macro=true\n',
            "macro/src/lib.rs": 'extern crate proc_macro;\n#[proc_macro]\n'
                                'pub fn answer(_: proc_macro::TokenStream) -> proc_macro::TokenStream '
                                '{ "42".parse().unwrap() }\n',
            "src/main.rs": 'fn main() { assert_eq!(env!("HOST_BUILD_PROBE"), "executed"); '
                           'assert_eq!(host_macro::answer!(), 42); '
                           'println!("BUILD_HOST_TOOLCHAIN=verified"); }\n'}
        for name, content in fixtures.items():
            path = probe / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        cargo = shutil.which("cargo", path=runner.env["PATH"])
        require(cargo is not None)
        target = probe / "target"
        configuration["command"] = [cargo, "run", "--quiet", "--offline", "--manifest-path",
                                    str(probe / "Cargo.toml"), "--target-dir", str(target)]
        config.write_text(json.dumps(configuration))
        position = argv.index("--chdir")
        selected = argv[:position] + ["--bind", str(probe), str(probe)] + argv[position:]
        position = selected.index("/etc/alternatives") - 1
        hidden = selected[:position] + selected[position + 3:]
        result = run_bounded(hidden, cwd=runner.owned, env=runner.env,
                             timeout=min(10, phase.seconds()), output_limit=65536, watch=runner.watch)
        require(result.returncode == 101 and not result.truncated and 'linker `cc` not found' in result.output
                and result.output.splitlines().count("BUILD_SOURCE_ISOLATION=verified") == 1
                and "BUILD_HOST_TOOLCHAIN=verified" not in result.output)
        # Reject using a fresh target, then remove partial outputs before the positive probe.
        if target.exists():
            shutil.rmtree(target)
        output = runner.run(selected, cwd=runner.owned, phase=phase)
        require(output.splitlines().count("BUILD_SOURCE_ISOLATION=verified") == 1
                and output.splitlines().count("BUILD_HOST_TOOLCHAIN=verified") == 1
                and not any(Path(configuration["target"]).iterdir()))
        return [{"control": "host_compiler_hidden", "outcome": "rejected"},
                {"control": "host_toolchain", "outcome": "passed"}]
    finally:
        shutil.rmtree(probe)


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
    # Preserve Ubuntu's cc symlink chain so GCC can locate its linker plugin.
    readonly = [Path("/usr"), Path("/etc/ld.so.cache"), Path("/etc/alternatives"), *tools, probe, config]
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
    outcomes.extend(host_preflight(argv, configuration, config, runner, phase))
    configuration["command"] = command
    config.write_text(json.dumps(configuration))
    return argv, outcomes
