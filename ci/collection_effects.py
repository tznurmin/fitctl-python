# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Declared collection reads and owned probe writes within existing call intervals."""

from pathlib import PurePosixPath
import re

from recorded_descriptors import OPEN, PATH_ARGS, READ, annotation, forbidden, under
from recorded_trace import arguments, descriptor, invalid, quoted

SCOPES = {name + "_BEGIN" for name in ("REPLAY", "CONFIG", "STATE", "SURVEY", "PATH", "PROVIDER", "OPTIONAL")}
COMMAND_SCOPES = {"SURVEY_BEGIN", "PROVIDER_BEGIN", "OPTIONAL_BEGIN"}
LIVE = {"STATE_BEGIN", "SURVEY_BEGIN", "PATH_BEGIN", "PROVIDER_BEGIN", "OPTIONAL_BEGIN"}
IDENTITY = {"uname", "getuid", "geteuid", "getgid", "getegid", "getgroups", "sched_getaffinity", "sysinfo"}
MUTATION = {"mkdir": (None, 0), "mkdirat": (0, 1), "unlink": (None, 0),
            "unlinkat": (0, 1), "rmdir": (None, 0)}
PROBE = re.compile(r"/work/paths/(a|b|denied|file|missing)/\.fitctl-link-(?:pair-)?probe-[0-9]+-[0-9]+(?:-source|-destination)?(?:/(?:source|hardlink|symlink|copy|reflink))?")
CONFIG = "/work/collection-configs"
PATHS = "/work/paths"
DEVICE_DIRS = {"SURVEY_BEGIN": {"/dev", "/dev/dri"}, "PATH_BEGIN": {"/dev/disk"}}
EXACT = {"/etc/machine-id", "/etc/hostname", "/var/lib/dbus/machine-id", "/.dockerenv",
         "/run/.containerenv", "/run/systemd/container"}


def resolved(event, handles, indexes):
    args = arguments(event.arguments)
    base, index = indexes
    path = quoted(args[index])
    if path.startswith('/'):
        return path
    parent = handles.cwd if base is None or args[base] == 'AT_FDCWD' else handles.path(args[base])
    return str(PurePosixPath(parent) / path)


def probe(path):
    return PROBE.fullmatch(path.removesuffix(' (deleted)')) is not None


class Scope:
    def __init__(self, name, handles, runtime, children):
        self.name, self.handles, self.runtime, self.children = name, handles, runtime, children
        self.opened, self.pipes = set(), set()
        self.spawned = []

    def readable(self, path, *, metadata=False):
        if not path.startswith('/'):
            return False
        if self.name == 'SURVEY_BEGIN' and path == '/dev':
            return True  # Only a directory handle can be opened below.
        roots = (["/work/collection"] if self.name == "REPLAY_BEGIN" else
                 [CONFIG] if self.name == "CONFIG_BEGIN" else ["/proc", "/sys", PATHS])
        if self.name in {"PROVIDER_BEGIN", "OPTIONAL_BEGIN"}:
            roots += [CONFIG, "/work/collection-tools"]
        if under(path, roots) or (self.name in LIVE and path in EXACT):
            return True
        # Canonical path traversal may inspect ancestors, but cannot open them.
        return metadata and any(PurePosixPath(path) in PurePosixPath(root).parents for root in roots + sorted(EXACT if self.name in LIVE else []))

    def owned_fd(self, text):
        number = descriptor(text)
        if number not in self.opened:
            invalid()
        expected, actual = self.handles.files.get(number), annotation(text)
        if expected is not None and probe(expected) and actual == expected + ' (deleted)':
            return expected
        return self.handles.path(text)

    def check(self, event):
        from recorded_effects import PURE
        args, name = arguments(event.arguments), event.name
        if name in PURE - {"mmap"}:
            return
        if name in IDENTITY and self.name in LIVE:
            return
        if name == 'prlimit64' and self.name in LIVE and len(args) == 4:
            if args[0] == '0' and args[2] == 'NULL' and re.fullmatch(r'RLIMIT_[A-Z_]+', args[1]):
                return  # Query this process only; setting a limit remains forbidden.
            forbidden(event)
        if name == 'fcntl' and args[1] in {'F_GETFL', 'F_GETFD', 'F_SETFD', 'F_DUPFD_CLOEXEC'}:
            path = self.owned_fd(args[0])
            if not (self.readable(path) or path in self.pipes):
                forbidden(event)
            if args[1] == 'F_SETFD' and args[2] != 'FD_CLOEXEC':
                forbidden(event)
            if args[1] == 'F_DUPFD_CLOEXEC' and not event.result.startswith('-1'):
                self.opened.add(descriptor(event.result.split(' ', 1)[0]))
            return
        if name in {"fork", "vfork", "clone", "clone3", "wait4", "waitid", "kill", "pipe", "pipe2", "fcntl", "poll", "ppoll"}:
            self.children.parent(event, self)
            return
        indexes = PATH_ARGS.get(name, (None, 0) if name == "statfs" else None)
        if indexes is not None:
            path = resolved(event, self.handles, indexes)
            writing = name in OPEN and any(flag in event.arguments for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_TMPFILE"))
            actual = annotation(event.result.split(' ', 1)[0]) if name in OPEN else None
            admitted = ((self.name == 'PATH_BEGIN' and probe(path) and (actual is None or probe(actual))) if writing else
                        (self.readable(path, metadata=name not in OPEN) and (actual is None or self.readable(actual))))
            if self.name in COMMAND_SCOPES and path == '/dev/null' and not writing:
                admitted = actual in (None, '/dev/null')
            if path in DEVICE_DIRS.get(self.name, set()):
                admitted = (not writing and (name not in OPEN or 'O_DIRECTORY' in event.arguments)
                            and actual in (None, path))
                if path != '/dev':
                    admitted &= event.result.startswith('-1 ENOENT')
            if not admitted:
                forbidden(event)
            if name in OPEN and not event.result.startswith('-1'):
                self.opened.add(descriptor(event.result.split(' ', 1)[0]))
            return
        if name in READ | {"mmap", "ioctl", "fstatfs"}:
            if name == 'mmap' and descriptor(args[4]) == -1 and 'MAP_ANONYMOUS' in args[3]:
                return
            path = self.owned_fd(args[4] if name == 'mmap' else args[0])
            if name == 'ioctl':
                if self.name != 'PATH_BEGIN' or args[1] not in {'FICLONE', 'BTRFS_IOC_CLONE or FICLONE'} or not probe(path) or not probe(self.owned_fd(args[2])):
                    forbidden(event)
            elif name == 'mmap' and ('MAP_SHARED' in args[3] or not self.readable(path)):
                forbidden(event)
            elif not (self.readable(path) or path in self.pipes or (self.name in COMMAND_SCOPES and path == '/dev/null')):
                forbidden(event)
            if name == 'close' and event.result == '0':
                self.opened.discard(descriptor(args[0]))
            return
        if self.name != 'PATH_BEGIN':
            forbidden(event)
        if name in MUTATION:
            if not probe(resolved(event, self.handles, MUTATION[name])):
                forbidden(event)
            return
        if name in {'link', 'symlink', 'linkat', 'symlinkat'}:
            locations = ([(None, 0), (None, 1)] if name in {'link', 'symlink'} else
                         [(0, 1), (2, 3)] if name == 'linkat' else [(None, 0), (1, 2)])
            if not all(probe(resolved(event, self.handles, index)) for index in locations):
                forbidden(event)
            return
        if name in {'write', 'pwrite64', 'ftruncate', 'fchmod', 'copy_file_range', 'sendfile'}:
            source = self.owned_fd(args[0])
            if not probe(source):
                forbidden(event)
            if name in {'write', 'pwrite64'} and descriptor(args[2]) > 23:
                forbidden(event)
            if name in {'copy_file_range', 'sendfile'}:
                target = self.owned_fd(args[2] if name == 'copy_file_range' else args[1])
                if not probe(target) or (not event.result.startswith('-1') and descriptor(event.result) > 23):
                    forbidden(event)
            if name == 'ftruncate' and descriptor(args[1]) > 23:
                forbidden(event)
            return
        forbidden(event)

    def finish(self, instant):
        for child in self.spawned:
            if child['end'] >= instant or not child['waited'] or (child['killed'] != child['kill_seen']):
                invalid()
