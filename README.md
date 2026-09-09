# fitctl Python bindings

Use [fitctl](https://github.com/tznurmin/fitctl) from Python to collect host evidence
and check whether a host meets a workload's requirements.

The bindings call `fitctl-core` directly. You do not need the fitctl command-line
tool. Version 0.1.0 uses fitctl-core 0.8.0.

## Install

The wheel supports standard CPython 3.13.x on Linux x86_64 with glibc 2.28 or newer.
Other Python versions, free-threaded Python, macOS and Windows are not supported
by this release.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install fitctl==0.1.0
```

## Collect host evidence

```python
import fitctl

survey = fitctl.collect_survey()
print(survey.to_json())
```

This collects one snapshot of the local host. Importing the package does not
collect anything or start a background monitor.

## Use saved evidence

Load a fitctl JSON artifact without contacting the host it describes:

```python
from pathlib import Path
import fitctl

survey = fitctl.Artifact.from_json(
    Path("host.survey.json").read_text(encoding="utf-8")
)
print(survey.artifact_id)
```

See [recorded evidence and decisions](docs/recorded.md) to derive a contract and
validate it, [batch comparison](docs/batch.md) to compare several inputs, and
[evidence collection](docs/collection.md) for storage and sensor checks.

Licensed under [Apache 2.0](LICENSE). Third-party licenses and notices are in [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).
