// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Dedicated-process panic controls; only this test harness installs hooks.

use crate::failure_assertions::native;
use crate::faults::{inject, Point};
use crate::test_support::{eval, run, with_python};
use std::panic::{set_hook, take_hook, PanicHookInfo};
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc,
};

type Hook = Box<dyn Fn(&PanicHookInfo<'_>) + Send + Sync + 'static>;

pub fn caught(emit: bool) {
    let previous = take_hook();
    let count = Arc::new(AtomicUsize::new(0));
    let observed = Arc::clone(&count);
    let hook: Hook = Box::new(move |_| {
        observed.fetch_add(1, Ordering::SeqCst);
        if emit {
            eprintln!("CALLER_HOOK ADAPTER_INPUT_SENTINEL synthetic.rs:1");
        }
    });
    let address = (&*hook) as *const _ as *const () as usize;
    set_hook(hook);
    // Initialization occurs after the caller hook was installed.
    with_python(|py, scope| {
        run(py, &scope, "before = survey.to_json(); raw = survey.to_dict()");
        let cases = if emit {
            vec![(Point::Detached, "api.Artifact.from_dict(raw)")]
        } else {
            vec![
                (Point::Conversion, "api.Artifact.from_dict(raw)"),
                (Point::Detached, "api.Artifact.from_dict(raw)"),
                (Point::ExportPanic, "survey.to_dict()"),
            ]
        };
        for (index, (point, expression)) in cases.into_iter().enumerate() {
            inject(point);
            let error = eval(py, &scope, expression).unwrap_err();
            native(py, &error);
            assert_eq!(count.load(Ordering::SeqCst), index + 1);
            run(py, &scope, "assert before == survey.to_json(); assert raw == survey.to_dict()");
        }
    });
    let retained = take_hook();
    let unchanged = (&*retained) as *const _ as *const () as usize == address;
    set_hook(previous);
    assert!(unchanged, "the library must leave the caller hook installed");
}

struct DropPanic;
impl Drop for DropPanic {
    fn drop(&mut self) {
        panic!("ADAPTER_INPUT_SENTINEL destructor");
    }
}

pub fn terminal_variant(variant: &str) {
    match variant {
        "abort" => std::process::abort(),
        "double" => {
            let _payload = DropPanic;
            panic!("ADAPTER_INPUT_SENTINEL unwind");
        }
        "payload_drop" => with_python(|py, _scope| {
            let _: pyo3::PyResult<()> = crate::panic_boundary::boundary(py, "terminal", || {
                std::panic::panic_any(DropPanic);
            });
            panic!("terminal panic returned");
        }),
        _ => panic!("invalid terminal test variant"),
    }
}

pub fn terminal() {
    if let Ok(variant) = std::env::var("FITCTL_TEST_TERMINAL_VARIANT") {
        terminal_variant(&variant);
        panic!("terminal variant returned");
    }
    use std::io::Read;
    use std::os::unix::process::ExitStatusExt;
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};
    for variant in ["payload_drop", "abort", "double"] {
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "failure_tests::terminal_panic", "--test-threads=1", "--nocapture"])
            .env("FITCTL_TEST_TERMINAL_VARIANT", variant)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let status = loop {
            if let Some(status) = child.try_wait().unwrap() {
                break status;
            }
            if Instant::now() >= deadline {
                child.kill().unwrap();
                child.wait().unwrap();
                panic!("terminal child exceeded deadline");
            }
            std::thread::sleep(Duration::from_millis(5));
        };
        assert_eq!(status.signal(), Some(6));
        assert_eq!(child.wait().unwrap(), status, "terminated child was reaped");
        let mut output = String::new();
        child.stdout.take().unwrap().take(65_537).read_to_string(&mut output).unwrap();
        assert!(output.len() <= 65_536);
        assert!(!output.contains("test result:") && !output.contains("RECORDED_RESULT="));
    }
    // The same process can still adapt an ordinary catchable panic.
    caught(false);
}
