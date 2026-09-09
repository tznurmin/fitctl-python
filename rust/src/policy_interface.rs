// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Policy ingress keeps the validated supplied JSON alongside the typed core policy.

use crate::error::Failure;
use crate::panic_boundary::{boundary, detached};
use crate::serialization;
use crate::value_interface::{constructor, loader_input, no_arguments, python};
use crate::values::Policy;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple, PyType};
use std::sync::Arc;

#[pymethods]
impl Policy {
    #[new]
    #[pyo3(signature = (*args, **kwargs))]
    fn new(
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        crate::attached_boundary::arguments(py, "Policy", args, kwargs, |args, kwargs| {
            Err(constructor(py, args, kwargs))
        })
    }
    #[classmethod]
    #[pyo3(signature = (*args, **kwargs), text_signature = "($cls, data)")]
    fn from_dict(
        _cls: &Bound<'_, PyType>,
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<Self>> {
        crate::attached_boundary::arguments(py, "Policy.from_dict", args, kwargs, |args, kwargs| {
            let raw = loader_input(py, "Policy.from_dict", false, args, kwargs)?;
            let value = detached(py, "Policy.from_dict", move || Self::load(raw))?;
            Py::new(py, value)
        })
    }
    #[classmethod]
    #[pyo3(signature = (*args, **kwargs), text_signature = "($cls, text)")]
    fn from_json(
        _cls: &Bound<'_, PyType>,
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<Self>> {
        crate::attached_boundary::arguments(py, "Policy.from_json", args, kwargs, |args, kwargs| {
            let raw = loader_input(py, "Policy.from_json", true, args, kwargs)?;
            let value = detached(py, "Policy.from_json", move || Self::load(raw))?;
            Py::new(py, value)
        })
    }
    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn to_dict<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(py, "Policy.to_dict", args, kwargs, |args, kwargs| {
            no_arguments(py, "Policy.to_dict", args, kwargs)?;
            python(py, "Policy.to_dict", serialization::value(py, &self.raw))
        })
    }
    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn to_json<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(py, "Policy.to_json", args, kwargs, |args, kwargs| {
            no_arguments(py, "Policy.to_json", args, kwargs)?;
            let raw = Arc::clone(&self.raw);
            let value = detached(py, "Policy.to_json", move || serialization::json(&raw))?;
            python(py, "Policy.to_json", serialization::text(py, &value))
        })
    }
    fn __setattr__(
        &self,
        py: Python<'_>,
        _name: &Bound<'_, PyAny>,
        _value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        boundary(py, "Policy", || Err(Failure::Immutable.python(py, "Policy")))
    }
    fn __delattr__(&self, py: Python<'_>, _name: &Bound<'_, PyAny>) -> PyResult<()> {
        boundary(py, "Policy", || Err(Failure::Immutable.python(py, "Policy")))
    }
}
