#!/usr/bin/env bash
# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
source_root=$1
operation_root=$2
python_executable=$3
mount --make-rprivate /
mount -t tmpfs -o size=4G,mode=700 tmpfs "$operation_root"
mount_type=$(findmnt -n -o FSTYPE --target "$operation_root")
mount_target=$(findmnt -n -o TARGET --target "$operation_root")
test "$mount_type" = tmpfs
test "$mount_target" = "$operation_root"
export FITCTL_DISTRIBUTION_ROOT="$operation_root"
export PYTHONDONTWRITEBYTECODE=1
exec "$python_executable" -B "$source_root/ci/driver.py"
