"""Trusted raster-oracle tests; never runs Blender, models or real Agent code."""
from copy import deepcopy
import tempfile
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np

from e_harness.benchmark import evaluate
from e_harness.benchmark_evidence import coverage_audit, load_document
from e_harness.benchmark_metrics import match_anchors


def anchor(key='a', category='plant', box=(8, 8, 20, 20), **extra):
    return dict(id=key, category=category, bbox=list(box), reviewed=True,
                reliability=1., importance=1., source='Trusted raster fixture', **extra)


def verdict(status, **extra):
    return dict(status=status, reviewed=True, reliability=1.,
                verification_type='synthetic_oracle', evidence_scope='input_view',
                source='Known visible raster fixture oracle', **extra)


class MissingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.image=np.zeros((48,64,3),np.uint8)
        self.image[8:20,8:20]=[180,50,20]
        self.ref=dict(anchors=[anchor()])

    def measure(self, observed, image=None, ref=None):
        return evaluate(self.image,self.image if image is None else image,
                        self.ref if ref is None else ref,observed)[0]

    def status(self, report):
        return report['error_diagnostics']['anchor_matching'][0]['verification_status']

    def test_matched_and_no_mask_required(self):
        report=self.measure(dict(anchors=[anchor('r')]))
        self.assertEqual(self.status(report),'matched')
        self.assertEqual(report['energies']['semantic']['value'],0.)

    def test_zero_iou_large_displacement_is_misplaced_not_missing(self):
        report=self.measure(dict(anchors=[anchor('r',box=(44,28,56,40))]))
        self.assertEqual(self.status(report),'misplaced')
        self.assertEqual(report['energies']['semantic']['value'],0.)
        self.assertGreater(report['energies']['spatial']['value'],0.)

    def test_overlapping_class_replacement_is_semantic_mismatch(self):
        report=self.measure(dict(anchors=[anchor('r',category='lamp')]))
        self.assertEqual(self.status(report),'semantic_mismatch')
        self.assertEqual(report['energies']['semantic']['value'],1.)

    def test_remote_unrelated_class_does_not_prove_replacement(self):
        report=self.measure(dict(anchors=[anchor('r',category='lamp',box=(44,28,56,40))]))
        self.assertEqual(self.status(report),'unknown')
        self.assertEqual(report['error_diagnostics']['extra_anchors'],[])
        self.assertIsNone(report['energies']['semantic']['value'])

    def test_complete_reviewed_render_oracle_confirms_missing(self):
        report=self.measure(dict(anchors=[],reviewed=True,inventory_complete=True),np.zeros_like(self.image))
        self.assertEqual(self.status(report),'confirmed_missing')
        self.assertEqual(report['energies']['semantic']['value'],1.)

    def test_single_human_absence_without_complete_inventory(self):
        v=verdict('confirmed_missing',reference_id='a');v['verification_type']='human'
        report=self.measure(dict(anchors=[],anchor_verdicts=[v]),np.zeros_like(self.image))
        self.assertFalse(report['error_diagnostics']['inventory']['complete'])
        self.assertEqual(self.status(report),'confirmed_missing')
        self.assertEqual(report['energies']['semantic']['value'],1.)

    def test_detector_false_negative_with_object_present_is_unknown(self):
        report=self.measure(dict(anchors=[],anchor_verdicts=[dict(reference_id='a',status='candidate_missing')]))
        self.assertEqual(self.status(report),'unknown')
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertEqual(report['uncertainty']['anchor_coverage'],0.)
        self.assertTrue(any('a:presence'==r['id'] for r in report['metric_records']))

    def test_unvalidated_vlm_or_unreviewed_absence_cannot_confirm(self):
        for change in [dict(verification_type='vlm',confidence=.999),dict(reviewed=False),
                       dict(source=''),dict(source=True),dict(evidence_scope='scene_objects'),dict(reliability=0.)]:
            v=verdict('confirmed_missing',reference_id='a');v.update(change)
            report=self.measure(dict(anchors=[],anchor_verdicts=[v]))
            self.assertEqual(self.status(report),'unknown')

    def test_missing_not_duplicated_as_anchor_appearance_or_spatial_penalty(self):
        v=verdict('confirmed_missing',reference_id='a')
        report=self.measure(dict(anchors=[],anchor_verdicts=[v]),np.zeros_like(self.image))
        rows=[r for r in report['metric_records'] if r['level']=='anchor' and r['id']=='a']
        self.assertEqual({r['energy'] for r in rows},{'spatial','appearance','perceptual'})
        self.assertTrue(all(r['value'] is None and 'Semantic' in r['reason'] for r in rows))

    def test_unmatched_render_is_unknown_extra_with_incomplete_reference(self):
        report=self.measure(dict(anchors=[anchor(),anchor('extra',box=(40,8,52,20))],reviewed=True,inventory_complete=True))
        self.assertEqual(report['error_diagnostics']['extra_anchors'],[])
        self.assertEqual(report['error_diagnostics']['inventory']['unknown_extras'],['extra'])
        self.assertEqual(report['energies']['semantic']['value'],0.)

    def test_explicit_verified_extra_without_complete_reference(self):
        report=self.measure(dict(anchors=[anchor(),anchor('extra',category='lamp',box=(40,8,52,20))],
                                 anchor_verdicts=[verdict('confirmed_extra',rendered_id='extra')]))
        self.assertEqual(report['error_diagnostics']['extra_anchors'],['extra'])
        self.assertGreater(report['energies']['semantic']['value'],0.)

    def test_unknown_extra_reduces_coverage_not_existing_conditional_error(self):
        base=self.measure(dict(anchors=[anchor()]))
        changed=self.measure(dict(anchors=[anchor(),anchor('extra',category='lamp',box=(40,8,52,20))]))
        self.assertEqual(base['observation_energy'],changed['observation_energy'])
        self.assertLess(changed['energies']['semantic']['coverage'],base['energies']['semantic']['coverage'])

    def test_partial_verified_missing_and_unknown_remain_separate(self):
        ref=dict(anchors=[anchor(),anchor('b',category='table',box=(32,8,48,24))])
        report=self.measure(dict(anchors=[],anchor_verdicts=[verdict('confirmed_missing',reference_id='a')]),ref=ref)
        states={m['reference_id']:m['verification_status'] for m in report['error_diagnostics']['anchor_matching']}
        self.assertEqual(states,dict(a='confirmed_missing',b='unknown'))
        self.assertEqual(report['energies']['semantic']['value'],1.)
        self.assertLess(report['energies']['semantic']['coverage'],1.)

    def test_unreviewed_render_candidate_does_not_erase_verified_absence(self):
        observed=dict(anchors=[],anchor_verdicts=[verdict('confirmed_missing',reference_id='a')])
        base=self.measure(observed)
        observed['anchors']=[dict(anchor('pending'),reviewed=False,reliability=0.)]
        changed=self.measure(observed)
        self.assertEqual(self.status(changed),'confirmed_missing')
        self.assertEqual(base['energies']['semantic']['value'],changed['energies']['semantic']['value'])
        self.assertEqual(base['observation_energy'],changed['observation_energy'])

    def test_complete_reference_allows_confirmed_extra(self):
        report=self.measure(dict(anchors=[anchor(),anchor('extra',box=(40,8,52,20))]),
                            ref=dict(self.ref,reviewed=True,inventory_complete=True))
        self.assertEqual(report['error_diagnostics']['extra_anchors'],['extra'])

    def test_scene_only_object_is_not_an_input_view_match(self):
        obj=anchor();obj['evidence_scope']='scene_objects'
        report=self.measure(dict(anchors=[obj]))
        self.assertEqual(self.status(report),'unknown')

    def test_empty_scene_inventory_cannot_confirm_input_view_absence(self):
        report=self.measure(dict(anchors=[],reviewed=True,inventory_complete=True,evidence_scope='scene_objects'))
        self.assertEqual(self.status(report),'unknown')
        with self.assertRaisesRegex(ValueError,'input-view RGB grid'):
            self.measure(dict(anchors=[],image_size=[128,128]))

    def test_explicit_correspondence_permits_displaced_class_mismatch(self):
        observed=dict(anchors=[anchor('r',category='lamp',box=(44,28,56,40))],
                      anchor_verdicts=[verdict('matched',reference_id='a',rendered_id='r')])
        self.assertEqual(self.status(self.measure(observed)),'semantic_mismatch')

    def test_conflicting_reviewed_verdicts_stay_unknown(self):
        report=self.measure(dict(anchors=[anchor('r')],reviewed=True,inventory_complete=True,
            anchor_verdicts=[verdict('matched',reference_id='a',rendered_id='r'),
                             verdict('confirmed_missing',reference_id='a')]))
        self.assertEqual(self.status(report),'unknown')
        self.assertIsNone(report['energies']['semantic']['value'])

    def test_region_replacement_still_compares_reference_pixels(self):
        region=dict(id='grass',bbox=[0,24,64,48],category='grass',reviewed=True,
                    metrics=['appearance','perceptual','semantic'],presence_evidence=True)
        a=np.zeros_like(self.image);a[24:]=[0,180,0]
        b=np.zeros_like(a);b[24:]=[100,100,100]
        # Real image-derived vectors test the gateway/formula, not DINO quality.
        def features(images):
            return np.array([list(im.mean(axis=(0,1))/255)+[1.] for im in images])
        report,_=evaluate(a,b,dict(regions=[region]),dict(regions=[]),extract=features)
        rows={ (r['id'],r['energy']):r for r in report['metric_records'] }
        self.assertGreater(rows['grass','appearance']['value'],0.)
        self.assertGreater(rows['grass','perceptual']['value'],0.)
        self.assertIsNone(rows['grass','semantic']['value'])

    def test_verified_region_occupancy_missing_fraction_and_wrong_category_gate(self):
        region=dict(id='grass',bbox=[0,0,64,48],category='grass',reviewed=True,
                    metrics=['semantic'],presence_evidence=True)
        observed=dict(id='grass',reviewed=True,occupancy_reviewed=True,occupancy_category='grass',
                      element_occupancy=np.full((48,64),.25))
        report=self.measure(dict(regions=[observed]),ref=dict(regions=[region]))
        self.assertEqual(report['energies']['semantic']['value'],.75)
        for change in [dict(occupancy_category='water'),dict(occupancy_reviewed=False),dict(reviewed=False)]:
            other=dict(observed,**change)
            self.assertIsNone(self.measure(dict(regions=[other]),ref=dict(regions=[region]))['energies']['semantic']['value'])

    def test_q_zero_additions_preserve_conditioned_scores(self):
        observed=dict(anchors=[anchor()]);base=self.measure(observed,np.zeros_like(self.image))
        ref=deepcopy(self.ref);ref['anchors'].append(dict(anchor('pending'),reviewed=False,reliability=0.,importance=50.))
        changed=self.measure(observed,np.zeros_like(self.image),ref)
        self.assertEqual(base['observation_energy'],changed['observation_energy'])
        self.assertLess(changed['evidence_coverage'],base['evidence_coverage'])
        for key in base['energies']:
            self.assertEqual(base['energies'][key]['value'],changed['energies'][key]['value'])

    def test_missing_relation_endpoint_is_not_another_absence_penalty(self):
        ref=dict(anchors=[anchor(),anchor('b',category='table',box=(32,8,48,24))],
                 relations=[dict(id='on',subject='a',predicate='on',object='b',reviewed=True)])
        report=self.measure(dict(anchors=[ref['anchors'][1]],anchor_verdicts=[verdict('confirmed_missing',reference_id='a')]),ref=ref)
        row=next(r for r in report['metric_records'] if r['id']=='on')
        self.assertIsNone(row['value'])


class CoverageAuditTests(unittest.TestCase):
    def test_union_not_area_sum_and_unreviewed_semantics(self):
        regions=[dict(id='a',mask=np.ones((4,6))*.3,category='floor',reviewed=False),
                 dict(id='b',bbox=[0,0,3,4],reviewed=False)]
        result=coverage_audit(regions,(4,6),np.zeros((4,6),int))
        self.assertEqual(result['dense_pixel_coverage'],1.)
        self.assertEqual(result['candidate_region_coverage'],1.)
        self.assertEqual(result['reviewed_semantic_coverage'],0.)
        self.assertEqual(result['overlap_fraction'],.5)
        self.assertEqual(result['max_mask_multiplicity'],2)

    def test_dense_unknown_partition_and_sparse_candidates_are_distinct(self):
        region=dict(id='patch',bbox=[0,0,3,4],reviewed=False)
        result=coverage_audit([region],(4,6),np.zeros((4,6),int))
        self.assertEqual(result['dense_pixel_coverage'],1.)
        self.assertEqual(result['candidate_region_coverage'],.5)
        self.assertEqual(result['unclassified_pixels'],24)

    def test_boolean_mask_archive_uses_existing_loader_without_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);mask=np.eye(5,dtype=bool)
            np.savez_compressed(p/'masks.npz',piece=mask)
            (p/'candidate.json').write_text(json.dumps(dict(image_size=[5,5],mask_archive='masks.npz',
                reviewed=False,regions=[dict(id='piece',reviewed=False)],anchors=[])))
            d=load_document(p/'candidate.json')
            np.testing.assert_array_equal(d['regions'][0]['mask'],mask)
            self.assertFalse(d['regions'][0]['reviewed'])


class SegmentationResourceTests(unittest.TestCase):
    def test_busy_gpu_is_rejected_before_model_loading(self):
        from scripts.compare_region_segmentation import sam2_candidates
        with tempfile.TemporaryDirectory() as td, patch.dict('os.environ',{'CUDA_VISIBLE_DEVICES':'GPU-test'}), \
                patch('scripts.compare_region_segmentation.subprocess.run',
                      return_value=SimpleNamespace(stdout='GPU-test, 40960, 24000, 60')):
            with self.assertRaisesRegex(RuntimeError,'not idle'):
                sam2_candidates(Path(td),dict(task_id='bw_9064',image_size=[1672,941]),'cuda:0')
            self.assertFalse((Path(td)/'sam2/raw_masks.npz').exists())

    def test_gpu_must_be_explicit_single_uuid(self):
        from scripts.compare_region_segmentation import sam2_candidates
        with tempfile.TemporaryDirectory() as td, patch.dict('os.environ',{'CUDA_VISIBLE_DEVICES':'0,1'}), \
                patch('scripts.compare_region_segmentation.subprocess.run') as query:
            with self.assertRaisesRegex(ValueError,'one idle GPU UUID'):
                sam2_candidates(Path(td),dict(task_id='bw_9064',image_size=[1672,941]),'cuda:0')
            query.assert_not_called()


if __name__=='__main__':unittest.main()
