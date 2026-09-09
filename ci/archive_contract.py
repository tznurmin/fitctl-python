# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure bounded archive admission. The caller owns streams and extraction."""

from dataclasses import dataclass
import hashlib
import io
from pathlib import PurePosixPath
import re
import stat
import tarfile
import zipfile

from .archive_metadata import validate_content

PRIVATE = re.compile(rb"\b[A-Z]{2}-[0-9]{4}\b|/(?:home|Users)/|ssh:/{2}|git\x40[a-z0-9.-]+:|\b[A-Za-z0-9_-]+\.execution\.", re.I)


@dataclass(frozen=True)
class Limits:
    members: int = 4096
    member_bytes: int = 64 * 1024 ** 2
    archive_bytes: int = 256 * 1024 ** 2
    expanded_bytes: int = 512 * 1024 ** 2


@dataclass(frozen=True)
class ArchiveInventory:
    members: tuple
    name: str
    version: str


def invalid():
    raise ValueError("archive content invalid")


def charge(used, size, limit):
    if any(type(value) is not int or value < 0 for value in (used, size, limit)):
        invalid()
    if used > limit or size > limit - used:
        raise OverflowError("archive limit exceeded")
    return used + size


def canonical(name, directory=False):
    if type(name) is not str or not name or "\\" in name or "\0" in name:
        invalid()
    normalized = name.removesuffix("/") if directory else name
    path = PurePosixPath(normalized)
    if (path.is_absolute() or str(path) != normalized or ".." in path.parts
            or set(path.parts) & {".git", ".venv", "target", "__pycache__"}
            or PRIVATE.search(name.encode("utf-8"))):
        invalid()
    return normalized


def read_member(stream, size, limits):
    charge(0, size, limits.member_bytes)
    output = bytearray()
    while len(output) < size:
        chunk = stream.read(min(65536, size - len(output)))
        if not chunk:
            invalid()
        charge(len(output), len(chunk), size)
        output.extend(chunk)
    if stream.read(1):
        invalid()
    data = bytes(output)
    if PRIVATE.search(data):
        invalid()
    return data


def zip_members(stream):
    with zipfile.ZipFile(stream) as archive:
        for member in archive.infolist():
            mode = member.external_attr >> 16
            directory = member.is_dir()
            if member.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFDIR if directory else stat.S_IFREG):
                invalid()
            with archive.open(member) as source:
                yield member.filename, member.file_size, mode & 0o7777 or 0o644, directory, source


def tar_members(stream):
    with tarfile.open(fileobj=stream, mode="r:*") as archive:
        for member in archive:
            if not member.isfile() and not member.isdir():
                invalid()
            if member.isdir():
                yield member.name, member.size, member.mode & 0o7777, True, io.BytesIO()
            else:
                with archive.extractfile(member) as source:
                    yield member.name, member.size, member.mode & 0o7777, False, source


def read_archive(kind, stream, *, limits):
    if kind not in {"wheel", "sdist"} or not isinstance(limits, Limits):
        invalid()
    for value in vars(limits).values():
        charge(0, 0, value)
    original = stream.tell()
    try:
        stream.seek(0, io.SEEK_END)
        charge(0, stream.tell(), limits.archive_bytes)
        stream.seek(0)
        members, contents, seen = [], {}, set()
        total, count = 0, 0
        iterator = zip_members(stream) if kind == "wheel" else tar_members(stream)
        for name, size, mode, directory, source in iterator:
            count = charge(count, 1, limits.members)
            name = canonical(name, directory)
            if name in seen or mode & 0o7000:
                invalid()
            seen.add(name)
            if directory:
                if size:
                    invalid()
                continue
            if mode not in (0o644, 0o755):
                invalid()
            total = charge(total, size, limits.expanded_bytes)
            data = read_member(source, size, limits)
            members.append((name, size, hashlib.sha256(data).hexdigest(), mode))
            contents[name] = data
        return contents, {name: mode for name, _, _, mode in members}
    except (zipfile.BadZipFile, tarfile.TarError, UnicodeError, KeyError, EOFError, OSError):
        invalid()
    finally:
        stream.seek(original)


def validate_archive(kind, stream, *, expected_package, limits):
    if type(expected_package) is not dict or not expected_package:
        invalid()
    contents, modes = read_archive(kind, stream, limits=limits)
    validate_content(kind, contents, expected_package, modes)
    members = ((name, len(data), hashlib.sha256(data).hexdigest(), modes[name])
               for name, data in contents.items())
    return ArchiveInventory(tuple(sorted(members)), "fitctl", "0.1.0")
