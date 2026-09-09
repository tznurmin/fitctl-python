// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Admission ownership and failure positions, isolated by the existing runner.

use crate::argument_binding::Arguments;
use crate::error::Result;
use crate::faults::{self, Point};
use crate::test_support::{eval, python_error, rejected, run, with_python};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::sync::mpsc;
use std::time::Duration;

fn state(
    py: Python<'_>,
    scope: &Bound<'_, PyDict>,
    code: &str,
) -> Result<crate::collection_admission::StateInput> {
    let args = PyTuple::empty(py);
    let kwargs = eval(py, scope, code)
        .unwrap()
        .cast_into::<PyDict>()
        .unwrap();
    let bound = Arguments::bind(
        &args,
        Some(&kwargs),
        crate::collection_admission::STATE_NAMES,
        0,
        0,
    )?;
    crate::collection_admission::state(&bound)
}

#[test]
fn admission_and_owned_inputs() {
    with_python(|py, scope| {
        for multi in [false, true] {
            scope.set_item("multi", multi).unwrap();
            for (field, cap) in [
                ("path", 4096),
                ("path_id", 128),
                ("from_path_id", 128),
                ("to_path_id", 128),
                ("config", 4096),
            ] {
                for delta in [-1_i32, 0, 1] {
                    scope.set_item("n", cap + delta).unwrap();
                    let code = match field {
                        "path" => "dict(path_checks=[dict(path_id='a',path=pad(n,multi))])",
                        "path_id" => "dict(path_checks=[dict(path_id=pad(n,multi),path='a')])",
                        "from_path_id" => {
                            "dict(link_pairs=[dict(from_path_id=pad(n,multi),to_path_id='b')])"
                        }
                        "to_path_id" => {
                            "dict(link_pairs=[dict(from_path_id='a',to_path_id=pad(n,multi))])"
                        }
                        _ => "dict(thermal_provider_config_paths=[pad(n,multi)])",
                    };
                    if delta > 0 {
                        rejected(state(py, &scope, code), "argument budget exceeded");
                    } else {
                        state(py, &scope, code).unwrap();
                    }
                }
            }
            for index in [0, 1] {
                let cap = if index == 0 { 4096 } else { 128 };
                for delta in [-1_i32, 0, 1] {
                    scope.set_item("n", cap + delta).unwrap();
                    let args = eval(
                        py,
                        &scope,
                        if index == 0 {
                            "(pad(n,multi),'sample')"
                        } else {
                            "('root',pad(n,multi))"
                        },
                    )
                    .unwrap()
                    .cast_into::<PyTuple>()
                    .unwrap();
                    let bound =
                        Arguments::bind(&args, None, &["fixtures_root", "fixture_id"], 2, 2)
                            .unwrap();
                    let result = crate::collection_admission::replay(&bound);
                    if delta > 0 {
                        rejected(result, "argument budget exceeded");
                    } else {
                        let value = result.unwrap();
                        let text = if index == 0 {
                            value.root.to_str().unwrap()
                        } else {
                            &value.id
                        };
                        assert_eq!(text.len(), (cap + delta) as usize);
                    }
                }
            }
            for delta in [-1, 0, 1] {
                scope.set_item("delta", delta).unwrap();
                for code in [
                    "dict(path_checks=[dict(path_id=pad(1+delta,multi),path=pad(4095,multi))]+[dict(path_id='a',path=pad(4095,multi))]*15)",
                    "dict(path_checks=[dict(path_id='',path=pad(4096,multi))]*14,link_pairs=[dict(from_path_id=pad(128,multi),to_path_id=pad(128,multi))]*16,thermal_provider_config_paths=[pad(1024,multi)]*3+[pad(1024+delta,multi)])",
                ] {
                    if delta > 0 {
                        rejected(state(py, &scope, code), "argument budget exceeded");
                    } else {
                        state(py, &scope, code).unwrap();
                    }
                }
            }
        }
        for (name, cap, item) in [
            ("path_checks", 16, "dict(path_id='a',path='a')"),
            ("link_pairs", 16, "dict(from_path_id='a',to_path_id='a')"),
            ("thermal_provider_config_paths", 4, "'a'"),
        ] {
            for count in [cap - 1, cap, cap + 1] {
                let code = format!("dict({name}=[{item}]*{count})");
                if count > cap {
                    rejected(state(py, &scope, &code), "argument budget exceeded");
                } else {
                    state(py, &scope, &code).unwrap();
                }
            }
        }
        for fault in [
            crate::assertion_mutants::Fault::None,
            crate::assertion_mutants::Fault::CollectionCount,
        ] {
            crate::assertion_mutants::with_fault(fault, || {
                let result = state(
                    py,
                    &scope,
                    "dict(path_checks=[dict(path_id='a',path='a')]*17)",
                );
                assert_eq!(
                    result.is_err(),
                    fault == crate::assertion_mutants::Fault::None
                );
            });
        }
        let tests = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../tests");
        scope
            .set_item("test_path", tests.to_str().unwrap())
            .unwrap();
        run(py, &scope, "import sys,unittest\nsys.path.insert(0,test_path)\nsys.modules['fitctl']=api\nimport test_collection_admission");
        faults::reset_native_entries();
        run(py, &scope, "result=unittest.TestResult()\ntest_collection_admission.CollectionAdmissionTests('test_state_types_counts_and_precedence').run(result)\nassert result.testsRun==1 and result.wasSuccessful() and not result.skipped");
        assert_eq!(faults::native_entries(), 0);
        run(py, &scope, "supplied=dict(path_checks=[dict(path_id='a',path='a\\0b',probe_links=True)],link_pairs=[dict(from_path_id='a',to_path_id='a')],thermal_provider_config_paths=['chosen'],hardware_sensors=True)");
        let request = state(py, &scope, "supplied").unwrap();
        let shared = scope.clone().unbind();
        let (ready, started) = mpsc::channel();
        let (resume, released) = mpsc::channel();
        let worker = std::thread::spawn(move || {
            started.recv_timeout(Duration::from_secs(2)).unwrap();
            Python::attach(|py| {
                run(
                    py,
                    shared.bind(py),
                    "supplied['path_checks'][0].clear(); supplied.clear()",
                );
                drop(shared);
            });
            resume.send(()).unwrap();
        });
        let request = crate::panic_boundary::detached(py, "collect_state", move || {
            assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 0);
            ready.send(()).unwrap();
            released.recv_timeout(Duration::from_secs(2)).unwrap();
            Ok(request)
        })
        .unwrap();
        py.detach(move || worker.join().unwrap());
        assert_eq!(request.checks[0].path.to_str().unwrap(), "a\0b");
        assert_eq!(request.checks[0].path_id, "a");
        assert!(request.checks[0].probe_links);
        assert_eq!(request.pairs[0].from_path_id, request.pairs[0].to_path_id);
        assert_eq!(request.configs[0].to_str().unwrap(), "chosen");
        assert!(request.hardware_sensors);
    });
}

#[test]
fn failure_boundaries() {
    with_python(|py, scope| {
        let calls = [
            "api.replay_survey('missing','sample')",
            "api.replay_state('missing','sample')",
            "api.collect_state(path_checks=[dict(path_id='a',path='a')])",
            "api.collect_survey()",
        ];
        for expression in calls {
            for point in [Point::Conversion, Point::Detached] {
                faults::inject(point);
                crate::failure_assertions::native(py, &eval(py, &scope, expression).unwrap_err());
            }
        }
        // Only entries with admitted strings/vectors have this reservation seam.
        for (index, expression) in calls[..3].iter().enumerate() {
            // State's keyword name is copied by the shared binder first.
            faults::inject_after(Point::Reservation, usize::from(index == 2));
            crate::failure_assertions::memory(py, &eval(py, &scope, expression).unwrap_err());
        }
        for (kind, expression) in [("survey", calls[0]), ("state", calls[1])] {
            let error = eval(py, &scope, expression).unwrap_err();
            python_error(
                py,
                &error,
                "CoreError",
                &format!("replay_{kind}: fixture_corpus_invalid"),
            );
            assert_eq!(
                error
                    .value(py)
                    .getattr("error_model_id")
                    .unwrap()
                    .extract::<String>()
                    .unwrap(),
                format!("fitctl.{kind}.v1")
            );
            assert_eq!(
                error
                    .value(py)
                    .getattr("error_model_version")
                    .unwrap()
                    .extract::<u32>()
                    .unwrap(),
                1
            );
            assert_eq!(
                error
                    .value(py)
                    .getattr("checkpoint_id")
                    .unwrap()
                    .extract::<String>()
                    .unwrap(),
                "fixture_load"
            );
            for position in 0..6 {
                faults::inject_after(Point::Exception, position);
                crate::failure_assertions::memory(py, &eval(py, &scope, expression).unwrap_err());
            }
        }
        let reference: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/collection/core-reference.json"
        ))
        .unwrap();
        let value = crate::values::Artifact::load(
            reference["observations"]["survey/complete"]["value"].clone(),
        )
        .unwrap();
        scope
            .set_item("collected", Py::new(py, value).unwrap())
            .unwrap();
        for (point, expression) in [
            (Point::Export, "collected.to_dict()"),
            (Point::ExportMemory, "collected.to_dict()"),
            (Point::Encode, "collected.to_json()"),
            (Point::PartialExport, "collected.to_dict()"),
            (Point::PartialMemory, "collected.to_dict()"),
        ] {
            faults::inject(point);
            let error = eval(py, &scope, expression).unwrap_err();
            if matches!(point, Point::ExportMemory | Point::PartialMemory) {
                crate::failure_assertions::memory(py, &error);
            } else {
                let (reason, checkpoint, message) = if point == Point::Encode {
                    (
                        "json_encode_failed",
                        "json_encode",
                        "JSON serialization failed",
                    )
                } else {
                    (
                        "export_conversion_failed",
                        "python_export",
                        "native value export failed",
                    )
                };
                crate::failure_assertions::structured(
                    py,
                    &error,
                    "SerializationError",
                    "fitctl.python.serialization.v1",
                    reason,
                    checkpoint,
                    message,
                );
            }
            assert!(eval(py, &scope, expression).is_ok());
        }
    });
}
