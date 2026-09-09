// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Exact Python built-ins to owned JSON, under admission counters.

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use serde_json::{Map, Number, Value};

use crate::conversion_budget::{add, Budget, DEPTH, DOCUMENT_BYTES};
use crate::error::{Failure, Result, TYPE};

pub fn exact<T: pyo3::PyTypeInfo>(value: &Bound<'_, PyAny>) -> Result<()> {
    if value.is_exact_instance_of::<T>() {
        Ok(())
    } else {
        Err(TYPE)
    }
}

pub fn utf8_size(value: &Bound<'_, PyAny>, limit: usize) -> Result<usize> {
    exact::<PyString>(value)?;
    let length = unsafe { pyo3::ffi::PyUnicode_GetLength(value.as_ptr()) };
    if length < 0 {
        return Err(Failure::Memory);
    }
    let mut bytes = 0;
    // Count before CPython allocates a UTF-8 cache or Rust copies the string.
    for index in 0..length {
        let scalar = unsafe { pyo3::ffi::PyUnicode_ReadChar(value.as_ptr(), index) };
        let scalar = char::from_u32(scalar).ok_or(Failure::Value("invalid Unicode scalar"))?;
        bytes = add(bytes, scalar.len_utf8(), limit)?;
    }
    Ok(bytes)
}

pub fn cached_utf8<'a>(value: &'a Bound<'_, PyAny>) -> Result<&'a str> {
    value.cast::<PyString>().map_err(|_| TYPE)?.to_str().map_err(|error| {
        if error.is_instance_of::<pyo3::exceptions::PyMemoryError>(value.py()) {
            Failure::Memory
        } else {
            Failure::Value("invalid Unicode scalar")
        }
    })
}

pub fn utf8<'a>(value: &'a Bound<'_, PyAny>, limit: usize) -> Result<&'a str> {
    utf8_size(value, limit)?;
    cached_utf8(value)
}

pub fn copy(text: &str) -> Result<String> {
    crate::faults::reservation()?;
    let mut owned = String::new();
    owned.try_reserve_exact(text.len()).map_err(|_| Failure::Memory)?;
    owned.push_str(text);
    Ok(owned)
}

pub fn string(value: &Bound<'_, PyAny>, limit: usize) -> Result<String> {
    copy(utf8(value, limit)?)
}

pub fn unsigned(value: &Bound<'_, PyAny>) -> Result<u64> {
    #[cfg(test)]
    if crate::assertion_mutants::active(crate::assertion_mutants::Fault::BoolAge)
        && value.is_exact_instance_of::<PyBool>()
    {
        return Ok(u64::from(value.is_truthy().map_err(|_| TYPE)?));
    }
    exact::<PyInt>(value)?;
    value.extract::<u64>().map_err(|_| Failure::Overflow)
}

fn integer(value: &Bound<'_, PyAny>) -> Result<Number> {
    if let Ok(number) = value.extract::<i64>() {
        return Ok(number.into());
    }
    Ok(unsigned(value)?.into())
}

pub fn document(value: &Bound<'_, PyAny>, budget: &mut Budget) -> Result<Value> {
    #[cfg(test)]
    crate::assertion_mutants::begin_document();
    exact::<PyDict>(value)?;
    let mut ancestors = Vec::new();
    ancestors.try_reserve_exact(DEPTH).map_err(|_| Failure::Memory)?;
    convert(value, budget, &mut ancestors, 0)
}

pub fn input(value: &Bound<'_, PyAny>, json: bool) -> Result<Value> {
    crate::faults::conversion();
    if json {
        let text = utf8(value, DOCUMENT_BYTES)?;
        crate::json_decode::document(text)
    } else {
        document(value, &mut Budget::document(DOCUMENT_BYTES))
    }
}

fn scalar_string(value: &Bound<'_, PyAny>, budget: &mut Budget, depth: usize) -> Result<String> {
    #[cfg(test)]
    crate::faults::budget_domain("individual");
    let bytes = utf8_size(value, budget.byte_limit - budget.counts.bytes)?;
    budget.charge(bytes, 1, depth)?;
    copy(cached_utf8(value)?)
}

fn convert(
    value: &Bound<'_, PyAny>,
    budget: &mut Budget,
    ancestors: &mut Vec<usize>,
    depth: usize,
) -> Result<Value> {
    if value.is_exact_instance_of::<PyString>() {
        return Ok(Value::String(scalar_string(value, budget, depth)?));
    }
    if value.is_none() {
        budget.charge(4, 1, depth)?;
        return Ok(Value::Null);
    }
    if value.is_exact_instance_of::<PyBool>() {
        let boolean = value.is_truthy().map_err(|_| TYPE)?;
        budget.charge(if boolean { 4 } else { 5 }, 1, depth)?;
        return Ok(Value::Bool(boolean));
    }
    if value.is_exact_instance_of::<PyInt>() {
        let number = integer(value)?;
        budget.charge(number.to_string().len(), 1, depth)?;
        return Ok(Value::Number(number));
    }
    if value.is_exact_instance_of::<PyFloat>() {
        let float = value.extract::<f64>().map_err(|_| TYPE)?;
        let number = Number::from_f64(float).ok_or(Failure::Value("non-finite input number"))?;
        budget.charge(8, 1, depth)?;
        return Ok(Value::Number(number));
    }
    let list = value.is_exact_instance_of::<PyList>();
    if !list && !value.is_exact_instance_of::<PyDict>() {
        return Err(TYPE);
    }
    let address = value.as_ptr() as usize;
    #[cfg(test)]
    if crate::assertion_mutants::alias(address) {
        return Ok(Value::Null);
    }
    if ancestors.contains(&address) {
        return Err(Failure::Value("cyclic input"));
    }
    let depth = depth + 1;
    let root_count = 1;
    #[cfg(test)]
    let root_count =
        if depth == 1 && crate::assertion_mutants::active(crate::assertion_mutants::Fault::Root) {
            0
        } else {
            root_count
        };
    budget.charge(0, root_count, depth)?;
    ancestors.push(address);
    let result = if list {
        let mut items = Vec::new();
        for item in value.cast::<PyList>().map_err(|_| TYPE)?.iter() {
            let item = convert(&item, budget, ancestors, depth)?;
            crate::faults::reservation()?;
            items.try_reserve(1).map_err(|_| Failure::Memory)?;
            items.push(item);
        }
        Value::Array(items)
    } else {
        let mut items = Map::new();
        for (key, item) in value.cast::<PyDict>().map_err(|_| TYPE)?.iter() {
            #[cfg(test)]
            let previous = budget.counts;
            let key = scalar_string(&key, budget, depth)?;
            #[cfg(test)]
            if crate::assertion_mutants::active(crate::assertion_mutants::Fault::Key) {
                budget.counts = previous;
            }
            let item = convert(&item, budget, ancestors, depth)?;
            items.insert(key, item);
        }
        Value::Object(items)
    };
    ancestors.pop();
    Ok(result)
}
