// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Collection-size, aggregate accounting and ownership assertions.

use crate::test_support::{derive, rejected, run, validate, with_python};
use std::sync::Arc;

pub fn extension_limits() {
    with_python(|py, scope| {
        for count in [15, 16] {
            assert_eq!(
                derive(py, &scope, &format!("dict(at=at, extension_packs=[{{}}]*{count})"))
                    .unwrap()
                    .packs
                    .len(),
                count
            );
        }
        for expression in ["[{}]*17", "[{}]*16 + [Sentinel()]"] {
            rejected(
                derive(py, &scope, &format!("dict(at=at, extension_packs={expression})")),
                "argument budget exceeded",
            );
        }
        for size in [1_048_575, 1_048_576, 1_048_577] {
            let result = derive(py, &scope, &format!("dict(at=at, extension_packs=[p({size})])"));
            if size > 1_048_576 {
                rejected(result, "argument budget exceeded");
            } else {
                assert_eq!(result.unwrap().packs[0]["k"].as_str().unwrap().len(), size - 1);
            }
        }
        for expression in ["()", "Items([{}])", "[None]", "[Sentinel()]"] {
            rejected(
                derive(py, &scope, &format!("dict(at=at, extension_packs={expression})")),
                "invalid argument type",
            );
        }
        run(py, &scope, "assert Sentinel.calls == 0");
    });
}

pub fn context_limits() {
    with_python(|py, scope| {
        assert!(derive(py, &scope, "dict(at=at, invocation_context=None)")
            .unwrap()
            .context
            .is_none());
        for size in [1_048_575, 1_048_576, 1_048_577] {
            let result = derive(py, &scope, &format!("dict(at=at, invocation_context=p({size}))"));
            if size > 1_048_576 {
                rejected(result, "argument budget exceeded");
            } else {
                assert_eq!(result.unwrap().context.unwrap()["k"].as_str().unwrap().len(), size - 1);
            }
        }
        for expression in ["[]", "Object()"] {
            rejected(
                derive(py, &scope, &format!("dict(at=at, invocation_context={expression})")),
                "invalid argument type",
            );
        }
        run(
            py,
            &scope,
            "one = {}; one['k'] = one\nfirst = {}; second = [first]; first['k'] = second",
        );
        for expression in ["one", "first"] {
            rejected(
                derive(py, &scope, &format!("dict(at=at, invocation_context={expression})")),
                "cyclic input",
            );
        }
        run(py, &scope, "one.clear(); first.clear(); second.clear(); assert Sentinel.calls == 0");
    });
}

pub fn combined_bytes() {
    with_python(|py, scope| {
        run(py, &scope, "shared = p(Q)");
        for delta in [-1, 0, 1] {
            for expression in [
                format!("dict(at=at, extension_packs=[shared]*7+[p(Q-20+({delta}))])"),
                format!("dict(at=at, extension_packs=[shared]*6+[p(Q-4116+({delta}))], invocation_context=shared, notes='a'*4096)")
            ] {
                let result = derive(py, &scope, &expression);
                if delta > 0 {
                    rejected(result, "argument budget exceeded");
                } else {
                    let request = result.unwrap();
                    let scalars: usize = request.packs.iter().chain(request.context.iter())
                        .map(|value| 1 + value["k"].as_str().unwrap().len()).sum();
                    assert_eq!(scalars + request.at.len() + request.notes.as_ref().map_or(0, String::len), (8_388_608_i64 + delta) as usize);
                }
            }
        }
    });
}

pub fn combined_nodes_depth() {
    with_python(|py, scope| {
        for nodes in [99_992, 99_993, 99_994] {
            let result = derive(py, &scope, &format!("dict(at=at, extension_packs=[{{'k':[None]*{nodes}}}], invocation_context={{'k':[]}})"));
            if nodes > 99_993 {
                rejected(result, "argument budget exceeded");
            } else {
                assert_eq!(result.unwrap().packs[0]["k"].as_array().unwrap().len(), nodes);
            }
        }
        for depth in [62, 63, 64] {
            for expression in [
                format!("dict(at=at, extension_packs=[nested({depth})])"),
                format!("dict(at=at, invocation_context=nested({depth}))"),
            ] {
                let result = derive(py, &scope, &expression);
                if depth > 63 {
                    rejected(result, "argument budget exceeded");
                } else {
                    assert!(result.is_ok());
                }
            }
        }
        rejected(
            crate::conversion_budget::add(usize::MAX, 1, usize::MAX),
            "argument budget exceeded",
        );
    });
}

pub fn thermal_list() {
    with_python(|py, scope| {
        for count in [127, 128] {
            let request =
                validate(py, &scope, &format!("dict(at=at, thermal_evidence=[thermal]*{count})"))
                    .unwrap();
            assert_eq!(request.thermal.len(), count);
            assert!(request
                .thermal
                .iter()
                .all(|value| Arc::ptr_eq(&value.core, &request.thermal[0].core)));
        }
        for expression in ["[thermal]*129", "[thermal]*128+[Sentinel()]"] {
            rejected(
                validate(py, &scope, &format!("dict(at=at, thermal_evidence={expression})")),
                "argument budget exceeded",
            );
        }
        for expression in ["None", "[]"] {
            assert!(validate(py, &scope, &format!("dict(at=at, thermal_evidence={expression})"))
                .unwrap()
                .thermal
                .is_empty());
        }
        for expression in ["()", "Items([thermal])", "[None]", "[1]"] {
            rejected(
                validate(py, &scope, &format!("dict(at=at, thermal_evidence={expression})")),
                "invalid argument type",
            );
        }
        rejected(
            validate(py, &scope, "dict(at=at, thermal_evidence=[survey])"),
            "incompatible artifact kind",
        );
        run(py, &scope, "assert Sentinel.calls == 0");
    });
}
