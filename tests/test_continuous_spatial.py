"""CPU Oracle masks exercise geometry, not RGB detection or VLM accuracy."""
from collections import OrderedDict
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from e_harness.spatial_diagnostics import compare_pairs, measure_visible_pair
from scripts.continuous_spatial_pilot import ROOT, load_saved, run


def masks(first_x=10):
    first=np.zeros((60,100),bool);first[20:50,first_x:first_x+20]=True
    second=np.zeros_like(first);second[25:45,70:90]=True
    return {'first':first,'second':second}


class ContinuousSpatialTests(unittest.TestCase):
    def test_analytic_non_square_centres_gap_and_direction(self):
        value=measure_visible_pair(masks(),[100,60])
        self.assertEqual(value['left_of'],True)
        self.assertAlmostEqual(value['relative_distance'],.6)
        self.assertAlmostEqual(value['delta_y'],0.)
        self.assertEqual(value['boundary_gap_pixels'],40.)
        self.assertAlmostEqual(value['boundary_gap'],.4)
        self.assertEqual(len(value['boundary_rows']),20)
        self.assertFalse(value['reviewed']);self.assertFalse(value['participates_in_energy'])
        self.assertIsNone(value['score'])

    def test_discrete_order_same_continuous_distance_decreases(self):
        first=measure_visible_pair(masks(),[100,60])
        second=measure_visible_pair(masks(40),[100,60])
        self.assertTrue(first['left_of'] and second['left_of'])
        self.assertAlmostEqual(first['relative_distance']-second['relative_distance'],.3)
        self.assertAlmostEqual(first['boundary_gap']-second['boundary_gap'],.3)
        self.assertAlmostEqual(compare_pairs(first,second)['delta_x_change'],-.3)

    def test_common_unclipped_translation_invariance(self):
        original=masks(); shifted={}
        for key,array in original.items():
            target=np.zeros_like(array);target[3:,4:]=array[:-3,:-4]
            self.assertEqual(target.sum(),array.sum());shifted[key]=target
        first=measure_visible_pair(original,[100,60]);second=measure_visible_pair(shifted,[100,60])
        for key in ('relative_distance','delta_y','boundary_gap'):
            self.assertAlmostEqual(first[key],second[key])

    def test_unavailable_and_empty_masks_are_na_not_missing_penalties(self):
        for raw in (None,np.zeros((60,100),bool)):
            pair=masks();pair['first']=raw
            result=measure_visible_pair(pair,[100,60])
            for key in ('left_of','relative_distance','delta_x','delta_y','boundary_gap'):
                self.assertIsNone(result[key],key)
            self.assertEqual(result['status'],'unavailable');self.assertIsNone(result['score'])

    def test_non_overlapping_rows_keep_centres_but_gap_is_na(self):
        pair=masks();pair['second'][:]=False;pair['second'][2:10,70:90]=True
        result=measure_visible_pair(pair,[100,60])
        self.assertAlmostEqual(result['relative_distance'],.6)
        self.assertIsNone(result['boundary_gap']);self.assertEqual(result['boundary_rows'],[])

    def test_visible_boundary_gap_is_not_bbox_envelope_proxy(self):
        first=np.zeros((60,100),bool);second=np.zeros_like(first)
        first[10,10:20]=True;second[10,30:40]=True
        first[11,10:30]=True;second[11,40:50]=True
        result=measure_visible_pair({'a':first,'b':second},[100,60])
        boxes=[result['localizations'][k]['bbox'] for k in ('a','b')]
        self.assertEqual(boxes[1][0]-boxes[0][2],0)  # envelope gap
        self.assertEqual(result['boundary_gap_pixels'],10.)  # actual row-wise boundaries

    def test_touching_boundaries_are_valid_zero(self):
        pair=masks(50)
        result=measure_visible_pair(pair,[100,60])
        self.assertEqual(result['boundary_gap'],0.)
        self.assertEqual(result['boundary_status'],'conditional_debug')

    def test_swapped_order_changes_sign_not_distance(self):
        pair=masks();a=measure_visible_pair(pair,[100,60])
        b=measure_visible_pair(OrderedDict(reversed(list(pair.items()))),[100,60])
        self.assertFalse(b['left_of']);self.assertAlmostEqual(a['relative_distance'],b['relative_distance'])
        self.assertAlmostEqual(a['delta_x'],-b['delta_x'])
        with self.assertRaisesRegex(ValueError,'ordered object'):
            compare_pairs(a,b)

    def test_invalid_shape_nonbinary_masks_and_grid_rejected(self):
        for raw in (np.ones((60,99)),np.ones((60,100,1)),np.full((60,100),.4),
                    np.full((60,100),np.nan),np.full((60,100),255)):
            with self.subTest(shape=raw.shape),self.assertRaises(ValueError):
                measure_visible_pair(dict(first=raw,second=masks()['second']),[100,60])
        for size in ([0,60],[100.5,60],[100],[np.inf,60]):
            with self.subTest(size=size),self.assertRaises(ValueError):
                measure_visible_pair(masks(),size)

    def test_one_or_three_objects_rejected(self):
        for pair in ({'a':None},{'a':None,'b':None,'c':None}):
            with self.assertRaises(ValueError):measure_visible_pair(pair,[100,60])

    def test_saved_m1_and_m2_replay_produces_only_three_outputs(self):
        m1=ROOT/'results/trusted_blender_e2e_pilot';m2=ROOT/'results/m2_reference_vlm_e2e'
        before=(m2/'verification_results.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'new'
            result=run(m1,m2,output)
            self.assertEqual({p.name for p in output.iterdir()},
                {'comparison.png','spatial_diagnostics.json','summary.md'})
            values=result['diagnostics']['continuous_spatial']
            self.assertTrue(values['reference']['left_of'] and values['changed']['left_of'])
            self.assertLess(values['changed']['relative_distance'],values['reference']['relative_distance'])
            self.assertLess(values['changed']['boundary_gap'],values['reference']['boundary_gap'])
            self.assertEqual(result['diagnostics']['vlm_discrete_relation']['original_record']['status'],'satisfied')
            self.assertEqual(result['provenance']['new_model_calls'],0)
            self.assertEqual(result['provenance']['new_blender_executions'],0)
            with self.assertRaises(FileExistsError):run(m1,m2,output)
        self.assertEqual((m2/'verification_results.json').read_bytes(),before)

    def test_m2_answer_image_mismatch_rejected(self):
        m1=ROOT/'results/trusted_blender_e2e_pilot';m2=ROOT/'results/m2_reference_vlm_e2e'
        document=json.loads((m2/'verification_results.json').read_text())
        document['image_pair'].update(reference_rgb=str(m1/'baseline/render.png'),render_rgb=str(m1/'baseline/render.png'))
        for side in ('reference','render'):
            document[side]['image_binding']['source_rgb']=str(m1/'baseline/render.png')
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);(directory/'verification_results.json').write_text(json.dumps(document))
            (directory/'report.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'different RGB'):
                run(m1,directory,directory/'new')

    def test_wrong_saved_camera_binding_rejected(self):
        source=ROOT/'results/trusted_blender_e2e_pilot/baseline'
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            for name in ('render.png','export_metadata.json','execution.json'):
                shutil.copyfile(source/name,directory/name)
            execution=json.loads((directory/'execution.json').read_text())
            execution['camera_after_export']['lens_mm']+=1
            (directory/'execution.json').write_text(json.dumps(execution))
            with self.assertRaisesRegex(ValueError,'association'):
                load_saved(directory)


if __name__=='__main__':unittest.main()
