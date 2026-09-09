// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Evidence handles are counted without copying their native payloads.

use crate::argument_binding::Arguments;
use crate::conversion::{exact, string, unsigned};
use crate::error::{Failure, Result, BUDGET, TYPE};
use crate::values::{Artifact, Role};
use fitctl_core::validate::ValidationModeV1;
use pyo3::prelude::*;
use pyo3::types::{PyInt, PyList, PyString};

pub struct Validate {
    pub contract: Artifact,
    pub profile: Artifact,
    pub at: String,
    pub mode: ValidationModeV1,
    pub state: Option<Artifact>,
    pub thermal: Vec<Artifact>,
    pub age: Option<u64>,
    pub notes: Option<String>,
}

pub fn thermal(value: Option<&Bound<'_, PyAny>>) -> Result<Vec<Artifact>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    exact::<PyList>(value)?;
    let supplied = value.cast::<PyList>().map_err(|_| TYPE)?;
    if supplied.len() > 128 {
        return Err(BUDGET);
    }
    let mut thermal = Vec::new();
    crate::faults::reservation()?;
    thermal.try_reserve_exact(supplied.len()).map_err(|_| Failure::Memory)?;
    for item in supplied.iter() {
        thermal.push(Artifact::handle(&item, Role::Thermal)?);
    }
    Ok(thermal)
}

pub fn admit(bound: &Arguments<'_>) -> Result<Validate> {
    let contract = Artifact::handle(bound.required(0), Role::Contract)?;
    let profile = Artifact::handle(bound.required(1), Role::Profile)?;
    exact::<PyString>(bound.required(2))?;
    if let Some(mode) = bound.supplied(3) {
        exact::<PyString>(mode)?;
    }
    let state = bound.optional(4).map(|value| Artifact::handle(value, Role::State)).transpose()?;
    if let Some(thermal) = bound.optional(5) {
        exact::<PyList>(thermal)?;
    }
    if let Some(age) = bound.optional(6) {
        #[cfg(not(test))]
        let bool_fault = false;
        #[cfg(test)]
        let bool_fault = crate::assertion_mutants::active(crate::assertion_mutants::Fault::BoolAge)
            && age.is_exact_instance_of::<pyo3::types::PyBool>();
        if !bool_fault {
            exact::<PyInt>(age)?;
        }
    }
    if let Some(notes) = bound.optional(7) {
        exact::<PyString>(notes)?;
    }

    let at = string(bound.required(2), 64)?;
    let mode = bound.supplied(3).map(|value| string(value, 32)).transpose()?;
    let thermal = thermal(bound.optional(5))?;
    let age = bound.optional(6).map(unsigned).transpose()?;
    let notes = bound.optional(7).map(|value| string(value, 4096)).transpose()?;
    let mode = match mode.as_deref().unwrap_or("contract_only") {
        "contract_only" => ValidationModeV1::ContractOnly,
        "state_advisory" => ValidationModeV1::StateAdvisory,
        "state_required" => ValidationModeV1::StateRequired,
        _ => return Err(Failure::Value("unsupported validation mode")),
    };
    Ok(Validate { contract, profile, at, mode, state, thermal, age, notes })
}
