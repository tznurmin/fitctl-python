# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence, decisions and explicit collection provided by the native core."""

from typing import Literal, NotRequired, TypedDict

from ._native import (
    Artifact, Policy, BatchReport, FitctlError, CoreError, DecodeError, SerializationError,
    NativeError, builtin_config, derive_contract, validate, classify_batch,
    collect_survey, collect_state, replay_survey, replay_state,
    __version__, core_version, semantic_encoding,
)

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]
type Verdict = Literal["fit", "fit_with_degradation", "unfit", "indeterminate"]


class PathCheck(TypedDict):
    path_id: str
    path: str
    probe_links: NotRequired[bool]
    probe_health: NotRequired[bool]


class LinkPair(TypedDict):
    from_path_id: str
    to_path_id: str

__all__ = ["Artifact", "Policy", "BatchReport", "FitctlError", "CoreError", "DecodeError",
           "SerializationError", "NativeError", "builtin_config", "derive_contract",
           "validate", "classify_batch", "collect_survey", "collect_state", "replay_survey", "replay_state",
           "PathCheck", "LinkPair", "__version__", "core_version", "semantic_encoding", "JSONValue", "Verdict"]
