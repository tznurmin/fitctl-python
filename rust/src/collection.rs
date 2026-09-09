// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Explicit synchronous collection through core engines and validated config paths.

use crate::argument_binding::Arguments;
use crate::collection_admission;
use crate::error::Result;
use crate::panic_boundary::detached;
use crate::value_interface::python;
use crate::values::Artifact;
use fitctl_core::artifacts::record_v1::ArtifactRecordV1;
use fitctl_core::{state, survey};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::sync::Arc;

fn replay(input: collection_admission::ReplayInput, survey: bool) -> Result<Artifact> {
    crate::faults::detached();
    let record = if survey {
        ArtifactRecordV1::Survey(
            survey::SurveyEngineV1::new(survey::NoopLiveProbeV1).collect_host_survey(
                survey::SurveyModeV1::Replay {
                    fixtures_root: input.root,
                    fixture_id: input.id,
                },
            )?,
        )
    } else {
        ArtifactRecordV1::State(
            state::StateEngineV1::new(state::NoopLiveStateProbeV1).collect_host_state(
                state::StateModeV1::Replay {
                    fixtures_root: input.root,
                    fixture_id: input.id,
                },
            )?,
        )
    };
    Ok(Artifact {
        core: Arc::new(record),
    })
}

fn replay_entry(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
    operation: &'static str,
    survey: bool,
) -> PyResult<Py<Artifact>> {
    crate::attached_boundary::arguments(py, operation, args, kwargs, |args, kwargs| {
        crate::faults::conversion();
        let bound = python(
            py,
            operation,
            Arguments::bind(args, kwargs, &["fixtures_root", "fixture_id"], 2, 2),
        )?;
        let input = python(py, operation, collection_admission::replay(&bound))?;
        let value = detached(py, operation, move || replay(input, survey))?;
        Py::new(py, value)
    })
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(fixtures_root, fixture_id)")]
pub fn replay_survey(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<Artifact>> {
    replay_entry(py, args, kwargs, "replay_survey", true)
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(fixtures_root, fixture_id)")]
pub fn replay_state(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<Artifact>> {
    replay_entry(py, args, kwargs, "replay_state", false)
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "()")]
pub fn collect_survey(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<Artifact>> {
    crate::attached_boundary::arguments(py, "collect_survey", args, kwargs, |args, kwargs| {
        crate::faults::conversion();
        python(
            py,
            "collect_survey",
            Arguments::bind(args, kwargs, &[], 0, 0),
        )?;
        let value = detached(py, "collect_survey", || {
            crate::faults::detached();
            let value = survey::SurveyEngineV1::new(survey::LocalLiveProbeV1)
                .collect_host_survey(survey::SurveyModeV1::Live)?;
            Ok(Artifact {
                core: Arc::new(ArtifactRecordV1::Survey(value)),
            })
        })?;
        Py::new(py, value)
    })
}

#[pyfunction]
#[pyo3(signature = (*args, **kwargs), text_signature = "(*, path_checks=None, link_pairs=None, thermal_provider_config_paths=None, memory_reliability=False, gpu_reliability=False, hardware_sensors=False)")]
pub fn collect_state(
    py: Python<'_>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<Artifact>> {
    crate::attached_boundary::arguments(py, "collect_state", args, kwargs, |args, kwargs| {
        crate::faults::conversion();
        let bound = python(
            py,
            "collect_state",
            Arguments::bind(args, kwargs, collection_admission::STATE_NAMES, 0, 0),
        )?;
        let input = python(py, "collect_state", collection_admission::state(&bound))?;
        let value = detached(py, "collect_state", move || {
            crate::faults::detached();
            let providers = state::thermal_v1::load_thermal_provider_config_entries_from_paths_v1(
                &input.configs,
            )?;
            let probe =
                state::LocalLiveStateProbeV1::new_with_path_link_pairs_and_thermal_providers(
                    input.checks,
                    input.pairs,
                    providers,
                )
                .with_memory_reliability_collection(input.memory_reliability)
                .with_gpu_reliability_collection(input.gpu_reliability)
                .with_hardware_sensor_collection(input.hardware_sensors);
            let value =
                state::StateEngineV1::new(probe).collect_host_state(state::StateModeV1::Live)?;
            Ok(Artifact {
                core: Arc::new(ArtifactRecordV1::State(value)),
            })
        })?;
        Py::new(py, value)
    })
}
