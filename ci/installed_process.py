# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Run installed tests and check their system-call traces."""

import json
from pathlib import Path
import shutil

from native_process import run_bounded
from recorded_channels import channels
from recorded_effects import check_trace
from recorded_failures import RecordedFailure
from recorded_trace import parse_trace


def add_bytes(used, size, limit):
    if used < 0 or size < 0 or size > limit - used:
        raise RecordedFailure("staging_limit_exceeded")
    return used + size


def execute(env, tests, runtime, selected, runner, phase, *, collect_failures=False, suffix="run", transform=None, command_builder):
    temporary = env.parent / (env.name + "-" + suffix)
    (temporary / "work").mkdir(parents=True)
    (temporary / "tmp").mkdir()
    prefix = temporary / "trace"
    strace = shutil.which("strace", path=runner.env["PATH"])
    argv = [strace, "-ff", "-qq", "-ttt", "-yy", "-s", "4096", "-e",
            "raw=read,readv,pread64,write,writev,pwrite64", "-o", str(prefix),
            *command_builder(env, tests, temporary, runtime, selected, runner)]
    if transform is not None:
        argv = transform(argv)
    config = temporary / "exec.json"
    config.write_text(json.dumps(argv))
    with channels() as (receipt, markers):
        def watch():
            runner.watch()
            receipt.read()
            markers.read()
            total = 0
            for path in temporary.glob("trace.*"):
                total = add_bytes(total, path.stat().st_size, 8 * 1024 ** 2)
        child = run_bounded([shutil.which("python3", path=runner.env["PATH"]), "-B",
                             str(Path(__file__).with_name("recorded_exec.py")), str(config),
                             str(receipt.writer), str(markers.writer)],
                            cwd=runner.owned, env=runner.env, timeout=min(30, phase.seconds()),
                            pass_fds=(receipt.writer, markers.writer), watch=watch)
        print(child.output, end="", flush=True)
        runner.commands.append({"argv": argv, "exit_code": child.returncode, "executable": strace})
        if child.truncated or child.returncode not in ({0, 1} if collect_failures else {0}):
            raise RecordedFailure("case_inventory_invalid")
        result, observations = json.loads(receipt.finish()), markers.finish()
    try:
        traces = {int(path.name.split(".")[-1]): parse_trace(int(path.name.split(".")[-1]), path.read_text())
                  for path in temporary.glob("trace.*")}
        configuration = json.loads((tests / "qualification-input.json").read_bytes())
        observed = check_trace(traces, observations, runtime, python_version=configuration.get("python_version", "3.13.13"))
    except RecordedFailure as error:
        if selected == "isolation-probe" and "traces" in locals():
            from recorded_descriptors import PATH_ARGS
            from recorded_trace import arguments, quoted
            paths = set()
            for events in traces.values():
                if not any(e.name == "execve" and e.arguments.startswith('"/env/bin/python"') for e in events):
                    continue
                for event in events:
                    if event.name in PATH_ARGS:
                        path = quoted(arguments(event.arguments)[PATH_ARGS[event.name][1]])
                        if path.startswith("/") and not any(path == root or path.startswith(root + "/") for root in runtime):
                            paths.add((path, event.result.split(" ", 2)[0:2][0] if not event.result.startswith("-1") else event.result.split(" ", 2)[1]))
            print("PROBE_PATH_DIAGNOSTICS=" + json.dumps(sorted(paths)[:256]), flush=True)
        if selected != "isolation-probe" and not selected.startswith("control:"):
            error.observed_result = result
        for note in getattr(error, "__notes__", []):
            print(note, flush=True)
        raise
    if selected == "isolation-probe":
        if result != {"probe": "isolation", "outcome": "passed"} or not traces:
            raise RecordedFailure("isolation_invalid")
        return result, {"probe_only": True, **observed}
    if selected.startswith("control:"):
        if result != {"control": selected.removeprefix("control:"), "outcome": "passed"}:
            raise RecordedFailure("case_inventory_invalid")
    return result, observed
