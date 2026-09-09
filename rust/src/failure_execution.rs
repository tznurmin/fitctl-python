// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Barrier-based execution ownership and post-completion interrupt delivery.

use crate::test_support::{derive, eval, run, with_python};
use pyo3::prelude::*;
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    mpsc, Arc,
};
use std::time::Duration;

pub fn detached_ownership() {
    with_python(|py, scope| {
        let request = derive(py, &scope, "dict(at=at)").unwrap();
        let original = request.survey.core.full_artifact_json().unwrap();
        let retained = Arc::clone(&request.survey.core);
        let expected = eval(py, &scope, "data['fixtures']['contract']").unwrap();
        let expected = crate::conversion::input(&expected, false).unwrap();
        let shared = scope.clone().unbind();
        let (ready, started) = mpsc::channel();
        let (resume, released) = mpsc::channel();
        let advanced = Arc::new(AtomicUsize::new(0));
        let progress = Arc::clone(&advanced);
        let worker = std::thread::spawn(move || {
            started.recv_timeout(Duration::from_secs(2)).unwrap();
            Python::attach(|py| {
                run(
                    py,
                    shared.bind(py),
                    "exported = survey.to_dict(); exported.clear(); del survey; del policy",
                );
                progress.fetch_add(1, Ordering::SeqCst);
                drop(shared);
            });
            resume.send(()).unwrap();
        });
        let result = crate::panic_boundary::boundary(py, "derive_contract", move || {
            crate::panic_boundary::detached(py, "derive_contract", move || {
                assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 0);
                ready.send(()).unwrap();
                released.recv_timeout(Duration::from_secs(2)).unwrap();
                assert_eq!(advanced.load(Ordering::SeqCst), 1);
                crate::core_calls::derive(request)
            })
        });
        py.detach(move || worker.join().unwrap());
        assert_eq!(result.unwrap().core.full_artifact_json().unwrap(), expected);
        assert_eq!(retained.full_artifact_json().unwrap(), original);
        assert_eq!(unsafe { pyo3::ffi::PyGILState_Check() }, 1);
    });
}

struct Completion(Arc<AtomicUsize>);
impl Drop for Completion {
    fn drop(&mut self) {
        self.0.fetch_add(1, Ordering::SeqCst);
    }
}

pub fn pending_interrupt() {
    with_python(|py, scope| {
        run(py, &scope, "import signal\nsignal.signal(signal.SIGINT, signal.default_int_handler)");
        let request = derive(py, &scope, "dict(at=at)").unwrap();
        let (ready, started) = mpsc::channel();
        let (resume, released) = mpsc::channel();
        let completion = Arc::new(AtomicUsize::new(0));
        let completed = Arc::clone(&completion);
        let worker = std::thread::spawn(move || {
            started.recv_timeout(Duration::from_secs(2)).unwrap();
            // CPython permits this queue operation without acquiring the GIL.
            unsafe {
                pyo3::ffi::PyErr_SetInterrupt();
            }
            resume.send(()).unwrap();
        });
        let result = crate::panic_boundary::boundary(py, "derive_contract", move || {
            crate::panic_boundary::detached(py, "derive_contract", move || {
                let _cleanup = Completion(Arc::clone(&completed));
                ready.send(()).unwrap();
                released.recv_timeout(Duration::from_secs(2)).unwrap();
                let value = crate::core_calls::derive(request);
                assert!(value.is_ok());
                completed.fetch_add(1, Ordering::SeqCst);
                value
            })
        });
        py.detach(move || worker.join().unwrap());
        let error = match result {
            Err(error) => error,
            Ok(_) => panic!("interrupt was swallowed"),
        };
        assert_eq!(
            completion.load(Ordering::SeqCst),
            2,
            "completion and owned cleanup preceded interrupt"
        );
        assert!(error.is_instance_of::<pyo3::exceptions::PyKeyboardInterrupt>(py));
        assert!(!error.value(py).hasattr("error_model_id").unwrap());
        assert!(error.value(py).getattr("__cause__").unwrap().is_none());
        assert!(error.value(py).getattr("__context__").unwrap().is_none());
        run(py, &scope, "assert api.derive_contract(survey, policy, at=at)");
    });
}
