// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Cross-argument precedence and owned request field assertions.

use crate::test_support::{derive, eval, python_error, run, validate, with_python};
use pyo3::prelude::*;
use std::sync::Arc;

fn calls(value: &str) -> Vec<String> {
    vec![
        format!("api.derive_contract(survey, policy, at={value})"),
        format!("api.validate(contract, profile, at={value})"),
        format!("survey.redact('local', at={value})"),
        format!("api.derive_contract(survey, policy, at=at, notes={value})"),
        format!("api.validate(contract, profile, at=at, notes={value})"),
        format!("api.builtin_config({value}, 'absent')"),
        format!("api.builtin_config('policy', {value})"),
        format!("survey.redact({value}, at=at)"),
        format!("api.validate(contract, profile, at=at, mode={value})"),
    ]
}

pub fn control_types_unicode() {
    with_python(|py, scope| {
        for value in ["0", "True", "Text('x')", "chr(0xd800)", "chr(0xdc00)"] {
            let unicode = value.starts_with("chr");
            for expression in calls(value) {
                crate::faults::reset_native_entries();
                let error = eval(py, &scope, &expression).unwrap_err();
                python_error(
                    py,
                    &error,
                    if unicode { "ValueError" } else { "TypeError" },
                    if unicode { "invalid Unicode scalar" } else { "invalid argument type" },
                );
                assert_eq!(crate::faults::native_entries(), 0);
            }
        }
        for expression in ["'é'", "'e'+chr(0x301)"] {
            let source = eval(py, &scope, expression).unwrap();
            let expected = source.extract::<String>().unwrap();
            assert_eq!(
                crate::conversion::string(&source, 32).unwrap().as_bytes(),
                expected.as_bytes()
            );
            assert_eq!(
                derive(py, &scope, &format!("dict(at={expression}, notes={expression})"))
                    .unwrap()
                    .at,
                expected
            );
            assert_eq!(
                validate(py, &scope, &format!("dict(at=at, notes={expression})"))
                    .unwrap()
                    .notes
                    .as_deref(),
                Some(expected.as_str())
            );
        }
        for (index, expression) in calls("None").into_iter().enumerate() {
            let result = eval(py, &scope, &expression);
            if [3, 4].contains(&index) {
                assert!(result.is_ok());
            } else {
                python_error(py, &result.unwrap_err(), "TypeError", "invalid argument type");
            }
        }
        run(py, &scope, "assert Sentinel.calls == 0");
    });
}

pub fn rejection_order() {
    with_python(|py, scope| {
        run(py, &scope, "cycle = {}; cycle['k'] = cycle");
        for (kwargs, kind, message) in [
            ("at='a'*65, notes=False", "TypeError", "invalid argument type"),
            ("at='a'*65, extension_packs=[p(Q+1)]", "ValueError", "argument budget exceeded"),
            (
                "at=at, extension_packs=[p(Q+1)], invocation_context=cycle",
                "ValueError",
                "argument budget exceeded",
            ),
        ] {
            crate::faults::reset_native_entries();
            let error = eval(py, &scope, &format!("api.derive_contract(survey, policy, {kwargs})"))
                .unwrap_err();
            python_error(py, &error, kind, message);
            assert_eq!(crate::faults::native_entries(), 0);
        }
        run(py, &scope, "cycle.clear()");
        use crate::conversion_budget::{Budget, Counts, CONFIG_BYTES, REQUEST_BYTES};
        let input = eval(py, &scope, "p(Q+1)").unwrap();
        let mut budget =
            Budget::configuration(Counts { bytes: REQUEST_BYTES - CONFIG_BYTES / 2, nodes: 0 });
        crate::faults::budget_domain("none");
        crate::test_support::rejected(
            crate::conversion::document(&input, &mut budget),
            "argument budget exceeded",
        );
        // Both counters would reject this one scalar. The individual check
        // must be first even when less combined space remains.
        assert_eq!(crate::faults::last_budget_domain(), "individual");
    });
}

pub fn request_ownership() {
    with_python(|py, scope| {
        for empty in ["None", "[]"] {
            for notes in ["None", "''"] {
                let expected =
                    eval(py, &scope, notes).unwrap().extract::<Option<String>>().unwrap();
                let d = derive(
                    py,
                    &scope,
                    &format!("dict(at=at, extension_packs={empty}, notes={notes})"),
                )
                .unwrap();
                let v = validate(py, &scope, &format!("dict(at=at, thermal_evidence={empty}, notes={notes}, max_state_age_seconds=None)")).unwrap();
                assert!(
                    d.packs.is_empty()
                        && d.context.is_none()
                        && v.thermal.is_empty()
                        && v.age.is_none()
                );
                assert_eq!(d.notes, expected);
                assert_eq!(v.notes, expected);
            }
        }
        run(py, &scope, "left = {'k': 'left'}; right = {'k': 'right'}\nsecond_thermal = api.Artifact.from_dict(data['fixtures']['thermal'])");
        for (items, first, last) in
            [("[left, right, left]", "left", "left"), ("[right, left]", "right", "left")]
        {
            let request =
                derive(py, &scope, &format!("dict(at=at, extension_packs={items})")).unwrap();
            assert_eq!(request.packs.first().unwrap()["k"], first);
            assert_eq!(request.packs.last().unwrap()["k"], last);
            assert_eq!(request.packs.len(), if first == "left" { 3 } else { 2 });
        }
        let forward = validate(
            py,
            &scope,
            "dict(at=at, thermal_evidence=[thermal, second_thermal, thermal])",
        )
        .unwrap();
        let backward =
            validate(py, &scope, "dict(at=at, thermal_evidence=[second_thermal, thermal])")
                .unwrap();
        assert_eq!(forward.thermal.len(), 3);
        assert_eq!(backward.thermal.len(), 2);
        assert!(Arc::ptr_eq(&forward.thermal[0].core, &forward.thermal[2].core));
        assert!(Arc::ptr_eq(&forward.thermal[1].core, &backward.thermal[0].core));
        assert!(Arc::ptr_eq(&forward.thermal[0].core, &backward.thermal[1].core));
        let expression =
            "data['observations']['builtin/invocation_contexts/core_default.v1.json']['value']";
        let request = derive(
            py,
            &scope,
            &format!("dict(at=at, extension_packs=[], invocation_context={expression})"),
        )
        .unwrap();
        assert!(request.packs.is_empty() && request.context.is_some());
        crate::faults::reset_resolver_entries();
        eval(py, &scope, &format!("api.derive_contract(survey, policy, at=at, extension_packs=[], invocation_context={expression})")).unwrap();
        assert_eq!(crate::faults::resolver_entries(), 1);
        crate::faults::reset_resolver_entries();
        eval(py, &scope, "api.derive_contract(survey, policy, at=at)").unwrap();
        assert_eq!(crate::faults::resolver_entries(), 0);
    });
}
