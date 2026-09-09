// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Compile-time-only seams for controlled failure-path qualification.

use crate::error::Result;

#[cfg(test)]
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Point {
    Reservation,
    Conversion,
    Detached,
    Export,
    Encode,
    Exception,
    ExportMemory,
    PartialExport,
    PartialMemory,
    ExportPanic,
    MalformedAsset,
}

#[cfg(test)]
thread_local! { static ACTIVE: std::cell::Cell<Option<(Point, usize)>> = const { std::cell::Cell::new(None) }; }

#[cfg(test)]
thread_local! { static NATIVE_ENTRIES: std::cell::Cell<usize> = const { std::cell::Cell::new(0) }; }

#[cfg(test)]
thread_local! {
    static RESOLVER_ENTRIES: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    static BUDGET_DOMAIN: std::cell::Cell<&'static str> = const { std::cell::Cell::new("none") };
}

#[cfg(test)]
pub fn reset_resolver_entries() {
    RESOLVER_ENTRIES.with(|count| count.set(0));
}
#[cfg(test)]
pub fn resolver_entries() -> usize {
    RESOLVER_ENTRIES.with(|count| count.get())
}
#[cfg(test)]
pub fn budget_domain(domain: &'static str) {
    BUDGET_DOMAIN.with(|value| value.set(domain));
}
#[cfg(test)]
pub fn last_budget_domain() -> &'static str {
    BUDGET_DOMAIN.with(|value| value.get())
}

pub fn resolver_entry() {
    #[cfg(test)]
    RESOLVER_ENTRIES.with(|count| count.set(count.get() + 1));
}

#[cfg(test)]
pub fn reset_native_entries() {
    NATIVE_ENTRIES.with(|count| count.set(0));
}

#[cfg(test)]
pub fn native_entries() -> usize {
    NATIVE_ENTRIES.with(|count| count.get())
}

pub fn native_entry() {
    #[cfg(test)]
    NATIVE_ENTRIES.with(|count| count.set(count.get() + 1));
}

#[cfg(test)]
pub fn inject(point: Point) {
    inject_after(point, 0);
}

#[cfg(test)]
pub fn inject_after(point: Point, skip: usize) {
    crate::fault_state::reset();
    ACTIVE.with(|active| active.set(Some((point, skip))));
}

#[cfg(test)]
fn take(point: Point) -> bool {
    ACTIVE.with(|active| match active.get() {
        Some((wanted, 0)) if wanted == point => {
            active.set(None);
            true
        }
        Some((wanted, skip)) if wanted == point => {
            active.set(Some((wanted, skip - 1)));
            false
        }
        _ => false,
    })
}

pub fn reservation() -> Result<()> {
    #[cfg(test)]
    if take(Point::Reservation) {
        return Err(crate::error::Failure::Memory);
    }
    Ok(())
}

pub fn conversion() {
    #[cfg(test)]
    if take(Point::Conversion) {
        panic!("ADAPTER_INPUT_SENTINEL");
    }
}

pub fn detached() {
    #[cfg(test)]
    if take(Point::Detached) {
        panic!("ADAPTER_INPUT_SENTINEL");
    }
}

pub fn export() -> Result<()> {
    #[cfg(test)]
    assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 1);
    #[cfg(test)]
    if take(Point::ExportPanic) {
        panic!("ADAPTER_INPUT_SENTINEL");
    }
    #[cfg(test)]
    if take(Point::Export) {
        return Err(crate::error::Failure::Export);
    }
    #[cfg(test)]
    if take(Point::ExportMemory) {
        return Err(crate::error::Failure::Memory);
    }
    Ok(())
}

pub fn item_complete() -> Result<()> {
    #[cfg(test)]
    if take(Point::PartialExport) {
        return Err(crate::error::Failure::Export);
    }
    #[cfg(test)]
    if take(Point::PartialMemory) {
        return Err(crate::error::Failure::Memory);
    }
    Ok(())
}

pub fn asset(contents: &str) -> &str {
    #[cfg(test)]
    if take(Point::MalformedAsset) {
        return "{ADAPTER_INPUT_SENTINEL";
    }
    contents
}

pub fn encode() -> Result<()> {
    #[cfg(test)]
    if take(Point::Encode) {
        return Err(crate::error::Failure::JsonEncode);
    }
    Ok(())
}

pub fn exception_field() -> pyo3::PyResult<()> {
    #[cfg(test)]
    if take(Point::Exception) {
        return Err(pyo3::exceptions::PyMemoryError::new_err(()));
    }
    Ok(())
}
