# fitctl Python bindings

Use [fitctl](https://github.com/tznurmin/fitctl) from Python to collect host evidence
and check whether a host meets a workload's requirements.

The bindings call `fitctl-core` directly. You do not need the fitctl command-line
tool. Version 0.1.1 uses fitctl-core 0.8.0.

## Install

Requires Python 3.12 or newer. The wheel is tested with ordinary CPython 3.12,
3.13 and 3.14 on Linux x86_64 with glibc 2.28 or newer. It requires the GIL;
free-threaded Python, macOS and Windows are not supported by this release.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install fitctl==0.1.1
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

See [recorded evidence and decisions](https://github.com/tznurmin/fitctl-python/blob/main/docs/recorded.md) to derive a contract and
validate it, [batch comparison](https://github.com/tznurmin/fitctl-python/blob/main/docs/batch.md) to compare several inputs, and
[evidence collection](https://github.com/tznurmin/fitctl-python/blob/main/docs/collection.md) for storage and sensor checks.

Licensed under [Apache 2.0](https://github.com/tznurmin/fitctl-python/blob/main/LICENSE). Third-party licenses and notices are in [THIRD_PARTY_LICENSES.txt](https://github.com/tznurmin/fitctl-python/blob/main/THIRD_PARTY_LICENSES.txt).
