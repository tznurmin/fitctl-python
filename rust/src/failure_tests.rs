// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Exact matrix selectors; each runs in a separately bounded native process.

#[test]
fn json_serialization() {
    crate::failure_exports::json_serialization();
}
#[test]
fn python_export() {
    crate::failure_exports::python_export();
}
#[test]
fn recoverable_allocation() {
    crate::failure_exports::recoverable_allocation();
}
#[test]
fn caught_panic() {
    crate::failure_panics::caught(false);
}
#[test]
fn panic_hook_scope() {
    crate::failure_panics::caught(true);
}
#[test]
fn terminal_panic() {
    crate::failure_panics::terminal();
}
#[test]
fn detached_ownership() {
    crate::failure_execution::detached_ownership();
}
#[test]
fn pending_interrupt() {
    crate::failure_execution::pending_interrupt();
}
