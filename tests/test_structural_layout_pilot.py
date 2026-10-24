import json
import unittest
from copy import deepcopy
from scripts.structural_layout_pilot import parse_topology,compare_topology,assisted_hypotheses


class StructuralLayoutTest(unittest.TestCase):
    def sample(self):
        return dict(top_to_bottom_complete='yes',horizontal_shelves=[],rows=[dict(id='x',y_range=[100,800],vertical_dividers=1,
            separate_compartments=2,divider_segments=[[400,100,400,800]],certainty='clear')],unknown=[])

    def test_clear_merge_is_mismatch_not_unknown(self):
        a=self.sample();b=deepcopy(a);b['rows'][0].update(vertical_dividers=0,separate_compartments=1,divider_segments=[])
        result=compare_topology(parse_topology(json.dumps(a)),parse_topology(json.dumps(b)))
        self.assertEqual(result['status'],'candidate_structural_layout_mismatch');self.assertEqual(result['rows'][0]['event_count'],1)

    def test_occlusion_abstains_and_incomplete_extent_not_aligned(self):
        a=self.sample();b=deepcopy(a);b['rows'][0]['certainty']='partial'
        self.assertEqual(compare_topology(parse_topology(json.dumps(a)),parse_topology(json.dumps(b)))['status'],'unknown')
        b['top_to_bottom_complete']='no'
        self.assertEqual(compare_topology(parse_topology(json.dumps(a)),parse_topology(json.dumps(b)))['rows'],[])

    def test_invalid_coordinates_and_duplicate_ids_rejected(self):
        a=self.sample();a['rows'][0]['divider_segments'][0][0]=1001
        self.assertEqual(parse_topology(json.dumps(a))['status'],'unavailable')
        a=self.sample();a['rows'].append(deepcopy(a['rows'][0]))
        self.assertEqual(parse_topology(json.dumps(a))['status'],'unavailable')

    def test_unavailable_is_not_zero_error(self):
        self.assertEqual(compare_topology(parse_topology('invalid'),parse_topology(json.dumps(self.sample())))['status'],'unavailable')

    def test_geometry_hypothesis_does_not_upgrade_partial_vlm(self):
        a=parse_topology(json.dumps(self.sample()));b=deepcopy(a)
        b['topology']['rows'][0].update(vertical_dividers=0,separate_compartments=1,divider_segments=[],certainty='partial')
        geometry=dict(status='conditional_geometry_support',openings_top_to_bottom_world_z=[[0,1]],internal_vertical_slab_candidates=[])
        self.assertEqual(len(assisted_hypotheses(a,b,geometry)),1)
        self.assertEqual(compare_topology(a,b)['status'],'unknown')
        self.assertEqual(b['topology']['rows'][0]['certainty'],'partial')
        self.assertEqual(assisted_hypotheses(a,b,dict(status='unavailable')),[])


if __name__=='__main__':unittest.main()
