"""CPU-only geometry and completeness guard checks; no semantic GT claims."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
from scripts.vlm_guided_slic import context,select,protected_core,export
from e_harness.benchmark_evidence import load_document,reliability


class GuidedSlicTests(unittest.TestCase):
    def test_overlap_denominator_uses_entire_superpixel_and_includes_ties(self):
        labels=np.array([[10,10,50,50],[10,10,50,50]])
        rgb=np.full((*labels.shape,3),120,np.uint8);roi=np.zeros(labels.shape,bool)
        roi[:,0]=True;roi[0,2]=True
        result=select(roi,context(rgb,labels));rows=result['labels']
        self.assertEqual([r['overlap_fraction'] for r in rows],[.5,.25])
        np.testing.assert_array_equal(result['c1'],labels==10)

    def test_core_and_small_disconnected_parts_survive_low_overlap(self):
        labels=np.zeros((40,60),np.int32);rgb=np.full((40,60,3),120,np.uint8)
        roi=np.zeros((40,60),bool);roi[4:14,4:14]=True;roi[30,40:43]=True
        result=select(roi,context(rgb,labels))
        self.assertFalse(result['c1'].any())
        self.assertTrue(result['c2'][30,40:43].all())
        self.assertFalse((protected_core(roi,2)&~result['c2']).any())
        self.assertGreater(result['c2_core_restored_pixels'],0)

    def test_shared_boundary_gradient_reduces_affinity(self):
        labels=np.repeat(np.arange(3)[None,:],4,axis=1);labels=np.repeat(labels,8,axis=0)
        rgb=np.zeros((*labels.shape,3),np.uint8);rgb[labels==2]=255
        graph=context(rgb,labels)
        self.assertLess(graph['mean_gradient'][0],graph['mean_gradient'][1])
        self.assertGreater(graph['weights'][0],graph['weights'][1])

    def test_label_renumbering_and_repeated_calls_cannot_change_roi(self):
        labels=np.arange(16).reshape(4,4).repeat(5,0).repeat(5,1)
        rgb=np.arange(labels.size*3,dtype=np.uint8).reshape(*labels.shape,3)
        roi=np.zeros(labels.shape,bool);roi[2:16,4:18]=True
        graph=context(rgb,labels);first=select(roi,graph)
        renumber=np.arange(16)[::-1]*7+11
        other=select(roi,context(rgb,renumber[labels]))
        repeated=select(roi,graph)
        for key in ('c1','c2','c2_raw'):
            np.testing.assert_array_equal(first[key],other[key]);np.testing.assert_array_equal(first[key],repeated[key])

    def test_invalid_roi_or_label_grid_is_rejected_without_resize(self):
        rgb=np.full((20,30,3),120,np.uint8);graph=context(rgb,np.zeros((20,30),int))
        for roi in (np.zeros((20,30),bool),np.ones((10,15),bool),np.ones((20,30),float)):
            with self.assertRaises(ValueError):select(roi,graph)
        with self.assertRaises(ValueError):context(rgb,np.zeros((10,15),int))
        with self.assertRaises(ValueError):context(rgb,np.full((20,30),-1,int))

    def test_export_preserves_native_grid_and_unreviewed_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);rgb=np.full((40,60,3),120,np.uint8);masks=np.zeros((1,40,60),bool);masks[0,5:30,10:50]=True
            regions=[dict(id='R1',name='group',reviewed=False)]
            export(out,'candidate',rgb,regions,masks,[120,80],'offline fixture')
            loaded=load_document(out/'candidate_native/evidence.json')
            self.assertEqual(loaded['regions'][0]['mask'].shape,(80,120))
            self.assertEqual(reliability(loaded['regions'][0]),0)
            self.assertFalse(loaded['regions'][0]['mask_reviewed'])
            Image.open(out/'candidate/R1_overlay.png').verify()


if __name__=='__main__':unittest.main()
