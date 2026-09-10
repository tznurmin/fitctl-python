# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Public source identity and safe extraction of the actually inspected sdist."""

import hashlib
from pathlib import Path
import tarfile

from .archive_contract import canonical, PRIVATE
from .distribution_contract import require


def snapshot(root, destination, runner, phase):
    text = runner.run(["git", "ls-files", "-z"], cwd=root, phase=phase)
    names = text.rstrip("\0").split("\0")
    require(0 < len(names) <= 4096 and len(names) == len(set(names)))
    expected, total = {}, 0
    for name in names:
        require(canonical(name) == name)
        source = root / name
        require(source.is_file() and not source.is_symlink() and source.stat().st_size <= 1024**2)
        data = source.read_bytes()
        total += len(data)
        require(total <= 8 * 1024**2 and PRIVATE.search(data) is None)
        mode = source.stat().st_mode & 0o777
        require(mode in (0o644, 0o755))
        expected[name] = (len(data), hashlib.sha256(data).hexdigest(), mode)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)
    return expected


def extract(archive, inventory, destination):
    destination.mkdir()
    expected = {name: (size, sha, mode) for name, size, sha, mode in inventory.members}
    total = 0
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            if member.isdir():
                continue
            require(member.name in expected and member.isfile())
            size, sha, mode = expected.pop(member.name)
            require(member.size == size and member.mode == mode and size <= 64 * 1024**2)
            data = stream.extractfile(member).read(size + 1)
            require(len(data) == size and hashlib.sha256(data).hexdigest() == sha)
            total += size
            require(total <= 128 * 1024**2)
            target = destination / Path(member.name).relative_to("fitctl-0.1.1")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data)
            target.chmod(mode)
    require(not expected)
