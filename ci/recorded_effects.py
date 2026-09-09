# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete import/call intervals and attempted-effect policy."""

from collections import defaultdict
import re

from recorded_failures import RecordedFailure
from recorded_trace import arguments, descriptor, invalid, quoted
from recorded_descriptors import Descriptors, PATH_ARGS, READ, forbidden
from collection_effects import SCOPES, Scope
from collection_processes import Children

MEMORY = {"brk", "mmap", "mprotect", "munmap", "mremap", "madvise"}
SYNC = {"futex", "futex_waitv", "sched_yield", "clock_gettime", "clock_nanosleep", "restart_syscall"}
SIGNALS = {"rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "signal"}
PURE = MEMORY | SYNC | SIGNALS | {"gettid", "getpid"}
FORBIDDEN = {"execve", "execveat", "fork", "vfork", "socket", "socketpair", "connect", "bind", "listen",
             "accept", "accept4", "sendto", "sendmsg", "recvfrom", "recvmsg", "memfd_create", "io_uring_setup",
             "mount", "umount2", "ptrace", "bpf", "open_by_handle_at"}


def check_call(event):
    if event.name in PURE:
        if event.name == "mmap" and descriptor(arguments(event.arguments)[4]) != -1:
            forbidden(event)
        return
    forbidden(event)


def check_import(event, runtime, handles):
    if event.name in (PURE - {"mmap"}) | {"getrandom"}:
        return
    if event.name in PATH_ARGS or event.name in READ | {"mmap", "ioctl"}:
        handles.admit_import(event, runtime)
        return
    forbidden(event)


def thread_end(traces, tid):
    matches = [events for events in traces.values()
               if any(event.name == "gettid" and event.result == tid for event in events)]
    if len(matches) != 1:
        invalid()
    terminal = matches[0][-1]
    if (terminal.name, terminal.arguments, terminal.result) != ("exit", "0", "?"):
        invalid()
    return terminal.time


def check_trace(traces, marker_data, runtime):
    if not marker_data.endswith(b"\n"):
        invalid()
    try:
        lines = marker_data.decode("ascii").splitlines()
    except UnicodeError:
        invalid()
    marker_queues = defaultdict(list)
    for line in lines:
        match = re.fullmatch(r"FITCTL_(IMPORT_BEGIN|IMPORT_END|BEGIN|END|(?:REPLAY|CONFIG|STATE|SURVEY|PATH|PROVIDER|OPTIONAL)_BEGIN) ([1-9][0-9]*)", line)
        if match is None:
            invalid()
        marker_queues[int(match[2])].append((match[1], len(line.encode()) + 1))
    if sum(sum(marker == "IMPORT_BEGIN" for marker, _ in queue) for queue in marker_queues.values()) != 1:
        invalid()
    starts = [event for events in traces.values() for event in events
              if event.name == "execve" and event.arguments.startswith('"/env/bin/python"')]
    if not starts:
        invalid()
    start = min(starts, key=lambda event: event.time)
    selected = {pid: events for pid, events in traces.items()
                if pid == start.pid or events[0].time > start.time}
    intervals, threads, tids = 0, set(), set()
    handles = Descriptors()
    children = Children(selected, start.pid, {str(tid) for tid in marker_queues})
    child_pids = {events[0].pid for events in children.candidates}
    # The interpreter creates its descendants. Inspect its effects before
    # descendant completeness, regardless of filesystem trace enumeration.
    for pid in sorted(selected, key=lambda pid: (pid != start.pid, selected[pid][0].time, pid)):
        if pid in child_pids:
            continue  # Admitted only through its parent's declared spawn and terminal wait.
        events = selected[pid]
        state, tid, marker_count = None, None, 0
        collection = None
        for event in events:
            if event.time <= start.time:
                continue
            if event.name == "gettid":
                try:
                    tid = int(event.result)
                except ValueError:
                    invalid()
                tids.add(tid)
            if event.name == "write" and descriptor(arguments(event.arguments)[0]) == 4:
                if tid is None or not marker_queues[tid]:
                    invalid()
                marker, size = marker_queues[tid].pop(0)
                args = arguments(event.arguments)
                if descriptor(args[2]) != size or descriptor(event.result) != size:
                    invalid()
                marker_count += 1
                if marker in {"BEGIN", "IMPORT_BEGIN"} | SCOPES:
                    if state is not None:
                        invalid()
                    state = marker
                    collection = Scope(marker, handles, runtime, children) if marker in SCOPES else None
                    intervals += 1
                elif (state, marker) in (("BEGIN", "END"), ("IMPORT_BEGIN", "IMPORT_END")) or (state in SCOPES and marker == "END"):
                    if collection is not None:
                        collection.finish(event.time)
                    state = None
                    collection = None
                else:
                    invalid()
                continue
            if collection is not None:
                try:
                    collection.check(event)
                except RecordedFailure as error:
                    error.add_note("observation phase: " + state)
                    raise
            elif state == "BEGIN":
                try:
                    check_call(event)
                except RecordedFailure as error:
                    error.add_note("observation phase: public call")
                    raise
            elif state == "IMPORT_BEGIN":
                try:
                    check_import(event, runtime, handles)
                except RecordedFailure as error:
                    error.add_note("observation phase: package import")
                    raise
            elif event.name in FORBIDDEN:
                forbidden(event)
            elif event.name in {"clone", "clone3"}:
                if "CLONE_THREAD" not in event.arguments:
                    forbidden(event)
                threads.add(event.result.split()[0])
                # Bound simultaneous harness workers, including across suites.
                # A completed pair does not consume the next pair's capacity;
                # its observed terminal syscall remains required evidence.
                if sum(thread_end(selected, value) >= event.time
                       for value in threads if value != "-1") > 2:
                    forbidden(event)
            if event.name not in {"signal", "exited", "killed"}:
                handles.observe(event)
        if state is not None:
            invalid()
        if pid != start.pid and not marker_count:
            invalid()
    # -qq suppresses strace's synthetic exit summary. Require the observed
    # terminal syscall; execute() separately requires the supervised exit 0.
    terminal = selected[start.pid][-1]
    children.finish()
    if (any(marker_queues.values()) or intervals < 2
            or any(int(value) not in tids for value in threads if value != "-1")
            or (terminal.name, terminal.arguments, terminal.result) != ("exit_group", "0", "?")):
        invalid()
    return {"complete": True, "intervals": intervals, "processes": len(selected)}
