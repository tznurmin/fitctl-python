# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable values compared with independent, supplied-input core observations."""

import copy
import json
import unittest

from support import AT, DATA, FAMILIES, PROFILES, api, artifact, asset, fixture, invoke, outcome


class ArtifactValueTests(unittest.TestCase):
    def setUp(self):
        self.api = api()

    def test_advertised_schema_operation_matrix(self):
        for family in FAMILIES:
            expected = DATA["observations"][f"artifact/{family}"]["value"]
            for loader, raw in ((self.api.Artifact.from_dict, fixture(family)),
                                (self.api.Artifact.from_json, json.dumps(fixture(family)))):
                with self.subTest(family=family, loader=loader.__name__):
                    value = invoke(loader, raw)
                    self.assertEqual(invoke(value.to_dict), expected["json"])
                    self.assertEqual(json.loads(invoke(value.to_json)), expected["json"])
                    self.assertEqual(invoke(value.semantic_hash), expected["semantic_hash"])
                    self.assertEqual(invoke(value.semantic_bytes), bytes.fromhex(expected["semantic_bytes_hex"]))
                    for field in ("schema_id", "schema_version", "artifact_id"):
                        self.assertEqual(invoke(getattr, value, field), expected["json"]["envelope"][field])
                    loaded = invoke(self.api.Artifact.from_dict, invoke(value.to_dict))
                    self.assertEqual(invoke(loaded.to_dict), expected["json"])
            raw = fixture(family)
            raw["envelope"]["provenance"]["correlation_id"] = "synthetic-operation-two"
            for encoded in (False, True):
                value = invoke(self.api.Artifact.from_json, json.dumps(raw)) if encoded else invoke(self.api.Artifact.from_dict, raw)
                self.assertEqual(invoke(value.to_dict), DATA["observations"][f"artifact/{family}/operational"]["value"])
                self.assertEqual(invoke(value.semantic_hash), expected["semantic_hash"])

    def test_mutation_independence(self):
        for cls, supplied in ((self.api.Artifact, fixture("survey")),
                              (self.api.Policy, asset("policy"))):
            source = copy.deepcopy(supplied)
            value = invoke(cls.from_dict, source)
            first, second = invoke(value.to_dict), invoke(value.to_dict)
            source.clear()
            first.clear()
            self.assertEqual(invoke(value.to_dict), second)
            self.assertEqual(invoke(invoke(cls.from_dict, second).to_dict), second)
            self.assertIsNot(first, second)
        raw = asset("policy")
        del raw["display_name"]
        value = invoke(self.api.Policy.from_dict, raw)
        self.assertEqual(invoke(value.to_dict), raw)
        self.assertEqual(json.loads(invoke(value.to_json)), raw)
        self.assertEqual(invoke(invoke(self.api.Policy.from_json, invoke(value.to_json)).to_dict), raw)

    def test_immutable_construction(self):
        for cls in (self.api.Artifact, self.api.Policy):
            with self.assertRaises(TypeError) as caught:
                invoke(cls)
            self.assertEqual(caught.exception.args, ("native value requires a loader",))
        for value in (artifact("survey"), invoke(self.api.Policy.from_dict, asset("policy"))):
            before = invoke(value.to_dict)
            for field in ("artifact_id", "schema_id", "schema_version", "verdict", "value"):
                for function, args in ((setattr, (value, field, None)), (delattr, (value, field))):
                    with self.assertRaises(AttributeError) as caught:
                        invoke(function, *args)
                    self.assertEqual(caught.exception.args, ("native value is immutable",))
                self.assertEqual(invoke(value.to_dict), before)

    def test_unknown_false_zero_preservation(self):
        for name in ("state-scalars", "state-unknown-cpu"):
            value = artifact(name)
            self.assertEqual(invoke(value.to_dict), fixture(name))
        raw = invoke(artifact("state-scalars").to_dict)["state"]["extension_state"]["example.adaptation"]
        self.assertIsNone(raw["null"])
        self.assertIs(raw["false"], False)
        self.assertEqual(raw["zero"], 0)
        self.assertIs(type(raw["zero"]), int)
        self.assertEqual(raw["minimum"], -(2 ** 63))
        self.assertEqual(raw["maximum"], 2 ** 64 - 1)
        self.assertEqual(raw["fraction"], 1.5)
        self.assertNotEqual(raw["é"], raw["e\u0301"])

    def test_semantic_identity_boundaries(self):
        for family in FAMILIES:
            original = artifact(family)
            raw = fixture(family)
            reordered = dict(reversed(list(raw.items())))
            reordered["envelope"]["provenance"]["correlation_id"] = "synthetic-operation-two"
            changed = invoke(self.api.Artifact.from_dict, reordered)
            self.assertEqual(invoke(original.semantic_hash), invoke(changed.semantic_hash))
        raw = fixture("state-scalars")
        original = invoke(self.api.Artifact.from_dict, raw)
        raw["state"]["extension_state"]["example.adaptation"]["zero"] = 1
        changed = invoke(self.api.Artifact.from_dict, raw)
        self.assertNotEqual(invoke(original.semantic_hash), invoke(changed.semantic_hash))

    def test_integrity_and_encoding_rejection(self):
        raw = fixture("contract")
        raw["contract"]["extension_contract"] = {"example.adaptation": {"zero": 0}}
        outcome(self, self.api.Artifact.from_dict,
                DATA["observations"]["artifact/contract/extension-without-basis"], raw)
        for family in FAMILIES:
            for encoding in ("fitctl.semantic_cbor.v1", "fitctl.semantic_cbor.v2"):
                raw = fixture(family)
                raw["envelope"]["signatures"] = [{"key_id": "synthetic", "signer_identity": "synthetic",
                    "public_key": "synthetic", "signature_format": "openssh_sshsig_v1",
                    "signature_namespace": "fitctl-artifact-v1", "payload_encoding": encoding,
                    "payload_semantic_hash": "invalid-integrity", "signed_at": AT, "signature": "synthetic"}]
                outcome(self, self.api.Artifact.from_dict,
                        DATA["observations"][f"artifact/{family}/signature/{encoding}"], raw)

    def test_redaction_profile_matrix(self):
        for family in FAMILIES:
            original = artifact(family)
            for profile in PROFILES:
                with self.subTest(family=family, profile=profile):
                    expected = DATA["observations"][f"redact/{family}/{profile}"]
                    value = outcome(self, original.redact, expected, profile, at=AT)
                    reloaded = invoke(self.api.Artifact.from_json, invoke(value.to_json))
                    self.assertEqual(invoke(reloaded.to_dict), expected["value"])
                    self.assertEqual(invoke(reloaded.semantic_hash), invoke(value.semantic_hash))
            self.assertEqual(invoke(original.to_dict), fixture(family))

    def test_redaction_rejections(self):
        for family in FAMILIES:
            original = artifact(family)
            for profile in PROFILES:
                redacted = invoke(original.redact, profile, at=AT)
                outcome(self, redacted.redact, DATA["observations"][f"redact/{family}/{profile}/repeat"], profile, at=AT)
            outcome(self, original.redact, DATA["observations"]["redact/unknown_profile"], "unknown", at=AT)

    def test_report_scalar_distinctions(self):
        for name in FAMILIES[:-1]:
            value = artifact(name)
            self.assertIsNone(invoke(getattr, value, "verdict"))
            self.assertIsNone(invoke(getattr, value, "primary_reason_code"))
        raw = DATA["observations"]["thermal/other-synthetic-host"]["value"]
        report = invoke(self.api.Artifact.from_dict, raw)
        self.assertEqual(invoke(getattr, report, "verdict"), "indeterminate")
        self.assertEqual(invoke(getattr, report, "primary_reason_code"), raw["report"]["primary_reason_code"])
