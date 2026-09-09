# Batch comparison

Use `classify_batch()` to evaluate every supplied contract against every supplied
service profile. It uses saved evidence and does not contact the hosts.

## Compare inputs

With your saved `host.contract.json` and `workload.profile.json`:

```python
from pathlib import Path
import fitctl

contract = fitctl.Artifact.from_json(Path("host.contract.json").read_text(encoding="utf-8"))
profile = fitctl.Artifact.from_json(Path("workload.profile.json").read_text(encoding="utf-8"))
report = fitctl.classify_batch([contract], [profile], at="2026-09-09T12:00:00Z")

for row in report.rows:
    print(row["contract_artifact_id"], row["verdict"], row["primary_reason_code"])

Path("rows.csv").write_text(report.export_csv("rows_csv"), encoding="utf-8")
```

Add more contracts or profiles to their lists to expand the comparison. The other
CSV views are `contract_summary_csv` and `service_profile_summary_csv`.
`report.to_json()` saves the full report; `BatchReport.from_json()` loads it again.

## Include state

Pass `states=[...]`, `mode="state_required"` or `mode="state_advisory"`, and
`max_state_age_seconds` when the comparison needs runtime evidence. fitctl matches
state to contracts. Missing required evidence produces an `indeterminate` row;
malformed, duplicate or unmatched inputs are errors.

## Limits

Each input list accepts at most 16 artifacts, with at most 64 contract/profile
pairs. Lists must contain the correct artifact types. `at` accepts 64 UTF-8 bytes;
mode and CSV-view names accept 32. The age must be an integer from 0 to 2**64-1,
not a boolean. Optional states omitted or set to `None` mean no states.

Reports are immutable; row and summary properties return independent copies.
The [same verdicts, errors and call behavior](recorded.md) apply as for individual
validation. These input limits are not a guarantee of runtime or memory usage.
