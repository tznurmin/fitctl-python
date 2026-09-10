# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Match each declared direct child to a complete trace in its collection interval."""

import copy
import re

from collection_effects import COMMAND_SCOPES
from recorded_descriptors import OPEN, PATH_ARGS, READ, annotation, forbidden, under
from recorded_trace import arguments, descriptor, invalid, quoted

MODES = {"good", "empty", "malformed", "exit7", "oversized", "sleep2", "delay0.2"}
STARTUP = {"arch_prctl", "set_tid_address", "set_robust_list", "rseq", "prlimit64", "getrandom",
           "getuid", "geteuid", "getgid", "getegid", "getgroups", "getcwd", "sched_getaffinity"}
BOOTSTRAP_READS = {'/tests/collection_provider.py', '/dev/null', '/proc/sys/vm/overcommit_memory'}


def executable(event, scope):
    args = arguments(event.arguments)
    path = quoted(args[0])
    argv = arguments(args[1][1:-1])
    argv = [quoted(item) for item in argv]
    return path, argv


def admitted_exec(event, scope):
    path, argv = executable(event, scope)
    allowed = []
    if scope == 'SURVEY_BEGIN':
        allowed = [['ip', '-json', 'addr', 'show']] + [['ip', flag, '-json', 'route', 'show', 'default'] for flag in ('-4', '-6')]
    if scope == 'OPTIONAL_BEGIN':
        allowed = [['sensors', '-j'], ['nvidia-smi', '-q', '-x']]
    if scope in {'PROVIDER_BEGIN', 'OPTIONAL_BEGIN'}:
        if path == '/env/bin/python' and argv[:4] == [path, '-I', '-B', '/tests/collection_provider.py'] and len(argv) == 5 and argv[-1] in MODES:
            return
        if path in {'/work/collection-tools/missing', '/work/collection-tools/denied'} and argv == [path]:
            return
    if any(path == '/env/bin/' + command[0] and argv in (command, [path, *command[1:]]) for command in allowed):
        return
    forbidden(event)


class Children:
    def __init__(self, traces, root, marker_tids):
        self.candidates = sorted((events for pid, events in traces.items() if pid != root and not any(
            e.name == 'gettid' and e.result in marker_tids for e in events)), key=lambda events: events[0].time)
        self.used, self.rows = set(), []

    def parent(self, event, scope):
        if scope.name not in COMMAND_SCOPES:
            forbidden(event)
        args, name = arguments(event.arguments), event.name
        if name in {'fork', 'vfork', 'clone', 'clone3'}:
            flags = set(re.findall(r'CLONE_[A-Z_]+', event.arguments))
            if not flags <= {'CLONE_VM', 'CLONE_VFORK', 'CLONE_CLEAR_SIGHAND', 'CLONE_CHILD_SETTID', 'CLONE_CHILD_CLEARTID'}:
                forbidden(event)
            if event.result.startswith('-1'):
                return
            if len(self.rows) >= 128 or any(row['end'] >= event.time for row in self.rows):
                forbidden(event)
            candidates = [events for events in self.candidates if events[0].pid not in self.used and events[0].time >= event.time]
            if not candidates:
                invalid()
            events = candidates[0]
            terminal = events[-1]
            killed = (terminal.name, terminal.arguments) == ('killed', 'SIGKILL')
            if not killed and (terminal.name != 'exit_group' or terminal.result != '?' or terminal.arguments not in {'0', '1', '7', '127'}):
                invalid()
            handles = copy.deepcopy(scope.handles)
            self.check_child(events, handles, scope, descriptor(event.result))
            row = {'tid': descriptor(event.result), 'end': terminal.time, 'waited': False, 'killed': killed, 'kill_seen': False}
            self.rows.append(row); scope.spawned.append(row); self.used.add(events[0].pid)
            return
        if name in {'pipe', 'pipe2'}:
            if event.result == '0':
                ends = arguments(args[0][1:-1])
                if len(ends) != 2:
                    invalid()
                for end in ends:
                    match = re.fullmatch(r'([0-9]+)<(pipe:\[[0-9]+\])>', end)
                    if match is None:
                        invalid()
                    scope.handles.files[int(match[1])] = match[2]
                    scope.opened.add(int(match[1])); scope.pipes.add(match[2])
            return
        if name in {'wait4', 'waitid', 'kill'}:
            if name == 'waitid' and args[0] != 'P_PID':
                forbidden(event)
            tid = descriptor(args[1] if name == 'waitid' else args[0])
            rows = [row for row in scope.spawned if row['tid'] == tid]
            if len(rows) != 1:
                forbidden(event)
            row = rows[0]
            if name == 'kill':
                if args[1] != 'SIGKILL' or event.result != '0':
                    forbidden(event)
                row['kill_seen'] = True
            elif (event.result == str(tid) or (name == 'waitid' and event.result == '0')):
                row['waited'] = True
            return
        if name == 'fcntl':
            if scope.owned_fd(args[0]) not in scope.pipes or args[1] not in {'F_GETFL', 'F_SETFL', 'F_GETFD', 'F_SETFD'}:
                forbidden(event)
            return
        if name in {'poll', 'ppoll'}:
            for match in re.finditer(r'fd=([^,}]+)', args[0]):
                if scope.owned_fd(match[1]) not in scope.pipes:
                    forbidden(event)
            return
        forbidden(event)

    def check_child(self, events, handles, scope, child_pid):
        from recorded_effects import PURE
        execs, emitted, memory_queries = 0, 0, 0
        maps_path, maps_opened, script_started, maps_bytes = None, False, False, 0
        maps_seeks = 0
        for event in events:
            args, name = arguments(event.arguments), event.name
            if name == 'execve':
                execs += 1
                admitted_exec(event, scope.name)
            elif name in (PURE - {'mmap'}) | STARTUP | {'exit_group', 'killed', 'exited', 'close_range'}:
                pass
            elif name == 'sysinfo' and '/usr/local' in scope.runtime and execs == 1:
                memory_queries += 1
                if memory_queries != 1 or event.result != '0':
                    forbidden(event)
            elif name in {'dup2', 'dup3'}:
                if descriptor(args[1]) not in {0, 1, 2} or handles.path(args[0]) not in scope.pipes | {'/dev/null'}:
                    forbidden(event)
            elif name in PATH_ARGS:
                path = handles.resolved(event)
                if path == '/proc/self/maps':
                    # CPython 3.14 asks glibc for its own main-thread stack limits.
                    # Admit one read-only startup handle, never another process.
                    actual = annotation(event.result.split(' ', 1)[0])
                    if (scope.python_version != '3.14.4' or execs != 1 or maps_opened or script_started
                            or name != 'openat' or args[2] != 'O_RDONLY|O_CLOEXEC'
                            or actual != f'/proc/{child_pid}/maps'):
                        forbidden(event)
                    maps_path, maps_opened = actual, True
                    handles.observe(event)
                    continue
                if path == maps_path:
                    if script_started or name != 'newfstatat' or quoted(args[1]) != '' or args[3] != 'AT_EMPTY_PATH' or event.result != '0':
                        forbidden(event)
                    handles.observe(event)
                    continue
                if name in OPEN and path in {'/tests/collection_provider.py', '/env/bin/ip', '/env/bin/sensors', '/env/bin/nvidia-smi'}:
                    script_started = True
                if (name == 'newfstatat' and quoted(args[1]) == '' and args[3] == 'AT_EMPTY_PATH'
                        and path in scope.pipes and args[0] == f'{descriptor(args[0])}<{path}>'
                        and event.result == '0'):
                    handles.observe(event)
                    continue
                roots = ['/env', *scope.runtime]
                prefix = '/usr/local/bin/../lib/'
                if '/usr/local' in scope.runtime and execs == 1 and path.startswith(prefix):
                    # The verified image's loader expands its $ORIGIN/../lib
                    # search path. Only this prefix maps back into its runtime.
                    path = '/usr/local/lib/' + path.removeprefix(prefix)
                allowed = under(path, roots) or path in BOOTSTRAP_READS
                if (name == 'readlink' and path == '/proc/self/exe'
                        and '/usr/local' in scope.runtime and execs == 1):
                    # The admitted public Python provider resolves its own
                    # executable during startup. No other process or target.
                    allowed = quoted(args[1]) in {'/usr/local/bin/python3.12', '/usr/local/bin/python3.13',
                                                  '/usr/local/bin/python3.14'} and event.result == '25'
                if path in {'/usr/share/locale/locale.alias', '/usr/lib/python312.zip', '/usr/lib/python313.zip', '/usr/lib/python314.zip',
                            '/usr/lib/ssl/openssl.cnf', '/usr/share/zoneinfo/UTC0'} and '/usr/local' in scope.runtime:
                    allowed = event.result.startswith('-1 ENOENT')
                if path in {'/etc/ld-nix.so.preload', '/etc/ld-nix.so.cache', '/etc/ld.so.cache', '/etc/ld.so.preload',
                            '/run/current-system/sw/lib/locale/locale-archive', '/usr/lib/locale/locale-archive',
                            '/nix/store/lib/python312.zip', '/nix/lib/python312.zip',
                            '/nix/store/lib/python313.zip', '/nix/lib/python313.zip',
                            '/nix/store/lib/python314.zip', '/nix/lib/python314.zip'}:
                    allowed = event.result.startswith('-1 ENOENT')
                if name not in OPEN:
                    allowed |= path in {'/', '/nix', '/nix/store', '/work', '/tests'}
                    if '/usr/local' in scope.runtime:
                        allowed |= path in {'/usr', '/usr/lib', '/usr/lib64', '/lib'}
                if not allowed or any(flag in event.arguments for flag in ('O_WRONLY', 'O_RDWR', 'O_CREAT', 'O_TRUNC')):
                    forbidden(event)
                actual = annotation(event.result.split(' ', 1)[0]) if name in OPEN else None
                if actual is not None and actual not in BOOTSTRAP_READS and not under(actual, roots):
                    forbidden(event)
            elif name in READ | {'mmap', 'ioctl', 'fcntl'}:
                if name == 'mmap' and descriptor(args[4]) == -1 and 'MAP_ANONYMOUS' in args[3]:
                    continue
                path = handles.path(args[4] if name == 'mmap' else args[0])
                if maps_path is not None and path == maps_path:
                    if name == 'fstat' and event.result == '0' and not script_started:
                        continue
                    if name == 'lseek' and not script_started:
                        offset, position = descriptor(args[1]), descriptor(event.result)
                        if (maps_seeks >= 2 or not 0 <= position <= maps_bytes
                                or (maps_seeks == 0 and (offset != 0 or args[2] != 'SEEK_CUR'))
                                or (maps_seeks == 1 and (offset != position or args[2] != 'SEEK_SET'))):
                            forbidden(event)
                        maps_seeks += 1
                        continue
                    if name == 'close' and event.result == '0' and not script_started:
                        handles.observe(event)
                        maps_path = None
                        continue
                    maps_bytes += max(0, descriptor(event.result))
                    if name != 'read' or script_started or maps_bytes > 256 * 1024:
                        forbidden(event)
                    handles.observe(event)
                    continue
                if path not in scope.pipes | BOOTSTRAP_READS and not under(path, ['/env', *scope.runtime]):
                    forbidden(event)
                if name == 'ioctl' and args[1] not in {'TCGETS', 'TCGETS2', 'FIOCLEX'}:
                    forbidden(event)
                if name == 'fcntl' and not (args[1] in {'F_GETFL', 'F_GETFD'} or (args[1:] == ['F_SETFD', 'FD_CLOEXEC'])):
                    forbidden(event)
            elif name == 'write':
                if handles.path(args[0]) not in scope.pipes:
                    forbidden(event)
                emitted += max(0, descriptor(event.result))
                if emitted > 1048577 + 4096:
                    forbidden(event)
            else:
                forbidden(event)
            if name not in {'killed', 'exited', 'signal'}:
                handles.observe(event)
        if execs != 1 or maps_path is not None:
            invalid()

    def finish(self):
        if len(self.used) != len(self.candidates):
            invalid()
