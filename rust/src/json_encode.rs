// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Presentation JSON with explicitly recoverable adapter buffer reservations.

use crate::error::{Failure, Result};
use std::io::{self, Write};

#[derive(Default)]
struct Buffer {
    bytes: Vec<u8>,
    allocation_failed: bool,
}

impl Write for Buffer {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if crate::faults::reservation().is_err() || self.bytes.try_reserve(bytes.len()).is_err() {
            self.allocation_failed = true;
            return Err(io::ErrorKind::OutOfMemory.into());
        }
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

pub fn encode(value: &impl serde::Serialize) -> Result<String> {
    let mut output = Buffer::default();
    if serde_json::to_writer(&mut output, value).is_err() {
        return Err(if output.allocation_failed { Failure::Memory } else { Failure::JsonEncode });
    }
    String::from_utf8(output.bytes).map_err(|_| Failure::JsonEncode)
}
