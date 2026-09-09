# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Installed literal JSON admission compared with the pinned core decoder."""

import unittest

from number_cases import literal_parity


class JsonNumberTests(unittest.TestCase):
    def test_literal_core_parity(self):
        literal_parity(self)
