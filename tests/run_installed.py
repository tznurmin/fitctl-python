# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Run explicit public unittest selectors from an isolated installed environment."""

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import installed_support
import support


class Results(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observed = []

    def stopTest(self, test):
        outcome = "passed"
        for name, values in (("failed", self.failures), ("error", self.errors), ("skipped", self.skipped),
                             ("expected_failure", self.expectedFailures)):
            if any(case is test or getattr(case, "test_case", None) is test for case, _ in values):
                outcome = name
        if test in self.unexpectedSuccesses:
            outcome = "unexpected_success"
        self.observed.append({"id": test.id(), "outcome": outcome})
        super().stopTest(test)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", required=True)
    parser.add_argument("--receipt-fd", type=int, choices=[3], required=True)
    args = parser.parse_args()
    installed_support.EXPECTED = json.loads((Path(__file__).parent / "qualification-input.json").read_bytes())
    expected = installed_support.EXPECTED["tests"]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(expected if args.select == "all" else [args.select])
    selected = [test.id() for test in flatten(suite)]
    if loader.errors or sorted(selected) != sorted(expected) or len(set(selected)) != len(selected) or not selected:
        raise AssertionError("installed test inventory invalid")
    installed_support.inspect_isolation()
    # Tests and fixtures are loaded before import and native call intervals.
    thread = threading.get_native_id()
    os.write(4, f"FITCTL_IMPORT_BEGIN {thread}\n".encode("ascii"))
    module = installed_support.runtime_import("fitctl")
    os.write(4, f"FITCTL_IMPORT_END {thread}\n".encode("ascii"))
    installed_support.IDENTITY = installed_support.inspect_installation(module)
    support.TRACE_FD = 4
    result = unittest.TextTestRunner(verbosity=2, resultclass=Results).run(suite)
    support.TRACE_FD = None
    success = (result.wasSuccessful() and not result.skipped and not result.expectedFailures
               and all(item["outcome"] == "passed" for item in result.observed)
               and sorted(item["id"] for item in result.observed) == sorted(expected))
    receipt = {"schema_id": "fitctl.installed-tests.v1", "schema_version": 1,
               "outcome": "passed" if success else "failed", "tests": result.observed,
               "identity": installed_support.IDENTITY}
    data = (json.dumps(receipt, sort_keys=True) + "\n").encode()
    if len(data) > 1024 ** 2:
        raise AssertionError("test receipt too large")
    while data:
        data = data[os.write(args.receipt_fd, data):]
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
