// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Frozen request controls exercised through admission and public native calls.

use crate::test_support::{derive, eval, python_error, rejected, validate, with_python};
use pyo3::prelude::*;

#[test]
fn json_numbers() {
    crate::number_tests::json_numbers();
}

#[test]
fn at_bytes() {
    with_python(|py, scope| {
        for multibyte in [false, true] {
            for size in [63, 64, 65] {
                let text = format!("pad({size}, {})", if multibyte { "True" } else { "False" });
                for call in [
                    format!("api.derive_contract(survey, policy, at={text})"),
                    format!("api.validate(contract, profile, at={text})"),
                    format!("survey.redact('local', at={text})"),
                ] {
                    crate::faults::reset_native_entries();
                    let result = eval(py, &scope, &call);
                    if size == 65 {
                        python_error(
                            py,
                            &result.unwrap_err(),
                            "ValueError",
                            "argument budget exceeded",
                        );
                        assert_eq!(crate::faults::native_entries(), 0);
                    } else {
                        assert_eq!(crate::faults::native_entries(), 1);
                        if let Err(error) = result {
                            assert!(error.is_instance_of::<crate::error::CoreError>(py));
                        }
                    }
                }
            }
        }
    });
}

#[test]
fn notes_bytes() {
    with_python(|py, scope| {
        for expression in [
            "None".to_owned(),
            "''".into(),
            "pad(4095)".into(),
            "pad(4096)".into(),
            "pad(4095, True)".into(),
            "pad(4096, True)".into(),
        ] {
            let expected =
                eval(py, &scope, &expression).unwrap().extract::<Option<String>>().unwrap();
            let kwargs = format!("dict(at=at, notes={expression})");
            assert_eq!(derive(py, &scope, &kwargs).unwrap().notes, expected);
            assert_eq!(validate(py, &scope, &kwargs).unwrap().notes, expected);
        }
        for expression in ["pad(4097)", "pad(4097, True)"] {
            let kwargs = format!("dict(at=at, notes={expression})");
            rejected(derive(py, &scope, &kwargs), "argument budget exceeded");
            rejected(validate(py, &scope, &kwargs), "argument budget exceeded");
        }
    });
}

#[test]
fn profile_mode_bytes() {
    with_python(|py, scope| {
        for expression in [
            "''",
            "pad(31)",
            "pad(32)",
            "pad(33)",
            "pad(31, True)",
            "pad(32, True)",
            "pad(33, True)",
        ] {
            let size = eval(py, &scope, &format!("len(({expression}).encode())"))
                .unwrap()
                .extract::<usize>()
                .unwrap();
            let result = validate(py, &scope, &format!("dict(at=at, mode={expression})"));
            rejected(
                result,
                if size > 32 { "argument budget exceeded" } else { "unsupported validation mode" },
            );
            crate::faults::reset_native_entries();
            let error =
                eval(py, &scope, &format!("survey.redact({expression}, at=at)")).unwrap_err();
            if size > 32 {
                python_error(py, &error, "ValueError", "argument budget exceeded");
                assert_eq!(crate::faults::native_entries(), 0);
            } else {
                assert!(error.is_instance_of::<crate::error::CoreError>(py));
                assert_eq!(crate::faults::native_entries(), 1);
            }
        }
        for mode in ["contract_only", "state_advisory", "state_required"] {
            assert!(validate(py, &scope, &format!("dict(at=at, mode='{mode}')")).is_ok());
        }
        for profile in ["local", "fleet", "auditor", "external"] {
            assert!(eval(py, &scope, &format!("survey.redact('{profile}', at=at)")).is_ok());
        }
    });
}

#[test]
fn extension_limits() {
    crate::budget_collections::extension_limits();
}
#[test]
fn context_limits() {
    crate::budget_collections::context_limits();
}
#[test]
fn combined_bytes() {
    crate::budget_collections::combined_bytes();
}
#[test]
fn combined_nodes_depth() {
    crate::budget_collections::combined_nodes_depth();
}
#[test]
fn thermal_list() {
    crate::budget_collections::thermal_list();
}

#[test]
fn control_types_unicode() {
    crate::budget_controls::control_types_unicode();
}
#[test]
fn rejection_order() {
    crate::budget_controls::rejection_order();
}
#[test]
fn request_ownership() {
    crate::budget_controls::request_ownership();
}
