// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! A closed, bounded signature adapter avoids raw PyO3 binder diagnostics.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString, PyTuple};

use crate::error::{Failure, Result, ARGUMENTS};

pub struct Arguments<'py> {
    values: Vec<Option<Bound<'py, PyAny>>>,
}

impl<'py> Arguments<'py> {
    pub fn bind(
        args: &Bound<'py, PyTuple>,
        kwargs: Option<&Bound<'py, PyDict>>,
        names: &[&str],
        positional: usize,
        required: usize,
    ) -> Result<Self> {
        if args.len() > positional || kwargs.is_some_and(|k| k.len() > names.len()) {
            return Err(ARGUMENTS);
        }
        let mut values = Vec::new();
        values.try_reserve_exact(names.len()).map_err(|_| Failure::Memory)?;
        values.resize_with(names.len(), || None);
        for (i, item) in args.iter().enumerate() {
            values[i] = Some(item);
        }
        if let Some(kwargs) = kwargs {
            for (key, value) in kwargs.iter() {
                if !key.is_exact_instance_of::<PyString>() {
                    return Err(ARGUMENTS);
                }
                let name = crate::conversion::string(&key, 32).map_err(|error| match error {
                    Failure::Memory => Failure::Memory,
                    _ => ARGUMENTS,
                })?;
                let Some(i) = names.iter().position(|candidate| *candidate == name) else {
                    return Err(ARGUMENTS);
                };
                if values[i].is_some() {
                    return Err(ARGUMENTS);
                }
                values[i] = Some(value);
            }
        }
        if values.iter().take(required).any(Option::is_none) {
            return Err(ARGUMENTS);
        }
        Ok(Self { values })
    }

    pub fn required(&self, index: usize) -> &Bound<'py, PyAny> {
        self.values[index].as_ref().expect("signature checked required argument")
    }

    pub fn optional(&self, index: usize) -> Option<&Bound<'py, PyAny>> {
        self.values[index].as_ref().filter(|value| !value.is_none())
    }

    pub fn supplied(&self, index: usize) -> Option<&Bound<'py, PyAny>> {
        self.values[index].as_ref()
    }
}
