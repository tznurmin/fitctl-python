// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Native adaptation and explicit collection over the maintained core.

mod argument_binding;
mod artifact_interface;
mod attached_boundary;
mod batch;
mod batch_admission;
mod batch_interface;
mod batch_value;
mod collection;
mod collection_admission;
mod conversion;
mod conversion_budget;
mod core_calls;
mod derive_admission;
mod error;
mod faults;
mod identity;
mod json_decode;
mod json_encode;
mod json_string;
mod operations;
mod panic_boundary;
mod policy_interface;
mod serialization;
mod validate_admission;
mod value_interface;
mod values;

#[cfg(test)]
mod assertion_mutants;
#[cfg(test)]
mod batch_failure_tests;
#[cfg(test)]
mod collection_failure_tests;
#[cfg(test)]
mod budget_collections;
#[cfg(test)]
mod budget_controls;
#[cfg(test)]
mod budget_tests;
#[cfg(test)]
mod failure_assertions;
#[cfg(test)]
mod failure_execution;
#[cfg(test)]
mod failure_exports;
#[cfg(test)]
mod failure_panics;
#[cfg(test)]
mod failure_tests;
#[cfg(test)]
mod fault_state;
#[cfg(test)]
mod test_support;
#[cfg(test)]
mod number_tests;

use pyo3::prelude::*;

#[pymodule(gil_used = true)]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    attached_boundary::initialize(module, |module| {
        error::register(module)?;
        identity::register(module)?;
        module.add_class::<values::Artifact>()?;
        module.add_class::<values::Policy>()?;
        module.add_class::<batch_value::BatchReport>()?;
        module.add_function(wrap_pyfunction!(collection::collect_survey, module)?)?;
        module.add_function(wrap_pyfunction!(collection::collect_state, module)?)?;
        module.add_function(wrap_pyfunction!(collection::replay_survey, module)?)?;
        module.add_function(wrap_pyfunction!(collection::replay_state, module)?)?;
        module.add_function(wrap_pyfunction!(batch::classify_batch, module)?)?;
        module.add_function(wrap_pyfunction!(operations::builtin_config, module)?)?;
        module.add_function(wrap_pyfunction!(operations::derive_contract, module)?)?;
        module.add_function(wrap_pyfunction!(operations::validate, module)?)
    })
}
