# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify the declared build view before executing the one selected backend."""

import json
import os
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise AssertionError("build probe input required")
    data = json.loads(Path(sys.argv[1]).read_bytes())
    if set(data) != {"command", "required", "forbidden", "cwd", "target"}:
        raise AssertionError("build probe shape invalid")
    for name in data["required"]:
        if not Path(name).is_file():
            raise AssertionError("declared build input missing")
    for name in data["forbidden"]:
        try:
            Path(name).stat()
        except FileNotFoundError:
            continue
        raise AssertionError("original or undeclared source visible")
    target = Path(data["target"])
    if os.environ.get("CARGO_TARGET_DIR") != str(target) or not target.is_dir() or any(target.iterdir()):
        raise AssertionError("sdist target must start empty")
    os.chdir(data["cwd"])
    print("BUILD_SOURCE_ISOLATION=verified", flush=True)
    os.execv(data["command"][0], data["command"])


if __name__ == "__main__":
    main()
