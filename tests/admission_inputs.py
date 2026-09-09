# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Write bounded, core-eligible reference inputs from the authoritative recipes."""

import hashlib
import json
from itertools import chain
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from admission_vectors import Sentinel, cases, reference_input
from number_cases import reference_cases


def write_inputs(destination):
    names, selected, used = set(), [], 0
    digest = hashlib.sha256()
    # Leave 2 MiB for the selected core input and the bounded reference result.
    limit = 126 * 1024 ** 2
    with destination.open("xb") as stream:
        for case in chain(cases(), reference_cases()):
            if case.name in names or len(names) >= 4096:
                raise AssertionError("admission input inventory invalid")
            names.add(case.name)
            if not case.reference:
                continue
            selected.append(case.name)
            size = 0
            chunks = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(reference_input(case))
            for chunk in chunks:
                data = chunk.encode("utf-8")
                size += len(data); used += len(data)
                if size > 16_777_215 or used >= limit:
                    raise AssertionError("admission fixture budget exceeded")
                stream.write(data); digest.update(data)
            stream.write(b"\n"); digest.update(b"\n"); used += 1
    assert Sentinel.calls == 0 and selected
    return {"cases": len(names), "references": selected, "input_bytes": used, "input_sha256": digest.hexdigest()}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("one output path is required")
    print(json.dumps(write_inputs(Path(sys.argv[1])), sort_keys=True))
