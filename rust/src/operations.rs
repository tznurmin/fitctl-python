// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Bounded signatures for the three public module-level operations.

use crate::argument_binding::Arguments;
use crate::error::Failure;
use crate::panic_boundary::detached;
use crate::value_interface::python;
use crate::values::Artifact;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString, PyTuple};

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(category, config_id)")]
pub fn builtin_config<'py>(
    py: Python<'py>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    crate::attached_boundary::arguments(py, "builtin_config", args, kwargs, |args, kwargs| {
        let bound = python(
            py,
            "builtin_config",
            Arguments::bind(args, kwargs, &["category", "config_id"], 2, 2),
        )?;
        for index in 0..2 {
            python(
                py,
                "builtin_config",
                crate::conversion::exact::<PyString>(bound.required(index)),
            )?;
        }
        let category =
            python(py, "builtin_config", crate::conversion::string(bound.required(0), 64))?;
        let id = python(py, "builtin_config", crate::conversion::string(bound.required(1), 128))?;
        let value = detached(py, "builtin_config", move || {
            if !["policy", "service_profiles", "extensions", "invocation_contexts"]
                .contains(&category.as_str())
            {
                return Err(Failure::Key);
            }
            let asset = fitctl_core::config::built_in_config_assets_v1()
                .iter()
                .find(|asset| asset.category == category && asset.id == id)
                .ok_or(Failure::Key)?;
            serde_json::from_str(crate::faults::asset(asset.contents)).map_err(|_| Failure::Export)
        })?;
        python(py, "builtin_config", crate::serialization::value(py, &value))
    })
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(survey, policy, *, at, extension_packs=None, invocation_context=None, notes=None)")]
pub fn derive_contract(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<Artifact>> {
    crate::attached_boundary::arguments(py, "derive_contract", args, kwargs, |args, kwargs| {
        let bound = python(
            py,
            "derive_contract",
            Arguments::bind(
                args,
                kwargs,
                &["survey", "policy", "at", "extension_packs", "invocation_context", "notes"],
                2,
                3,
            ),
        )?;
        let input = python(py, "derive_contract", crate::derive_admission::admit(&bound))?;
        let value = detached(py, "derive_contract", move || crate::core_calls::derive(input))?;
        Py::new(py, value)
    })
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(contract, profile, *, at, mode='contract_only', state=None, thermal_evidence=None, max_state_age_seconds=None, notes=None)")]
pub fn validate(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<Artifact>> {
    crate::attached_boundary::arguments(py, "validate", args, kwargs, |args, kwargs| {
        let bound = python(
            py,
            "validate",
            Arguments::bind(
                args,
                kwargs,
                &[
                    "contract",
                    "profile",
                    "at",
                    "mode",
                    "state",
                    "thermal_evidence",
                    "max_state_age_seconds",
                    "notes",
                ],
                2,
                3,
            ),
        )?;
        let input = python(py, "validate", crate::validate_admission::admit(&bound))?;
        let value = detached(py, "validate", move || crate::core_calls::validate(input))?;
        Py::new(py, value)
    })
}
