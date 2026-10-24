"""CPU-only construction/parser contracts, never model observations.

All predictions below are explicit synthetic fixtures. No render, model, API,
credential, image hashing, or temporary output is needed by these tests.
"""
import builtins
from copy import deepcopy
import json
from pathlib import Path
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import group_statistical_controls as controls


class StatisticalControlTests(unittest.TestCase):
    def prediction(self, horizontal_stack='yes', upright_books='yes'):
        """A synthetic parser input, not a response from any image/model."""
        return controls.parse_prediction(json.dumps(dict(
            horizontal_stack=horizontal_stack, upright_books=upright_books)))

    def assert_unscored(self, rows):
        self.assertEqual([row['field'] for row in rows],
                         ['horizontal_stack', 'upright_books'])
        for row in rows:
            self.assertIs(row['score'], None)
            self.assertIs(row['value'], None)
            self.assertIs(row['scorable'], False)
            self.assertIs(row['reviewed'], False)
            self.assertNotIn('energy', row)

    def test_frozen_two_question_prompt_schema_and_definitions(self):
        self.assertEqual(controls.SYSTEM,
            '你是视觉证据验证器。只根据当前图像判断书籍的可见摆放方式。不要把唱片或文件夹当作书籍，不猜测不可见内容。无法判断时回答 unknown。只输出 JSON。')
        self.assertEqual(controls.USER, '''请回答：

1. 是否能清楚看到至少两本水平叠放的书籍？
2. 是否能清楚看到竖直站立摆放的书籍？

只输出：
{
  "horizontal_stack": "yes",
  "upright_books": "yes"
}

字段取值均为 yes、no 或 unknown。

以上 JSON 只是格式示例，不是预期答案。''')
        self.assertEqual(controls.DEFINITIONS, dict(
            horizontal_stack='至少两本可辨认的书水平叠放，存在明显上下堆叠关系。',
            upright_books='存在可辨认的书籍，其书脊或书体主要呈竖直站立状态。',
            exclusions='唱片、文件夹、单本平放且无法确认的物体不强行当作横向书堆。',
            abstention='遮挡严重、分辨率不足或类别不明确时回答unknown。'))
        self.assertEqual(controls.FIELDS, ('horizontal_stack', 'upright_books'))
        self.assertEqual(controls.SCHEMA, dict(type='object', additionalProperties=False,
            required=['horizontal_stack', 'upright_books'], properties={
                key: dict(type='string', enum=['yes', 'no', 'unknown'])
                for key in controls.FIELDS}))
        for legacy_field in ('present', 'shelf_sections', 'arrangement'):
            self.assertNotIn(legacy_field, controls.USER)
            self.assertNotIn(legacy_field, controls.SCHEMA['properties'])

    def test_three_configs_keep_the_same_nine_books_and_scene(self):
        configs = controls.scene_configs()
        before = deepcopy(configs)
        result = controls.validate_config_controls(configs)
        self.assertEqual(configs, before)
        self.assertEqual(set(configs), {'A', 'B', 'C'})
        self.assertIs(result['passed'], True)
        self.assertEqual(result['book_count'], 9)
        self.assertEqual(result['converted_books'], 6)
        expected_ids = ['book_%02d' % index for index in range(1, 10)]
        for config in configs.values():
            self.assertEqual([book['id'] for book in config['books']], expected_ids)
        baseline = configs['A']
        for variant in ('B', 'C'):
            self.assertEqual({k: v for k, v in baseline.items() if k != 'books'},
                             {k: v for k, v in configs[variant].items() if k != 'books'})
        for first, second, third in zip(*(configs[k]['books'] for k in ('A', 'B', 'C'))):
            changed_b = {k for k in first if first[k] != second[k]}
            changed_c = {k for k in first if first[k] != third[k]}
            if first['source_group'] == 'standing':
                self.assertEqual(changed_b, set())
            else:
                self.assertEqual(changed_b, {'location', 'rotation_y'})
                self.assertGreater(first['rotation_y'], 1.5)
                self.assertEqual(second['rotation_y'], 0.)
            self.assertEqual(changed_c, {'cover_color'})
            self.assertEqual(first['dimensions'], second['dimensions'])
            self.assertEqual(first['dimensions'], third['dimensions'])
            self.assertEqual(first['cover_color'], second['cover_color'])

    def test_extra_lighting_or_book_size_change_is_rejected(self):
        for variant in ('B', 'C'):
            with self.subTest(variant=variant, change='lighting'):
                configs = controls.scene_configs()
                configs[variant]['lighting']['key_energy'] += 1
                with self.assertRaises(ValueError):
                    controls.validate_config_controls(configs)
            with self.subTest(variant=variant, change='dimensions'):
                configs = controls.scene_configs()
                configs[variant]['books'][3]['dimensions'][0] += .01
                with self.assertRaises(ValueError):
                    controls.validate_config_controls(configs)

    def test_b_cannot_change_cover_color_or_original_upright_books(self):
        configs = controls.scene_configs()
        configs['B']['books'][3]['cover_color'][0] += .01
        with self.assertRaises(ValueError):
            controls.validate_config_controls(configs)
        configs = controls.scene_configs()
        configs['B']['books'][0]['location'][0] += .01
        with self.assertRaises(ValueError):
            controls.validate_config_controls(configs)

    def test_b_cannot_gain_unapproved_material_metadata(self):
        configs = controls.scene_configs()
        configs['B']['books'][3]['material'] = dict(roughness=.25)
        with self.assertRaises(ValueError):
            controls.validate_config_controls(configs)

    def test_adding_duplicate_book_does_not_preserve_nine_book_contract(self):
        configs = controls.scene_configs()
        for config in configs.values():
            config['books'].append(deepcopy(config['books'][0]))
        with self.assertRaises(ValueError):
            controls.validate_config_controls(configs)

    def test_location_changes_alone_do_not_convert_stacks_to_upright(self):
        configs = controls.scene_configs()
        for first, second in zip(configs['A']['books'], configs['B']['books']):
            if first['source_group'].startswith('stack_'):
                second['rotation_y'] = first['rotation_y']
        with self.assertRaises(ValueError):
            controls.validate_config_controls(configs)

    def test_exact_json_and_one_whole_fence_are_accepted(self):
        raw = '{"horizontal_stack":"yes","upright_books":"no"}'
        for text in (raw, ' \n' + raw + '\n ', '```json\n' + raw + '\n```',
                     '```\n' + raw + '\n```'):
            with self.subTest(text=text):
                packet = controls.parse_prediction(text)
                self.assertEqual(packet['status'], 'valid')
                self.assertEqual(packet['schema_errors'], [])
                self.assertEqual(packet['fields']['horizontal_stack']['value'], 'yes')
                self.assertEqual(packet['fields']['upright_books']['value'], 'no')

    def test_strict_json_rejects_duplicates_nonfinite_and_extra_text(self):
        valid = '{"horizontal_stack":"yes","upright_books":"yes"}'
        rejected = [None, {}, [], 1, True, 'null', '[]', '1', '"yes"',
            'prefix ' + valid, valid + ' trailing', valid + valid,
            '```json\n' + valid + '\n```\nextra',
            '{"horizontal_stack":"no","horizontal_stack":"yes","upright_books":"yes"}',
            '{"horizontal_stack":"yes","upright_books":"yes","extra":{"x":1,"x":2}}',
            '{"horizontal_stack":NaN}', '{"horizontal_stack":Infinity}',
            '{"upright_books":-Infinity}', "{'horizontal_stack':'yes'}"]
        for raw in rejected:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                controls.parse_prediction(raw)

    def test_every_enum_and_unknown_are_accepted(self):
        for key in controls.FIELDS:
            for value in ('yes', 'no', 'unknown'):
                answers = dict.fromkeys(controls.FIELDS, 'yes')
                answers[key] = value
                with self.subTest(key=key, value=value):
                    packet = controls.parse_prediction(json.dumps(answers))
                    self.assertEqual(packet['status'], 'valid')
                    self.assertEqual(packet['fields'][key]['value'], value)
                    self.assertEqual(packet['fields'][key]['validation_status'], 'valid')

    def test_missing_or_invalid_field_preserves_other_valid_field(self):
        for key in controls.FIELDS:
            other = next(field for field in controls.FIELDS if field != key)
            cases = [dict.fromkeys([other], 'yes')]
            for value in (None, True, False, 0, 1, [], {}, 'YES', 'yes ', 'mixed'):
                cases.append({key: value, other: 'yes'})
            for answers in cases:
                with self.subTest(key=key, answers=answers):
                    packet = controls.parse_prediction(json.dumps(answers))
                    self.assertEqual(packet['status'], 'partial')
                    self.assertEqual(packet['fields'][key]['validation_status'], 'unavailable')
                    self.assertIsNone(packet['fields'][key]['value'])
                    self.assertTrue(packet['fields'][key]['error'])
                    self.assertEqual(packet['fields'][other]['validation_status'], 'valid')
                    self.assertEqual(packet['fields'][other]['value'], 'yes')
                    rows = controls.compare_expected(dict.fromkeys(controls.FIELDS, 'yes'), packet)
                    self.assert_unscored(rows)
                    self.assertEqual({row['field']: row['status'] for row in rows},
                        {key: 'unavailable', other: 'satisfied'})

    def test_extra_fields_remain_schema_errors_without_losing_valid_fields(self):
        packet = controls.parse_prediction(json.dumps(dict(
            horizontal_stack='yes', upright_books='yes', explanation='Synthetic fixture only')))
        self.assertEqual(packet['status'], 'partial')
        self.assertTrue(packet['schema_errors'])
        self.assertTrue(all(field['validation_status'] == 'valid'
                            for field in packet['fields'].values()))

    def test_expected_comparison_keeps_construction_provenance_and_four_states(self):
        expected = dict(horizontal_stack='yes', upright_books='yes')
        cases = [
            (self.prediction(), ['satisfied', 'satisfied']),
            (self.prediction('no'), ['candidate_violated', 'satisfied']),
            (self.prediction('unknown'), ['unknown', 'satisfied']),
            (dict(status='unavailable', fields={}), ['unavailable', 'unavailable'])]
        for packet, statuses in cases:
            before = deepcopy((expected, packet))
            rows = controls.compare_expected(expected, packet)
            self.assertEqual((expected, packet), before)
            self.assertEqual([row['status'] for row in rows], statuses)
            self.assert_unscored(rows)
            for row in rows:
                self.assertEqual(row['expected_source'], 'construction_expected')
                self.assertEqual(row['construction_expected'], expected[row['field']])

    def test_synthetic_ab_and_ac_pairs_are_contract_checks_not_model_results(self):
        synthetic_a = self.prediction('yes', 'yes')
        synthetic_b = self.prediction('no', 'yes')
        synthetic_c = self.prediction('yes', 'yes')
        for second, statuses in ((synthetic_b, ['candidate_violated', 'satisfied']),
                                 (synthetic_c, ['satisfied', 'satisfied'])):
            before = deepcopy((synthetic_a, second))
            rows = controls.compare_pair(synthetic_a, second)
            self.assertEqual((synthetic_a, second), before)
            self.assertEqual([row['status'] for row in rows], statuses)
            self.assert_unscored(rows)
            self.assertEqual(rows[0]['first_answer'], 'yes')
            self.assertEqual(rows[0]['second_answer'], second['fields']['horizontal_stack']['value'])

    def test_group_adapter_preserves_boolean_expected_and_single_fact_ownership(self):
        labels = dict(expected_source='construction_expected', reviewed=False, samples={
            'A': dict(horizontal_stack='yes', upright_books='yes'),
            'B': dict(horizontal_stack='no', upright_books='yes'),
            'C': dict(horizontal_stack='yes', upright_books='yes')})
        before = deepcopy(labels)
        with patch.object(controls, 'group_questions', wraps=controls.group_questions) as grouped, \
             patch.object(controls, 'replay_atomic_answers', wraps=controls.replay_atomic_answers) as replayed, \
             patch.object(controls, 'group_energy_rows', wraps=controls.group_energy_rows) as recorded:
            evidence, questions, applicability = controls.group_contracts(labels)
        self.assertEqual(labels, before)
        self.assertEqual(grouped.call_count, 3)
        self.assertEqual(replayed.call_count, 3)
        self.assertEqual(recorded.call_count, 3)
        for call in replayed.call_args_list:
            self.assertEqual(len(call.args), 1)
            self.assertEqual(call.kwargs, dict(source_kind='unavailable'))
        self.assertEqual(evidence['expected_source'], 'construction_expected')
        self.assertIs(evidence['reviewed'], False)
        self.assertEqual(set(evidence['samples']), {'A', 'B', 'C'})
        for sample, expected in labels['samples'].items():
            with self.subTest(sample=sample):
                case = evidence['samples'][sample]
                atoms = case['atomic_evidence']
                qs = questions[sample]
                pending = applicability[sample]
                results = pending['verification_results']
                records = pending['energy_records']
                expected_ids = {'books_' + field for field in controls.FIELDS}
                for rows in (atoms, qs, results, records):
                    self.assertEqual(len(rows), 2)
                    self.assertEqual({row['id'] for row in rows}, expected_ids)
                self.assertEqual(len(case['semantic_groups']), 1)
                self.assertEqual(set(case['semantic_groups'][0]['evidence']), expected_ids)
                # Each of the two canonical facts has one Group owner and one
                # pending record; the shared Group must not duplicate a fact.
                for rows in (atoms, qs, records):
                    self.assertEqual(len({(row['canonical_fact_id'], row['owner_id'])
                                          for row in rows}), 2)
                    self.assertEqual({row['owner_id'] for row in rows}, {'G_books'})
                    self.assertTrue(all(not row.get('alias_of') for row in rows))
                for atom in atoms:
                    self.assertIs(atom['expected'], expected[atom['answer_field']] == 'yes')
                    self.assertEqual(atom['source_type'], 'construction_expected')
                    question = next(row for row in qs if row['id'] == atom['id'])
                    self.assertIs(question['expected'], atom['expected'])
                    self.assertEqual(question['answer_type'], 'boolean')
                    self.assertEqual(question['energy'], 'statistical')
                    self.assertEqual(question['reliability'], 0.)
                self.assertIsNone(pending['statistical_energy'])
                self.assertIs(pending['scorable'], False)
                for result in results:
                    self.assertEqual(result['status'], 'unavailable')
                    self.assertEqual(result['source_kind'], 'unavailable')
                    self.assertIsNone(result['observed'])
                    self.assertIsNone(result['score'])
                    self.assertIs(result['scorable'], False)
                    self.assertIs(result['reviewed'], False)
                for record in records:
                    self.assertEqual(record['energy'], 'statistical')
                    self.assertEqual(record['level'], 'region')
                    self.assertEqual(record['status'], 'unavailable')
                    self.assertEqual(record['verification_status'], 'unavailable')
                    self.assertIsNone(record['value'])
                    self.assertEqual(record['q'], 0.)
                    self.assertIs(record['scorable'], False)
                    self.assertIs(record['reviewed'], False)

    def test_pair_unknown_is_distinct_from_missing_or_unrequested(self):
        known = self.prediction()
        unknown = self.prediction('unknown')
        partial = controls.parse_prediction('{"upright_books":"yes"}')
        for first, second, statuses in (
                (unknown, known, ['unknown', 'satisfied']),
                (known, unknown, ['unknown', 'satisfied']),
                (partial, known, ['unavailable', 'satisfied']),
                (known, partial, ['unavailable', 'satisfied'])):
            rows = controls.compare_pair(first, second)
            self.assertEqual([row['status'] for row in rows], statuses)
            self.assert_unscored(rows)
        unrequested = dict(status='unavailable', fields={}, request_status='not_requested')
        for first, second in ((unrequested, known), (known, unrequested),
                              (unrequested, unrequested)):
            rows = controls.compare_pair(first, second)
            self.assertEqual([row['status'] for row in rows], ['unavailable'] * 2)
            self.assert_unscored(rows)

    def test_request_rejects_before_credentials_clients_imports_or_network(self):
        forbidden = Mock(side_effect=AssertionError('Forbidden external operation'))
        class ForbiddenEnvironment(dict):
            def __getitem__(self, key):
                raise AssertionError('Credential environment read forbidden')
            def get(self, key, default=None):
                raise AssertionError('Credential environment read forbidden')
        with patch.object(controls, 'configuration', forbidden, create=True), \
             patch.object(controls, 'VLMClient', forbidden, create=True), \
             patch.object(controls, 'OfoxTunnel', forbidden, create=True), \
             patch.object(controls, 'requests', SimpleNamespace(Session=forbidden), create=True), \
             patch.object(controls.os, 'environ', ForbiddenEnvironment()), \
             patch.object(controls.os, 'getenv', forbidden), \
             patch.object(Path, 'read_text', forbidden), \
             patch.object(Path, 'open', forbidden), \
             patch.object(builtins, 'open', forbidden), \
             patch.object(socket, 'socket', forbidden), \
             patch.object(socket, 'create_connection', forbidden), \
             patch.object(builtins, '__import__', forbidden):
            with self.assertRaises(PermissionError):
                controls.request()
            with self.assertRaises(PermissionError):
                controls.request(Path('/nonexistent/synthetic-control-output'), authorized=True)
        forbidden.assert_not_called()


if __name__ == '__main__':
    unittest.main()
