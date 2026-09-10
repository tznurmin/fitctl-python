# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated into the upload workflow; validation only, never a build."""

import hashlib
import json
import os
from pathlib import Path

root = Path("release-artifacts")
manifest = root / "manifest.json"
if manifest.is_symlink() or manifest.stat().st_size > 65536:
    raise ValueError("distribution verification failed")
data = manifest.read_bytes()
if hashlib.sha256(data).hexdigest() != os.environ["MANIFEST_SHA256"]:
    raise ValueError("distribution verification failed")
document = json.loads(data)
expected_names = {"fitctl-0.1.1.tar.gz", "fitctl-0.1.1-cp312-abi3-manylinux_2_28_x86_64.whl"}
expected_tests = {variant + ":" + version for variant in ("direct", "sdist")
                  for version in ("3.12.13", "3.13.0", "3.13.13", "3.14.4")}
if (set(document) != {"version", "artifacts", "passed"} or document["version"] != "0.1.1"
        or len(document["passed"]) != len(expected_tests) or set(document["passed"]) != expected_tests
        or set(document["artifacts"]) != expected_names
        or {p.name for p in root.iterdir()} != {"dist", "manifest.json"}
        or (root / "dist").is_symlink()
        or {p.name for p in (root / "dist").iterdir()} != expected_names):
    raise ValueError("distribution verification failed")
for name, expected in document["artifacts"].items():
    path = root / "dist" / name
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 256 * 1024**2:
        raise ValueError("distribution verification failed")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("distribution verification failed")
print("Exact tested artifacts verified")
