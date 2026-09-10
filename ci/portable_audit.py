# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Enforced manylinux audit plus independent ELF, dependency and tag checks."""

from email.parser import BytesParser
import re
import zipfile

from .distribution_contract import portability, require, WHEEL
from .archive_metadata import NATIVE, TAG


def wheel_command(python, destination):
    return [str(python), "-B", "ci/build_backend.py", "wheel", "--release", "--locked", "--offline", "--zig",
            "--target", "x86_64-unknown-linux-gnu", "--compatibility", "manylinux_2_28",
            "--auditwheel", "check", "--features", "extension-module",
            "--interpreter", str(python), "--out", str(destination)]


def build(package, destination, runner, phase, python):
    previous = runner.env
    runner.env = {key: value for key, value in previous.items() if key != "_PYTHON_HOST_PLATFORM"}
    try:
        # Maturin gives this ambient interpreter override precedence over its
        # audited platform tag. Derive the tag from the enforced audit instead.
        return runner.run(wheel_command(python, destination), cwd=package, phase=phase)
    finally:
        runner.env = previous


def audit_policy(output):
    # auditwheel wraps paragraphs, including words inside this phrase.
    policies = re.findall(r'consistent with the following platform tag: "(manylinux_2_([0-9]+)_x86_64)"',
                          " ".join(output.split()))
    require(len(policies) == 1 and int(policies[0][1]) <= 28)
    return policies[0][0]


def inspect(wheel, runner, phase):
    require(wheel.name == WHEEL and not wheel.is_symlink() and wheel.stat().st_size <= 256 * 1024**2)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)))
        natives = [name for name in names if name.endswith(".so")]
        require(natives == [NATIVE])
        require(archive.getinfo(natives[0]).file_size <= 64 * 1024**2)
        data = archive.read(natives[0])
        metadata = BytesParser().parsebytes(archive.read("fitctl-0.1.1.dist-info/WHEEL"))
        require(metadata.get_all("Tag") == [TAG])
    require(data[:6] == b"\x7fELF\x02\x01" and int.from_bytes(data[18:20], "little") == 62)
    native = runner.owned / ("audit-" + wheel.parent.name + ".so")
    require(not native.exists())
    native.write_bytes(data)
    try:
        rpath = runner.run(["patchelf", "--print-rpath", str(native)], cwd=runner.owned, phase=phase).strip()
        needed = runner.run(["patchelf", "--print-needed", str(native)], cwd=runner.owned, phase=phase).splitlines()
        versions = runner.run(["readelf", "--version-info", str(native)], cwd=runner.owned, phase=phase)
        glibc = [tuple(map(int, version.split("."))) for version in re.findall(r"\bGLIBC_([0-9]+\.[0-9]+)\b", versions)]
        require(bool(glibc))
        report = {"tag": metadata["Tag"], "machine": "x86_64", "glibc": list(max(glibc)),
                  "rpaths": rpath.split(":") if rpath else [], "external": sorted(needed),
                  "python": "3.13.13", "gil": True}
        portability(report)
        audit = runner.run(["auditwheel", "show", str(wheel)], cwd=runner.owned, phase=phase)
        # Cross-check auditwheel's reported policy against the ELF checks and isolated runtime tests.
        return {"elf": report, "auditwheel_policy": audit_policy(audit), "auditwheel_output": audit}
    finally:
        native.unlink()
