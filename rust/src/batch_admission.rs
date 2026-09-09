// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Bounded handle admission before native payload copies or batch execution.

use crate::argument_binding::Arguments;
use crate::conversion::{exact, string, unsigned};
use crate::error::{Failure, Result, BUDGET, TYPE};
use crate::values::{Artifact, Role};
use fitctl_core::validate::ValidationModeV1;
use pyo3::prelude::*;
use pyo3::types::{PyInt, PyList, PyString};

pub struct BatchInput {
    pub contracts: Vec<Artifact>,
    pub profiles: Vec<Artifact>,
    pub states: Vec<Artifact>,
    pub at: String,
    pub mode: ValidationModeV1,
    pub age: Option<u64>,
}

fn handles(value: Option<&Bound<'_, PyAny>>, role: Role) -> Result<Vec<Artifact>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let items = value.cast::<PyList>().map_err(|_| TYPE)?;
    let mut owned = Vec::new();
    crate::faults::reservation()?;
    owned
        .try_reserve_exact(items.len())
        .map_err(|_| Failure::Memory)?;
    for item in items.iter() {
        owned.push(Artifact::handle(&item, role)?);
    }
    Ok(owned)
}

pub fn admit(bound: &Arguments<'_>) -> Result<BatchInput> {
    exact::<PyList>(bound.required(0))?;
    exact::<PyList>(bound.required(1))?;
    exact::<PyString>(bound.required(2))?;
    if let Some(mode) = bound.supplied(3) {
        exact::<PyString>(mode)?;
    }
    if let Some(states) = bound.optional(4) {
        exact::<PyList>(states)?;
    }
    if let Some(age) = bound.optional(5) {
        exact::<PyInt>(age)?;
    }

    let count = |value: &Bound<'_, PyAny>| -> Result<usize> {
        Ok(value.cast::<PyList>().map_err(|_| TYPE)?.len())
    };
    let contracts = count(bound.required(0))?;
    let profiles = count(bound.required(1))?;
    let states = bound.optional(4).map(count).transpose()?.unwrap_or(0);
    #[cfg(not(test))]
    let bypass_count = false;
    #[cfg(test)]
    let bypass_count =
        crate::assertion_mutants::active(crate::assertion_mutants::Fault::BatchCount);
    if (!bypass_count
        && [contracts, profiles, states]
            .into_iter()
            .any(|count| count > 16))
        || contracts
            .checked_mul(profiles)
            .is_none_or(|pairs| pairs > 64)
    {
        return Err(BUDGET);
    }
    let at = string(bound.required(2), 64)?;
    let mode = bound
        .supplied(3)
        .map(|value| string(value, 32))
        .transpose()?;
    let age = bound.optional(5).map(unsigned).transpose()?;
    let contracts = handles(Some(bound.required(0)), Role::Contract)?;
    let profiles = handles(Some(bound.required(1)), Role::Profile)?;
    let states = handles(bound.optional(4), Role::State)?;
    let mode = match mode.as_deref().unwrap_or("contract_only") {
        "contract_only" => ValidationModeV1::ContractOnly,
        "state_advisory" => ValidationModeV1::StateAdvisory,
        "state_required" => ValidationModeV1::StateRequired,
        _ => return Err(Failure::Value("unsupported validation mode")),
    };
    Ok(BatchInput {
        contracts,
        profiles,
        states,
        at,
        mode,
        age,
    })
}
