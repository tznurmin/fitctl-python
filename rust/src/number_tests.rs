// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Literal-input differential admission assertions against the pinned core.

use crate::error::Failure;
use fitctl_core::artifacts::record_v1::load_artifact_record_from_value;
use serde_json::{json, Value};

pub fn json_numbers() {
    let cases: Vec<(String, String)> =
        serde_json::from_str(include_str!("../../tests/fixtures/adaptation/numbers.json")).unwrap();
    let data: Value = serde_json::from_str(include_str!(
        "../../tests/fixtures/recorded/core-reference.json"
    ))
    .unwrap();
    let mut template = data["fixtures"]["state-scalars"].clone();
    template["state"]["extension_state"]["example.adaptation"] = json!({"number": "NUMBER_TOKEN"});
    let template = serde_json::to_string(&template).unwrap();
    for (token, kind) in &cases {
        let text = template.replace("\"NUMBER_TOKEN\"", token);
        let actual = crate::json_decode::document(&text);
        match kind.as_str() {
            "overflow" => assert!(matches!(actual, Err(Failure::Overflow)), "{token}"),
            "nonfinite" => assert!(
                matches!(actual, Err(Failure::Decode("non_finite_json_number"))),
                "{token}"
            ),
            "syntax" => {
                assert!(
                    matches!(actual, Err(Failure::Decode("invalid_json"))),
                    "{token}"
                )
            }
            _ => {
                let expected: Value = serde_json::from_str(&text).unwrap();
                let actual = actual.unwrap();
                let pointer = "/state/extension_state/example.adaptation/number";
                let number = actual.pointer(pointer).unwrap().as_number().unwrap();
                let reference = expected.pointer(pointer).unwrap().as_number().unwrap();
                assert_eq!(reference.is_f64(), kind == "float", "{token}");
                assert_eq!(number.is_f64(), reference.is_f64(), "type for {token}");
                if reference.is_f64() {
                    assert_eq!(
                        number.as_f64().unwrap().to_bits(),
                        reference.as_f64().unwrap().to_bits(),
                        "bits for {token}"
                    );
                } else {
                    assert_eq!(number, reference, "integer for {token}");
                }
                let expected = load_artifact_record_from_value(expected).unwrap();
                let actual = load_artifact_record_from_value(actual).unwrap();
                assert_eq!(
                    actual.full_artifact_json().unwrap(),
                    expected.full_artifact_json().unwrap()
                );
                assert_eq!(
                    actual.semantic_bytes().unwrap(),
                    expected.semantic_bytes().unwrap()
                );
                assert_eq!(
                    actual.semantic_hash_hex().unwrap(),
                    expected.semantic_hash_hex().unwrap()
                );
            }
        }
    }
    // Eight negative floating zeros cost 64 scalar bytes, not eight integer digits.
    let cap = crate::conversion_budget::DOCUMENT_BYTES;
    for scalar_bytes in [cap - 1, cap, cap + 1] {
        let text = format!(
            "{{\"n\":[-0,-0,-0,-0,-0,-0,-0,-0],\"p\":\"{}\"}}",
            "a".repeat(scalar_bytes - 66)
        );
        assert!(text.len() <= cap);
        let result = crate::json_decode::document(&text);
        if scalar_bytes > cap {
            assert!(matches!(
                result,
                Err(Failure::Value("argument budget exceeded"))
            ));
        } else {
            assert!(result.is_ok());
        }
    }
    println!("JSON_NUMBER_VECTORS={} scalar_boundaries=3", cases.len());
}
