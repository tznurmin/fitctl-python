# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Installed native identity, typing and immutable threaded use."""

import concurrent.futures
import gc
import inspect
from pathlib import Path
import unittest

import installed_support
from support import AT, DATA, api, artifact, asset, invoke


class InstalledInterfaceTests(unittest.TestCase):
    def test_isolated_installed_workflow(self):
        self.assertEqual(installed_support.inspect_installation(api()), installed_support.IDENTITY)
        survey = artifact("survey")
        policy = invoke(api().Policy.from_dict, asset("policy"))
        contract = invoke(api().derive_contract, survey, policy, at=AT)
        report = invoke(api().validate, contract, artifact("profile"), at=AT)
        self.assertEqual(invoke(report.to_dict), DATA["fixtures"]["report"])

    def test_wheel_from_sdist(self):
        inputs = installed_support.EXPECTED
        self.assertIn(inputs["variant"], ("direct", "sdist"))
        self.assertTrue(inputs["source_members_verified"])
        self.assertEqual(len(inputs["wheel_sha256"]), 64)
        for function in (api().Artifact.from_dict, api().Policy.from_json, api().validate, api().derive_contract):
            self.assertNotIn("**kwargs", str(inspect.signature(function)))
        stub = (Path(api().__file__).parent / "__init__.pyi").read_text()
        for name in ("Artifact", "Policy", "CoreError", "DecodeError", "SerializationError", "NativeError"):
            self.assertIn("class " + name, stub)

    def test_import_and_operation_effects(self):
        installed_support.inspect_isolation()
        value = artifact("state-scalars")
        for _ in range(3):
            self.assertEqual(invoke(value.to_dict), DATA["fixtures"]["state-scalars"])
            self.assertTrue(invoke(value.semantic_bytes))
        # The external observer must separately accept every traced syscall.

    def test_native_ownership_and_thread_progress(self):
        contract, profile = artifact("contract"), artifact("profile")
        expected = DATA["fixtures"]["report"]
        def worker(value, requirement):
            retained = (value, requirement)
            del value, requirement
            gc.collect()
            outputs = []
            for _ in range(5):
                report = invoke(api().validate, *retained, at=AT)
                exported = invoke(report.to_dict)
                exported.clear()
                outputs.append(invoke(report.to_dict))
            return outputs
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, contract, profile) for _ in range(2)]
            del contract, profile
            for future in futures:
                self.assertEqual(future.result(timeout=5), [expected] * 5)
