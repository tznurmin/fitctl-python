// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Test-only observation of allocations under Python execution ownership.

thread_local! {
    static CONTAINERS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

pub fn reset() {
    CONTAINERS.with(|count| count.set(0));
}

pub fn container() {
    assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 1);
    CONTAINERS.with(|count| count.set(count.get() + 1));
}

pub fn container_count() -> usize {
    CONTAINERS.with(|count| count.get())
}
