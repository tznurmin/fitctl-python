# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Run installed tests in isolated Debian Python environments."""

import hashlib
import json
from pathlib import Path
import shutil

from .distribution_contract import require
from .installed_process import execute
from .portable_images import acquire, IMAGES
from .archive_metadata import NATIVE, python_layout

ROOTS = ("/usr/local", "/lib/x86_64-linux-gnu", "/lib64", "/usr/lib/locale", "/usr/lib/x86_64-linux-gnu")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(env, tests, temporary, runtime, selector, runner):
    configuration = json.loads((tests / "qualification-input.json").read_text())
    version = configuration["python_version"]
    image = runner.owned / "images" / version / "bundle/rootfs"
    require(runtime == list(ROOTS))
    entry = ("isolation_probe.py" if selector == "isolation-probe" else
             "run_controls.py" if selector.startswith("control:") else "run_installed.py")
    return [shutil.which("bwrap", path=runner.env["PATH"]), "--unshare-all", "--die-with-parent",
            "--new-session", "--cap-drop", "ALL", "--clearenv",
            "--setenv", "PATH", "/env/bin", "--setenv", "LANG", "C.UTF-8",
            "--setenv", "LC_ALL", "C.UTF-8", "--setenv", "TZ", "UTC0",
            "--setenv", "TMPDIR", "/tmp", "--setenv", "HOME", "/work",
            "--ro-bind", str(env), "/env", "--ro-bind", str(tests), "/tests",
            *[argument for path in ROOTS for argument in ("--ro-bind", str(image / path[1:]), path)],
            "--bind", str(temporary / "work"), "/work", "--bind", str(temporary / "tmp"), "/tmp",
            "--dev-bind", "/dev/null", "/dev/null", "--dev-bind", "/dev/zero", "/dev/zero",
            "--dev-bind", "/dev/urandom", "/dev/urandom", "--proc", "/proc", "--chdir", "/work",
            "/env/bin/python", "-I", "-B", "/tests/" + entry, "--select", selector, "--receipt-fd", "3"]


def environment(version, label, runner, phase, wheel=None):
    image = acquire(version, runner, phase)
    env = runner.owned / (label + "-env")
    env.mkdir()
    temporary = runner.owned / (label + "-setup")
    temporary.mkdir()
    base = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
            "--clearenv", "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin", "--setenv", "HOME", "/tmp",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--ro-bind", str(image / "usr"), "/usr", "--ro-bind", str(image / "etc"), "/etc",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--bind", str(env), "/env", "--bind", str(temporary), "/tmp", "--proc", "/proc",
            "--dev-bind", "/dev/null", "/dev/null", "--dev-bind", "/dev/urandom", "/dev/urandom",
            "--chdir", "/tmp"]
    runner.run([*base, "/usr/local/bin/python3", "-I", "-B", "-m", "venv", "--without-pip", "/env"],
               cwd=runner.owned, phase=phase)
    if wheel is not None:
        runner.run([*base, "--ro-bind", str(wheel), "/tmp/" + wheel.name,
                    "/usr/local/bin/python3", "-I", "-B", "-m", "pip", "--python", "/env/bin/python",
                    "install", "--no-index", "--no-deps", "--no-compile", "/tmp/" + wheel.name],
                   cwd=runner.owned, phase=phase)
    members = {path: sorted(child.name for child in (image / path[1:]).iterdir()) for path in ROOTS}
    return env, {"runtime_profile": "bookworm", "runtime_closure": list(ROOTS),
                 "runtime_members": members, "python_version": version, "image_sha256": IMAGES[version]}


def preflight(package, version, runner, phase):
    label = "portable-probe-" + version
    env, inputs = environment(version, label, runner, phase)
    tests = runner.owned / (label + "-tests")
    tests.mkdir()
    for name in ("isolation_probe.py", "installed_support.py", "collection_probe.py", "collection_provider.py"):
        shutil.copyfile(package / "tests" / name, tests / name)
    (tests / "qualification-input.json").write_text(json.dumps(inputs))
    return execute(env, tests, list(ROOTS), "isolation-probe", runner, phase, command_builder=command)


def install(wheel, package, variant, version, selectors, runner, phase):
    label = "portable-" + variant + "-" + version
    env, inputs = environment(version, label, runner, phase, wheel)
    tests = runner.owned / (label + "-tests")
    shutil.copytree(package / "tests", tests)
    native = env / python_layout(version) / NATIVE
    inputs.update(variant=variant, native_sha256=sha(native.read_bytes()), tests=selectors,
                  wheel_sha256=sha(wheel.read_bytes()),
                  source_members_verified=True,
                  typing_sha256={name: sha((package / "python/fitctl" / name).read_bytes())
                                 for name in ("__init__.pyi", "py.typed")})
    (tests / "qualification-input.json").write_text(json.dumps(inputs))
    result, trace = execute(env, tests, list(ROOTS), "all", runner, phase, command_builder=command)
    require(result["outcome"] == "passed" and trace["complete"] is True
            and sorted(row["id"] for row in result["tests"]) == sorted(selectors)
            and all(row["outcome"] == "passed" for row in result["tests"]))
    return {"installed": result, "trace": trace, "image_sha256": IMAGES[version],
            "python": version, "wheel_sha256": sha(wheel.read_bytes())}
