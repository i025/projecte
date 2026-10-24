"""CPU-only construction and comparison contracts; no model/image observations.

The answer values below are synthetic test fixtures, never saved as VLM results.
Passing these tests establishes neither visible book identity nor label validity.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from scripts import group_statistical_hard_controls as controls
from scripts import group_statistical_controls as previous


class HardStatisticalControlTests(unittest.TestCase):
    def test_prompt_schema_and_definitions_reuse_the_frozen_protocol(self):
        frozen_path = (Path(__file__).resolve().parents[1] /
                       'results/group_statistical_controls_books/frozen_protocol.json')
        frozen = json.loads(frozen_path.read_text())
        self.assertEqual(controls.SYSTEM, previous.SYSTEM)
        self.assertEqual(controls.USER, previous.USER)
        self.assertEqual(controls.SCHEMA, previous.SCHEMA)
        self.assertEqual(controls.DEFINITIONS, previous.DEFINITIONS)
        for key, value in (('system', controls.SYSTEM), ('user', controls.USER),
                           ('schema', controls.SCHEMA),
                           ('definitions', controls.DEFINITIONS)):
            self.assertEqual(frozen[key], value)
        for label in ('construction_expected', 'T1', 'T2', 'T3', 'T4', 'T5'):
            self.assertNotIn(label, controls.USER)

    def test_new_shelf_and_camera_are_different_from_the_simple_controls(self):
        cases = controls.configs()
        self.assertEqual(set(cases), {'T1', 'T2', 'T3', 'T4'})
        old = previous.scene_configs()['A']
        new = cases['T1']
        self.assertNotEqual(new['shelf']['levels'], old['shelf']['levels'])
        self.assertNotEqual(new['shelf'].get('divider_positions'),
                            [old['shelf']['divider_x']])
        self.assertEqual(len(new['shelf']['divider_positions']), 2)
        self.assertNotEqual(new['camera'], old['camera'])
        self.assertNotEqual(new['shelf']['width'], old['shelf']['width'])
        self.assertEqual(new['rendering']['device'], 'CPU')
        self.assertEqual(new['rendering']['threads'], 2)

    def test_t1_t2_have_identical_scene_book_identity_geometry_and_material(self):
        first, second = (controls.configs()[key] for key in ('T1', 'T2'))
        self.assertEqual({k: v for k, v in first.items() if k != 'books'},
                         {k: v for k, v in second.items() if k != 'books'})
        self.assertEqual([book['id'] for book in first['books']],
                         [book['id'] for book in second['books']])
        ids = [book['id'] for book in first['books']]
        self.assertEqual(len(ids), len(set(ids)))
        converted = 0
        for a, b in zip(first['books'], second['books']):
            changed = {key for key in set(a) | set(b) if a.get(key) != b.get(key)}
            if math.isclose(a['rotation_y'], math.pi / 2):
                converted += 1
                self.assertEqual(changed, {'rotation_y', 'location'})
                self.assertEqual(b['rotation_y'], 0.)
                self.assertEqual(b['location'][2],
                                 b['support_z'] + b['dimensions'][2] / 2)
            else:
                self.assertEqual(a['rotation_y'], 0.)
                self.assertEqual(changed, set())
            self.assertEqual(a['dimensions'], b['dimensions'])
            self.assertEqual(a['cover_color'], b['cover_color'])
        self.assertGreaterEqual(converted, 2)
        self.assertTrue(all(b['rotation_y'] == 0. for b in second['books']))

    def test_t1_horizontal_stack_has_contact_and_upright_books(self):
        books = controls.configs()['T1']['books']
        stack = [book for book in books if math.isclose(book['rotation_y'], math.pi / 2)]
        standing = [book for book in books if book['rotation_y'] == 0.]
        self.assertGreaterEqual(len(stack), 2)
        self.assertTrue(standing)
        ordered = sorted(stack, key=lambda book: book['location'][2])
        prior_top = ordered[0]['support_z']
        for book in ordered:
            thickness = book['dimensions'][0]
            self.assertAlmostEqual(book['location'][2] - thickness / 2, prior_top)
            prior_top = book['location'][2] + thickness / 2

    def test_t3_has_exactly_one_horizontal_book_and_no_construction_stack(self):
        books = controls.configs()['T3']['books']
        horizontal = [b for b in books if math.isclose(b['rotation_y'], math.pi / 2)]
        self.assertEqual(len(horizontal), 1)
        self.assertTrue(any(b['rotation_y'] == 0. for b in books))
        single = horizontal[0]
        self.assertAlmostEqual(single['location'][2] - single['dimensions'][0] / 2,
                               single['support_z'])
        self.assertEqual(controls.expected_labels()['T3']['horizontal_stack'], 'no')

    def test_t4_has_no_horizontal_books_and_round_record_prop_configuration(self):
        scene = controls.configs()['T4']
        self.assertTrue(scene['books'])
        self.assertTrue(all(b['rotation_y'] == 0. for b in scene['books']))
        props = scene['vinyl_records']
        self.assertGreaterEqual(len(props), 3)
        self.assertTrue(any(p['upright'] for p in props))
        self.assertTrue(any(not p['upright'] for p in props))
        for prop in props:
            # Disc radius, orientation and colored center are rendering inputs;
            # visible recognizability still requires a separate image review.
            self.assertGreater(prop['radius'], .1)
            self.assertEqual(len(prop['label_color']), 4)
            self.assertEqual(len(prop['location']), 3)
        self.assertEqual(controls.expected_labels()['T4']['horizontal_stack'], 'no')

    def test_predefined_labels_leave_t5_unreviewed_without_modifying_others(self):
        labels = controls.expected_labels()
        self.assertEqual(labels, {
            'T1': {'horizontal_stack': 'yes', 'upright_books': 'yes'},
            'T2': {'horizontal_stack': 'no', 'upright_books': 'yes'},
            'T3': {'horizontal_stack': 'no', 'upright_books': 'yes'},
            'T4': {'horizontal_stack': 'no', 'upright_books': 'yes'},
            'T5': {'horizontal_stack': None, 'upright_books': None},
        })
        before = deepcopy(labels)
        for expected in labels['T5'].values():
            for prediction in ('yes', 'no'):
                self.assertEqual(controls.assess(expected, prediction),
                                 'expected_unreviewed')
        self.assertEqual(labels, before)

    def test_assess_separates_correct_false_positive_and_false_negative(self):
        for expected, prediction, status in (
                ('yes', 'yes', 'correct'), ('no', 'no', 'correct'),
                ('no', 'yes', 'false_positive'),
                ('yes', 'no', 'false_negative')):
            with self.subTest(expected=expected, prediction=prediction):
                self.assertEqual(controls.assess(expected, prediction), status)

    def test_unknown_and_unavailable_never_become_correct_or_incorrect(self):
        for expected in ('yes', 'no', None):
            with self.subTest(expected=expected):
                self.assertEqual(controls.assess(expected, 'unknown'), 'unknown')
                self.assertEqual(controls.assess(expected, None), 'unavailable')
        for prediction in ('yes', 'no', 'unknown', None):
            self.assertNotIn(controls.assess(None, prediction),
                             ('correct', 'false_positive', 'false_negative'))

    def test_config_calls_return_independent_values_and_do_not_mutate_history(self):
        first = controls.configs()
        unchanged = deepcopy(first)
        first['T1']['books'][0]['dimensions'][0] += .01
        self.assertEqual(controls.configs(), unchanged)
        self.assertEqual(first['T2'], unchanged['T2'])
        labels = controls.expected_labels()
        labels['T5']['horizontal_stack'] = 'unknown'
        self.assertIsNone(controls.expected_labels()['T5']['horizontal_stack'])


if __name__ == '__main__':
    unittest.main()
