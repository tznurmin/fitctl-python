// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Public artifact methods; synchronous owned calls into core.

use fitctl_core::artifacts::record_v1::ArtifactRecordV1;
use fitctl_core::redact::{
    parse_builtin_redaction_profile_v1, redact_artifact_v1, RedactionRequestV1,
};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString, PyTuple, PyType};
use std::sync::Arc;

use crate::argument_binding::Arguments;
use crate::error::Failure;
use crate::panic_boundary::{boundary, detached};
use crate::serialization;
use crate::value_interface::{constructor, loader_input, no_arguments, python};
use crate::values::Artifact;

#[pymethods]
impl Artifact {
    #[new]
    #[pyo3(signature = (*args, **kwargs))]
    fn new(
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        crate::attached_boundary::arguments(py, "Artifact", args, kwargs, |args, kwargs| {
            Err(constructor(py, args, kwargs))
        })
    }

    #[classmethod]
    #[pyo3(signature = (*args, **kwargs), text_signature = "($cls, data)")]
    fn from_dict(
        _cls: &Bound<'_, PyType>,
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<Self>> {
        crate::attached_boundary::arguments(
            py,
            "Artifact.from_dict",
            args,
            kwargs,
            |args, kwargs| {
                let raw = loader_input(py, "Artifact.from_dict", false, args, kwargs)?;
                let value = detached(py, "Artifact.from_dict", move || Self::load(raw))?;
                Py::new(py, value)
            },
        )
    }

    #[classmethod]
    #[pyo3(signature = (*args, **kwargs), text_signature = "($cls, text)")]
    fn from_json(
        _cls: &Bound<'_, PyType>,
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<Self>> {
        crate::attached_boundary::arguments(
            py,
            "Artifact.from_json",
            args,
            kwargs,
            |args, kwargs| {
                let raw = loader_input(py, "Artifact.from_json", true, args, kwargs)?;
                let value = detached(py, "Artifact.from_json", move || Self::load(raw))?;
                Py::new(py, value)
            },
        )
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn to_dict<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(py, "Artifact.to_dict", args, kwargs, |args, kwargs| {
            no_arguments(py, "Artifact.to_dict", args, kwargs)?;
            let core = Arc::clone(&self.core);
            let value = detached(py, "Artifact.to_dict", move || Ok(core.full_artifact_json()?))?;
            python(py, "Artifact.to_dict", serialization::value(py, &value))
        })
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn to_json<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(py, "Artifact.to_json", args, kwargs, |args, kwargs| {
            no_arguments(py, "Artifact.to_json", args, kwargs)?;
            let core = Arc::clone(&self.core);
            let value = detached(py, "Artifact.to_json", move || {
                serialization::json(&core.full_artifact_json()?)
            })?;
            python(py, "Artifact.to_json", serialization::text(py, &value))
        })
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn semantic_hash<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(
            py,
            "Artifact.semantic_hash",
            args,
            kwargs,
            |args, kwargs| {
                no_arguments(py, "Artifact.semantic_hash", args, kwargs)?;
                let core = Arc::clone(&self.core);
                let value =
                    detached(py, "Artifact.semantic_hash", move || Ok(core.semantic_hash_hex()?))?;
                python(py, "Artifact.semantic_hash", serialization::text(py, &value))
            },
        )
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn semantic_bytes<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(
            py,
            "Artifact.semantic_bytes",
            args,
            kwargs,
            |args, kwargs| {
                no_arguments(py, "Artifact.semantic_bytes", args, kwargs)?;
                let core = Arc::clone(&self.core);
                let value =
                    detached(py, "Artifact.semantic_bytes", move || Ok(core.semantic_bytes()?))?;
                python(py, "Artifact.semantic_bytes", serialization::bytes(py, &value))
            },
        )
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self, profile, *, at)")]
    fn redact(
        &self,
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<Self>> {
        crate::attached_boundary::arguments(py, "Artifact.redact", args, kwargs, |args, kwargs| {
            let bound = python(
                py,
                "Artifact.redact",
                Arguments::bind(args, kwargs, &["profile", "at"], 1, 2),
            )?;
            for index in 0..2 {
                python(
                    py,
                    "Artifact.redact",
                    crate::conversion::exact::<PyString>(bound.required(index)),
                )?;
            }
            let profile =
                python(py, "Artifact.redact", crate::conversion::string(bound.required(0), 32))?;
            let at =
                python(py, "Artifact.redact", crate::conversion::string(bound.required(1), 64))?;
            let core = Arc::clone(&self.core);
            let value = detached(py, "Artifact.redact", move || {
                let profile = parse_builtin_redaction_profile_v1(&profile)?;
                let result = redact_artifact_v1(RedactionRequestV1 {
                    artifact: core.as_ref().clone(),
                    profile,
                    redacted_at: at,
                })?;
                Ok(Self { core: Arc::new(result) })
            })?;
            Py::new(py, value)
        })
    }

    #[getter]
    fn schema_id<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "Artifact.schema_id", || {
            python(py, "Artifact.schema_id", serialization::text(py, self.core.schema_id()))
        })
    }
    #[getter]
    fn schema_version<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "Artifact.schema_version", || {
            python(
                py,
                "Artifact.schema_version",
                serialization::value(py, &self.core.envelope().schema_version.into()),
            )
        })
    }
    #[getter]
    fn artifact_id<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "Artifact.artifact_id", || {
            python(py, "Artifact.artifact_id", serialization::text(py, self.core.artifact_id()))
        })
    }
    #[getter]
    fn verdict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "Artifact.verdict", || match self.core.as_ref() {
            ArtifactRecordV1::ValidationReport(value) => python(
                py,
                "Artifact.verdict",
                serialization::text(py, value.report.verdict.as_str()),
            ),
            _ => Ok(py.None().into_bound(py)),
        })
    }
    #[getter]
    fn primary_reason_code<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "Artifact.primary_reason_code", || match self.core.as_ref() {
            ArtifactRecordV1::ValidationReport(value) => python(
                py,
                "Artifact.primary_reason_code",
                serialization::text(py, value.report.primary_reason_code.as_str()),
            ),
            _ => Ok(py.None().into_bound(py)),
        })
    }
    fn __setattr__(
        &self,
        py: Python<'_>,
        _name: &Bound<'_, PyAny>,
        _value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        boundary(py, "Artifact", || Err(Failure::Immutable.python(py, "Artifact")))
    }
    fn __delattr__(&self, py: Python<'_>, _name: &Bound<'_, PyAny>) -> PyResult<()> {
        boundary(py, "Artifact", || Err(Failure::Immutable.python(py, "Artifact")))
    }
}
