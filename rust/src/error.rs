// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Typed, owned failures; no core diagnostic text enters Python exceptions.

use pyo3::create_exception;
use pyo3::exceptions::{PyException, PyMemoryError};
use pyo3::prelude::*;
use pyo3::types::PyType;

create_exception!(fitctl, FitctlError, PyException);
create_exception!(fitctl, CoreError, FitctlError);
create_exception!(fitctl, DecodeError, FitctlError);
create_exception!(fitctl, SerializationError, FitctlError);
create_exception!(fitctl, NativeError, FitctlError);

#[derive(Debug)]
pub enum Failure {
    Type(&'static str),
    Value(&'static str),
    Overflow,
    Key,
    Immutable,
    Memory,
    Decode(&'static str),
    JsonEncode,
    Export,
    Panic,
    Core { model: &'static str, version: u32, reason: &'static str, checkpoint: &'static str },
}

pub type Result<T> = std::result::Result<T, Failure>;
pub const TYPE: Failure = Failure::Type("invalid argument type");
pub const ARGUMENTS: Failure = Failure::Type("invalid arguments");
pub const BUDGET: Failure = Failure::Value("argument budget exceeded");
pub const KIND: Failure = Failure::Value("incompatible artifact kind");

macro_rules! core_failure {
    ($t:ty) => {
        impl From<$t> for Failure {
            fn from(error: $t) -> Self {
                Self::Core {
                    model: error.error_model_id,
                    version: error.error_model_version,
                    reason: error.code.as_str(),
                    checkpoint: error.checkpoint_id,
                }
            }
        }
    };
}
core_failure!(fitctl_core::contract::ContractDerivationError);
core_failure!(fitctl_core::service_profile::ServiceProfileError);
core_failure!(fitctl_core::config::ConfigError);
core_failure!(fitctl_core::artifacts::record_v1::ArtifactRecordError);
core_failure!(fitctl_core::validate::ValidationError);
core_failure!(fitctl_core::redact::RedactionError);
core_failure!(fitctl_core::classify::BatchClassificationError);
core_failure!(fitctl_core::survey::SurveyError);
core_failure!(fitctl_core::state::StateError);

pub fn no_memory(py: Python<'_>) -> PyErr {
    unsafe {
        pyo3::ffi::PyErr_NoMemory();
    }
    PyErr::fetch(py)
}

pub fn export_failure(py: Python<'_>, error: PyErr) -> Failure {
    if error.is_instance_of::<PyMemoryError>(py) {
        Failure::Memory
    } else {
        Failure::Export
    }
}

fn structured(
    py: Python<'_>,
    class: Bound<'_, PyType>,
    model: &str,
    version: u32,
    reason: &str,
    checkpoint: &str,
    message: String,
) -> PyResult<PyErr> {
    crate::faults::exception_field()?;
    let value = class.call1((&message,))?;
    #[cfg(test)]
    if crate::assertion_mutants::active(crate::assertion_mutants::Fault::Fields) {
        return Ok(PyErr::from_value(value));
    }
    for (key, text) in [
        ("error_model_id", model),
        ("reason_code", reason),
        ("checkpoint_id", checkpoint),
        ("message", message.as_str()),
    ] {
        crate::faults::exception_field()?;
        value.setattr(key, crate::serialization::text(py, text).map_err(|_| no_memory(py))?)?;
    }
    crate::faults::exception_field()?;
    value.setattr("error_model_version", version)?;
    Ok(PyErr::from_value(value))
}

impl Failure {
    pub fn python(self, py: Python<'_>, operation: &'static str) -> PyErr {
        use pyo3::exceptions::{
            PyAttributeError, PyKeyError, PyOverflowError, PyTypeError, PyValueError,
        };
        let (class, model, version, reason, checkpoint, message) = match self {
            Self::Type(text) => return PyTypeError::new_err(text),
            Self::Value(text) => return PyValueError::new_err(text),
            Self::Overflow => return PyOverflowError::new_err("integer outside supported range"),
            Self::Key => return PyKeyError::new_err("unknown builtin configuration"),
            Self::Immutable => return PyAttributeError::new_err("native value is immutable"),
            Self::Memory => return no_memory(py),
            Self::Core { model, version, reason, checkpoint } => (
                py.get_type::<CoreError>(),
                model,
                version,
                reason,
                checkpoint,
                format!("{operation}: {reason}"),
            ),
            Self::Decode(reason) => (
                py.get_type::<DecodeError>(),
                "fitctl.python.decode.v1",
                1,
                reason,
                "json_decode",
                format!("JSON decode failed: {reason}"),
            ),
            Self::JsonEncode => (
                py.get_type::<SerializationError>(),
                "fitctl.python.serialization.v1",
                1,
                "json_encode_failed",
                "json_encode",
                "JSON serialization failed".into(),
            ),
            Self::Export => (
                py.get_type::<SerializationError>(),
                "fitctl.python.serialization.v1",
                1,
                "export_conversion_failed",
                "python_export",
                "native value export failed".into(),
            ),
            Self::Panic => (
                py.get_type::<NativeError>(),
                "fitctl.python.native.v1",
                1,
                "native_panic",
                "native_call",
                "native operation panicked".into(),
            ),
        };
        structured(py, class, model, version, reason, checkpoint, message)
            .unwrap_or_else(|_| no_memory(py))
    }
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    module.add("FitctlError", py.get_type::<FitctlError>())?;
    module.add("CoreError", py.get_type::<CoreError>())?;
    module.add("DecodeError", py.get_type::<DecodeError>())?;
    module.add("SerializationError", py.get_type::<SerializationError>())?;
    module.add("NativeError", py.get_type::<NativeError>())
}
