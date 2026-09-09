// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Exact exception and partial-export ownership assertions.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

pub fn structured(
    py: Python<'_>,
    error: &PyErr,
    class: &str,
    model: &str,
    reason: &str,
    checkpoint: &str,
    message: &str,
) {
    crate::test_support::python_error(py, error, class, message);
    let value = error.value(py);
    let fields = value.getattr("__dict__").unwrap().cast_into::<PyDict>().unwrap();
    assert_eq!(fields.len(), 5);
    for (key, expected) in [
        ("error_model_id", model),
        ("reason_code", reason),
        ("checkpoint_id", checkpoint),
        ("message", message),
    ] {
        assert_eq!(fields.get_item(key).unwrap().unwrap().extract::<String>().unwrap(), expected);
    }
    assert_eq!(
        fields.get_item("error_model_version").unwrap().unwrap().extract::<u32>().unwrap(),
        1
    );
    assert_eq!(value.str().unwrap().to_str().unwrap(), message);
    for text in [value.repr().unwrap(), fields.repr().unwrap()] {
        assert!(!text.to_str().unwrap().contains("ADAPTER_INPUT_SENTINEL"));
    }
}

pub fn memory(py: Python<'_>, error: &PyErr) {
    assert!(error.is_instance_of::<pyo3::exceptions::PyMemoryError>(py));
    let value = error.value(py);
    assert!(value.getattr("args").unwrap().cast::<PyTuple>().unwrap().is_empty());
    assert_eq!(value.str().unwrap().to_str().unwrap(), "");
    assert!(value.getattr("__dict__").unwrap().cast::<PyDict>().unwrap().is_empty());
    assert!(value.getattr("__cause__").unwrap().is_none());
    assert!(value.getattr("__context__").unwrap().is_none());
}

pub fn native(py: Python<'_>, error: &PyErr) {
    structured(
        py,
        error,
        "NativeError",
        "fitctl.python.native.v1",
        "native_panic",
        "native_call",
        "native operation panicked",
    );
}

pub fn container_counts(py: Python<'_>, scope: &Bound<'_, PyDict>) -> (usize, usize) {
    crate::test_support::run(py, scope, "import gc");
    crate::test_support::eval(py, scope,
        "(sum(type(item) is list for item in gc.get_objects()), sum(type(item) is dict for item in gc.get_objects()))")
        .unwrap().extract().unwrap()
}

pub fn partials_removed(py: Python<'_>, scope: &Bound<'_, PyDict>, before: (usize, usize)) {
    assert_eq!(
        crate::fault_state::container_count(),
        3,
        "root and two completed child containers were allocated"
    );
    assert_eq!(
        container_counts(py, scope),
        before,
        "acyclic output containers must be decremented immediately, without gc.collect"
    );
}
