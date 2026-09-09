// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Observe literal JSON with core's serde decoder and validated artifact loader.

use super::output::Result;
use fitctl_core::artifacts::record_v1::load_artifact_record_from_value;
use serde_json::{json, Value};

pub struct Basis {
    bytes: Vec<u8>,
    json: Value,
}

pub fn observe(text: &str, basis: &mut Option<Basis>) -> Result<Value> {
    let raw: Value = serde_json::from_str(text).expect("selected admitted numeric literal");
    let record = load_artifact_record_from_value(raw)?;
    let exported = record.full_artifact_json()?;
    let number = exported["state"]["extension_state"]["example.adaptation"]["number"]
        .as_number()
        .expect("selected number slot");
    let (kind, bits, negative, decimal) = if number.is_f64() {
        let float = number.as_f64().unwrap();
        (
            "float",
            Some(format!("{:016x}", float.to_bits())),
            Some(float.is_sign_negative()),
            None,
        )
    } else {
        ("int", None, None, Some(number.to_string()))
    };
    let bytes = record.semantic_bytes()?;
    // Compact fixture transport only: the common core bytes are stored once.
    // This never computes or substitutes the core's semantic representation.
    let hex = |data: &[u8]| {
        data.iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    };
    let (encoded, json_field, json_value) = if let Some(base) = basis {
        // All non-number export fields must actually match before deduplicating.
        let mut normalized = exported.clone();
        normalized["state"]["extension_state"]["example.adaptation"]["number"] =
            base.json["state"]["extension_state"]["example.adaptation"]["number"].clone();
        assert_eq!(
            normalized, base.json,
            "numeric fixture export changed outside its number"
        );
        let prefix = bytes
            .iter()
            .zip(base.bytes.iter())
            .take_while(|(a, b)| a == b)
            .count();
        (
            json!({"prefix_bytes": prefix, "tail_hex": hex(&bytes[prefix..])}),
            "json_number",
            Value::Number(number.clone()),
        )
    } else {
        *basis = Some(Basis {
            bytes: bytes.clone(),
            json: exported.clone(),
        });
        (json!(hex(&bytes)), "json", exported)
    };
    let mut result = json!({"number_kind": kind,
        "number_bits": bits, "negative": negative, "number_decimal": decimal,
        "semantic_bytes_hex": encoded, "semantic_hash": record.semantic_hash_hex()?});
    result[json_field] = json_value;
    Ok(result)
}
