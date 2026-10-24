import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PIL import Image

from scripts.group_visibility import analyze,roi_on_grid,mask_on_reference,render


class GroupVisibilityTests(unittest.TestCase):
    def fixture(self):
        mapping=[dict(index=i,object_id='body_'+str(i),row_hint=str(i)) for i in (1,2,3)]
        boxes=[dict(base_bounds_projection=dict(xyxy_normalized=[0,0,1,1]))]
        return mapping,boxes

    def test_unique_ids_count_sampled_meshes_not_gt_instances(self):
        mapping,boxes=self.fixture();ids=np.array([[0,1],[2,0]],np.uint16);roi=np.array([[0,1],[0,1]],bool)
        result,mask=analyze(ids,mapping,roi,boxes)
        self.assertEqual(result['candidate_body_objects'],3)
        self.assertEqual(result['bodies_with_sampled_id_pixels'],2)
        self.assertEqual(result['group_inside_r3_pixels'],1)
        self.assertEqual(result['group_outside_r3_pixels'],1)
        self.assertEqual(result['r3_group_pixel_fraction'],.5)
        self.assertEqual(result['group_outside_r3_fraction'],.5)
        self.assertIsNone(result['historical_full_resolution_visible_object_count'])
        self.assertIsNone(result['actual_semantic_record_count'])
        self.assertEqual(result['rows'][2]['mask_pixels'],0)

    def test_bbox_pixels_never_become_group_mask(self):
        mapping,boxes=self.fixture();ids=np.zeros((2,2),np.uint16)
        result,mask=analyze(ids,mapping,np.ones_like(ids,bool),boxes)
        self.assertFalse(mask.any());self.assertEqual(result['bbox_proxy_pixels'],4)
        self.assertEqual(result['bbox_proxy_without_group_id_pixels'],4)
        self.assertIsNone(result['sampled_support_bbox_xyxy'])

    def test_unknown_ids_or_grid_mismatch_are_rejected(self):
        mapping,boxes=self.fixture()
        with self.assertRaises(ValueError):analyze(np.array([[4]],np.uint16),mapping,np.ones((1,1),bool),boxes)
        with self.assertRaises(ValueError):analyze(np.zeros((2,2),np.uint16),mapping,np.ones((1,1),bool),boxes)

    def test_letterbox_removed_before_roi_sampling(self):
        roi=np.zeros((6,4),np.uint8);roi[1:5]=255
        sampled=roi_on_grid(Image.fromarray(roi),dict(offset_xy=[0,1],resized_size=[4,4]),(2,2))
        self.assertTrue(sampled.all());self.assertEqual(sampled.shape,(2,2))

    def test_mask_display_transform_does_not_shift_roi(self):
        image=mask_on_reference(np.ones((2,2),bool),dict(offset_xy=[0,1],resized_size=[4,4]),(4,6))
        array=np.asarray(image)>0
        self.assertFalse(array[0].any());self.assertFalse(array[-1].any())
        self.assertEqual(array.sum(),16)

    def test_render_reservation_prevents_any_second_launch(self):
        with TemporaryDirectory() as directory:
            output=Path(directory);plan=dict(work=str(output))
            (output/'visibility.json').write_text(json.dumps(dict(status='prepared',protocol=plan)))
            (output/'frozen_plan.json').write_text(json.dumps(plan));(output/'render_reserved.json').write_text('{}')
            with self.assertRaises(ValueError):render(output)

    def test_trusted_helper_has_one_nonsaving_render_and_no_agent_execution(self):
        helper=Path(__file__).resolve().parents[1]/'scripts/group_id_blender.py'
        calls=[n for n in ast.walk(ast.parse(helper.read_text())) if isinstance(n,ast.Call)]
        names=[ast.unparse(n.func) for n in calls]
        self.assertEqual(names.count('bpy.ops.render.render'),1)
        self.assertFalse(set(names)&{'exec','eval','runpy.run_path','bpy.ops.wm.save_as_mainfile'})
        call=next(n for n in calls if ast.unparse(n.func)=='bpy.ops.render.render')
        self.assertIs(next(k.value.value for k in call.keywords if k.arg=='write_still'),False)


if __name__=='__main__':unittest.main()
