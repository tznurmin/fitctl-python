# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolated negative controls for installed origin, native identity and effects."""

import argparse
import copy
import importlib.machinery
import json
import os
from pathlib import Path
import socket
import sys
import threading
import types
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import installed_support as checks


def rejected(function, message=None):
    try:
        function()
    except (AssertionError, OSError) as error:
        if message is not None and error.args != (message,):
            raise AssertionError("control rejected for wrong reason") from None
        return
    raise AssertionError("injected fault was accepted")


def effect(name):
    try:
        if name == "open":
            Path("/host-probe").read_bytes()
        elif name == "stat":
            Path("/host-probe").stat()
        elif name == "write":
            Path("/tmp/effect-probe").write_bytes(b"x")
        elif name == "memfd":
            os.close(os.memfd_create("effect-probe"))
        elif name == "exec":
            os.execv("/probe-cli", ["/probe-cli"])
        elif name == "fork":
            child = os.fork()
            if child == 0:
                os._exit(0)
            os.waitpid(child, 0)
        elif name in ("socket", "connect"):
            with socket.socket() as connection:
                if name == "connect":
                    connection.connect(("127.0.0.1", 9))
        else:
            raise AssertionError("unknown effect control")
    except OSError:
        pass  # The external observer must reject attempts, including failures.


def identity(name, module):
    native = sys.modules["fitctl._native"]
    if name in ("source", "closure", "canary"):
        rejected(checks.inspect_isolation)
    elif name == "descriptor":
        # The supplied read-only canary is opened by the harness before inspection.
        with Path("/tests/isolation-canary.txt").open("rb"):
            rejected(checks.inspect_isolation, "unexpected inherited descriptor")
    elif name == "origin":
        with patch.object(module, "__file__", "/tests/run_controls.py"):
            rejected(lambda: checks.inspect_installation(module), "installed origin invalid")
    elif name in ("standin", "forged"):
        fake = types.ModuleType("fitctl._native")
        source = Path(__file__).parent / "fixtures/adaptation/native-standin.py.txt"
        exec(compile(source.read_bytes(), "native-standin", "exec"), fake.__dict__)
        fake.__file__ = native.__file__
        fake.__spec__ = copy.copy(native.__spec__)
        if name == "standin":
            fake.__spec__.loader = importlib.machinery.SourceFileLoader("fitctl._native", fake.__file__)
        with patch.dict(sys.modules, {"fitctl._native": fake}):
            rejected(lambda: checks.inspect_installation(module),
                     "native extension loader required" if name == "standin" else "native callable required")
    elif name in ("elf", "typing", "marker"):
        original = Path.read_bytes
        def changed(path):
            if name == "elf" and str(path) == native.__file__:
                data = bytearray(original(path)); data[-1] ^= 1; return bytes(data)
            if name == "typing" and path.name == "__init__.pyi":
                raise FileNotFoundError("selected typing member absent")
            if name == "marker" and path.name == "py.typed":
                raise FileNotFoundError("selected typing member absent")
            return original(path)
        with patch.object(Path, "read_bytes", changed):
            rejected(lambda: checks.inspect_installation(module),
                     "native extension identity invalid" if name == "elf" else "selected typing member absent")
    elif name in ("core_version", "semantic_encoding"):
        with patch.object(module, name, "wrong"):
            rejected(lambda: checks.inspect_installation(module), "public version identity invalid")
    elif name == "hook":
        with patch.object(native, "inject_fault", lambda: None, create=True):
            rejected(lambda: checks.inspect_installation(module), "release test hook exposed")
    elif name == "free_threaded":
        original = checks.sysconfig.get_config_var
        with patch.object(checks.sysconfig, "get_config_var", side_effect=lambda key: 1 if key == "Py_GIL_DISABLED" else original(key)):
            rejected(lambda: checks.inspect_installation(module), "runtime identity invalid")
    elif name in ("soabi", "python311", "platform", "machine"):
        target, value = {"soabi": ("sysconfig.get_config_var", "abi3"),
                         "python311": ("platform.python_version", "3.11.0"),
                         "platform": ("sys.platform", "darwin"), "machine": ("platform.machine", "aarch64")}[name]
        options = {"new": value} if name == "platform" else {"return_value": value}
        with patch(target, **options):
            rejected(lambda: checks.inspect_installation(module), "runtime identity invalid")
    else:
        raise AssertionError("unknown identity control")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", required=True)
    parser.add_argument("--receipt-fd", type=int, choices=[3], required=True)
    args = parser.parse_args()
    name = args.select.removeprefix("control:")
    checks.EXPECTED = json.loads((Path(__file__).parent / "qualification-input.json").read_bytes())
    tid = threading.get_native_id()
    def marker(value):
        os.write(4, f"FITCTL_{value} {tid}\n".encode())
    marker("IMPORT_BEGIN")
    module = checks.runtime_import("fitctl")
    if name.startswith("import_effect:"):
        effect(name.split(":", 1)[1])
    marker("IMPORT_END")
    if name not in ("source", "closure", "canary"):
        checks.inspect_isolation()
    checks.inspect_installation(module)
    marker("BEGIN")
    if name.startswith("effect:"):
        effect(name.split(":", 1)[1])
    else:
        module.builtin_config("policy", "general_compute_default.v1.json")
    marker("END")
    if not name.startswith(("effect:", "import_effect:")):
        identity(name, module)
    os.write(args.receipt_fd, json.dumps({"control": name, "outcome": "passed"}).encode())


if __name__ == "__main__":
    main()
