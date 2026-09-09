# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Public conversion errors and typed core failures are distinct from reports."""

import unittest

import error_cases as cases
import request_cases as requests
from support import api


class InputErrorTests(unittest.TestCase):
    def setUp(self):
        self.api = api()

    def test_omission_is_not_null(self):
        cases.omission(self)

    def test_supplied_null_uses_validated_core_loader(self):
        cases.supplied_null(self)

    def test_unknown_fields_reach_core_validation(self):
        cases.unknown_fields(self)

    def test_unsupported_schema_versions(self):
        cases.schemas(self)

    def test_wrong_native_types(self):
        cases.wrong_types(self)

    def test_bool_is_not_max_age(self):
        cases.bool_age(self)

    def test_integer_boundaries(self):
        cases.integers(self)

    def test_non_finite_numbers(self):
        cases.nonfinite(self)

    def test_malformed_and_duplicate_json(self):
        cases.malformed(self)

    def test_custom_coercions_are_not_used(self):
        cases.custom_types(self)

    def test_utf8_byte_budgets(self):
        cases.byte_budgets(self)

    def test_depth_and_node_budgets(self):
        cases.depth_nodes(self)

    def test_cyclic_values(self):
        cases.cycles(self)

    def test_modes_and_artifact_roles(self):
        requests.modes_and_roles(self)

    def test_errors_do_not_echo_input(self):
        requests.safe_errors(self)

    def test_unicode_scalar_boundaries(self):
        cases.unicode_scalars(self)

    def test_shared_containers_count_each_occurrence(self):
        cases.aliases(self)

    def test_exception_field_and_rendering_contract(self):
        requests.exception_fields(self)

    def test_max_age_unsigned_boundaries(self):
        requests.max_age(self)

    def test_builtin_argument_budgets(self):
        requests.builtin_budgets(self)

    def test_public_request_admission(self):
        requests.admission(self)

    def test_safe_signature_binding(self):
        requests.signatures(self)

    def test_unadvertised_core_families(self):
        requests.unadvertised(self)
