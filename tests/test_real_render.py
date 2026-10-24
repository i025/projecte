"""CPU checks for fixed-coordinate provisional image diagnostics."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from scripts.region_real_render import fit_render,fixed_grid,area_rectangle,measures,observed_area_controls
from e_harness.benchmark_metrics import compare


class RealRenderTests(unittest.TestCase):
    def test_letterbox_preserves_full_view_and_marks_padding_unobserved(self):
        image=Image.new('RGB',(20,10),(80,120,160));before=np.asarray(image).copy()
        fitted,valid,meta=fit_render(image,(12,12))
        self.assertEqual(meta['resized_size'],[12,6]);self.assertEqual(meta['offset_xy'],[0,3])
        self.assertEqual(int(valid.sum()),72);self.assertFalse(valid[:3].any());self.assertFalse(valid[9:].any())
        self.assertTrue((fitted[valid]==[80,120,160]).all())
        np.testing.assert_array_equal(np.asarray(image),before)
        self.assertFalse(meta['content_alignment'])

    def test_padding_or_transparency_is_not_scored_as_scene_colour(self):
        image=Image.new('RGBA',(20,10),(80,120,160,255));fitted,valid,_=fit_render(image,(20,20))
        reference=np.full((20,20,3),255,np.uint8);reference[valid]=fitted[valid]
        appearance,perceptual,reason=measures(reference,fitted,valid)
        self.assertEqual(appearance,0);self.assertIsNone(perceptual)
        rgba=np.asarray(image).copy();rgba[0,0,3]=0
        _,alpha_valid,_=fit_render(Image.fromarray(rgba),(20,10));self.assertFalse(alpha_valid[0,0])

    def test_fixed_grids_partition_odd_canvas_without_gaps_or_overlap(self):
        for n in (2,4):
            masks=[mask for _,_,mask in fixed_grid((43,71),n)]
            np.testing.assert_array_equal(np.stack(masks).sum(0),np.ones((43,71),int))

    def test_area_control_uses_only_geometry_and_is_nearly_area_matched(self):
        mask=np.zeros((100,160),bool);mask[15:60,20:100]=True;mask[70:90,70:130]=True
        rect,meta=area_rectangle(mask)
        self.assertLess(abs(meta['area_ratio']-1),.01);self.assertFalse(meta['semantics_used'])
        source=meta['source_bbox'];control=meta['control_bbox']
        self.assertLessEqual(abs((source[0]+source[2])-(control[0]+control[2])),1)
        self.assertLessEqual(abs((source[1]+source[3])-(control[1]+control[3])),1)
        again,_=area_rectangle(rect);np.testing.assert_array_equal(rect,again)

    def test_observed_area_control_does_not_change_frozen_roi(self):
        roi=np.zeros((100,160),bool);roi[10:90,:90]=True;roi[40:70,90:110]=True
        valid=np.ones_like(roi);valid[:,:12]=False;before=roi.copy()
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'measurement_rois').mkdir()
            units=[dict(id='polygon_X',group='polygon',region_id='X')]
            extra=observed_area_controls(out,units,{'polygon_X':roi},valid)
            rect=np.asarray(Image.open(out/extra[0]['mask']),bool)
            self.assertLess(abs((rect&valid).sum()/(roi&valid).sum()-1),.01)
            self.assertFalse((rect&~valid).any());np.testing.assert_array_equal(roi,before)
            self.assertFalse(extra[0]['reviewed'])

    def test_appearance_reuses_conditional_rgb_error_and_identity_is_zero(self):
        a=np.zeros((24,32,3),np.uint8);b=a.copy();mask=np.zeros((24,32),bool);mask[2:18,4:24]=True
        b[mask,0]=255;b[~mask,1]=255
        error,_,_=measures(a,b,mask);self.assertAlmostEqual(error,1/3)
        self.assertEqual(measures(a,a,mask)[0],0)

    def test_official_compare_still_rejects_unreviewed_region_evidence(self):
        a=np.zeros((32,32,3),np.uint8);b=np.full_like(a,220)
        region=dict(id='R1',bbox=[0,0,32,32],metrics=['appearance','perceptual'],reviewed=False,reliability=0.)
        reference=dict(regions=[region],anchors=[],relations=[],anchor_exclusion=np.zeros((32,32)),reviewed=False)
        rows,_=compare(a,b,reference)
        selected=[r for r in rows if r['level']=='region']
        self.assertTrue(selected);self.assertTrue(all(r['value'] is None and r['q']==0 for r in selected))
        self.assertFalse(region['reviewed']);self.assertEqual(region['reliability'],0)


if __name__=='__main__':unittest.main()
