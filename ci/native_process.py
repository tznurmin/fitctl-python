# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded output, deadlines, resource monitoring and owned process cleanup."""

import ctypes
from dataclasses import dataclass
from functools import partial
import os
import selectors
import signal
import subprocess
import time

from native_policy import NativeFailure


@dataclass
class Result:
    returncode: int
    output: str
    truncated: bool


def parent_death_signal(parent, ignore_interrupt=False):
    if ignore_interrupt:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        os._exit(125)
    if os.getppid() != parent:
        os._exit(125)


def kill_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def run_bounded(command, *, timeout, cwd=None, env=None, watch=None, grace=1,
                output_limit=65536, pass_fds=(), interactive=False, session=None):
    if timeout <= 0 or not 1 <= output_limit <= 1024 * 1024:
        raise NativeFailure("supervisor_limits_invalid", "positive deadline and bounded output required")
    process = subprocess.Popen(command, cwd=cwd, env=env,
                               stdin=None if interactive else subprocess.DEVNULL,
                               stdout=None if interactive else subprocess.PIPE,
                               stderr=None if interactive else subprocess.STDOUT,
                               pass_fds=(*pass_fds, session.child_fd) if session else pass_fds,
                               start_new_session=session is None,
                               **({"process_group": 0} if session else {}),
                               preexec_fn=partial(parent_death_signal, os.getpid(), session is not None))
    tail = bytearray()
    truncated = False
    started, next_watch = time.monotonic(), 0
    pidfd = None
    try:
        with selectors.DefaultSelector() as selector:
            if session is not None:
                clock = session.clock(started, timeout)
                session.spawned()
                pidfd = os.pidfd_open(process.pid)
                selector.register(pidfd, selectors.EVENT_READ, "exit")
                selector.register(session.channel, selectors.EVENT_READ, "ready")
            if process.stdout is not None:
                selector.register(process.stdout, selectors.EVENT_READ, "output")
            while True:
                now = time.monotonic()
                if session is not None:
                    clock.wait_seconds(now)  # Reject setup expiry before another check.
                    if clock.check_due(now):
                        if session.runtime:
                            session.watch()
                        elif watch is not None:
                            watch()
                        clock.checked(now)
                    now = time.monotonic()
                    wait = min(clock.wait_seconds(now), max(0.0, clock.next_check - now))
                elif now - started >= timeout:
                    raise NativeFailure("deadline_exceeded", f"operation exceeded {timeout} seconds")
                elif watch is not None and now >= next_watch:
                    watch()
                    next_watch = now + 0.5
                events = selector.select(wait if session is not None else 0.05)
                for key, _ in events:
                    if key.data == "exit":
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "ready":
                        if session.receive(process):
                            clock.ready(time.monotonic())
                        selector.unregister(key.fileobj)
                        continue
                    data = os.read(key.fd, 16384)
                    if data:
                        tail.extend(data)
                        if len(tail) > output_limit:
                            del tail[:-output_limit]
                            truncated = True
                    else:
                        selector.unregister(key.fileobj)
                if process.poll() is not None and not events:
                    break
                if process.poll() is not None and not selector.get_map():
                    break
        if session is not None and process.returncode == 0 and not session.runtime:
            raise NativeFailure("operation_failed", "Python exited without validated runtime readiness")
        return Result(process.wait(), tail.decode("utf-8", errors="replace"), truncated)
    except NativeFailure as error:
        if tail:
            error.add_note(tail.decode("utf-8", errors="replace"))
        raise
    finally:
        kill_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
        kill_group(process, signal.SIGKILL)
        process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if pidfd is not None:
            os.close(pidfd)


def checked(command, **kwargs):
    result = run_bounded(command, **kwargs)
    if result.output:
        print(result.output, end="", flush=True)
    if result.truncated:
        print("[diagnostic output retained as a bounded tail]", flush=True)
    if result.returncode:
        raise NativeFailure("command_failed", f"{command[0]} exited {result.returncode}")
    return result
