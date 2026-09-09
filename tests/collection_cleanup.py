# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Selected cleanup evidence mutations; removal failures are data, not forced OS faults."""

import copy

from collection_support import core_error
from support import AT, api, invoke


def parts(value):
    paths = value['state']['core_state']['path_resources']
    return paths['paths'][0]['link_capabilities'], paths['link_pairs'][0]


def check(test, raw):
    for presence in ('recorded', 'empty', 'absent', 'null', 'remove_failed'):
        selected = copy.deepcopy(raw)
        for part in parts(selected):
            if presence == 'empty':
                part['cleanup'] = []
            elif presence == 'absent':
                del part['cleanup']
            elif presence == 'null':
                part['cleanup'] = None
            elif presence == 'remove_failed':
                for index, entry in enumerate(part['cleanup']):
                    entry.update(outcome='remove_failed', error='selected cleanup diagnostic',
                                 probe_root=f'/selected/probe/root-{index}')
        value = invoke(api().Artifact.from_dict, selected)
        exported = invoke(value.to_dict)
        for actual, supplied in zip(parts(exported), parts(selected), strict=True):
            if presence in ('absent', 'null'):
                test.assertNotIn('cleanup', actual)
            else:
                test.assertEqual(actual['cleanup'], supplied['cleanup'])
            test.assertEqual(actual['copy_possible'], {'state': 'observed', 'value': True})
        restored = invoke(api().Artifact.from_json, invoke(value.to_json))
        test.assertEqual(invoke(restored.to_dict), exported)
        test.assertEqual(invoke(restored.semantic_bytes), invoke(value.semantic_bytes))
        test.assertEqual(invoke(restored.semantic_hash), invoke(value.semantic_hash))
        if presence == 'remove_failed':
            changed = copy.deepcopy(exported)
            for part in parts(changed):
                for entry in part['cleanup']:
                    entry.update(outcome='removed'); del entry['error']
            other = invoke(api().Artifact.from_dict, changed)
            test.assertNotEqual(invoke(other.semantic_hash), invoke(value.semantic_hash))
            for profile in ('local', 'fleet', 'auditor', 'external'):
                redacted = invoke(value.redact, profile, at=AT)
                output = invoke(redacted.to_dict)
                for part in parts(output):
                    test.assertTrue(all(entry['outcome'] == 'remove_failed' for entry in part['cleanup']))
                    test.assertEqual(part['copy_possible'], {'state': 'observed', 'value': True})
                for token in ('/selected/probe/root-', 'selected cleanup diagnostic'):
                    test.assertEqual(token in str(output), profile in ('local', 'fleet'))
                invoke(api().Artifact.from_dict, output)
    mutations = ('blank_root', 'unknown_outcome', 'unknown_field', 'missing_error', 'blank_error',
                 'removed_error', 'not_created_error', 'bad_count', 'bad_type', 'null_entry', 'duplicate_root')
    for index in (0, 1):
        for mutation in mutations:
            if index == 0 and mutation == 'duplicate_root':
                continue  # A single root has no distinct second root to duplicate.
            selected = copy.deepcopy(raw)
            part = parts(selected)[index]
            first = part['cleanup'][0]
            if mutation == 'blank_root': first['probe_root'] = ' '
            elif mutation == 'unknown_outcome': first['outcome'] = 'assumed_clean'
            elif mutation == 'unknown_field': first['unexpected'] = True
            elif mutation == 'missing_error': first['outcome'] = 'remove_failed'
            elif mutation == 'blank_error': first.update(outcome='remove_failed', error=' ')
            elif mutation == 'removed_error': first.update(outcome='removed', error='unexpected')
            elif mutation == 'not_created_error': first.update(outcome='not_created', error='unexpected')
            elif mutation == 'bad_count': part['cleanup'] = [first] if index else [first, {'probe_root': '/distinct', 'outcome': 'removed'}]
            elif mutation == 'bad_type': part['cleanup'] = {}
            elif mutation == 'null_entry': part['cleanup'][0] = None
            else: part['cleanup'][1] = copy.deepcopy(first)
            with test.subTest(part=index, mutation=mutation), test.assertRaises(api().CoreError) as caught:
                invoke(api().Artifact.from_dict, selected)
            reason = 'artifact_decode_invalid' if mutation in ('unknown_outcome', 'unknown_field', 'bad_type', 'null_entry') else 'artifact_load_invalid'
            core_error(test, caught.exception, {'error_model_id': 'fitctl.artifact_record.v1',
                       'error_model_version': 1, 'reason_code': reason, 'checkpoint_id': 'artifact_load'}, 'Artifact.from_dict')
