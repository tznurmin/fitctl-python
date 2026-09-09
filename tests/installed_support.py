# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Installed-test inputs and runtime identity, supplied by the external harness."""

import hashlib
import fcntl
import importlib.machinery
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig
import types

EXPECTED = {}
IDENTITY = {}
ENVIRONMENT = {"PATH": "/env/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
               "TZ": "UTC0", "TMPDIR": "/tmp", "PWD": "/work", "HOME": "/work"}


def inspect_environment(environ):
    if dict(environ) != ENVIRONMENT:
        raise AssertionError("unexpected environment input")


def runtime_import(name):
    # Tests are already loaded. Keep their directory out of the import search
    # for the observed package/runtime import; restore it only for the harness.
    previous = sys.path[:]
    sys.path[:] = [path for path in previous if path != "/tests"]
    try:
        return importlib.import_module(name)
    finally:
        sys.path[:] = previous


def inspect_installation(module):
    native = sys.modules["fitctl._native"]
    site = Path("/env/lib/python3.13/site-packages")
    for value in (module, native):
        origin = Path(value.__file__).resolve(strict=True)
        if not origin.is_relative_to(site) or value.__spec__.origin != value.__file__:
            raise AssertionError("installed origin invalid")
    if not isinstance(native.__spec__.loader, importlib.machinery.ExtensionFileLoader):
        raise AssertionError("native extension loader required")
    for name in ("builtin_config", "derive_contract", "validate"):
        if not isinstance(getattr(native, name, None), types.BuiltinFunctionType):
            raise AssertionError("native callable required")
    for name in ("Artifact", "Policy"):
        cls = getattr(native, name, None)
        for factory in ("from_dict", "from_json"):
            method = getattr(cls, factory, None)
            if not isinstance(method, types.BuiltinFunctionType) or method.__self__ is not cls:
                raise AssertionError("native class factory required")
    path = Path(native.__file__)
    data = path.read_bytes()
    if (path.name != "_native.cpython-313-x86_64-linux-gnu.so" or not data.startswith(b"\x7fELF")
            or hashlib.sha256(data).hexdigest() != EXPECTED["native_sha256"]):
        raise AssertionError("native extension identity invalid")
    if ((module.__version__, module.core_version, module.semantic_encoding)
            != ("0.1.0", "0.8.0", "fitctl.semantic_cbor.v2")):
        raise AssertionError("public version identity invalid")
    version = EXPECTED.get("python_version", "3.13.13")
    if (version not in {"3.13.0", "3.13.13"} or platform.python_version() != version
            or sysconfig.get_config_var("SOABI") != "cpython-313-x86_64-linux-gnu"
            or sysconfig.get_config_var("Py_GIL_DISABLED") or sys.platform != "linux" or platform.machine() != "x86_64"):
        raise AssertionError("runtime identity invalid")
    if sys.prefix != "/env" or not sys.flags.isolated or not sys.dont_write_bytecode:
        raise AssertionError("isolated runtime required")
    for name in ("__init__.pyi", "py.typed"):
        data = (site / "fitctl" / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != EXPECTED["typing_sha256"][name]:
            raise AssertionError("installed typing identity invalid")
    forbidden = [name for name in vars(native) if "fault" in name.lower() or "inject" in name.lower()]
    if forbidden:
        raise AssertionError("release test hook exposed")
    return {"module_origin": module.__file__, "native_origin": native.__file__,
            "native_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "version": module.__version__, "core_version": module.core_version,
            "semantic_encoding": module.semantic_encoding, "variant": EXPECTED["variant"]}


def inspect_isolation():
    profile = EXPECTED.get("runtime_profile", "nix")
    roots = {"dev", "env", "proc", "tests", "tmp", "work"}
    if profile == "nix":
        roots.add("nix")
    elif profile == "bookworm":
        roots.update({"usr", "lib", "lib64"})
        if EXPECTED["runtime_closure"] != ["/usr/local", "/lib/x86_64-linux-gnu", "/lib64", "/usr/lib/locale", "/usr/lib/x86_64-linux-gnu"]:
            raise AssertionError("unexpected dependency visibility")
        if (set(os.listdir("/usr")) != {"local", "lib"} or set(os.listdir("/lib")) != {"x86_64-linux-gnu"}
                or set(os.listdir("/usr/lib")) != {"locale", "x86_64-linux-gnu"}):
            raise AssertionError("unexpected dependency visibility")
        for path in EXPECTED["runtime_closure"]:
            if sorted(os.listdir(path)) != EXPECTED["runtime_members"][path]:
                raise AssertionError("unexpected dependency visibility")
    else:
        raise AssertionError("unexpected runtime profile")
    if set(os.listdir("/")) != roots:
        raise AssertionError("unexpected root visibility")
    if profile == "nix" and set(os.listdir("/nix/store")) != {Path(path).name for path in EXPECTED["runtime_closure"]}:
        raise AssertionError("unexpected dependency visibility")
    found = set()
    for entry in Path("/proc/self/fd").iterdir():
        try:
            target = os.readlink(entry)
        except FileNotFoundError:
            continue  # listdir's own already-closed descriptor
        descriptor = int(entry.name)
        found.add(descriptor)
        if descriptor == 0 and target != "/dev/null":
            raise AssertionError("unexpected standard input")
        if descriptor > 4:
            raise AssertionError("unexpected inherited descriptor")
        if descriptor in (1, 2, 3, 4) and not target.startswith("pipe:["):
            raise AssertionError("unexpected channel identity")
        if descriptor in (3, 4) and fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_WRONLY:
            raise AssertionError("unexpected channel access")
    if found != {0, 1, 2, 3, 4}:
        raise AssertionError("missing inherited descriptor")
    inspect_environment(os.environ)
