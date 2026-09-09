# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Safe test-harness failures; separate from the extension's public API errors."""


class RecordedFailure(ValueError):
    def __init__(self, code):
        super().__init__("distribution verification failed")
        self.code = code
