// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Exact Python request shapes and budgets; core owns all path semantics.

use crate::argument_binding::Arguments;
use crate::conversion::{cached_utf8, copy, exact, utf8, utf8_size};
use crate::conversion_budget::add;
use crate::error::{Failure, Result, ARGUMENTS, BUDGET, TYPE};
use fitctl_core::state::{StatePathCheckRequestV1, StatePathLinkPairProbeRequestV1};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyList, PyString};
use std::path::PathBuf;

pub const STATE_NAMES: &[&str] = &[
    "path_checks",
    "link_pairs",
    "thermal_provider_config_paths",
    "memory_reliability",
    "gpu_reliability",
    "hardware_sensors",
];
const CHECK: &[&str] = &["path_id", "path", "probe_links", "probe_health"];
const PAIR: &[&str] = &["from_path_id", "to_path_id"];

pub struct ReplayInput {
    pub root: PathBuf,
    pub id: String,
}

pub struct StateInput {
    pub checks: Vec<StatePathCheckRequestV1>,
    pub pairs: Vec<StatePathLinkPairProbeRequestV1>,
    pub configs: Vec<PathBuf>,
    pub memory_reliability: bool,
    pub gpu_reliability: bool,
    pub hardware_sensors: bool,
}

pub fn replay(bound: &Arguments<'_>) -> Result<ReplayInput> {
    for index in 0..2 {
        exact::<PyString>(bound.required(index))?;
    }
    utf8_size(bound.required(0), 4096)?;
    utf8_size(bound.required(1), 128)?;
    Ok(ReplayInput {
        root: copy(cached_utf8(bound.required(0))?)?.into(),
        id: copy(cached_utf8(bound.required(1))?)?,
    })
}

fn field<'py>(value: &Bound<'py, PyDict>, name: &str) -> Result<Bound<'py, PyAny>> {
    value
        .get_item(name)
        .map_err(|_| Failure::Memory)?
        .ok_or(ARGUMENTS)
}

fn shape(value: &Bound<'_, PyAny>, names: &[&str]) -> Result<()> {
    exact::<PyDict>(value)?;
    let value = value.cast::<PyDict>().map_err(|_| TYPE)?;
    for (key, item) in value.iter() {
        exact::<PyString>(&key)?;
        let name = utf8(&key, 32).map_err(|error| match error {
            Failure::Memory => Failure::Memory,
            _ => ARGUMENTS,
        })?;
        let index = names
            .iter()
            .position(|entry| *entry == name)
            .ok_or(ARGUMENTS)?;
        if index < 2 {
            exact::<PyString>(&item)?;
        } else {
            exact::<PyBool>(&item)?;
        }
    }
    field(value, names[0])?;
    field(value, names[1])?;
    Ok(())
}

fn boolean(value: Option<&Bound<'_, PyAny>>) -> Result<bool> {
    value
        .map(|value| value.extract::<bool>().map_err(|_| TYPE))
        .transpose()
        .map(|v| v.unwrap_or(false))
}

fn reserve<T>(size: usize) -> Result<Vec<T>> {
    let mut value = Vec::new();
    crate::faults::reservation()?;
    value.try_reserve_exact(size).map_err(|_| Failure::Memory)?;
    Ok(value)
}

pub fn state(bound: &Arguments<'_>) -> Result<StateInput> {
    // Validate all top-level types before any count, shape or byte rejection.
    for index in 0..3 {
        if let Some(value) = bound.optional(index) {
            exact::<PyList>(value)?;
        }
    }
    for index in 3..6 {
        if let Some(value) = bound.supplied(index) {
            exact::<PyBool>(value)?;
        }
    }
    let lists = [0, 1, 2].map(|index| {
        bound
            .optional(index)
            .map(|v| v.cast::<PyList>().expect("checked exact list"))
    });
    #[cfg(not(test))]
    let bypass_count = false;
    #[cfg(test)]
    let bypass_count =
        crate::assertion_mutants::active(crate::assertion_mutants::Fault::CollectionCount);
    for (list, cap) in lists.iter().zip([16, 16, 4]) {
        if !bypass_count && list.is_some_and(|list| list.len() > cap) {
            return Err(BUDGET);
        }
    }
    for (index, list) in lists.iter().enumerate() {
        if let Some(list) = list {
            for item in list.iter() {
                match index {
                    0 => shape(&item, CHECK)?,
                    1 => shape(&item, PAIR)?,
                    _ => exact::<PyString>(&item)?,
                }
            }
        }
    }
    // Complete byte admission before allocating any owned input payload.
    let mut bytes = 0;
    for (index, list) in lists.iter().enumerate() {
        if let Some(list) = list {
            for item in list.iter() {
                if index == 2 {
                    bytes = add(bytes, utf8_size(&item, 4096)?, 65536)?;
                } else {
                    let dict = item.cast::<PyDict>().map_err(|_| TYPE)?;
                    let names = if index == 0 { CHECK } else { PAIR };
                    for (i, name) in names[..2].iter().enumerate() {
                        let cap = if index == 0 && i == 1 { 4096 } else { 128 };
                        bytes = add(bytes, utf8_size(&field(dict, name)?, cap)?, 65536)?;
                    }
                }
            }
        }
    }
    let mut checks = reserve(lists[0].map_or(0, |list| list.len()))?;
    let mut pairs = reserve(lists[1].map_or(0, |list| list.len()))?;
    let mut configs = reserve(lists[2].map_or(0, |list| list.len()))?;
    if let Some(list) = lists[0] {
        for item in list.iter() {
            let dict = item.cast::<PyDict>().map_err(|_| TYPE)?;
            checks.push(StatePathCheckRequestV1 {
                path_id: copy(cached_utf8(&field(dict, "path_id")?)?)?,
                path: copy(cached_utf8(&field(dict, "path")?)?)?.into(),
                probe_links: boolean(
                    dict.get_item("probe_links")
                        .map_err(|_| Failure::Memory)?
                        .as_ref(),
                )?,
                probe_health: boolean(
                    dict.get_item("probe_health")
                        .map_err(|_| Failure::Memory)?
                        .as_ref(),
                )?,
            });
        }
    }
    if let Some(list) = lists[1] {
        for item in list.iter() {
            let dict = item.cast::<PyDict>().map_err(|_| TYPE)?;
            pairs.push(StatePathLinkPairProbeRequestV1 {
                from_path_id: copy(cached_utf8(&field(dict, "from_path_id")?)?)?,
                to_path_id: copy(cached_utf8(&field(dict, "to_path_id")?)?)?,
            });
        }
    }
    if let Some(list) = lists[2] {
        for item in list.iter() {
            configs.push(copy(cached_utf8(&item)?)?.into());
        }
    }
    Ok(StateInput {
        checks,
        pairs,
        configs,
        memory_reliability: boolean(bound.supplied(3))?,
        gpu_reliability: boolean(bound.supplied(4))?,
        hardware_sensors: boolean(bound.supplied(5))?,
    })
}
