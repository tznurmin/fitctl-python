// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Fallible Python export; JSON presentation is distinct from core semantics.

use crate::error::{export_failure, Failure, Result};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

unsafe fn owned(py: Python<'_>, pointer: *mut pyo3::ffi::PyObject) -> Result<Bound<'_, PyAny>> {
    Bound::from_owned_ptr_or_err(py, pointer).map_err(|error| export_failure(py, error))
}

pub fn text<'py>(py: Python<'py>, value: &str) -> Result<Bound<'py, PyAny>> {
    crate::faults::export()?;
    unsafe {
        owned(
            py,
            pyo3::ffi::PyUnicode_FromStringAndSize(value.as_ptr().cast(), value.len() as isize),
        )
    }
}

pub fn bytes<'py>(py: Python<'py>, value: &[u8]) -> Result<Bound<'py, PyAny>> {
    crate::faults::export()?;
    unsafe {
        owned(py, pyo3::ffi::PyBytes_FromStringAndSize(value.as_ptr().cast(), value.len() as isize))
    }
}

pub fn value<'py>(py: Python<'py>, raw: &Value) -> Result<Bound<'py, PyAny>> {
    crate::faults::export()?;
    match raw {
        Value::Null => Ok(py.None().into_bound(py)),
        Value::Bool(value) => unsafe {
            owned(py, pyo3::ffi::PyBool_FromLong(i64::from(*value) as _))
        },
        Value::Number(value) => unsafe {
            if let Some(value) = value.as_i64() {
                owned(py, pyo3::ffi::PyLong_FromLongLong(value))
            } else if let Some(value) = value.as_u64() {
                owned(py, pyo3::ffi::PyLong_FromUnsignedLongLong(value))
            } else {
                owned(py, pyo3::ffi::PyFloat_FromDouble(value.as_f64().ok_or(Failure::Export)?))
            }
        },
        Value::String(value) => text(py, value),
        Value::Array(items) => {
            // Allocate an empty list through the checked C API, then append
            // checked values. No partially initialized list can escape.
            let list = unsafe { owned(py, pyo3::ffi::PyList_New(0))? };
            #[cfg(test)]
            crate::fault_state::container();
            for item in items {
                list.cast::<PyList>()
                    .map_err(|_| Failure::Export)?
                    .append(value(py, item)?)
                    .map_err(|error| export_failure(py, error))?;
                crate::faults::item_complete()?;
            }
            Ok(list)
        }
        Value::Object(items) => {
            let dictionary = unsafe { owned(py, pyo3::ffi::PyDict_New())? };
            #[cfg(test)]
            crate::fault_state::container();
            for (key, item) in items {
                dictionary
                    .cast::<PyDict>()
                    .map_err(|_| Failure::Export)?
                    .set_item(text(py, key)?, value(py, item)?)
                    .map_err(|error| export_failure(py, error))?;
                crate::faults::item_complete()?;
            }
            Ok(dictionary)
        }
    }
}

pub fn json(value: &Value) -> Result<String> {
    crate::faults::encode()?;
    encode(value)
}

pub fn encode(value: &impl serde::Serialize) -> Result<String> {
    crate::json_encode::encode(value)
}
