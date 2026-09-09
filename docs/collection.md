# Explicit evidence collection

Use `collect_survey()` for host facts and `collect_state()` for runtime state.
Each call takes one snapshot of what the local process can see; neither starts
a background monitor.

```python
import fitctl

survey = fitctl.collect_survey()
state = fitctl.collect_state()
print(state.to_json())
```

Optional storage probes, thermal providers, hardware sensors and reliability
checks are off by default.

## Check storage

Select a mounted path and opt into its available storage-health evidence:

```python
state = fitctl.collect_state(
    path_checks=[{"path_id": "data", "path": "/data", "probe_health": True}]
)
print(state.to_dict()["state"]["core_state"]["path_resources"])
```

Replace `/data` with your path. Missing tools or device access can leave health
values unknown. A successful call is not proof that the drive is healthy.

`probe_links=True` tests file-link support. To test between two checked paths,
pass `link_pairs=[{"from_path_id": "cache", "to_path_id": "data"}]` after defining
both paths. Link probes create temporary files; check the reported cleanup
outcome as well as link support.

## Collect sensors

```python
state = fitctl.collect_state(
    thermal_provider_config_paths=["thermal-providers.json"],
    hardware_sensors=True,
)
```

Supply your own [thermal provider configuration](https://github.com/tznurmin/fitctl/blob/v0.8.0/docs/validation.md#thermal-provider-evidence).
`hardware_sensors=True` separately collects voltage, current, power, fan speed
and other supported non-temperature readings through lm-sensors.
`memory_reliability=True` and `gpu_reliability=True` enable reliability checks.
Read provider outcomes before using their values; unavailable evidence is not zero.

## Replay a fixture corpus

Use `fitctl.replay_survey("survey-corpus", "sample")` or
`fitctl.replay_state("state-corpus", "sample")` with a fitctl fixture corpus.
The root is a corpus directory, not an artifact file. To load saved JSON instead,
use [`Artifact.from_json()`](recorded.md).

## Call limits

Paths must be strings, not `Path` objects. Lists and booleans must be built-in
`list` and `bool` values. Unknown dictionary fields are rejected.

Each path may contain 4,096 UTF-8 bytes and each identifier 128. A call accepts
up to 16 path checks, 16 link pairs and four provider-config paths, with 65,536
UTF-8 bytes across its string arguments. Omitted lists or `None` mean empty lists.

Collection is synchronous and has no overall cancellation or timeout argument.
Some provider commands have individual timeouts, but these do not bound the whole
call. Missing observations remain in the artifact; operation failures raise the
[documented exceptions](recorded.md#errors-and-input-limits).
