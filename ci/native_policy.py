# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Errors raised by distribution checks."""


class NativeFailure(ValueError):
    def __init__(self, code, message):
        super().__init__("distribution verification failed")
        self.code = code
