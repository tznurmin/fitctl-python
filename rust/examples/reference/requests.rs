// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Independent, direct-core caller for admitted recorded request vectors.

use super::output::Result;
use fitctl_core::artifacts::record_v1::{load_artifact_record_from_value, ArtifactRecordV1};
use fitctl_core::{config, contract, policy, redact, service_profile, validate};
use serde_json::Value;

pub fn optional<'a>(kwargs: &'a Value, name: &str) -> Option<&'a Value> {
    kwargs.get(name).filter(|value| !value.is_null())
}

pub fn asset(category: &str, identity: &str) -> Option<Value> {
    config::built_in_config_assets_v1()
        .iter()
        .find(|asset| asset.category == category && asset.id == identity)
        .map(|asset| serde_json::from_str(asset.contents).expect("embedded configuration JSON"))
}

pub fn derive(fixtures: &Value, kwargs: &Value) -> Result<Value> {
    let ArtifactRecordV1::Survey(survey) =
        load_artifact_record_from_value(fixtures["survey"].clone())?
    else {
        panic!("survey fixture required")
    };
    let policy = policy::load_policy_document_from_value(
        asset("policy", "general_compute_default.v1.json").expect("selected policy"),
    )?;
    let packs = optional(kwargs, "extension_packs")
        .map(|value| value.as_array().unwrap().as_slice())
        .unwrap_or(&[])
        .iter()
        .cloned()
        .map(config::load_extension_pack_from_value)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let context = optional(kwargs, "invocation_context")
        .cloned()
        .map(config::load_invocation_context_from_value)
        .transpose()?;
    let basis = if packs.is_empty() && context.is_none() {
        None
    } else {
        let resolved = config::resolve_configuration_v1(config::ResolveConfigurationRequestV1 {
            policy: policy.clone(),
            trust_policy: None,
            extension_packs: packs.clone(),
            recommendation_packs: vec![],
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
    let request = contract::ContractDerivationRequestV1 {
        survey,
        policy,
        live_state: None,
        derivation_context: contract::DerivationContextV1 {
            derived_at: kwargs["at"].as_str().unwrap().into(),
            notes: optional(kwargs, "notes").map(|value| value.as_str().unwrap().into()),
        },
    };
    let value = match basis {
        Some(basis) => contract::derive_host_contract_with_extensions_v1(request, basis)?,
        None => contract::derive_host_contract_v1(request)?,
    };
    Ok(ArtifactRecordV1::Contract(value).full_artifact_json()?)
}

pub fn validate(fixtures: &Value, kwargs: &Value) -> Result<Value> {
    let ArtifactRecordV1::Contract(contract) =
        load_artifact_record_from_value(fixtures["contract"].clone())?
    else {
        panic!("contract fixture required")
    };
    let profile = service_profile::load_service_profile_from_value(fixtures["profile"].clone())?;
    let thermal = optional(kwargs, "thermal_evidence")
        .map(|value| value.as_array().unwrap().as_slice())
        .unwrap_or(&[])
        .iter()
        .map(|name| -> Result<_> {
            let name = match name.as_str().unwrap() {
                "thermal-copy" => "thermal",
                name => name,
            };
            let ArtifactRecordV1::ThermalEvidence(value) =
                load_artifact_record_from_value(fixtures[name].clone())?
            else {
                panic!("thermal fixture required")
            };
            Ok(value)
        })
        .collect::<Result<Vec<_>>>()?;
    let mode = match optional(kwargs, "mode")
        .and_then(Value::as_str)
        .unwrap_or("contract_only")
    {
        "contract_only" => validate::ValidationModeV1::ContractOnly,
        "state_advisory" => validate::ValidationModeV1::StateAdvisory,
        "state_required" => validate::ValidationModeV1::StateRequired,
        _ => panic!("only admitted mode vectors enter the core reference"),
    };
    let report = validate::validate_request_v1(validate::ValidationRequestV1 {
        contract,
        service_profile: profile,
        host_state: None,
        thermal_evidence: thermal,
        mode,
        validated_at: kwargs["at"].as_str().unwrap().into(),
        notes: optional(kwargs, "notes").map(|value| value.as_str().unwrap().into()),
        max_state_age_seconds: optional(kwargs, "max_state_age_seconds")
            .map(|value| value.as_u64().unwrap()),
    })?;
    Ok(ArtifactRecordV1::ValidationReport(report).full_artifact_json()?)
}

pub fn redact(fixtures: &Value, kwargs: &Value) -> Result<Value> {
    let artifact = load_artifact_record_from_value(fixtures["survey"].clone())?;
    let profile = redact::parse_builtin_redaction_profile_v1(kwargs["profile"].as_str().unwrap())?;
    let result = redact::redact_artifact_v1(redact::RedactionRequestV1 {
        artifact,
        profile,
        redacted_at: kwargs["at"].as_str().unwrap().into(),
    })?;
    Ok(result.full_artifact_json()?)
}
