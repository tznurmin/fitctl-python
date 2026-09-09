// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Public batch factories, immutable accessors and native CSV presentation.

use crate::argument_binding::Arguments;
use crate::batch_value::{self, BatchReport, Part};
use crate::error::Failure;
use crate::panic_boundary::{boundary, detached};
use crate::serialization;
use crate::value_interface::{constructor, loader_input, no_arguments, python};
use fitctl_core::classify::{
    render_batch_classification_export_view, BatchClassificationExportViewV1,
};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple, PyType};
use std::sync::Arc;

#[pymethods]
impl BatchReport {
    #[new]
    #[pyo3(signature = (*args, **kwargs))]
    fn new(
        py: Python<'_>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        crate::attached_boundary::arguments(py, "BatchReport", args, kwargs, |args, kwargs| {
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
            "BatchReport.from_dict",
            args,
            kwargs,
            |args, kwargs| {
                let raw = loader_input(py, "BatchReport.from_dict", false, args, kwargs)?;
                let value = detached(py, "BatchReport.from_dict", move || Self::load(raw))?;
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
            "BatchReport.from_json",
            args,
            kwargs,
            |args, kwargs| {
                let raw = loader_input(py, "BatchReport.from_json", true, args, kwargs)?;
                let value = detached(py, "BatchReport.from_json", move || Self::load(raw))?;
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
        crate::attached_boundary::arguments(
            py,
            "BatchReport.to_dict",
            args,
            kwargs,
            |args, kwargs| {
                no_arguments(py, "BatchReport.to_dict", args, kwargs)?;
                self.export(py, "BatchReport.to_dict", Part::Full)
            },
        )
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self)")]
    fn to_json<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(
            py,
            "BatchReport.to_json",
            args,
            kwargs,
            |args, kwargs| {
                no_arguments(py, "BatchReport.to_json", args, kwargs)?;
                let core = Arc::clone(&self.core);
                let value = detached(py, "BatchReport.to_json", move || {
                    serialization::json(&batch_value::value(&core, Part::Full)?)
                })?;
                python(py, "BatchReport.to_json", serialization::text(py, &value))
            },
        )
    }

    #[pyo3(signature = (*args, **kwargs), text_signature = "($self, view)")]
    fn export_csv<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        crate::attached_boundary::arguments(
            py,
            "BatchReport.export_csv",
            args,
            kwargs,
            |args, kwargs| {
                let bound = python(
                    py,
                    "BatchReport.export_csv",
                    Arguments::bind(args, kwargs, &["view"], 1, 1),
                )?;
                let view = python(
                    py,
                    "BatchReport.export_csv",
                    crate::conversion::string(bound.required(0), 32),
                )?;
                let view = match view.as_str() {
                    "rows_csv" => BatchClassificationExportViewV1::RowsCsv,
                    "contract_summary_csv" => BatchClassificationExportViewV1::ContractSummaryCsv,
                    "service_profile_summary_csv" => {
                        BatchClassificationExportViewV1::ServiceProfileSummaryCsv
                    }
                    _ => {
                        return Err(Failure::Value("unsupported batch export view")
                            .python(py, "BatchReport.export_csv"))
                    }
                };
                let core = Arc::clone(&self.core);
                let value = detached(py, "BatchReport.export_csv", move || {
                    Ok(render_batch_classification_export_view(&core, view))
                })?;
                python(
                    py,
                    "BatchReport.export_csv",
                    serialization::text(py, &value),
                )
            },
        )
    }

    #[getter]
    fn schema_id<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "BatchReport.schema_id", || {
            python(
                py,
                "BatchReport.schema_id",
                serialization::text(py, &self.core.envelope.schema_id),
            )
        })
    }
    #[getter]
    fn schema_version<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "BatchReport.schema_version", || {
            python(
                py,
                "BatchReport.schema_version",
                serialization::value(py, &self.core.envelope.schema_version.into()),
            )
        })
    }
    #[getter]
    fn artifact_id<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, "BatchReport.artifact_id", || {
            python(
                py,
                "BatchReport.artifact_id",
                serialization::text(py, &self.core.envelope.artifact_id),
            )
        })
    }
    #[getter]
    fn rows<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.export(py, "BatchReport.rows", Part::Rows)
    }
    #[getter]
    fn contract_summaries<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.export(py, "BatchReport.contract_summaries", Part::Contracts)
    }
    #[getter]
    fn service_profile_summaries<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.export(py, "BatchReport.service_profile_summaries", Part::Profiles)
    }
    fn __setattr__(
        &self,
        py: Python<'_>,
        _name: &Bound<'_, PyAny>,
        _value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        boundary(py, "BatchReport", || {
            Err(Failure::Immutable.python(py, "BatchReport"))
        })
    }
    fn __delattr__(&self, py: Python<'_>, _name: &Bound<'_, PyAny>) -> PyResult<()> {
        boundary(py, "BatchReport", || {
            Err(Failure::Immutable.python(py, "BatchReport"))
        })
    }
}
