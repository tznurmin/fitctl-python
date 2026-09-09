// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Direct core batch invocation with exclusively Rust-owned request values.

use crate::argument_binding::Arguments;
use crate::batch_admission::BatchInput;
use crate::batch_value::BatchReport;
use crate::error::{Failure, Result, KIND};
use crate::panic_boundary::detached;
use crate::value_interface::python;
use crate::values::Artifact;
use fitctl_core::artifacts::record_v1::ArtifactRecordV1;
use fitctl_core::classify::{classify_batch_v1, BatchClassificationRequestV1};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::sync::Arc;

fn payloads<T>(
    values: Vec<Artifact>,
    extract: impl Fn(&ArtifactRecordV1) -> Result<T>,
) -> Result<Vec<T>> {
    let mut result = Vec::new();
    crate::faults::reservation()?;
    result
        .try_reserve_exact(values.len())
        .map_err(|_| Failure::Memory)?;
    for value in values {
        result.push(extract(value.core.as_ref())?);
    }
    Ok(result)
}

pub fn execute(input: BatchInput) -> Result<BatchReport> {
    crate::faults::detached();
    let contracts = payloads(input.contracts, |value| match value {
        ArtifactRecordV1::Contract(value) => Ok(value.clone()),
        _ => Err(KIND),
    })?;
    let service_profiles = payloads(input.profiles, |value| match value {
        ArtifactRecordV1::ServiceProfile(value) => Ok(value.clone()),
        _ => Err(KIND),
    })?;
    let host_states = payloads(input.states, |value| match value {
        ArtifactRecordV1::State(value) => Ok(value.clone()),
        _ => Err(KIND),
    })?;
    let core = classify_batch_v1(BatchClassificationRequestV1 {
        contracts,
        service_profiles,
        host_states,
        validation_mode: input.mode,
        max_state_age_seconds: input.age,
        validated_at: input.at,
    })?;
    Ok(BatchReport {
        core: Arc::new(core),
    })
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(contracts, profiles, *, at, mode='contract_only', states=None, max_state_age_seconds=None)")]
pub fn classify_batch(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<BatchReport>> {
    crate::attached_boundary::arguments(py, "classify_batch", args, kwargs, |args, kwargs| {
        let bound = python(
            py,
            "classify_batch",
            Arguments::bind(
                args,
                kwargs,
                &[
                    "contracts",
                    "profiles",
                    "at",
                    "mode",
                    "states",
                    "max_state_age_seconds",
                ],
                2,
                3,
            ),
        )?;
        let input = python(py, "classify_batch", crate::batch_admission::admit(&bound))?;
        let value = detached(py, "classify_batch", move || execute(input))?;
        Py::new(py, value)
    })
}
