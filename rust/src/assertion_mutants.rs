// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Single-fault negative controls reuse the authoritative public assertions.

use pyo3::prelude::*;
use std::cell::{Cell, RefCell};
use std::collections::HashSet;

#[derive(Clone, Copy, PartialEq)]
pub enum Fault {
    None,
    Duplicate,
    Key,
    Root,
    Alias,
    BoolAge,
    Combined,
    Fields,
    BatchCount,
    CollectionCount,
    Number,
}

thread_local! {
    static SELECTED: Cell<Fault> = const { Cell::new(Fault::None) };
    static SEEN: RefCell<HashSet<usize>> = RefCell::new(HashSet::new());
}

pub fn active(fault: Fault) -> bool {
    SELECTED.get() == fault
}
pub fn alias(address: usize) -> bool {
    active(Fault::Alias) && SEEN.with_borrow_mut(|seen| !seen.insert(address))
}
pub fn begin_document() {
    SEEN.with_borrow_mut(HashSet::clear);
}

struct Guard;
impl Drop for Guard {
    fn drop(&mut self) {
        SELECTED.set(Fault::None);
        begin_document();
    }
}

pub fn with_fault<T>(fault: Fault, function: impl FnOnce() -> T) -> T {
    let _guard = Guard;
    SELECTED.set(fault);
    function()
}

#[test]
fn public_assertions_reject_mutants() {
    use crate::test_support::{eval, run, with_python};
    let _guard = Guard;
    with_python(|py, scope| {
        let tests = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../tests");
        scope
            .set_item("test_path", tests.to_str().unwrap())
            .unwrap();
        run(py, &scope, "import sys, unittest\nsys.path.insert(0,test_path)\nsys.modules['fitctl']=api\nimport test_errors");
        for (fault, method) in [
            (Fault::Duplicate, "test_malformed_and_duplicate_json"),
            (Fault::Key, "test_utf8_byte_budgets"),
            (Fault::Root, "test_depth_and_node_budgets"),
            (Fault::Alias, "test_shared_containers_count_each_occurrence"),
            (Fault::BoolAge, "test_bool_is_not_max_age"),
            (Fault::Fields, "test_exception_field_and_rendering_contract"),
        ] {
            scope.set_item("method", method).unwrap();
            for selected in [Fault::None, fault] {
                SELECTED.set(selected);
                run(
                    py,
                    &scope,
                    "result=unittest.TestResult()\ntest_errors.InputErrorTests(method).run(result)",
                );
                assert_eq!(
                    eval(py, &scope, "result.testsRun")
                        .unwrap()
                        .extract::<usize>()
                        .unwrap(),
                    1
                );
                assert!(eval(
                    py,
                    &scope,
                    "not result.skipped and not result.expectedFailures"
                )
                .unwrap()
                .is_truthy()
                .unwrap());
                assert_eq!(
                    eval(py, &scope, "result.wasSuccessful()")
                        .unwrap()
                        .is_truthy()
                        .unwrap(),
                    selected == Fault::None,
                    "{method}"
                );
            }
            SELECTED.set(Fault::None);
        }
    });
    crate::budget_collections::combined_bytes();
    SELECTED.set(Fault::Combined);
    assert!(std::panic::catch_unwind(crate::budget_collections::combined_bytes).is_err());
    SELECTED.set(Fault::None);
    with_python(|py, scope| {
        let tests = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../tests");
        scope
            .set_item("test_path", tests.to_str().unwrap())
            .unwrap();
        run(py, &scope, "import sys, unittest\nsys.path.insert(0,test_path)\nsys.modules['fitctl']=api\nimport test_json_numbers");
        for selected in [Fault::None, Fault::Number] {
            SELECTED.set(selected);
            run(py, &scope, "result=unittest.TestResult()\ntest_json_numbers.JsonNumberTests('test_literal_core_parity').run(result)\nassert result.testsRun == 1 and not result.skipped and not result.expectedFailures");
            assert_eq!(
                eval(py, &scope, "result.wasSuccessful()")
                    .unwrap()
                    .is_truthy()
                    .unwrap(),
                selected == Fault::None,
                "literal number assertions must reject loss of negative zero"
            );
        }
    });
}
