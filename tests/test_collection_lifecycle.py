# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Fresh-thread replay and synchronous native completion before interruption."""

import concurrent.futures
import os
import signal
import threading
import time
import unittest

from collection_provider_inputs import provider, write_config
from collection_support import DATA, collect, prepare, replay
from support import api, invoke


class CollectionLifecycleTests(unittest.TestCase):
    def test_fresh_thread_replay(self):
        prepare()
        ready = threading.Barrier(2)
        def worker(name):
            ready.wait(timeout=3)
            return threading.get_native_id(), invoke(replay(name).to_dict)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            selected = ("survey/complete", "state/complete")
            results = [(name, pool.submit(worker, name)) for name in selected]
            threads = set()
            for name, result in results:
                thread, value = result.result(timeout=5)
                threads.add(thread)
                self.assertEqual(value, DATA["observations"][name]["value"])
            self.assertEqual(len(threads), 2)

    def test_interrupt_waits_for_native_and_timeout_is_core(self):
        prepare()
        config = write_config([provider("delay0.2")])
        entered = threading.Event()
        original = signal.getsignal(signal.SIGINT)
        completed = []
        def interrupt():
            entered.wait(2)
            # Exercise a real native call on the sender too, with its own marker.
            invoke(api().builtin_config, "policy", "general_compute_default.v1.json")
            time.sleep(0.04)
            completed.append("python-progress")
            os.kill(os.getpid(), signal.SIGINT)
        worker = threading.Thread(target=interrupt)
        worker.start()
        start = time.monotonic()
        try:
            entered.set()
            with self.assertRaises(KeyboardInterrupt):
                collect("PROVIDER", api().collect_state, thermal_provider_config_paths=[config])
        finally:
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(completed, ["python-progress"])
        self.assertGreaterEqual(time.monotonic() - start, 0.15)
        self.assertIs(signal.getsignal(signal.SIGINT), original)
        self.assertEqual(invoke(replay("state/complete").to_dict), DATA["observations"]["state/complete"]["value"])
        config = write_config([provider("sleep2")])
        start = time.monotonic()
        raw = invoke(collect("PROVIDER", api().collect_state, thermal_provider_config_paths=[config]).to_dict)
        self.assertGreaterEqual(time.monotonic() - start, 0.9)
        row = raw["state"]["core_state"]["thermal_resources"]["providers"][0]
        self.assertEqual((row["outcome"], row["error_code"]), ("command_failed", "thermal_provider_command_timeout"))
