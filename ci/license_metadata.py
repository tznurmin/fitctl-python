# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Finalize artifact-specific license metadata without changing payload bytes."""

import base64
import csv
from email.parser import BytesParser
import gzip
import hashlib
import io
import os
from pathlib import Path
import tarfile
import tempfile
import zipfile

from .archive_contract import Limits, charge, read_archive
from .archive_metadata import DIST_INFO, LEGAL_FILES, approved_files, invalid, metadata, notices, record


def metadata_bytes(data, kind):
    """Maturin's Cargo fallback is the project's own license, before linkage."""
    if kind not in ("wheel", "sdist") or b"\r" in data:
        invalid()
    document = BytesParser().parsebytes(data)
    expression = approved_files()["license_expressions"][kind]
    old = document.get_all("License-Expression", [])
    legacy = document.get_all("License", [])
    if ((old and legacy) or (not old and legacy != ["Apache-2.0"])
            or (old and old not in (["Apache-2.0"], [expression]))
            or document.get_all("Dynamic", []) not in ([], ["License"], ["License-Expression"])):
        invalid()
    header, separator, body = data.partition(b"\n\n")
    if not separator:
        invalid()
    lines, skipping = [], False
    for line in header.split(b"\n"):
        if not line.startswith((b" ", b"\t")):
            skipping = line.split(b":", 1)[0].lower() in (b"license", b"license-expression", b"dynamic")
            if skipping and line.lower().startswith((b"license:", b"license-expression:")):
                lines.append(b"License-Expression: " + expression.encode("ascii"))
                if kind == "sdist":
                    lines.append(b"Dynamic: License-Expression")
        if not skipping:
            lines.append(line)
    result = b"\n".join(lines) + separator + body
    metadata(result, kind)
    return result


def write_archive(kind, contents, modes, output):
    """Deterministic containers; existing readers own admission and bounds."""
    if kind == "wheel":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(contents.items()):
                member = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                member.external_attr = (0o100000 | modes[name]) << 16
                member.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(member, data)
    elif kind == "sdist":
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(contents.items()):
                    member = tarfile.TarInfo(name)
                    member.size, member.mode, member.mtime = len(data), modes[name], 1767225600
                    archive.addfile(member, io.BytesIO(data))
    else:
        invalid()


def finalize(kind, path):
    try:
        _finalize(kind, path)
    except (KeyError, UnicodeError, csv.Error):
        invalid()


def _finalize(kind, path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        invalid()
    with path.open("rb") as stream:
        contents, modes = read_archive(kind, stream, limits=Limits())
    prefix = DIST_INFO + "licenses/" if kind == "wheel" else "fitctl-0.1.1/"
    notices({name: contents[prefix + name] for name in LEGAL_FILES if prefix + name in contents})
    key = DIST_INFO + "METADATA" if kind == "wheel" else "fitctl-0.1.1/PKG-INFO"
    if key not in contents:
        invalid()
    if kind == "wheel":
        if DIST_INFO + "RECORD" not in contents:
            invalid()
        record(contents)  # Never repair corrupt incoming payload/RECORD pairs.
    updated = metadata_bytes(contents[key], kind)
    if updated == contents[key]:
        return
    contents[key] = updated
    if kind == "wheel":
        rows = io.StringIO(newline="")
        writer = csv.writer(rows, lineterminator="\n")
        for name, data in sorted(contents.items()):
            if name != DIST_INFO + "RECORD":
                digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
                writer.writerow([name, "sha256=" + digest, str(len(data))])
        writer.writerow([DIST_INFO + "RECORD", "", ""])
        contents[DIST_INFO + "RECORD"] = rows.getvalue().encode()
        record(contents)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix="license-", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            write_archive(kind, contents, modes, output)
        charge(0, temporary.stat().st_size, Limits().archive_bytes)
        temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
