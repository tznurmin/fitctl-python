# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve observed file descriptors; an inherited handle is not import authority."""

from pathlib import PurePosixPath
import re

from recorded_failures import RecordedFailure
from recorded_trace import arguments, descriptor, invalid, quoted

PATH_ARGS = {"open": (None, 0), "openat": (0, 1), "openat2": (0, 1), "stat": (None, 0),
             "lstat": (None, 0), "newfstatat": (0, 1), "statx": (0, 1), "access": (None, 0),
             "faccessat": (0, 1), "faccessat2": (0, 1), "readlink": (None, 0), "readlinkat": (0, 1)}
OPEN = {"open", "openat", "openat2"}
READ = {"fstat", "lseek", "read", "readv", "pread64", "getdents64", "getdents", "close"}


def forbidden(event=None):
    error = RecordedFailure("effect_forbidden")
    if event is not None:
        error.add_note("rejected syscall " + event.name + " at " + str(event.time))
        error.add_note("syscall detail: " + (event.arguments + " = " + event.result)[:1024])
    raise error


def under(path, roots):
    parsed = PurePosixPath(path)
    if not parsed.is_absolute() or ".." in parsed.parts:
        try:
            invalid()
        except RecordedFailure as error:
            error.add_note("noncanonical observed path: " + repr(path[:512]))
            raise
    return any(parsed == PurePosixPath(root) or PurePosixPath(root) in parsed.parents for root in roots)


def annotation(text):
    match = re.fullmatch(r"\d+<(/[^<>]+)>", text)
    return match[1] if match else None


class Descriptors:
    def __init__(self):
        self.files = {0: "/dev/null", 1: "@stdout", 2: "@stderr", 3: "@receipt", 4: "@markers"}
        self.cwd = "/work"

    def path(self, value):
        number = descriptor(value)
        if number not in self.files:
            invalid()
        path = self.files[number]
        observed = annotation(value)
        if observed is not None and observed != path:
            invalid()
        return path

    def resolved(self, event):
        args = arguments(event.arguments)
        base_index, path_index = PATH_ARGS[event.name]
        path = quoted(args[path_index])
        if path.startswith("/"):
            return path
        base = self.cwd if base_index is None or args[base_index] == "AT_FDCWD" else self.path(args[base_index])
        return str(PurePosixPath(base) / path)

    def admit_import(self, event, runtime):
        args = arguments(event.arguments)
        if event.name in PATH_ARGS:
            path = self.resolved(event)
            if not under(path, ["/env", *runtime]) or any(flag in event.arguments for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC")):
                try:
                    forbidden(event)
                except RecordedFailure as error:
                    error.add_note("import path root: /" + path.split("/")[1])
                    raise
        elif event.name in READ or event.name in {"mmap", "ioctl"}:
            if event.name == "ioctl" and args[1] not in {"TCGETS", "TCGETS2"}:
                try:
                    forbidden(event)
                except RecordedFailure as error:
                    request = args[1]
                    if re.fullmatch(r"[A-Z0-9_x]+", request):
                        error.add_note("ioctl request: " + request[:64])
                    raise
            arg = args[4] if event.name == "mmap" else args[0]
            if event.name == "mmap" and descriptor(arg) == -1 and "MAP_ANONYMOUS" in args[3]:
                return
            path = self.path(arg)
            if path.startswith("@") or not under(path, ["/env", *runtime]):
                forbidden(event)
        else:
            forbidden(event)

    def observe(self, event):
        args = arguments(event.arguments)
        if event.name in OPEN and not event.result.startswith("-1"):
            result = event.result.split(" ", 1)[0]
            self.files[descriptor(result)] = annotation(result) or self.resolved(event)
        elif event.name == "close" and event.result == "0":
            self.files.pop(descriptor(args[0]), None)
        elif event.name in {"dup", "dup2", "dup3"} and not event.result.startswith("-1"):
            self.files[descriptor(event.result.split(" ", 1)[0])] = self.path(args[0])
        elif event.name == "fcntl" and "F_DUPFD" in event.arguments and not event.result.startswith("-1"):
            self.files[descriptor(event.result.split(" ", 1)[0])] = self.path(args[0])
        elif event.name == "chdir" and event.result == "0":
            path = quoted(args[0])
            self.cwd = path if path.startswith("/") else str(PurePosixPath(self.cwd) / path)
        elif event.name == "fchdir" and event.result == "0":
            self.cwd = self.path(args[0])
