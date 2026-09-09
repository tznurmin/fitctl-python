# Recorded evidence and decisions

Load saved evidence, derive a host contract, and check it against a service
profile. These operations do not contact a host or refresh old observations.

## Make a fit decision

The example uses your saved `host.survey.json` and `workload.profile.json`, plus
the bundled general-compute policy:

```python
from pathlib import Path
import fitctl

survey = fitctl.Artifact.from_json(Path("host.survey.json").read_text(encoding="utf-8"))
profile = fitctl.Artifact.from_json(Path("workload.profile.json").read_text(encoding="utf-8"))
policy = fitctl.Policy.from_dict(
    fitctl.builtin_config("policy", "general_compute_default.v1.json")
)
at = "2026-09-09T12:00:00Z"
contract = fitctl.derive_contract(survey, policy, at=at)
report = fitctl.validate(contract, profile, at=at)
print(report.verdict, report.primary_reason_code)
```

Choose `at` for the time you want to evaluate. The verdict is `fit`,
`fit_with_degradation`, `unfit` or `indeterminate`. A non-fit result is a report,
not an exception. Fit does not authorize execution or reserve resources.

## Include runtime state

For requirements that depend on current conditions, load matching state and
set its permitted age:

```python
state = fitctl.Artifact.from_json(Path("host.state.json").read_text(encoding="utf-8"))
report = fitctl.validate(
    contract, profile, at=at, state=state,
    mode="state_required", max_state_age_seconds=60,
)
```

Use `thermal_evidence=[...]` for saved standalone thermal artifacts. See
[fitctl validation](https://github.com/tznurmin/fitctl/blob/v0.8.0/docs/validation.md)
for modes, freshness rules and evidence requirements.

## Export and share

Artifacts are immutable. `to_dict()` returns an independent dictionary and
`to_json()` returns JSON text. `semantic_bytes()` and `semantic_hash()` use
fitctl's encoding. `Artifact.from_dict()` accepts a decoded artifact dictionary.

Use `survey.redact("external", at=at)` to reduce identifying details before
sharing. Review the result: redaction does not guarantee anonymity. The other
profiles are `local`, `fleet` and `auditor`.

## Errors and input limits

Invalid Python arguments raise `TypeError`, `ValueError` or `OverflowError`.
Malformed JSON raises `DecodeError`; core validation failures raise `CoreError`,
with `reason_code` and `checkpoint_id`. Export failures use `SerializationError`
and caught native panics use `NativeError`. Process termination is not recoverable.

Use built-in JSON types, not custom subclasses. Duplicate keys, cycles and
non-finite numbers are rejected. JSON numbers follow fitctl-core, including
the sign of `-0`; integer literals must fit signed 64-bit or unsigned 64-bit range.

| Input | Limit |
|---|---|
| Artifact document | 16 MiB, 64 container levels, 100,000 conversion nodes |
| Configuration document | 1 MiB |
| Derivation | 16 extension packs, 8 MiB combined arguments |
| Validation | 128 thermal artifacts |
| `at` / `notes` | 64 / 4,096 UTF-8 bytes |

Calls are synchronous. A Python waiting timeout does not cancel native work.
See the [type signatures](../python/fitctl/__init__.pyi) for all arguments.
