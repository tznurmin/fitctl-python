// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Rust-owned request adaptation. Evidence and decision semantics remain in core.

use crate::derive_admission::Derive;
use crate::error::{Result, KIND};
use crate::validate_admission::Validate;
use crate::values::Artifact;
use fitctl_core::artifacts::record_v1::ArtifactRecordV1;
use fitctl_core::config::{self, ResolveConfigurationRequestV1};
use fitctl_core::contract::{self, ContractDerivationRequestV1, DerivationContextV1};
use fitctl_core::validate::{validate_request_v1, ValidationRequestV1};
use std::sync::Arc;

pub fn derive(input: Derive) -> Result<Artifact> {
    crate::faults::detached();
    let ArtifactRecordV1::Survey(survey) = input.survey.core.as_ref() else {
        return Err(KIND);
    };
    let basis = if input.packs.is_empty() && input.context.is_none() {
        None
    } else {
        let packs = input
            .packs
            .into_iter()
            .map(config::load_extension_pack_from_value)
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let context = input.context.map(config::load_invocation_context_from_value).transpose()?;
        crate::faults::resolver_entry();
        let resolved = config::resolve_configuration_v1(ResolveConfigurationRequestV1 {
            policy: input.policy.core.as_ref().clone(),
            trust_policy: None,
            extension_packs: packs.clone(),
            recommendation_packs: Vec::new(),
            invocation_context: context,
            selected_policy_pack_id: None,
            selected_policy_entry_id: None,
            selected_policy_entry_source: None,
            selected_policy_pack_lock_id: None,
            selected_policy_pack_lock_signed: None,
            selected_service_profile_catalogue_id: None,
            selected_service_profile_entry_id: None,
            selected_service_profile_entry_source: None,
        })?;
        config::build_extension_basis_v1(&resolved, &packs)?
    };
    let request = ContractDerivationRequestV1 {
        survey: survey.clone(),
        policy: input.policy.core.as_ref().clone(),
        live_state: None,
        derivation_context: DerivationContextV1 { derived_at: input.at, notes: input.notes },
    };
    let contract = match basis {
        Some(basis) => contract::derive_host_contract_with_extensions_v1(request, basis)?,
        None => contract::derive_host_contract_v1(request)?,
    };
    Ok(Artifact { core: Arc::new(ArtifactRecordV1::Contract(contract)) })
}

pub fn validate(input: Validate) -> Result<Artifact> {
    crate::faults::detached();
    let ArtifactRecordV1::Contract(contract) = input.contract.core.as_ref() else {
        return Err(KIND);
    };
    let ArtifactRecordV1::ServiceProfile(profile) = input.profile.core.as_ref() else {
        return Err(KIND);
    };
    let state = input
        .state
        .map(|value| match value.core.as_ref() {
            ArtifactRecordV1::State(state) => Ok(state.clone()),
            _ => Err(KIND),
        })
        .transpose()?;
    let thermal = input
        .thermal
        .into_iter()
        .map(|value| match value.core.as_ref() {
            ArtifactRecordV1::ThermalEvidence(thermal) => Ok(thermal.clone()),
            _ => Err(KIND),
        })
        .collect::<Result<Vec<_>>>()?;
    let report = validate_request_v1(ValidationRequestV1 {
        contract: contract.clone(),
        service_profile: profile.clone(),
        host_state: state,
        thermal_evidence: thermal,
        mode: input.mode,
        validated_at: input.at,
        notes: input.notes,
        max_state_age_seconds: input.age,
    })?;
    Ok(Artifact { core: Arc::new(ArtifactRecordV1::ValidationReport(report)) })
}
