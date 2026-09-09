// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Owned unwind handling; the process-global panic hook remains untouched.

use pyo3::prelude::*;
use std::any::Any;
use std::panic::{catch_unwind, AssertUnwindSafe, UnwindSafe};

use crate::error::{Failure, Result};

fn dispose(payload: Box<dyn Any + Send>) {
    // The assertion covers only disposal of this owned opaque payload. No
    // shared adapter state is asserted unwind-safe, inspected or formatted.
    let result = catch_unwind(AssertUnwindSafe(move || drop(payload)));
    match result {
        Ok(()) => (),
        Err(_second_payload) => std::process::abort(),
    }
}

pub fn boundary<T, F>(py: Python<'_>, operation: &'static str, function: F) -> PyResult<T>
where
    F: FnOnce() -> PyResult<T> + UnwindSafe,
{
    match catch_unwind(function) {
        Ok(result) => result,
        Err(payload) => {
            dispose(payload);
            match catch_unwind(|| Failure::Panic.python(py, operation)) {
                Ok(error) => Err(error),
                Err(_payload) => std::process::abort(),
            }
        }
    }
}

pub fn detached<T, F>(py: Python<'_>, operation: &'static str, function: F) -> PyResult<T>
where
    T: Send,
    F: FnOnce() -> Result<T> + Send,
{
    let result = py.detach(|| {
        crate::faults::native_entry();
        function()
    });
    py.check_signals()?;
    result.map_err(|error| error.python(py, operation))
}
