// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Shared safe wrappers around value construction and exports.

use crate::argument_binding::Arguments;
use crate::error::{Failure, Result, ARGUMENTS};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

pub fn python<T>(py: Python<'_>, operation: &'static str, result: Result<T>) -> PyResult<T> {
    result.map_err(|error| error.python(py, operation))
}

pub fn constructor(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyErr {
    if args.is_empty() && kwargs.is_none_or(|k| k.is_empty()) {
        Failure::Type("native value requires a loader").python(py, "construction")
    } else {
        ARGUMENTS.python(py, "construction")
    }
}

pub fn no_arguments(
    py: Python<'_>,
    operation: &'static str,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<()> {
    python(py, operation, Arguments::bind(args, kwargs, &[], 0, 0).map(|_| ()))
}

pub fn loader_input(
    py: Python<'_>,
    operation: &'static str,
    json: bool,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<serde_json::Value> {
    let names = if json { ["text"] } else { ["data"] };
    let bound = python(py, operation, Arguments::bind(args, kwargs, &names, 1, 1))?;
    python(py, operation, crate::conversion::input(bound.required(0), json))
}
