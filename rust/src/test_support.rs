// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Embedded-Python test setup using retained core inputs and real native types.

use crate::argument_binding::Arguments;
use crate::error::{Failure, Result};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use serde_json::Value;
use std::ffi::CString;

pub fn with_python(test: impl for<'py> FnOnce(Python<'py>, Bound<'py, PyDict>)) {
    Python::initialize();
    Python::attach(|py| {
        let scope = PyDict::new(py);
        let module = PyModule::new(py, "fitctl").unwrap();
        crate::_native(&module).unwrap();
        scope.set_item("api", module).unwrap();
        let raw: Value =
            serde_json::from_str(include_str!("../../tests/fixtures/recorded/core-reference.json"))
                .unwrap();
        scope.set_item("data", crate::serialization::value(py, &raw).unwrap()).unwrap();
        run(
            py,
            &scope,
            r#"
at = '2026-01-01T00:00:00Z'
Q = 1048576
survey = api.Artifact.from_dict(data['fixtures']['survey'])
contract = api.Artifact.from_dict(data['fixtures']['contract'])
profile = api.Artifact.from_dict(data['fixtures']['profile'])
thermal = api.Artifact.from_dict(data['fixtures']['thermal'])
policy = api.Policy.from_dict(data['observations']['builtin/policy/general_compute_default.v1.json']['value'])
def pad(n, multibyte=False):
    return 'é' * (n//2) + 'a' * (n%2) if multibyte else 'a' * n
def p(n):
    return {'k': 'a' * (n-1)}
def nested(n):
    value = None
    for i in range(n):
        value = [value]
    return {'k': value}
class Sentinel:
    calls = 0
    def forbidden(self, *args):
        Sentinel.calls += 1
        raise AssertionError('callback invoked')
    __str__ = __repr__ = __iter__ = __len__ = forbidden
class Text(str):
    __str__ = __repr__ = Sentinel.forbidden
class Items(list):
    __iter__ = __len__ = Sentinel.forbidden
class Object(dict):
    __iter__ = __len__ = Sentinel.forbidden
"#,
        );
        test(py, scope);
    });
}

pub fn run(py: Python<'_>, scope: &Bound<'_, PyDict>, code: &str) {
    py.run(&CString::new(code).unwrap(), Some(scope), Some(scope)).unwrap();
}

pub fn eval<'py>(
    py: Python<'py>,
    scope: &Bound<'py, PyDict>,
    code: &str,
) -> PyResult<Bound<'py, PyAny>> {
    py.eval(&CString::new(code).unwrap(), Some(scope), Some(scope))
}

pub fn derive<'py>(
    py: Python<'py>,
    scope: &Bound<'py, PyDict>,
    expression: &str,
) -> Result<crate::derive_admission::Derive> {
    let args = PyTuple::new(
        py,
        [scope.get_item("survey").unwrap().unwrap(), scope.get_item("policy").unwrap().unwrap()],
    )
    .unwrap();
    let kwargs = eval(py, scope, expression).unwrap().cast_into::<PyDict>().unwrap();
    let bound = Arguments::bind(
        &args,
        Some(&kwargs),
        &["survey", "policy", "at", "extension_packs", "invocation_context", "notes"],
        2,
        3,
    )?;
    crate::derive_admission::admit(&bound)
}

pub fn validate<'py>(
    py: Python<'py>,
    scope: &Bound<'py, PyDict>,
    expression: &str,
) -> Result<crate::validate_admission::Validate> {
    let args = PyTuple::new(
        py,
        [scope.get_item("contract").unwrap().unwrap(), scope.get_item("profile").unwrap().unwrap()],
    )
    .unwrap();
    let kwargs = eval(py, scope, expression).unwrap().cast_into::<PyDict>().unwrap();
    let bound = Arguments::bind(
        &args,
        Some(&kwargs),
        &[
            "contract",
            "profile",
            "at",
            "mode",
            "state",
            "thermal_evidence",
            "max_state_age_seconds",
            "notes",
        ],
        2,
        3,
    )?;
    crate::validate_admission::admit(&bound)
}

pub fn rejected<T>(result: Result<T>, message: &str) {
    let error = match result {
        Err(error) => error,
        Ok(_) => panic!("invalid request admitted"),
    };
    match error {
        Failure::Type(text) | Failure::Value(text) => assert_eq!(text, message),
        other => panic!("unexpected adapter failure: {other:?}"),
    }
}

pub fn python_error(py: Python<'_>, error: &PyErr, name: &str, message: &str) {
    assert_eq!(error.get_type(py).name().unwrap().to_str().unwrap(), name);
    assert_eq!(
        error.value(py).getattr("args").unwrap().extract::<(String,)>().unwrap(),
        (message.into(),)
    );
    assert!(error.value(py).getattr("__cause__").unwrap().is_none());
    assert!(error.value(py).getattr("__context__").unwrap().is_none());
}
