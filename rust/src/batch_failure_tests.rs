// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Isolated batch admission, execution ownership and returned-failure tests.

use crate::faults::{self, Point};
use crate::test_support::{eval, python_error, run, with_python};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::sync::{mpsc, Arc};
use std::time::Duration;

#[test]
fn admission_and_ownership() {
    with_python(|py, scope| {
        for (expression, class, message) in [
            (
                "api.classify_batch([contract]*17,[profile],at=at)",
                "ValueError",
                "argument budget exceeded",
            ),
            (
                "api.classify_batch([contract]*5,[profile]*13,at=at)",
                "ValueError",
                "argument budget exceeded",
            ),
            (
                "api.classify_batch([contract],[profile],at='a'*65)",
                "ValueError",
                "argument budget exceeded",
            ),
            (
                "api.classify_batch(Items(),[profile],at=at)",
                "TypeError",
                "invalid argument type",
            ),
            (
                "api.classify_batch([survey],[profile],at=at)",
                "ValueError",
                "incompatible artifact kind",
            ),
            (
                "api.classify_batch([contract],[profile],at=at,max_state_age_seconds=True)",
                "TypeError",
                "invalid argument type",
            ),
            (
                "api.classify_batch([contract],[profile],at=at,max_state_age_seconds=-1)",
                "OverflowError",
                "integer outside supported range",
            ),
        ] {
            faults::reset_native_entries();
            let error = eval(py, &scope, expression).unwrap_err();
            python_error(py, &error, class, message);
            assert_eq!(faults::native_entries(), 0);
        }
        let args = eval(py, &scope, "([contract],[profile])")
            .unwrap()
            .cast_into::<PyTuple>()
            .unwrap();
        let kwargs = eval(py, &scope, "dict(at=at)")
            .unwrap()
            .cast_into::<PyDict>()
            .unwrap();
        let bound = crate::argument_binding::Arguments::bind(
            &args,
            Some(&kwargs),
            &[
                "contracts",
                "profiles",
                "at",
                "mode",
                "states",
                "max_state_age_seconds",
            ],
            2,
            3,
        )
        .unwrap();
        let request = crate::batch_admission::admit(&bound).unwrap();
        let retained = Arc::clone(&request.contracts[0].core);
        let original = retained.full_artifact_json().unwrap();
        drop(bound);
        drop(args);
        drop(kwargs);
        let shared = scope.clone().unbind();
        let (ready, started) = mpsc::channel();
        let (resume, released) = mpsc::channel();
        let worker = std::thread::spawn(move || {
            started.recv_timeout(Duration::from_secs(2)).unwrap();
            Python::attach(|py| {
                run(
                    py,
                    shared.bind(py),
                    "exported=contract.to_dict(); exported.clear(); del contract; del profile",
                );
                drop(shared);
            });
            resume.send(()).unwrap();
        });
        faults::reset_native_entries();
        let result = crate::panic_boundary::boundary(py, "classify_batch", move || {
            crate::panic_boundary::detached(py, "classify_batch", move || {
                assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 0);
                ready.send(()).unwrap();
                released.recv_timeout(Duration::from_secs(2)).unwrap();
                crate::batch::execute(request)
            })
        })
        .unwrap();
        py.detach(move || worker.join().unwrap());
        assert_eq!(faults::native_entries(), 1);
        assert_eq!(retained.full_artifact_json().unwrap(), original);
        assert_eq!(result.core.report.rows.len(), 1);
        assert_eq!(result.core.report.rows[0].verdict.as_str(), "fit");
        assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 1);
    });
    with_python(|py, scope| {
        let tests = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../tests");
        scope
            .set_item("test_path", tests.to_str().unwrap())
            .unwrap();
        run(py, &scope, "import sys,unittest\nsys.path.insert(0,test_path)\nsys.modules['fitctl']=api\nimport test_batch_errors");
        for fault in [
            crate::assertion_mutants::Fault::None,
            crate::assertion_mutants::Fault::BatchCount,
        ] {
            crate::assertion_mutants::with_fault(fault, || {
                run(py, &scope, "result=unittest.TestResult()\ntest_batch_errors.BatchErrorTests('test_collection_boundaries').run(result)");
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
                    fault == crate::assertion_mutants::Fault::None
                );
            });
        }
    });
}

#[test]
fn returned_failures_and_unwinds() {
    with_python(|py, scope| {
        run(
            py,
            &scope,
            "batch=api.classify_batch([contract],[profile],at=at)\nraw_batch=batch.to_dict()",
        );
        for expression in [
            "api.classify_batch([contract],[profile],at=at)",
            "api.BatchReport.from_dict(raw_batch)",
        ] {
            faults::inject(Point::Reservation);
            crate::failure_assertions::memory(py, &eval(py, &scope, expression).unwrap_err());
            assert!(eval(py, &scope, expression).is_ok());
        }
        for expression in [
            "batch.to_dict()",
            "batch.to_json()",
            "batch.rows",
            "batch.contract_summaries",
            "batch.service_profile_summaries",
            "batch.export_csv('rows_csv')",
        ] {
            for (point, memory) in [(Point::Export, false), (Point::ExportMemory, true)] {
                faults::inject(point);
                let error = eval(py, &scope, expression).unwrap_err();
                if memory {
                    crate::failure_assertions::memory(py, &error);
                } else {
                    crate::failure_assertions::structured(
                        py,
                        &error,
                        "SerializationError",
                        "fitctl.python.serialization.v1",
                        "export_conversion_failed",
                        "python_export",
                        "native value export failed",
                    );
                }
                assert!(eval(py, &scope, expression).is_ok());
            }
        }
        faults::inject(Point::Encode);
        crate::failure_assertions::structured(
            py,
            &eval(py, &scope, "batch.to_json()").unwrap_err(),
            "SerializationError",
            "fitctl.python.serialization.v1",
            "json_encode_failed",
            "json_encode",
            "JSON serialization failed",
        );
        for (point, expression) in [
            (Point::Conversion, "api.BatchReport.from_dict(raw_batch)"),
            (
                Point::Detached,
                "api.classify_batch([contract],[profile],at=at)",
            ),
            (
                Point::Detached,
                "api.BatchReport.from_json(batch.to_json())",
            ),
            (Point::ExportPanic, "batch.rows"),
        ] {
            faults::inject(point);
            crate::failure_assertions::native(py, &eval(py, &scope, expression).unwrap_err());
            assert!(eval(py, &scope, expression).is_ok());
        }
        for point in [Point::PartialExport, Point::PartialMemory] {
            faults::inject_after(point, 2);
            let error = eval(py, &scope, "batch.to_dict()").unwrap_err();
            if point == Point::PartialMemory {
                crate::failure_assertions::memory(py, &error);
            } else {
                crate::failure_assertions::structured(
                    py,
                    &error,
                    "SerializationError",
                    "fitctl.python.serialization.v1",
                    "export_conversion_failed",
                    "python_export",
                    "native value export failed",
                );
            }
            assert!(eval(py, &scope, "batch.to_dict() == raw_batch")
                .unwrap()
                .is_truthy()
                .unwrap());
        }
        let error = eval(py, &scope, "api.classify_batch([], [profile], at=at)").unwrap_err();
        python_error(
            py,
            &error,
            "CoreError",
            "classify_batch: batch_input_invalid",
        );
        assert_eq!(
            error
                .value(py)
                .getattr("error_model_version")
                .unwrap()
                .extract::<u32>()
                .unwrap(),
            2
        );
        faults::inject(Point::Exception);
        crate::failure_assertions::memory(
            py,
            &eval(py, &scope, "api.classify_batch([], [profile], at=at)").unwrap_err(),
        );
        assert!(eval(py, &scope, "batch.to_dict() == raw_batch")
            .unwrap()
            .is_truthy()
            .unwrap());
    });
}
