// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Validated immutable batch values and complete report-view serialization.

use crate::error::{Failure, Result};
use crate::panic_boundary::{boundary, detached};
use crate::serialization;
use crate::value_interface::python;
use fitctl_core::artifacts::batch_classification_report_v1::BatchClassificationReportV1;
use fitctl_core::classify::load_batch_classification_report_from_value;
use pyo3::prelude::*;
use serde_json::Value;
use std::sync::Arc;

#[pyclass(module = "fitctl", frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct BatchReport {
    pub core: Arc<BatchClassificationReportV1>,
}

#[derive(Clone, Copy)]
pub enum Part {
    Full,
    Rows,
    Contracts,
    Profiles,
}

pub fn value(core: &BatchClassificationReportV1, part: Part) -> Result<Value> {
    match part {
        Part::Full => serde_json::to_value(core),
        Part::Rows => serde_json::to_value(&core.report.rows),
        Part::Contracts => serde_json::to_value(&core.report.contract_summaries),
        Part::Profiles => serde_json::to_value(&core.report.service_profile_summaries),
    }
    .map_err(|_| Failure::Export)
}

impl BatchReport {
    pub fn load(raw: Value) -> Result<Self> {
        crate::faults::detached();
        let core = load_batch_classification_report_from_value(raw)?;
        Ok(Self {
            core: Arc::new(core),
        })
    }

    pub fn export<'py>(
        &self,
        py: Python<'py>,
        operation: &'static str,
        part: Part,
    ) -> PyResult<Bound<'py, PyAny>> {
        boundary(py, operation, || {
            let core = Arc::clone(&self.core);
            let raw = detached(py, operation, move || value(&core, part))?;
            python(py, operation, serialization::value(py, &raw))
        })
    }
}
