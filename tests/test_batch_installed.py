# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Real native exports and immutable ownership on fresh caller threads."""

import concurrent.futures
import gc
import inspect
from pathlib import Path
import types
import unittest

import installed_support
from batch_support import DATA, arguments
from batch_inputs import requests
from support import api, invoke


class BatchInstalledTests(unittest.TestCase):
    def test_installed_workflow_and_threads(self):
        module = api()
        self.assertEqual(installed_support.inspect_installation(module), installed_support.IDENTITY)
        self.assertIsInstance(module.classify_batch, types.BuiltinFunctionType)
        self.assertIs(module.classify_batch, module._native.classify_batch)
        self.assertIs(module.BatchReport, module._native.BatchReport)
        for factory in (module.BatchReport.from_dict, module.BatchReport.from_json):
            self.assertIsInstance(factory, types.BuiltinFunctionType)
            self.assertIs(factory.__self__, module.BatchReport)
        self.assertNotIn("**kwargs", str(inspect.signature(module.classify_batch)))
        stub = (Path(module.__file__).parent / "__init__.pyi").read_text()
        self.assertIn("class BatchReport:", stub)
        self.assertIn("def classify_batch(", stub)
        supplied = arguments(requests()["matrix"])
        expected = DATA["observations"]["matrix"]["value"]
        def worker(values):
            retained = dict(values)
            del values
            gc.collect()
            result = invoke(module.classify_batch, **retained)
            exported = invoke(result.to_dict)
            exported.clear()
            return invoke(result.to_dict), invoke(result.export_csv, "rows_csv")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, supplied) for _ in range(2)]
            del supplied
            for future in futures:
                value, csv = future.result(timeout=5)
                self.assertEqual(value, expected)
                self.assertEqual(csv, DATA["csv"]["matrix"]["rows_csv"])
