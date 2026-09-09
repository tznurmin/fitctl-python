// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Bounded fixture reference using core directly, independent of the binding.

#[path = "reference/numbers.rs"]
mod numbers;
#[path = "reference/output.rs"]
mod output;
#[path = "reference/requests.rs"]
mod requests;

use serde_json::{json, Map, Value};
use std::io::{BufRead, BufReader, Read};

fn main() -> std::result::Result<(), Box<dyn std::error::Error>> {
    let arguments = std::env::args().skip(1).collect::<Vec<_>>();
    assert_eq!(arguments.len(), 2);
    let mut fixture_bytes = Vec::new();
    std::fs::File::open(&arguments[0])?
        .take(1_048_577)
        .read_to_end(&mut fixture_bytes)?;
    assert!(fixture_bytes.len() <= 1_048_576);
    let data: Value = serde_json::from_slice(&fixture_bytes)?;
    let mut input = BufReader::new(std::fs::File::open(&arguments[1])?);
    let mut observations = Map::new();
    let mut number_basis = None;
    let mut total = 0_usize;
    loop {
        let mut line = String::new();
        let size = input.by_ref().take(16_777_217).read_line(&mut line)?;
        if size == 0 {
            break;
        }
        total = total.checked_add(size).expect("fixture byte counter");
        assert!(size <= 16_777_216 && total <= 134_217_728 && line.ends_with('\n'));
        assert!(observations.len() < 4096);
        let case: Value = serde_json::from_str(&line)?;
        let kwargs = &case["kwargs"];
        let observed = match case["operation"].as_str().unwrap() {
            "numeric_json" => {
                if number_basis.is_none() {
                    assert_eq!(case["name"], "number/-0");
                }
                output::outcome(numbers::observe(
                    kwargs["text"].as_str().unwrap(),
                    &mut number_basis,
                ))
            }
            "derive" => output::outcome(requests::derive(&data["fixtures"], kwargs)),
            "validate" => output::outcome(requests::validate(&data["fixtures"], kwargs)),
            "redact" => output::outcome(requests::redact(&data["fixtures"], kwargs)),
            "builtin" => match requests::asset(
                kwargs["category"].as_str().unwrap(),
                kwargs["config_id"].as_str().unwrap(),
            ) {
                Some(value) => json!({"value": value}),
                None => json!({"selection": false}),
            },
            _ => panic!("unknown reference operation"),
        };
        assert!(observations
            .insert(case["name"].as_str().unwrap().into(), observed)
            .is_none());
    }
    println!("{}", serde_json::to_string(&observations)?);
    Ok(())
}
