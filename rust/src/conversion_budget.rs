// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Admission counters only: no artifact schema or evidence semantics.

use crate::error::{Result, BUDGET};

pub const DOCUMENT_BYTES: usize = 16_777_216;
pub const CONFIG_BYTES: usize = 1_048_576;
pub const REQUEST_BYTES: usize = 8_388_608;
pub const NODES: usize = 100_000;
pub const DEPTH: usize = 64;

#[derive(Clone, Copy, Debug, Default)]
pub struct Counts {
    pub bytes: usize,
    pub nodes: usize,
}

pub fn add(current: usize, increment: usize, limit: usize) -> Result<usize> {
    current.checked_add(increment).filter(|&n| n <= limit).ok_or(BUDGET)
}

pub struct Budget {
    pub counts: Counts,
    pub byte_limit: usize,
    pub combined: Option<Counts>,
}

impl Budget {
    pub fn document(byte_limit: usize) -> Self {
        Self { counts: Counts::default(), byte_limit, combined: None }
    }

    pub fn configuration(combined: Counts) -> Self {
        Self { counts: Counts::default(), byte_limit: CONFIG_BYTES, combined: Some(combined) }
    }

    pub fn charge(&mut self, bytes: usize, nodes: usize, depth: usize) -> Result<()> {
        #[cfg(test)]
        crate::faults::budget_domain("individual");
        if depth > DEPTH {
            return Err(BUDGET);
        }
        let individual = Counts {
            bytes: add(self.counts.bytes, bytes, self.byte_limit)?,
            nodes: add(self.counts.nodes, nodes, NODES)?,
        };
        let combined = self
            .combined
            .map(|value| -> Result<Counts> {
                #[cfg(test)]
                if crate::assertion_mutants::active(crate::assertion_mutants::Fault::Combined) {
                    return Ok(value);
                }
                #[cfg(test)]
                crate::faults::budget_domain("combined");
                Ok(Counts {
                    bytes: add(value.bytes, bytes, REQUEST_BYTES)?,
                    nodes: add(value.nodes, nodes, NODES)?,
                })
            })
            .transpose()?;
        self.counts = individual;
        self.combined = combined;
        Ok(())
    }
}
