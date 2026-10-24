"""Synthetic, CPU-only contracts for non-scoring island/pendant diagnostics."""
from copy import deepcopy
import unittest

import numpy as np

from e_harness.spatial_diagnostics import compare_pairs, measure_pair


IMAGE_SIZE = [200, 100]  # Width, height; deliberately non-square.
PAIR_VALUES = ('delta_x', 'delta_y', 'bbox_area_ratio_proxy', 'visible_mask_area_ratio')
CHANGE_VALUES = tuple(key + '_change' for key in PAIR_VALUES)


def objects():
    return {
        'island': dict(category='island', bbox=[40, 60, 160, 90], status='matched',
                       reviewed=True, reliability=1.,
                       extent_definition='visible island body and countertop'),
        'pendant': dict(category='pendant light', bbox=[110, 10, 130, 30], status='matched',
                        reviewed=True, reliability=1.,
                        extent_definition='visible light fitting, excluding suspension wire'),
    }


def with_masks(rows=None):
    rows = objects() if rows is None else rows
    for key, fill in (('island', 1.), ('pendant', .5)):
        mask = np.zeros(IMAGE_SIZE[::-1], float)
        x0, y0, x1, y1 = rows[key]['bbox']
        mask[y0:y1, x0:x1] = fill
        rows[key].update(mask=mask, mask_reviewed=True, mask_scope='visible_object')
    return rows


class SpatialMinimalTests(unittest.TestCase):
    def assert_non_scoring(self, row):
        self.assertIsNone(row['score'])
        self.assertIs(row['participates_in_energy'], False)

    def assert_pair_unavailable(self, row):
        self.assert_non_scoring(row)
        for key in PAIR_VALUES:
            self.assertIsNone(row[key], key)
        self.assertTrue(row['reason'])

    def test_non_square_grid_has_signed_pendant_minus_island_offsets(self):
        result = measure_pair(objects(), IMAGE_SIZE)
        self.assertEqual(list(result['image_size']), IMAGE_SIZE)
        np.testing.assert_allclose(result['normalized_centers']['island'], [.5, .75])
        np.testing.assert_allclose(result['normalized_centers']['pendant'], [.6, .2])
        self.assertAlmostEqual(result['delta_x'], .1)
        self.assertAlmostEqual(result['delta_y'], -.55)
        self.assertAlmostEqual(result['bbox_area_ratio_proxy'], 1 / 9)
        self.assertIsNone(result['visible_mask_area_ratio'])
        self.assert_non_scoring(result)

    def test_direction_and_offset_strength_are_preserved(self):
        left = objects()
        left['pendant']['bbox'] = [70, 20, 90, 40]
        result = measure_pair(left, IMAGE_SIZE)
        self.assertAlmostEqual(result['delta_x'], -.1)
        self.assertAlmostEqual(result['delta_y'], -.45)
        right = objects()
        right['pendant'].update(bbox=[150, 10, 170, 30], status='misplaced')
        result = measure_pair(right, IMAGE_SIZE)
        self.assertAlmostEqual(result['delta_x'], .3)
        self.assertAlmostEqual(result['delta_y'], -.55)
        self.assert_non_scoring(result)
        below = objects()
        below['pendant']['bbox'] = [110, 80, 130, 100]
        self.assertAlmostEqual(measure_pair(below, IMAGE_SIZE)['delta_y'], .15)

    def test_common_translation_does_not_change_pair_layout_or_area_ratio(self):
        original = measure_pair(objects(), IMAGE_SIZE)
        translated = objects()
        for row in translated.values():
            row['bbox'] = (np.asarray(row['bbox']) + [10, 5, 10, 5]).tolist()
        result = measure_pair(translated, IMAGE_SIZE)
        for key in ('delta_x', 'delta_y', 'bbox_area_ratio_proxy'):
            self.assertAlmostEqual(result[key], original[key], msg=key)

    def test_independent_image_axis_scaling_preserves_normalized_measurements(self):
        original = measure_pair(objects(), IMAGE_SIZE)
        scaled = objects()
        for row in scaled.values():
            row['bbox'] = (np.asarray(row['bbox']) * [2, 3, 2, 3]).tolist()
        result = measure_pair(scaled, [400, 300])
        for key in ('delta_x', 'delta_y', 'bbox_area_ratio_proxy'):
            self.assertAlmostEqual(result[key], original[key], msg=key)

    def test_reviewed_visible_soft_masks_use_mass_and_remain_distinct_from_bbox(self):
        result = measure_pair(with_masks(), IMAGE_SIZE)
        self.assertAlmostEqual(result['bbox_area_ratio_proxy'], 1 / 9)
        self.assertAlmostEqual(result['visible_mask_area_ratio'], 1 / 18)
        self.assert_non_scoring(result)

    def test_bbox_proxy_uses_continuous_box_area_and_does_not_clip_ratios(self):
        rows = objects()
        rows['pendant']['bbox'] = [110.2, 10.2, 130.2, 30.2]
        self.assertAlmostEqual(measure_pair(rows, IMAGE_SIZE)['bbox_area_ratio_proxy'], 1 / 9)
        rows['pendant']['bbox'] = [0, 0, 200, 40]
        result = measure_pair(rows, IMAGE_SIZE)
        self.assertAlmostEqual(result['bbox_area_ratio_proxy'], 20 / 9)
        self.assert_non_scoring(result)

    def test_mask_requires_both_review_flags_visible_scope_and_both_objects(self):
        for key in ('island', 'pendant'):
            for change in (dict(mask_reviewed=False), dict(mask_scope='amodal')):
                with self.subTest(key=key, change=change):
                    rows = with_masks()
                    rows[key].update(change)
                    result = measure_pair(rows, IMAGE_SIZE)
                    self.assertIsNone(result['visible_mask_area_ratio'])
                    self.assertAlmostEqual(result['bbox_area_ratio_proxy'], 1 / 9)
            rows = with_masks()
            rows[key].pop('mask')
            result = measure_pair(rows, IMAGE_SIZE)
            self.assertIsNone(result['visible_mask_area_ratio'])
            self.assertAlmostEqual(result['bbox_area_ratio_proxy'], 1 / 9)

    def test_unknown_missing_wrong_class_and_absent_object_are_not_zero_measurements(self):
        for key in ('island', 'pendant'):
            for status in ('unknown', 'unavailable', 'confirmed_missing', 'semantic_mismatch'):
                with self.subTest(key=key, status=status):
                    rows = objects()
                    rows[key]['status'] = status
                    self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
                    self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE, allow_provisional=True))
            rows = objects()
            rows[key]['category'] = 'chair'
            self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
            self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE, allow_provisional=True))
            rows = objects()
            del rows[key]
            self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
            rows = objects()
            rows[key] = None
            self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
            self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE, allow_provisional=True))
        self.assert_pair_unavailable(measure_pair({}, IMAGE_SIZE))

    def test_unreviewed_coarse_boxes_require_explicit_provisional_mode(self):
        rows = objects()
        for row in rows.values():
            row['reviewed'] = False
        self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
        candidate = measure_pair(rows, IMAGE_SIZE, allow_provisional=True)
        self.assertAlmostEqual(candidate['delta_x'], .1)
        self.assertAlmostEqual(candidate['delta_y'], -.55)
        self.assertAlmostEqual(candidate['bbox_area_ratio_proxy'], 1 / 9)
        self.assert_non_scoring(candidate)

    def test_existing_reliability_gate_rejects_zero_conflicted_and_default_inferred(self):
        for change in (dict(reliability=0.), dict(conflicted=True)):
            with self.subTest(change=change):
                rows = objects()
                rows['pendant'].update(change)
                self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
        rows = objects()
        rows['pendant'].update(status='inferred', confidence=.999)
        rows['pendant'].pop('reliability')
        self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE))
        for bad_q in (-.1, 1.1, np.nan, np.inf):
            rows = objects()
            rows['pendant']['reliability'] = bad_q
            with self.subTest(reliability=bad_q), self.assertRaises(ValueError):
                measure_pair(rows, IMAGE_SIZE)

    def test_conflict_and_unknown_visibility_cannot_be_overridden_by_provisional_mode(self):
        for change in (dict(conflicted=True), dict(visibility='unknown'), dict(visibility='not_visible'),
                       dict(visible_in_input_view=False), dict(evidence_scope='scene_objects')):
            for provisional in (False, True):
                with self.subTest(change=change, provisional=provisional):
                    rows = objects()
                    rows['pendant'].update(change)
                    self.assert_pair_unavailable(measure_pair(rows, IMAGE_SIZE, allow_provisional=provisional))

    def test_compare_changes_are_render_minus_reference_without_area_type_substitution(self):
        reference = measure_pair(with_masks(), IMAGE_SIZE)
        rows = objects()
        rows['pendant']['bbox'] = [130, 25, 170, 55]
        rows = with_masks(rows)
        rows['pendant']['mask'] *= 1.5  # Soft visible mass: 1200 * .75 = 900.
        rendered = measure_pair(rows, IMAGE_SIZE)
        result = compare_pairs(reference, rendered)
        self.assertAlmostEqual(result['delta_x_change'], .15)
        self.assertAlmostEqual(result['delta_y_change'], .2)
        self.assertAlmostEqual(result['bbox_area_ratio_proxy_change'], 2 / 9)
        self.assertAlmostEqual(result['visible_mask_area_ratio_change'], 7 / 36)
        self.assert_non_scoring(result)
        reverse = compare_pairs(rendered, reference)
        for key in CHANGE_VALUES:
            self.assertAlmostEqual(reverse[key], -result[key], msg=key)
        no_render_mask = measure_pair(objects(), IMAGE_SIZE)
        for first, second in ((reference, no_render_mask), (no_render_mask, reference)):
            result = compare_pairs(first, second)
            self.assertAlmostEqual(result['bbox_area_ratio_proxy_change'], 0.)
            self.assertIsNone(result['visible_mask_area_ratio_change'])

    def test_unavailable_measurement_does_not_turn_into_a_comparison_penalty(self):
        known = measure_pair(objects(), IMAGE_SIZE)
        unknown = measure_pair({}, IMAGE_SIZE)
        for reference, rendered in ((known, unknown), (unknown, known), (unknown, unknown)):
            with self.subTest(reference=reference, rendered=rendered):
                result = compare_pairs(reference, rendered)
                self.assert_non_scoring(result)
                for key in CHANGE_VALUES:
                    self.assertIsNone(result[key], key)

    def test_comparison_rejects_grid_and_object_extent_mismatches(self):
        reference = measure_pair(objects(), IMAGE_SIZE)
        other_grid = measure_pair(objects(), [400, 200])
        with self.assertRaises(ValueError):
            compare_pairs(reference, other_grid)
        for key in ('island', 'pendant'):
            rows = objects()
            rows[key]['extent_definition'] += '; changed extent'
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare_pairs(reference, measure_pair(rows, IMAGE_SIZE))

    def test_bbox_is_validated_independently_even_with_a_valid_mask(self):
        bad_boxes = ([0, 0, 201, 20], [-1, 0, 20, 20], [0, 0, 20, 101],
                     [20, 0, 20, 20], [30, 0, 20, 20], [0, 20, 20, 20],
                     [0, 0, np.nan, 20], [0, 0, np.inf, 20], [0, 0, 20])
        for box in bad_boxes:
            with self.subTest(bbox=box):
                rows = with_masks()
                rows['pendant']['bbox'] = box
                with self.assertRaises(ValueError):
                    measure_pair(rows, IMAGE_SIZE)

    def test_invalid_empty_or_off_grid_masks_are_rejected(self):
        bad_masks = (np.zeros((100, 200)), np.zeros((0, 0)), np.ones((50, 100)),
                     np.ones((100, 200, 1)), np.full((100, 200), np.nan),
                     np.full((100, 200), np.inf), np.full((100, 200), -.1),
                     np.full((100, 200), 1.1))
        for mask in bad_masks:
            with self.subTest(shape=mask.shape, first=mask.flat[0] if mask.size else None):
                rows = with_masks()
                rows['pendant']['mask'] = mask
                with self.assertRaises(ValueError):
                    measure_pair(rows, IMAGE_SIZE)

    def test_nonpositive_nonfinite_and_malformed_image_sizes_are_rejected(self):
        for size in ([0, 100], [200, 0], [-200, 100], [200, -100],
                     [np.nan, 100], [200, np.inf], [200.5, 100], [200, 100.5],
                     [200], [200, 100, 3]):
            with self.subTest(size=size), self.assertRaises(ValueError):
                measure_pair(objects(), size)

    def test_usable_boxes_require_nonempty_string_extent_definitions(self):
        for value in (None, '', '   ', 123, ['visible light fitting']):
            with self.subTest(extent_definition=value):
                rows = objects()
                rows['pendant']['extent_definition'] = value
                with self.assertRaises(ValueError):
                    measure_pair(rows, IMAGE_SIZE)
        rows = objects()
        rows['pendant'].pop('extent_definition')
        with self.assertRaises(ValueError):
            measure_pair(rows, IMAGE_SIZE)

    def test_measurement_and_comparison_do_not_mutate_inputs(self):
        rows = with_masks()
        before = deepcopy(rows)
        image_size = IMAGE_SIZE.copy()
        reference = measure_pair(rows, image_size)
        rendered = measure_pair(objects(), image_size)
        self.assertEqual(image_size, IMAGE_SIZE)
        for key in rows:
            for field in rows[key]:
                if field == 'mask':
                    np.testing.assert_array_equal(rows[key][field], before[key][field])
                else:
                    self.assertEqual(rows[key][field], before[key][field])
        reference_before, rendered_before = deepcopy(reference), deepcopy(rendered)
        compare_pairs(reference, rendered)
        self.assertEqual(reference, reference_before)
        self.assertEqual(rendered, rendered_before)


if __name__ == '__main__':
    unittest.main()
