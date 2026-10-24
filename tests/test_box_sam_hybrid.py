"""CPU-only safeguards for retaining multi-object functional regions."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from scripts.vlm_box_sam_hybrid import conservative_hybrid,render
from scripts.region_grounding_experiment import read,save
from e_harness.benchmark_evidence import load_document,reliability


class BoxSamHybridTests(unittest.TestCase):
    def test_partial_target_cannot_delete_disconnected_group_members(self):
        box=np.zeros((64,96),bool);box[5:60,10:90]=True
        sam=np.zeros_like(box);sam[30:48,25:75]=True
        # A single mask around a table does not establish that the upper lamp
        # or lower chairs are background. Preserve these unsupported pixels.
        original=sam.copy();hybrid,decision=conservative_hybrid(box,sam)
        self.assertTrue(hybrid[10,45] and hybrid[55,30])
        np.testing.assert_array_equal(hybrid,box);np.testing.assert_array_equal(sam,original)
        self.assertEqual(decision['status'],'uncertain');self.assertFalse(decision['reviewed'])
        self.assertFalse(np.shares_memory(hybrid,box))

    def test_sam_leakage_cannot_expand_roi_and_missing_sam_is_explicit(self):
        box=np.zeros((20,30),bool);box[5:15,5:25]=True
        for candidate in (np.ones_like(box),np.zeros_like(box),None):
            result,status=conservative_hybrid(box,candidate)
            np.testing.assert_array_equal(result,box)
            self.assertEqual(status['decision'],'retain_box')

    def test_invalid_grid_is_not_silently_resized(self):
        with self.assertRaises(ValueError):conservative_hybrid(np.zeros((20,30),bool),None)
        with self.assertRaises(ValueError):conservative_hybrid(np.ones((20,30),bool),np.ones((10,15),bool))

    def test_real_render_separates_raw_mask_hybrid_and_deleted_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);size=(96,64);Image.new('RGB',size,(140,150,160)).save(root/'reference.png')
            save(root/'input.json',dict(native_image_size=list(size)))
            plan=[dict(id='R'+str(i),name='functional group',content='several visible items',reviewed=False) for i in range(1,5)]
            save(root/'region_plan.json',dict(regions=plan))
            save(root/'box_prompts.json',dict(regions=[]))
            (root/'A_box_native').mkdir();(root/'sam_raw').mkdir()
            a=np.zeros(size[::-1],bool);a[5:60,10:90]=True
            b=np.zeros_like(a);b[25:45,25:75]=True;b[2:8,2:8]=True
            for row in plan:
                Image.fromarray(a).save(root/'A_box_native'/(row['id']+'.png'))
                Image.fromarray(b).save(root/'sam_raw'/(row['id']+'.png'))
            save(root/'sam_raw/candidates.json',dict(regions=[dict(r,raw_iou_head_score=.999) for r in plan]))
            render(root)
            for row in plan:
                rid=row['id']
                np.testing.assert_array_equal(np.asarray(Image.open(root/'sam_raw'/(rid+'.png'))),b)
                np.testing.assert_array_equal(np.asarray(Image.open(root/'C_hybrid_native'/(rid+'.png'))),a)
                np.testing.assert_array_equal(np.asarray(Image.open(root/'differences'/(rid+'_removed_from_box.png'))),a&~b)
                Image.open(root/'per_region'/(rid+'.png')).verify()
            doc=load_document(root/'C_hybrid_native/evidence.json')
            self.assertTrue(all(reliability(row)==0 and row['reviewed'] is False for row in doc['regions']))
            detail=read(root/'diagnostics.json')['regions'][0]
            self.assertEqual(detail['sam_removed_box_pixels'],int((a&~b).sum()))
            self.assertEqual(detail['sam_outside_box_pixels'],int((b&~a).sum()))
            self.assertTrue(detail['removed_pixels_are_not_verified_background'])


if __name__=='__main__':unittest.main()
