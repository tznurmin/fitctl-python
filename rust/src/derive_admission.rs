// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! All Python request admission finishes before any configuration loader runs.

use crate::argument_binding::Arguments;
use crate::conversion::{document, exact, string};
use crate::conversion_budget::{add, Budget, Counts, REQUEST_BYTES};
use crate::error::{Failure, Result, BUDGET, TYPE};
use crate::values::{Artifact, Policy, Role};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use serde_json::Value;

pub struct Derive {
    pub survey: Artifact,
    pub policy: Policy,
    pub at: String,
    pub packs: Vec<Value>,
    pub context: Option<Value>,
    pub notes: Option<String>,
}

pub fn admit(bound: &Arguments<'_>) -> Result<Derive> {
    let survey = Artifact::handle(bound.required(0), Role::Survey)?;
    let policy = Policy::handle(bound.required(1))?;
    exact::<PyString>(bound.required(2))?;
    if let Some(packs) = bound.optional(3) {
        exact::<PyList>(packs)?;
    }
    if let Some(context) = bound.optional(4) {
        exact::<PyDict>(context)?;
    }
    if let Some(notes) = bound.optional(5) {
        exact::<PyString>(notes)?;
    }

    let at = string(bound.required(2), 64)?;
    let mut combined = Counts { bytes: at.len(), nodes: 0 };
    let mut packs = Vec::new();
    if let Some(supplied) = bound.optional(3) {
        let supplied = supplied.cast::<PyList>().map_err(|_| TYPE)?;
        if supplied.len() > 16 {
            return Err(BUDGET);
        }
        combined.nodes = 1;
        crate::faults::reservation()?;
        packs.try_reserve_exact(supplied.len()).map_err(|_| Failure::Memory)?;
        for pack in supplied.iter() {
            let mut budget = Budget::configuration(combined);
            let pack = document(&pack, &mut budget)?;
            combined = budget.combined.expect("combined configuration budget");
            packs.push(pack);
        }
    }
    let context = if let Some(supplied) = bound.optional(4) {
        let mut budget = Budget::configuration(combined);
        let context = document(supplied, &mut budget)?;
        combined = budget.combined.expect("combined configuration budget");
        Some(context)
    } else {
        None
    };
    let notes = if let Some(supplied) = bound.optional(5) {
        let bytes = crate::conversion::utf8_size(supplied, 4096)?;
        add(combined.bytes, bytes, REQUEST_BYTES)?;
        Some(crate::conversion::copy(crate::conversion::cached_utf8(supplied)?)?)
    } else {
        None
    };
    Ok(Derive { survey, policy, at, packs, context, notes })
}
