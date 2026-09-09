// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Narrow unwind assertions for attached Python argument inspection and import.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::panic::UnwindSafe;

struct Input<'a, 'py> {
    args: &'a Bound<'py, PyTuple>,
    kwargs: Option<&'a Bound<'py, PyDict>>,
}

// Only read-only signature/admission access is permitted through this wrapper.
// Exact built-ins are inspected with the GIL held, without coercion callbacks.
// No Python mutation participates in a Rust invariant; converted Rust locals
// are disposable. The wrapper is never sent to the detached closure. PyO3's
// GIL guard reacquires before unwinding drops any attached reference.
impl UnwindSafe for Input<'_, '_> {}

impl<'a, 'py> Input<'a, 'py> {
    fn run<T>(
        self,
        function: impl FnOnce(&'a Bound<'py, PyTuple>, Option<&'a Bound<'py, PyDict>>) -> PyResult<T>,
    ) -> PyResult<T> {
        function(self.args, self.kwargs)
    }
}

pub fn arguments<'a, 'py, T, F>(
    py: Python<'_>,
    operation: &'static str,
    args: &'a Bound<'py, PyTuple>,
    kwargs: Option<&'a Bound<'py, PyDict>>,
    function: F,
) -> PyResult<T>
where
    F: FnOnce(&'a Bound<'py, PyTuple>, Option<&'a Bound<'py, PyDict>>) -> PyResult<T> + UnwindSafe,
{
    let input = Input { args, kwargs };
    crate::panic_boundary::boundary(py, operation, move || input.run(function))
}

struct Initializing<'a, 'py>(&'a Bound<'py, PyModule>);

// This module is still inside its PyO3 initializer and is published only on
// success. Additions are ordinary Python-managed references; there is no
// shared mutable Rust state or held mutable native borrow to repair on unwind.
impl UnwindSafe for Initializing<'_, '_> {}

impl<'a, 'py> Initializing<'a, 'py> {
    fn run(self, function: impl FnOnce(&'a Bound<'py, PyModule>) -> PyResult<()>) -> PyResult<()> {
        function(self.0)
    }
}

pub fn initialize<'a, 'py, F>(module: &'a Bound<'py, PyModule>, function: F) -> PyResult<()>
where
    F: FnOnce(&'a Bound<'py, PyModule>) -> PyResult<()> + UnwindSafe,
{
    let initializing = Initializing(module);
    crate::panic_boundary::boundary(module.py(), "import", move || initializing.run(function))
}
