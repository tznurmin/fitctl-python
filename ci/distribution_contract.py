# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Closed public source, runtime and tested-artifact admission."""

import hashlib
import json
import re

CORE_SHA256 = "0aa75a2b76afcd3530a53fc7c803371cc0165088eee8682633edbc9bede676e8"
# Pinned registry build inputs; graph membership does not imply redistribution.
DEPENDENCY_SET_SHA256 = "8cf997e0645d2d4e5ecaf304756ef2e5ea48a3e55e52a124cda9971ba2b59dfb"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
WHEEL = "fitctl-0.1.0-cp313-cp313-manylinux_2_28_x86_64.whl"
SDIST = "fitctl-0.1.0.tar.gz"
RUNTIMES = {"direct:3.13.0", "direct:3.13.13", "sdist:3.13.0", "sdist:3.13.13"}
DOWNLOAD = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
PUBLISH = "pypa/gh-action-pypi-publish@ed0c53931b1dc9bd32cbe73a98c7f6766f8a527e"


def require(value):
    if not value:
        raise ValueError("distribution verification failed")


def sha256(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def sources(pyproject, cargo, lock):
    project = pyproject.get("project", {})
    require(project.get("name") == "fitctl" and project.get("version") == "0.1.0"
            and project.get("requires-python") == ">=3.13,<3.14"
            and "license" not in project and project.get("dynamic") == ["license"]
            and project.get("license-files") == ["LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.txt"]
            and project.get("dependencies") == [])
    require(pyproject.get("build-system") == {
        "requires": ["maturin==1.12.6"], "build-backend": "ci.build_backend", "backend-path": ["."]})
    require(cargo.get("package", {}).get("version") == "0.1.0"
            and cargo.get("package", {}).get("license") == "Apache-2.0"
            and cargo.get("dependencies", {}).get("fitctl-core") == "=0.8.0"
            and not any(key in cargo for key in ("patch", "replace")))
    for dependency in cargo["dependencies"].values():
        require(type(dependency) is str or (type(dependency) is dict
                and not {"path", "git", "registry", "registry-index"} & dependency.keys()))
    packages = lock.get("package", [])
    require(type(packages) is list and bool(packages))
    names = set()
    for package in packages:
        identity = package.get("name"), package.get("version")
        require(identity not in names)
        names.add(identity)
        if package.get("name") == "fitctl-native":
            require(package.get("version") == "0.1.0"
                    and not {"source", "checksum"} & package.keys())
        else:
            require(package.get("source") == REGISTRY and sha256(package.get("checksum")))
    core = [package for package in packages if package.get("name") == "fitctl-core"]
    require(len(core) == 1 and core[0].get("version") == "0.8.0"
            and core[0].get("checksum") == CORE_SHA256)
    require(("fitctl-native", "0.1.0") in names)
    locked = sorted((p["name"], p["version"], p["checksum"]) for p in packages if p.get("source"))
    require(hashlib.sha256(json.dumps(locked, separators=(",", ":")).encode()).hexdigest()
            == DEPENDENCY_SET_SHA256)


def portability(report):
    require(type(report) is dict and set(report) == {
        "tag", "machine", "glibc", "rpaths", "external", "python", "gil"})
    require(report["tag"] == "cp313-cp313-manylinux_2_28_x86_64"
            and report["machine"] == "x86_64" and report["gil"] is True)
    glibc = report["glibc"]
    require(type(glibc) is list and len(glibc) == 2
            and all(type(value) is int and value >= 0 for value in glibc)
            and (2, 0) <= tuple(glibc) <= (2, 28))
    require(report["rpaths"] == [] and type(report["external"]) is list
            and len(report["external"]) == len(set(report["external"])))
    require(set(report["external"]) <= {"libc.so.6", "libm.so.6", "libgcc_s.so.1",
                                       "libpthread.so.0", "libdl.so.2", "librt.so.1",
                                       "ld-linux-x86-64.so.2"})
    require(type(report["python"]) is str
            and re.fullmatch(r"3\.13\.(0|[1-9][0-9]*)", report["python"]) is not None)


def artifact_manifest(document, actual):
    require(type(document) is dict and set(document) == {"version", "artifacts", "passed"}
            and document["version"] == "0.1.0" and type(actual) is dict
            and set(actual) == {WHEEL, SDIST} and all(sha256(value) for value in actual.values())
            and document["artifacts"] == actual and type(document["passed"]) is list
            and len(document["passed"]) == len(RUNTIMES) and set(document["passed"]) == RUNTIMES)


def workflow(document):
    require(type(document) is dict and document.get("on") == {"workflow_dispatch": {
        "inputs": {"publish": {"description": "Publish the tested 0.1.0 artifacts", "type": "boolean",
                               "required": True, "default": False}}}})
    require(document.get("permissions") == {"contents": "read"})
    jobs = document.get("jobs", {})
    require(set(jobs) == {"qualify", "publish"}
            and jobs["qualify"] == {"uses": "./.github/workflows/build.yaml"})
    publish = jobs["publish"]
    require(publish.get("needs") == "qualify" and publish.get("if") == "${{ inputs.publish }}"
            and publish.get("environment") == "pypi"
            and publish.get("permissions") == {"id-token": "write"}
            and publish.get("runs-on") == "ubuntu-24.04"
            and publish.get("timeout-minutes") == 10)
    steps = publish.get("steps", [])
    require(len(steps) == 3 and steps[0] == {
        "uses": DOWNLOAD, "with": {"name": "tested-distributions", "path": "release-artifacts"}})
    require(steps[2] == {"uses": PUBLISH, "with": {"packages-dir": "release-artifacts/dist/",
                                                   "skip-existing": False}})
    from pathlib import Path
    expected = (Path(__file__).with_name("verify_upload.py")).read_text()
    require(steps[1] == {"name": "Verify exact tested artifacts", "shell": "python",
                        "env": {"MANIFEST_SHA256": "${{ needs.qualify.outputs.manifest-sha256 }}"},
                        "run": expected})


def build_workflow(document):
    require(document.get("permissions") == {"contents": "read"}
            and set(document.get("jobs", {})) == {"build"})
    job = document["jobs"]["build"]
    require(job.get("runs-on") == "ubuntu-24.04" and job.get("timeout-minutes") == 30
            and job.get("outputs") == {"manifest-sha256": "${{ steps.qualify.outputs.manifest-sha256 }}"})
    steps = job.get("steps", [])
    require(len(steps) > 3 and steps[3] == {
        "name": "Install sandbox and ELF tools", "timeout-minutes": 5,
        "run": "test -s /etc/apt/sources.list.d/ubuntu.sources\n"
               "apt_sources=(-o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources "
               "-o Dir::Etc::sourceparts=-)\n"
               'sudo apt-get "${apt_sources[@]}" update --error-on=any\n'
               'sudo apt-get "${apt_sources[@]}" install --no-install-recommends --yes '
               "bubblewrap strace skopeo umoci patchelf binutils pkg-config\n"
               "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0\n"})
    require(len(steps) == 7 and steps[0].get("with") == {"persist-credentials": False}
            and steps[1].get("with") == {"python-version": "3.13.13"}
            and steps[2].get("with") == {"toolchain": "1.95.0", "components": "clippy"})
    expected = {0: "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
                1: "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
                2: "dtolnay/rust-toolchain@d1031067263f94b142dd6c0ce24c5eb9d02d52a0",
                5: "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
                6: "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"}
    require(all(steps[index].get("uses") == value for index, value in expected.items())
            and steps[4] == {"name": "Build once per configuration and qualify", "id": "qualify",
                            "run": "python -B ci/gate.py"}
            and steps[6].get("with") == {"name": "tested-distributions", "path": "release-artifacts/",
                "if-no-files-found": "error", "retention-days": 7, "compression-level": 0, "overwrite": False}
            and not any("if" in step or step.get("continue-on-error") for step in steps))
