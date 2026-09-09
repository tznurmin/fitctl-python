// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Only core-owned error identities and complete core exports are observed.

use serde_json::{json, Value};

pub struct Fault(pub Value);
pub type Result<T> = std::result::Result<T, Fault>;

macro_rules! typed {
    ($type:ty) => {
        impl From<$type> for Fault {
            fn from(error: $type) -> Self {
                Self(json!({"error_model_id": error.error_model_id,
                    "error_model_version": error.error_model_version,
                    "reason_code": error.code.as_str(), "checkpoint_id": error.checkpoint_id}))
            }
        }
    };
}
typed!(fitctl_core::artifacts::record_v1::ArtifactRecordError);
typed!(fitctl_core::config::ConfigError);
typed!(fitctl_core::service_profile::ServiceProfileError);
typed!(fitctl_core::contract::ContractDerivationError);
typed!(fitctl_core::validate::ValidationError);
typed!(fitctl_core::redact::RedactionError);

pub fn outcome(result: Result<Value>) -> Value {
    match result {
        Ok(value) => json!({"value": value}),
        Err(Fault(error)) => json!({"error": error}),
    }
}
