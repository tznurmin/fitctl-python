# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Finite direct-executable fixture; never a fallback implementation."""

import os
import sys
import time

GOOD = b'{"fixture":{"Core 0":{"temp1_input":55.0}}}\n'

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode in ("sleep2", "delay0.2"):
        time.sleep(2 if mode == "sleep2" else 0.2)
        mode = "good"
    if mode == "exit7":
        raise SystemExit(7)
    data = {"good": GOOD, "empty": b"{}\n", "malformed": b"{invalid\n",
            "oversized": b"x" * 1048577}[mode]
    while data:
        data = data[os.write(1, data):]
