// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Validated immutable core values, with input preservation for policies.

use crate::error::{Result, KIND, TYPE};
use fitctl_core::artifacts::record_v1::{load_artifact_record_from_value, ArtifactRecordV1};
use fitctl_core::artifacts::schema_ids_v1::{
    CONFIG_BUNDLE_SCHEMA_ID, DECISION_BUNDLE_SCHEMA_ID, SERVICE_PROFILE_SCHEMA_ID,
};
use fitctl_core::policy::{load_policy_document_from_value, PolicyDocumentV1};
use fitctl_core::service_profile::load_service_profile_from_value;
use pyo3::prelude::*;
use serde_json::Value;
use std::sync::Arc;

#[pyclass(module = "fitctl", frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct Artifact {
    pub core: Arc<ArtifactRecordV1>,
}

#[pyclass(module = "fitctl", frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct Policy {
    pub core: Arc<PolicyDocumentV1>,
    pub raw: Arc<Value>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Role {
    Survey,
    Contract,
    Profile,
    State,
    Thermal,
}

impl Artifact {
    pub fn load(raw: Value) -> Result<Self> {
        crate::faults::detached();
        let schema = raw.get("envelope").and_then(|v| v.get("schema_id")).and_then(Value::as_str);
        let core = match schema {
            Some(CONFIG_BUNDLE_SCHEMA_ID | DECISION_BUNDLE_SCHEMA_ID) => return Err(KIND),
            Some(SERVICE_PROFILE_SCHEMA_ID) => {
                ArtifactRecordV1::ServiceProfile(load_service_profile_from_value(raw)?)
            }
            _ => load_artifact_record_from_value(raw)?,
        };
        Ok(Self { core: Arc::new(core) })
    }

    pub fn role(&self, expected: Role) -> Result<()> {
        let actual = match self.core.as_ref() {
            ArtifactRecordV1::Survey(_) => Some(Role::Survey),
            ArtifactRecordV1::Contract(_) => Some(Role::Contract),
            ArtifactRecordV1::ServiceProfile(_) => Some(Role::Profile),
            ArtifactRecordV1::State(_) => Some(Role::State),
            ArtifactRecordV1::ThermalEvidence(_) => Some(Role::Thermal),
            _ => None,
        };
        if actual == Some(expected) {
            Ok(())
        } else {
            Err(KIND)
        }
    }

    pub fn handle(value: &Bound<'_, PyAny>, role: Role) -> Result<Self> {
        crate::conversion::exact::<Self>(value)?;
        let artifact = value.extract::<PyRef<'_, Self>>().map_err(|_| TYPE)?;
        artifact.role(role)?;
        Ok(artifact.clone())
    }
}

impl Policy {
    pub fn load(raw: Value) -> Result<Self> {
        crate::faults::detached();
        let core = load_policy_document_from_value(raw.clone())?;
        Ok(Self { core: Arc::new(core), raw: Arc::new(raw) })
    }

    pub fn handle(value: &Bound<'_, PyAny>) -> Result<Self> {
        crate::conversion::exact::<Self>(value)?;
        Ok(value.extract::<PyRef<'_, Self>>().map_err(|_| TYPE)?.clone())
    }
}
