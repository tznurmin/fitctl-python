# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""CI adapter for the same bounded command and runtime consumers."""

import os
from pathlib import Path
import shutil
import time

from .gate import capacity
from .native_process import run_bounded
from .distribution_contract import require
from .portable_images import bounded


class Phase:
    def __init__(self, deadline):
        self.deadline = deadline

    def seconds(self):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0)
        return remaining


class Runner:
    def __init__(self, root, owned, env):
        self.root, self.owned, self.env = root, owned, env
        self.commands = []
        self.deadline = time.monotonic() + 1140

    def phase(self, seconds):
        return Phase(min(self.deadline, time.monotonic() + seconds))

    def watch(self):
        capacity()
        require(shutil.disk_usage(self.owned).free >= 32 * 1024**2)
        bounded(self.owned)

    def run(self, argv, *, cwd, phase, limit=65536):
        executable = shutil.which(argv[0], path=self.env["PATH"])
        require(executable is not None)
        result = run_bounded(argv, cwd=cwd, env=self.env, timeout=phase.seconds(),
                             output_limit=limit, watch=self.watch)
        self.commands.append({"argv": argv, "executable": executable, "exit_code": result.returncode})
        if result.output:
            print(result.output, end="", flush=True)
        require(result.returncode == 0 and not result.truncated)
        return result.output
