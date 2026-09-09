// Copyright 2026 fitctl contributors
// SPDX-License-Identifier: Apache-2.0

//! Returned errors and recoverable allocation failures through real exports.

use crate::error::Failure;
use crate::failure_assertions::{container_counts, memory, partials_removed, structured};
use crate::faults::{inject, inject_after, Point};
use crate::test_support::{eval, run, with_python};
use pyo3::prelude::*;
use serde::{Serialize, Serializer};
use serde_json::json;
use std::sync::Arc;

struct Refused;
impl Serialize for Refused {
    fn serialize<S: Serializer>(&self, _serializer: S) -> std::result::Result<S::Ok, S::Error> {
        Err(serde::ser::Error::custom("ADAPTER_INPUT_SENTINEL"))
    }
}

pub fn json_serialization() {
    with_python(|py, scope| {
        let error = crate::serialization::encode(&Refused).unwrap_err().python(py, "export");
        structured(
            py,
            &error,
            "SerializationError",
            "fitctl.python.serialization.v1",
            "json_encode_failed",
            "json_encode",
            "JSON serialization failed",
        );
        inject(Point::Encode);
        let error = eval(py, &scope, "survey.to_json()").unwrap_err();
        structured(
            py,
            &error,
            "SerializationError",
            "fitctl.python.serialization.v1",
            "json_encode_failed",
            "json_encode",
            "JSON serialization failed",
        );
        let artifact = scope
            .get_item("survey")
            .unwrap()
            .unwrap()
            .extract::<PyRef<'_, crate::values::Artifact>>()
            .unwrap()
            .clone();
        let fitctl_core::artifacts::record_v1::ArtifactRecordV1::Survey(mut invalid) =
            artifact.core.as_ref().clone()
        else {
            panic!("survey fixture required")
        };
        invalid.survey = json!({});
        scope
            .set_item(
                "invalid",
                Py::new(
                    py,
                    crate::values::Artifact {
                        core: Arc::new(
                            fitctl_core::artifacts::record_v1::ArtifactRecordV1::Survey(invalid),
                        ),
                    },
                )
                .unwrap(),
            )
            .unwrap();
        let error = eval(py, &scope, "invalid.semantic_bytes()").unwrap_err();
        structured(
            py,
            &error,
            "CoreError",
            "fitctl.artifact_record.v1",
            "artifact_load_invalid",
            "artifact_projection",
            "Artifact.semantic_bytes: artifact_load_invalid",
        );
        run(py, &scope, "assert survey.to_json(); assert survey.semantic_bytes()");
    });
}

pub fn python_export() {
    with_python(|py, scope| {
        run(py, &scope, "before = survey.to_json()");
        let baseline = container_counts(py, &scope);
        let retained = crate::serialization::value(py, &json!([[], [], []])).unwrap();
        assert_ne!(
            container_counts(py, &scope),
            baseline,
            "cleanup observer must detect retained output"
        );
        drop(retained);
        assert_eq!(container_counts(py, &scope), baseline);
        inject(Point::Export);
        let error = eval(py, &scope, "survey.to_dict()").unwrap_err();
        structured(
            py,
            &error,
            "SerializationError",
            "fitctl.python.serialization.v1",
            "export_conversion_failed",
            "python_export",
            "native value export failed",
        );
        for raw in [json!([[], [], []]), json!({"a": [], "b": [], "c": []})] {
            let before = container_counts(py, &scope);
            inject_after(Point::PartialExport, 1);
            let error = crate::serialization::value(py, &raw).unwrap_err().python(py, "export");
            structured(
                py,
                &error,
                "SerializationError",
                "fitctl.python.serialization.v1",
                "export_conversion_failed",
                "python_export",
                "native value export failed",
            );
            partials_removed(py, &scope, before);
            let exported = crate::serialization::value(py, &raw).unwrap();
            scope.set_item("exported", exported).unwrap();
            run(py, &scope, "assert len(exported) == 3");
        }
        inject(Point::MalformedAsset);
        let error =
            eval(py, &scope, "api.builtin_config('policy', 'general_compute_default.v1.json')")
                .unwrap_err();
        structured(
            py,
            &error,
            "SerializationError",
            "fitctl.python.serialization.v1",
            "export_conversion_failed",
            "python_export",
            "native value export failed",
        );
        run(py, &scope, "assert before == survey.to_json()\nassert api.builtin_config('policy', 'general_compute_default.v1.json')");
    });
}

pub fn recoverable_allocation() {
    with_python(|py, scope| {
        run(py, &scope, "before = survey.to_json(); raw = survey.to_dict()");
        inject(Point::ExportMemory);
        memory(py, &eval(py, &scope, "survey.semantic_bytes()").unwrap_err());
        for expression in ["api.Artifact.from_dict(raw)", "survey.to_json()"] {
            inject(Point::Reservation);
            let error = eval(py, &scope, expression).unwrap_err();
            memory(py, &error);
            run(py, &scope, "assert raw == survey.to_dict(); assert before == survey.to_json()");
        }
        for raw in [json!([[], [], []]), json!({"a": [], "b": [], "c": []})] {
            let before = container_counts(py, &scope);
            inject_after(Point::PartialMemory, 1);
            let error = crate::serialization::value(py, &raw).unwrap_err().python(py, "export");
            memory(py, &error);
            partials_removed(py, &scope, before);
            assert!(crate::serialization::value(py, &raw).is_ok());
        }
        for index in 0..6 {
            inject_after(Point::Exception, index);
            let error = Failure::Export.python(py, "export");
            memory(py, &error);
            let next = Failure::Export.python(py, "export");
            structured(
                py,
                &next,
                "SerializationError",
                "fitctl.python.serialization.v1",
                "export_conversion_failed",
                "python_export",
                "native value export failed",
            );
        }
    });
}
