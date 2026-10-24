import unittest
from copy import deepcopy
from scripts.structural_local_comparability import compare_local


class LocalComparabilityTest(unittest.TestCase):
    def claim(self):
        return dict(reference=dict(value='present',visibility='visible',conflict=False),
                    render=dict(value='absent',visibility='visible',global_left_boundary_cropped=True),
                    correspondence='exact_oracle',geometry=dict(kind='conditional_no_internal_slab_candidates'))

    def test_other_boundary_crop_does_not_block_local_difference(self):
        self.assertEqual(compare_local(self.claim())['status'],'candidate_structural_layout_mismatch')

    def test_target_crop_not_upgraded_by_geometry(self):
        c=self.claim();c['render']['visibility']='cropped'
        self.assertEqual(compare_local(c)['status'],'unknown')

    def test_unknown_and_conflict_are_local_not_global(self):
        a=self.claim();b=deepcopy(a);b['reference']['conflict']=True;b['reference']['value']='absent'
        self.assertEqual([compare_local(c)['status'] for c in (a,b)],['candidate_structural_layout_mismatch','unknown'])

    def test_coarse_geometry_retains_image_only_unknown(self):
        c=self.claim();c['render'].update(visibility='partial',value='unknown');c['correspondence']='coarse_ordered_opening'
        r=compare_local(c);self.assertEqual(r['status'],'candidate_structural_layout_mismatch');self.assertEqual(r['image_only_status'],'unknown')
        c['correspondence']='unknown';self.assertEqual(compare_local(c)['status'],'unknown')


if __name__=='__main__':unittest.main()
