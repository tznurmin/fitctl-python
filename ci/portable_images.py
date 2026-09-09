# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Digest-pinned public runtime images, acquired only inside owned RAM."""

import hashlib
import json
import os
from pathlib import Path

from .distribution_contract import require

IMAGES = {
    "3.13.0": "b0c5cb8792bf58879f532c1e10f44e1af02d72735758374198f9717d67a7ae52",
    "3.13.13": "f576b530293e74140ea91d262232648d5c4f45640a95ec447757701bfcacf034",
}


def bounded(owned):
    compressed = expanded = count = 0
    for directory, _, files in os.walk(owned / "images", followlinks=False):
        for name in files:
            path = Path(directory) / name
            try:
                size = path.lstat().st_size
            except FileNotFoundError:
                continue
            count += 1
            if "blobs" in path.parts:
                compressed += size
            else:
                expanded += size
            require(count <= 50000 and compressed <= 256 * 1024**2 and expanded <= 1024**3)


def acquire(version, runner, phase):
    require(version in IMAGES)
    destination = runner.owned / "images" / version
    if destination.exists():
        require((destination / "verified.json").read_text() == json.dumps({"digest": IMAGES[version]}))
        return destination / "bundle/rootfs"
    destination.mkdir(parents=True)
    auth = destination / "auth.json"
    auth.write_text('{"auths":{}}')
    source = "docker://docker.io/library/python@sha256:" + IMAGES[version]
    runner.run(["skopeo", "--insecure-policy", "copy", "--authfile", str(auth),
                "--preserve-digests", source, "oci:" + str(destination / "oci") + ":runtime"],
               cwd=runner.owned, phase=phase)
    index = json.loads((destination / "oci/index.json").read_bytes())
    require(len(index["manifests"]) == 1
            and index["manifests"][0]["digest"] == "sha256:" + IMAGES[version])
    blobs = destination / "oci/blobs/sha256"
    for path in blobs.iterdir():
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 128 * 1024**2)
        with path.open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == path.name)
    bounded(runner.owned)
    runner.run(["umoci", "unpack", "--rootless", "--image", str(destination / "oci") + ":runtime",
                str(destination / "bundle")], cwd=runner.owned, phase=phase)
    bounded(runner.owned)
    (destination / "verified.json").write_text(json.dumps({"digest": IMAGES[version]}))
    return destination / "bundle/rootfs"
