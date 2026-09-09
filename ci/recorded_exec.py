# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Set only the two consumer pipe descriptors before the fixed traced exec."""

import json
import fcntl
import os
from pathlib import Path
import sys
import shutil


def main():
    if len(sys.argv) != 4:
        raise SystemExit(2)
    path = Path(sys.argv[1])
    if path.is_symlink() or path.stat().st_size > 65536:
        raise SystemExit(2)
    command = json.loads(path.read_bytes())
    if type(command) is not list or not command or command[0] != shutil.which("strace"):
        raise SystemExit(2)
    # Keep both copies above the destination range. dup2(fd, fd) is a no-op
    # and does not clear the close-on-exec flag set by os.dup.
    copies = [fcntl.fcntl(int(value), fcntl.F_DUPFD_CLOEXEC, 5) for value in sys.argv[2:]]
    for destination, source in zip((3, 4), copies, strict=True):
        os.dup2(source, destination, inheritable=True)
    os.closerange(5, os.sysconf("SC_OPEN_MAX"))
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
