# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit read-only versus temporary-write core path probes."""

from pathlib import Path
import unittest

from collection_support import collect
from support import api, invoke

ROOT = Path("/work/paths")


def path_inputs(names, *, links=False, health=False):
    return [{"path_id": name, "path": str(ROOT / name), "probe_links": links, "probe_health": health}
            for name in names]


def resources(checks, pairs=None, *, scope="STATE", full=False):
    value = collect(scope, api().collect_state, path_checks=checks, link_pairs=pairs)
    raw = invoke(value.to_dict)
    return raw if full else raw["state"]["core_state"]["path_resources"]


class ProbeEffectTests(unittest.TestCase):
    def setUp(self):
        ROOT.mkdir(exist_ok=True)
        for name in ("a", "b", "denied"):
            (ROOT / name).mkdir(exist_ok=True)
        (ROOT / "file").write_text("unchanged input\n")
        (ROOT / "denied").chmod(0)

    def tearDown(self):
        (ROOT / "denied").chmod(0o700)
        self.assertEqual(list(ROOT.glob("*/.fitctl-*")), [])
        self.assertEqual((ROOT / "file").read_text(), "unchanged input\n")

    def test_read_only_checks_do_not_write(self):
        result = resources(path_inputs(("a", "missing")))
        self.assertEqual([row["path_id"] for row in result["paths"]], ["a", "missing"])
        self.assertEqual(result["link_pairs"], [])
        for row in result["paths"]:
            self.assertEqual(row["path"], str(ROOT / row["path_id"]))
            self.assertEqual(row["exists"], {"state": "observed", "value": row["path_id"] == "a"})
            self.assertNotIn("link_capabilities", row)
            self.assertNotIn("storage_health", row)
        first, missing = result["paths"]
        self.assertGreater(first["filesystem_total_bytes"]["value"], 0)
        self.assertEqual(missing["filesystem_total_bytes"], {"state": "unknown", "value": None})
        self.assertEqual(list((ROOT / "a").iterdir()), [])

    def test_opt_in_links_and_failure_cleanup(self):
        checks = path_inputs(("a", "b", "missing", "file", "denied"), links=True, health=True)
        pairs = [{"from_path_id": "a", "to_path_id": name} for name in ("b", "denied")]
        raw = resources(checks, pairs, scope="PATH", full=True)
        # Restore test-owned access after the observed call, before inspecting
        # absence beneath the denied parent. This does not remove probe output.
        (ROOT / "denied").chmod(0o700)
        result = raw["state"]["core_state"]["path_resources"]
        for row in result["paths"]:
            link = row["link_capabilities"]
            good = row["path_id"] in ("a", "b")
            for name in ("hardlink_supported", "symlink_supported", "copy_possible"):
                self.assertEqual(link[name], {"state": "observed", "value": good})
            self.assertEqual(link["reflink_supported"]["state"], "observed")
            self.assertIs(type(link["reflink_supported"]["value"]), bool)
            self.assertEqual(link["probe_method"], "temporary-files-under-checked-path")
            self.assertEqual(bool(link.get("probe_error")), not good)
            expected = [] if row["path_id"] in ("missing", "file") else ["removed" if good else "not_created"]
            self.assertEqual([entry["outcome"] for entry in link["cleanup"]], expected)
            for entry in link["cleanup"]:
                self.assertEqual(set(entry), {"probe_root", "outcome"})
                self.assertEqual(entry["probe_root"], link["probe_root"])
                self.assertEqual(Path(entry["probe_root"]).parent, ROOT / row["path_id"])
                self.assertFalse(Path(entry["probe_root"]).exists())
            self.assertEqual(row["storage_health"]["health_state"]["state"], "unknown")
        self.assertEqual([row["pair_id"] for row in result["link_pairs"]], ["a-to-b", "a-to-denied"])
        for pair in result["link_pairs"]:
            good = pair["to_path_id"] == "b"
            self.assertEqual(pair["from_path_id"], "a")
            self.assertEqual(pair["probe_method"], "temporary-files-under-checked-path-pair")
            for name in ("hardlink_supported", "symlink_supported", "copy_possible"):
                self.assertEqual(pair[name], {"state": "observed", "value": good})
            self.assertEqual(bool(pair.get("probe_error")), not good)
            self.assertEqual([entry["outcome"] for entry in pair["cleanup"]],
                             ["removed", "removed" if good else "not_created"])
            for entry, path_id in zip(pair["cleanup"], ("a", pair["to_path_id"]), strict=True):
                self.assertEqual(set(entry), {"probe_root", "outcome"})
                self.assertEqual(Path(entry["probe_root"]).parent, ROOT / path_id)
                self.assertFalse(Path(entry["probe_root"]).exists())
        self.assertEqual(list((ROOT / "a").iterdir()), [])
        self.assertEqual(list((ROOT / "b").iterdir()), [])
        from collection_cleanup import check
        check(self, raw)
