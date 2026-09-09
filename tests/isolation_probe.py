# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Cheap installed-harness preflight; this never imports or qualifies a binding."""

import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).parent))
import installed_support
import collection_probe

if sys.argv[1:] != ["--select", "isolation-probe", "--receipt-fd", "3"]:
    raise SystemExit(2)
installed_support.EXPECTED = json.loads((Path(__file__).parent / "qualification-input.json").read_bytes())
installed_support.inspect_isolation()
thread = threading.get_native_id()
for marker in ("IMPORT_BEGIN", "IMPORT_END", "BEGIN", "END"):
    os.write(4, f"FITCTL_{marker} {thread}\n".encode("ascii"))
    if marker == "IMPORT_BEGIN":
        installed_support.runtime_import("_csv")
        installed_support.runtime_import("colorsys")


def thread_probe():
    tid = threading.get_native_id()
    os.write(4, f"FITCTL_BEGIN {tid}\n".encode("ascii"))
    sum(range(10))
    os.write(4, f"FITCTL_END {tid}\n".encode("ascii"))


for _ in range(2):
    workers = [threading.Thread(target=thread_probe) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(2)
        assert not worker.is_alive()
collection_probe.run()
os.write(3, b'{"probe":"isolation","outcome":"passed"}\n')
