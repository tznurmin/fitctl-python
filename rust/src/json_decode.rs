// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Incremental JSON admission. Core alone validates decoded documents.

use crate::conversion_budget::{Budget, DOCUMENT_BYTES};
use crate::error::{Failure, Result, TYPE};
use serde_json::{Map, Number, Value};

const SYNTAX: Failure = Failure::Decode("invalid_json");
const NONFINITE: Failure = Failure::Decode("non_finite_json_number");

struct Decoder<'a> {
    input: &'a str,
    index: usize,
    budget: Budget,
}

pub fn document(input: &str) -> Result<Value> {
    if input.len() > DOCUMENT_BYTES {
        return Err(crate::error::BUDGET);
    }
    let mut decoder = Decoder {
        input,
        index: 0,
        budget: Budget::document(DOCUMENT_BYTES),
    };
    let value = decoder.value(0)?;
    decoder.whitespace();
    if decoder.index != input.len() {
        return Err(SYNTAX);
    }
    if !value.is_object() {
        return Err(TYPE);
    }
    Ok(value)
}

impl Decoder<'_> {
    fn peek(&self) -> Option<u8> {
        self.input.as_bytes().get(self.index).copied()
    }
    fn whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\r' | b'\n')) {
            self.index += 1;
        }
    }
    fn consume(&mut self, byte: u8) -> bool {
        if self.peek() == Some(byte) {
            self.index += 1;
            true
        } else {
            false
        }
    }
    fn string(&mut self, depth: usize) -> Result<String> {
        crate::json_string::decode(self.input, &mut self.index, &mut self.budget, depth)
    }
    fn literal(&mut self, literal: &str, value: Value, depth: usize) -> Result<Value> {
        if !self.input[self.index..].starts_with(literal) {
            return Err(SYNTAX);
        }
        self.budget.charge(literal.len(), 1, depth)?;
        self.index += literal.len();
        Ok(value)
    }
    fn value(&mut self, depth: usize) -> Result<Value> {
        self.whitespace();
        match self.peek() {
            Some(b'{') => self.object(depth + 1),
            Some(b'[') => self.array(depth + 1),
            Some(b'"') => Ok(Value::String(self.string(depth)?)),
            Some(b't') => self.literal("true", Value::Bool(true), depth),
            Some(b'f') => self.literal("false", Value::Bool(false), depth),
            Some(b'n') => self.literal("null", Value::Null, depth),
            Some(b'N' | b'I') => {
                if self.input[self.index..].starts_with("NaN")
                    || self.input[self.index..].starts_with("Infinity")
                {
                    Err(NONFINITE)
                } else {
                    Err(SYNTAX)
                }
            }
            Some(b'-' | b'0'..=b'9') => self.number(depth),
            _ => Err(SYNTAX),
        }
    }
    fn object(&mut self, depth: usize) -> Result<Value> {
        self.budget.charge(0, 1, depth)?;
        self.index += 1;
        self.whitespace();
        let mut map = Map::new();
        if self.consume(b'}') {
            return Ok(Value::Object(map));
        }
        loop {
            let key = self.string(depth)?;
            let duplicate = map.contains_key(&key);
            #[cfg(test)]
            let duplicate = duplicate
                && !crate::assertion_mutants::active(crate::assertion_mutants::Fault::Duplicate);
            if duplicate {
                return Err(Failure::Decode("duplicate_json_key"));
            }
            self.whitespace();
            if !self.consume(b':') {
                return Err(SYNTAX);
            }
            let value = self.value(depth)?;
            map.insert(key, value);
            self.whitespace();
            if self.consume(b'}') {
                return Ok(Value::Object(map));
            }
            if !self.consume(b',') {
                return Err(SYNTAX);
            }
            self.whitespace();
        }
    }
    fn array(&mut self, depth: usize) -> Result<Value> {
        self.budget.charge(0, 1, depth)?;
        self.index += 1;
        self.whitespace();
        let mut array = Vec::new();
        if self.consume(b']') {
            return Ok(Value::Array(array));
        }
        loop {
            let value = self.value(depth)?;
            crate::faults::reservation()?;
            array.try_reserve(1).map_err(|_| Failure::Memory)?;
            array.push(value);
            self.whitespace();
            if self.consume(b']') {
                return Ok(Value::Array(array));
            }
            if !self.consume(b',') {
                return Err(SYNTAX);
            }
        }
    }
    fn digits(&mut self) -> Result<()> {
        let start = self.index;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.index += 1;
        }
        if self.index == start {
            Err(SYNTAX)
        } else {
            Ok(())
        }
    }
    fn number(&mut self, depth: usize) -> Result<Value> {
        let start = self.index;
        self.consume(b'-');
        if self.input[self.index..].starts_with("Infinity") {
            return Err(NONFINITE);
        }
        if !self.consume(b'0') {
            self.digits()?;
        }
        let fraction = self.consume(b'.');
        if fraction {
            self.digits()?;
        }
        let exponent = self.consume(b'e') || self.consume(b'E');
        if exponent {
            if !self.consume(b'+') {
                self.consume(b'-');
            }
            self.digits()?;
        }
        let token = &self.input[start..self.index];
        if !fraction && !exponent {
            // Retain the adapter's exact integer limits before serde's fallback
            // to floating point for out-of-range integer spellings.
            if token.starts_with('-') {
                token.parse::<i64>().map_err(|_| Failure::Overflow)?;
            } else {
                token.parse::<u64>().map_err(|_| Failure::Overflow)?;
            }
        }
        // The lexer has admitted one complete number token. Use the pinned
        // core decoder for its representation, including -0 and float rounding.
        let number: Number = serde_json::from_str(token).map_err(|_| NONFINITE)?;
        #[cfg(test)]
        let number = if token == "-0"
            && crate::assertion_mutants::active(crate::assertion_mutants::Fault::Number)
        {
            Number::from(0)
        } else {
            number
        };
        self.budget.charge(
            if number.is_f64() {
                8
            } else {
                number.to_string().len()
            },
            1,
            depth,
        )?;
        Ok(Value::Number(number))
    }
}
