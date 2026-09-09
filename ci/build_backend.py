# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Maturin build hooks with artifact-scoped license metadata."""

import importlib
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ci.license_metadata import finalize, metadata_bytes
else:
    from .license_metadata import finalize, metadata_bytes


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = importlib.import_module("maturin").build_wheel(wheel_directory, config_settings, metadata_directory)
    finalize("wheel", Path(wheel_directory) / name)
    return name


def build_sdist(sdist_directory, config_settings=None):
    name = importlib.import_module("maturin").build_sdist(sdist_directory, config_settings)
    finalize("sdist", Path(sdist_directory) / name)
    return name


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    name = importlib.import_module("maturin").build_editable(wheel_directory, config_settings, metadata_directory)
    finalize("wheel", Path(wheel_directory) / name)
    return name


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    name = importlib.import_module("maturin").prepare_metadata_for_build_wheel(metadata_directory, config_settings)
    path = Path(metadata_directory) / name / "METADATA"
    path.write_bytes(metadata_bytes(path.read_bytes(), "wheel"))
    return name


def get_requires_for_build_wheel(config_settings=None):
    return importlib.import_module("maturin").get_requires_for_build_wheel(config_settings)


def get_requires_for_build_sdist(config_settings=None):
    return importlib.import_module("maturin").get_requires_for_build_sdist(config_settings)


get_requires_for_build_editable = get_requires_for_build_wheel
prepare_metadata_for_build_editable = prepare_metadata_for_build_wheel


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("wheel", "sdist") or args.count("--out") != 1:
        raise ValueError("distribution verification failed")
    kind = args.pop(0)
    destination = Path(args[args.index("--out") + 1])
    subprocess.run(["maturin", "build" if kind == "wheel" else "sdist", *args], check=True)
    files = list(destination.glob("*.whl" if kind == "wheel" else "*.tar.gz"))
    if len(files) != 1:
        raise ValueError("distribution verification failed")
    finalize(kind, files[0])


if __name__ == "__main__":
    main()
