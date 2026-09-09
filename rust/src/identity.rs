// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

use pyo3::prelude::*;

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("__version__", "0.1.0")?;
    module.add("core_version", fitctl_core::artifacts::envelope_v1::LOCAL_FITCTL_VERSION_V1)?;
    module.add("semantic_encoding", fitctl_core::sign::PAYLOAD_ENCODING_V2)
}
