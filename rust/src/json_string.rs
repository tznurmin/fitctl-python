// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Bounded JSON string decoding without normalization or replacement characters.

use crate::conversion_budget::Budget;
use crate::error::{Failure, Result};

const SYNTAX: Failure = Failure::Decode("invalid_json");
const UNICODE: Failure = Failure::Decode("invalid_json_unicode");

fn hex(input: &str, index: &mut usize) -> Result<u32> {
    let end = index.checked_add(4).ok_or(SYNTAX)?;
    let digits = input.as_bytes().get(*index..end).ok_or(SYNTAX)?;
    let mut scalar = 0;
    for &digit in digits {
        scalar = scalar * 16
            + match digit {
                b'0'..=b'9' => u32::from(digit - b'0'),
                b'a'..=b'f' => u32::from(digit - b'a' + 10),
                b'A'..=b'F' => u32::from(digit - b'A' + 10),
                _ => return Err(SYNTAX),
            };
    }
    *index = end;
    Ok(scalar)
}

fn escape(input: &str, index: &mut usize) -> Result<char> {
    let byte = *input.as_bytes().get(*index).ok_or(SYNTAX)?;
    *index += 1;
    match byte {
        b'"' => Ok('"'),
        b'\\' => Ok('\\'),
        b'/' => Ok('/'),
        b'b' => Ok('\u{8}'),
        b'f' => Ok('\u{c}'),
        b'n' => Ok('\n'),
        b'r' => Ok('\r'),
        b't' => Ok('\t'),
        b'u' => {
            let mut scalar = hex(input, index)?;
            if (0xd800..=0xdbff).contains(&scalar) {
                if input.as_bytes().get(*index..*index + 2) != Some(b"\\u") {
                    return Err(UNICODE);
                }
                *index += 2;
                let low = hex(input, index)?;
                if !(0xdc00..=0xdfff).contains(&low) {
                    return Err(UNICODE);
                }
                scalar = 0x10000 + ((scalar - 0xd800) << 10) + low - 0xdc00;
            }
            char::from_u32(scalar).ok_or(UNICODE)
        }
        _ => Err(SYNTAX),
    }
}

pub fn decode(input: &str, index: &mut usize, budget: &mut Budget, depth: usize) -> Result<String> {
    if input.as_bytes().get(*index) != Some(&b'"') {
        return Err(SYNTAX);
    }
    budget.charge(0, 1, depth)?;
    *index += 1;
    let mut output = String::new();
    loop {
        let scalar = input.get(*index..).and_then(|text| text.chars().next()).ok_or(SYNTAX)?;
        *index += scalar.len_utf8();
        if scalar == '"' {
            return Ok(output);
        }
        let scalar = if scalar == '\\' {
            escape(input, index)?
        } else {
            if scalar < '\u{20}' {
                return Err(SYNTAX);
            }
            scalar
        };
        budget.charge(scalar.len_utf8(), 0, depth)?;
        crate::faults::reservation()?;
        output.try_reserve(scalar.len_utf8()).map_err(|_| Failure::Memory)?;
        output.push(scalar);
    }
}
