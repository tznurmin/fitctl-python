# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Build and test public distributions once per configuration in owned RAM."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci.archive_contract import Limits, validate_archive
from ci.archive_metadata import PYTHON_VERSIONS, python_layout
from ci.distribution_contract import artifact_manifest, require, sources, WHEEL, SDIST
from ci.installed_controls import controls
from ci.native_acceptance import admission, native, selectors
from ci.portable_audit import inspect, build
from ci.portable_runtime import install, preflight
from ci.runner import Runner
from ci.sdist_build import prepare
from ci.source_archive import extract, snapshot


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate(kind, path, expected):
    with path.open("rb") as stream:
        return validate_archive(kind, stream, expected_package=expected, limits=Limits())


def setup(root, owned):
    # Resolve the installed toolchain before dropping ambient home/credentials.
    rust = Path(subprocess.run(["rustc", "--print", "sysroot"], check=True, capture_output=True,
                               text=True, timeout=5).stdout.strip()).resolve()
    require(rust.is_dir() and not rust.is_relative_to(root))
    names = ("target", "cargo", "tmp", "home", "cache", "zig-cache", "direct-dist", "sdist-dist")
    for name in names:
        (owned / name).mkdir()
    env = {"PATH": str(rust / "bin") + ":" + os.environ["PATH"], "HOME": str(owned / "home"),
           "TMPDIR": str(owned / "tmp"), "TMP": str(owned / "tmp"), "TEMP": str(owned / "tmp"),
           "XDG_CACHE_HOME": str(owned / "cache"), "CARGO_HOME": str(owned / "cargo"),
           "CARGO_TARGET_DIR": str(owned / "target"), "CARGO_BUILD_JOBS": "2", "RUST_TEST_THREADS": "2",
           "CARGO_NET_RETRY": "0", "CARGO_HTTP_TIMEOUT": "30", "PYO3_PYTHON": sys.executable,
           # Native test executables need the selected setup-python shared library.
           # Installed acceptance clears this environment and uses the OCI runtime.
           "LD_LIBRARY_PATH": str(Path(sys.prefix).resolve() / "lib"),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "FITCTL_EMBED_VCS": "0",
           "RUSTFLAGS": "--remap-path-prefix=" + str(owned) + "=/src --remap-path-prefix=" + str(root) + "=/src",
           "SOURCE_DATE_EPOCH": "1767225600", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC0",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
           "ZIG_GLOBAL_CACHE_DIR": str(owned / "zig-cache")}
    runner = Runner(root, owned, env)
    phase = runner.phase(120)
    toolenv = owned / "tools"
    runner.run([sys.executable, "-I", "-B", "-m", "venv", str(toolenv)], cwd=owned, phase=phase)
    runner.run([str(toolenv / "bin/python"), "-I", "-B", "-m", "pip", "install", "--no-cache-dir",
                "--only-binary=:all:", "--index-url", "https://pypi.org/simple", "-r", str(root / "ci/build-requirements.txt")],
               cwd=owned, phase=phase)
    zig = toolenv / python_layout(".".join(map(str, sys.version_info[:3]))) / "ziglang"
    require((zig / "zig").is_file())
    runner.env["PATH"] = str(toolenv / "bin") + ":" + str(zig) + ":" + env["PATH"]
    versions = {}
    for tool in ("rustc", "cargo", "maturin", "zig", "auditwheel", "python3", "bwrap", "strace", "skopeo", "umoci"):
        versions[tool] = runner.run([tool, "version" if tool == "zig" else "--version"], cwd=owned, phase=phase).strip()
    return runner, [rust, Path(sys.prefix).resolve(), toolenv], versions


def distributions(root, owned, runner, tools):
    source = owned / "source"
    expected = snapshot(root, source, runner, runner.phase(15))
    inputs = [tomllib.loads((source / name).read_text()) for name in ("pyproject.toml", "rust/Cargo.toml", "rust/Cargo.lock")]
    sources(*inputs)
    lock = sha(source / "rust/Cargo.lock")
    runner.run(["cargo", "fetch", "--locked"], cwd=source / "rust", phase=runner.phase(120))
    runner.env["CARGO_NET_OFFLINE"] = "true"
    for version in PYTHON_VERSIONS:
        preflight(source, version, runner, runner.phase(180))
    phase = runner.phase(30)
    runner.run(["git", "init", "--quiet"], cwd=source, phase=phase)
    runner.run(["git", "add", "--", *sorted(expected)], cwd=source, phase=phase)
    runner.run([sys.executable, "-B", "ci/build_backend.py", "sdist", "--out", str(owned / "sdist-dist")], cwd=source, phase=phase)
    sdist = owned / "sdist-dist" / SDIST
    require(list(sdist.parent.iterdir()) == [sdist] and sha(source / "rust/Cargo.lock") == lock)
    inventory = validate("sdist", sdist, expected)
    extracted = owned / "sdist-source"
    extract(sdist, inventory, extracted)
    argv, build_controls = prepare(extracted, source, root, owned / "sdist-wheel", runner, runner.phase(30), tools)
    evidence = {"lock_sha256": lock, "source": expected, "build_controls": build_controls,
                "native": native(source, runner, runner.phase(240)),
                "admission": admission(source, runner, runner.phase(180))}
    build(source, owned / "direct-dist", runner, runner.phase(180), sys.executable)
    output = runner.run(argv, cwd=owned, phase=runner.phase(180))
    require(output.splitlines().count("BUILD_SOURCE_ISOLATION=verified") == 1
            and sha(extracted / "rust/Cargo.lock") == lock and sha(source / "rust/Cargo.lock") == lock)
    selected = selectors(source)
    evidence["runtime"], evidence["audit"], evidence["controls"] = {}, {}, {}
    for variant, directory, package in (("direct", "direct-dist", source), ("sdist", "sdist-wheel", extracted)):
        wheel = owned / directory / WHEEL
        require(list(wheel.parent.iterdir()) == [wheel])
        validate("wheel", wheel, expected)
        evidence["audit"][variant] = inspect(wheel, runner, runner.phase(15))
        for version in PYTHON_VERSIONS:
            evidence["runtime"][variant + ":" + version] = install(wheel, package, variant, version, selected, runner, runner.phase(60))
            if variant == "direct":
                evidence["controls"][version] = controls(source, version, runner, runner.phase(90))
    return owned / "direct-dist" / WHEEL, sdist, evidence


def main():
    root = Path(__file__).resolve().parents[1]
    owned = Path(os.environ["FITCTL_DISTRIBUTION_ROOT"])
    require(owned.is_absolute() and not owned.is_symlink())
    mount = subprocess.run(["findmnt", "-n", "-o", "FSTYPE,TARGET", "--target", str(owned)],
                           check=True, capture_output=True, text=True, timeout=5).stdout.split()
    require(mount == ["tmpfs", str(owned)] and not any(owned.iterdir()))
    runner, tools, versions = setup(root, owned)
    wheel, sdist, evidence = distributions(root, owned, runner, tools)
    evidence["tools"] = versions
    manifest = {"version": "0.1.1", "artifacts": {path.name: sha(path) for path in (wheel, sdist)},
                "passed": sorted(evidence["runtime"])}
    artifact_manifest(manifest, manifest["artifacts"])
    destination = root / "release-artifacts"
    require(not destination.exists())
    destination.mkdir()
    (destination / "dist").mkdir()
    for path in (wheel, sdist):
        shutil.copyfile(path, destination / "dist" / path.name)
        require(sha(destination / "dist" / path.name) == manifest["artifacts"][path.name])
    encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (destination / "manifest.json").write_bytes(encoded)
    # Per-test outcomes are a separate evidence artifact, never uploaded to PyPI.
    report = json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n"
    require(len(report.encode()) <= 1024**2)
    with (root / "qualification.json").open("x") as stream:
        stream.write(report)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write("manifest-sha256=" + hashlib.sha256(encoded).hexdigest() + "\n")
    print("Public native, direct-wheel and independent-sdist qualification passed", flush=True)


if __name__ == "__main__":
    main()
