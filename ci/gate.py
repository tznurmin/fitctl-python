# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed public CI operation with a private mount and bounded process lifetime."""

import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile

from native_process import run_bounded
from native_policy import NativeFailure

GIB = 1024**3


def capacity(*, launch=False):
    values = {line.split()[0].rstrip(":"): int(line.split()[1]) * 1024
              for line in Path("/proc/meminfo").read_text().splitlines() if len(line.split()) == 3}
    if (platform.system() != "Linux" or platform.machine() != "x86_64"
            or values["MemTotal"] < 8 * GIB
            or values["MemAvailable"] < (8 if launch else 6) * GIB):
        raise NativeFailure("resource_limit", "unsupported CI capacity")
    if shutil.disk_usage(Path(__file__).resolve()).free < 20 * GIB:
        raise NativeFailure("resource_limit", "insufficient CI disk headroom")


def main():
    if sys.argv[1:] or os.environ.get("GITHUB_ACTIONS") != "true":
        raise NativeFailure("usage_invalid", "the reviewed CI entry is required")
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root or (root / "release-artifacts").exists():
        raise NativeFailure("usage_invalid", "clean public source root required")
    capacity(launch=True)
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    if not parent.is_dir() or parent.is_symlink():
        raise NativeFailure("usage_invalid", "CI temporary root required")
    def interrupted(signum, frame):
        raise NativeFailure("interrupted", "CI interrupted")
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    owned = Path(tempfile.mkdtemp(prefix="fitctl-distribution-", dir=parent))
    identity = owned.stat()
    try:
        result = run_bounded(["unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork",
                              "--kill-child=SIGKILL", "--mount-proc", "bash", str(root / "ci/namespace.sh"),
                              str(root), str(owned), sys.executable],
                             cwd=root, env=os.environ.copy(), timeout=1200, watch=capacity, output_limit=1024**2)
        print(result.output, end="", flush=True)
        if result.returncode or result.truncated:
            raise NativeFailure("qualification_failed", "CI qualification did not complete")
    finally:
        current = owned.lstat()
        if owned.is_symlink() or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise NativeFailure("cleanup_failed", "CI owned mount did not exit")
        owned.rmdir()
        if owned.exists():
            raise NativeFailure("cleanup_failed", "CI owned child remains")
        print(json.dumps({"cleanup": "verified_removed"}), flush=True)
        capacity()


if __name__ == "__main__":
    main()
