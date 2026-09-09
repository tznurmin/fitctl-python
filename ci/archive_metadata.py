# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Self-contained public source and wheel metadata contracts."""

import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re

DIST_INFO = "fitctl-0.1.0.dist-info/"
NATIVE = "fitctl/_native.cpython-313-x86_64-linux-gnu.so"
LEGAL_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.txt")
WHEEL_EXPRESSION = "Apache-2.0 AND BlueOak-1.0.0 AND MIT AND Unicode-3.0"


def invalid():
    raise ValueError("archive content invalid")


def approved_files():
    # Load the expected license-file digests and distribution expressions.
    location = Path(globals().get("_shared", __file__)).with_name("license_materials.json")
    try:
        data = location.read_bytes()
        if len(data) > 4096:
            invalid()
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    invalid()
                result[key] = value
            return result
        table = json.loads(data, object_pairs_hook=pairs)
        if (set(table) != {"schema_id", "schema_version", "files", "profile", "license_expressions"}
                or table["schema_id"] != "license-release-files.v1" or type(table["schema_version"]) is not int
                or table["schema_version"] != 1 or table["profile"] != "whitespace-v1"
                or set(table["files"]) != set(LEGAL_FILES)
                or any(type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value) for value in table["files"].values())
                or table["license_expressions"] != {"sdist": "Apache-2.0", "wheel": WHEEL_EXPRESSION}):
            invalid()
        return table
    except (OSError, ValueError, KeyError, TypeError):
        invalid()


def metadata(data, kind="wheel"):
    if kind not in ("wheel", "sdist"):
        invalid()
    document = BytesParser().parsebytes(data)
    if (document.get_all("Name") != ["fitctl"] or document.get_all("Version") != ["0.1.0"]
            or document.get_all("Requires-Python") != [">=3.13, <3.14"] or document.get_all("Requires-Dist")
            or sorted(document.get_all("License-File", [])) != list(LEGAL_FILES)
            or document.get_all("License-Expression") != [approved_files()["license_expressions"][kind]]
            or document.get_all("Metadata-Version") != ["2.4"] or document.get_all("License")
            or document.get_all("Dynamic", []) != (["License-Expression"] if kind == "sdist" else [])):
        invalid()


def notices(contents):
    for name, expected in approved_files()["files"].items():
        if name not in contents or hashlib.sha256(contents[name]).hexdigest() != expected:
            invalid()


def equal(data, expected, actual_mode):
    size, digest, mode = expected
    if (type(size) is not int or type(mode) is not int or type(digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or len(data) != size or hashlib.sha256(data).hexdigest() != digest
            or mode not in (0o644, 0o755) or actual_mode != mode):
        invalid()


def record(contents):
    path = DIST_INFO + "RECORD"
    rows = list(csv.reader(io.StringIO(contents[path].decode("utf-8"))))
    found = set()
    for row in rows:
        if len(row) != 3:
            invalid()
        name, digest, size = row
        if name in found or name not in contents:
            invalid()
        found.add(name)
        if name == path:
            if digest or size:
                invalid()
        else:
            data = contents[name]
            actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            if digest != "sha256=" + actual or size != str(len(data)):
                invalid()
    if found != contents.keys():
        invalid()


def validate_content(kind, contents, expected, modes):
    if kind == "sdist":
        prefix = "fitctl-0.1.0/"
        if not all(name.startswith(prefix) for name in contents):
            invalid()
        relative = {name.removeprefix(prefix): data for name, data in contents.items()}
        notices(relative)
        if relative.keys() != expected.keys() | {"PKG-INFO"}:
            invalid()
        for name, identity in expected.items():
            equal(relative[name], identity, modes[prefix + name])
        metadata(relative["PKG-INFO"], "sdist")
        return
    required = {name.removeprefix("python/"): identity for name, identity in expected.items()
                if name.startswith("python/")}
    extra = {NATIVE, DIST_INFO + "METADATA", DIST_INFO + "WHEEL", DIST_INFO + "RECORD"}
    licenses = {DIST_INFO + "licenses/" + name for name in LEGAL_FILES if name in expected}
    notices({name.removeprefix(DIST_INFO + "licenses/"): data for name, data in contents.items()
             if name.startswith(DIST_INFO + "licenses/")})
    if contents.keys() != required.keys() | extra | licenses or not contents[NATIVE].startswith(b"\x7fELF"):
        invalid()
    for name, identity in required.items():
        equal(contents[name], identity, modes[name])
    for name in licenses:
        equal(contents[name], expected[name.rsplit("/", 1)[1]], modes[name])
    metadata(contents[DIST_INFO + "METADATA"])
    wheel = BytesParser().parsebytes(contents[DIST_INFO + "WHEEL"])
    if wheel.get_all("Tag") != ["cp313-cp313-manylinux_2_28_x86_64"] or wheel.get_all("Root-Is-Purelib") != ["false"]:
        invalid()
    record(contents)
