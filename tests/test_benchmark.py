"""CPU metric contracts. Feature stubs below test formulas, never actual DINO quality."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from e_harness.benchmark import evaluate, write_report, render_cpu
from e_harness.benchmark_config import ENERGIES, RENDER
from e_harness.benchmark_evidence import build_reference, load_document, area_mask, vlm_verify
from e_harness.benchmark_metrics import aggregate, compare, distribution_error, match_anchors, record
from e_harness.benchmark_structure import structural_report
from e_harness.prompts import get_system_prompt
from e_harness.runtime.blender_runtime import BlenderRuntime


def anchor(key='a', category='cube', bbox=(8,8,20,20), **kwargs):
    return dict(id=key, category=category, bbox=list(bbox), reviewed=True,
                reliability=1., importance=1., **kwargs)


def inventory(anchors):
    return dict(anchors=anchors, reviewed=True, inventory_complete=True)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.image=np.zeros((48,64,3),np.uint8)
        self.image[8:20,8:20]=[240,50,20]
        self.ref=dict(anchors=[anchor()])

    def test_identity_and_all_five_outputs(self):
        report,_=evaluate(self.image,self.image,self.ref,inventory([anchor()]))
        self.assertEqual(set(report['energies']),set(ENERGIES))
        for k in ['semantic','spatial','appearance','statistical']:
            self.assertAlmostEqual(report['energies'][k]['value'],0.)
        self.assertIsNone(report['energies']['perceptual']['value'])
        self.assertIsNone(report['structural_energy'])

    def test_reference_independence_and_nonmutation(self):
        original=deepcopy(self.ref)
        a=build_reference(self.image,self.ref)
        evaluate(self.image,255-self.image,self.ref,inventory([]))
        b=build_reference(self.image,self.ref)
        self.assertEqual(self.ref,original)
        for x,y in zip(a['regions'],b['regions']):
            np.testing.assert_array_equal(x['mask'],y['mask'])

    def test_deleted_anchor_and_extra(self):
        report,_=evaluate(self.image,np.zeros_like(self.image),self.ref,inventory([]))
        self.assertEqual(report['energies']['semantic']['value'],1.)
        self.assertEqual(report['error_diagnostics']['anchor_matching'][0]['status'],'missing')
        # Extras also require a complete reviewed REFERENCE inventory.
        complete_ref=dict(self.ref,reviewed=True,inventory_complete=True)
        more,_=evaluate(self.image,self.image,complete_ref,inventory([anchor(),anchor('extra',bbox=(40,8,50,20))]))
        self.assertGreater(more['energies']['semantic']['value'],0.)
        self.assertEqual(more['error_diagnostics']['extra_anchors'],['extra'])

    def test_semantic_mismatch(self):
        report,_=evaluate(self.image,self.image,self.ref,inventory([anchor(category='sphere')]))
        self.assertEqual(report['energies']['semantic']['value'],1.)
        self.assertEqual(report['error_diagnostics']['anchor_matching'][0]['status'],'semantic_mismatch')

    def test_optional_mask_and_movement(self):
        baseline,_=evaluate(self.image,self.image,self.ref,inventory([anchor()]))
        moved,_=evaluate(self.image,self.image,self.ref,inventory([anchor(bbox=(36,8,48,20))]))
        self.assertGreater(moved['energies']['spatial']['value'],baseline['energies']['spatial']['value'])
        self.assertNotIn('mask',self.ref['anchors'][0])

    def test_global_assignment_same_class_instances(self):
        refs=[anchor('a',bbox=(0,0,8,8)),anchor('b',bbox=(30,0,38,8))]
        score,pairs,*_=match_anchors(refs,inventory([anchor('x',bbox=(30,0,38,8)),anchor('y',bbox=(0,0,8,8))]),(48,64))
        self.assertEqual(score,0.)
        self.assertEqual(pairs['a']['id'],'y');self.assertEqual(pairs['b']['id'],'x')

    def test_no_inventory_is_unknown_not_missing(self):
        report,_=evaluate(self.image,self.image,self.ref)
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertEqual(report['error_diagnostics']['anchor_matching'][0]['status'],'unknown')
        self.assertEqual(report['uncertainty']['anchor_coverage'],0.)

    def test_candidates_are_never_ground_truth(self):
        ref=deepcopy(self.ref);ref['anchors'][0]['reviewed']=False
        report,_=evaluate(self.image,self.image,ref,inventory([anchor()]))
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertEqual(report['uncertainty']['unreviewed_anchor_count'],1)
        self.assertEqual(report['uncertainty']['anchor_evidence_review_coverage'],0.)

    def test_color_perturbation(self):
        other=self.image.copy();other[:24]=[40,230,100]
        report,_=evaluate(self.image,other)
        self.assertGreater(report['energies']['appearance']['value'],.1)

    def test_repeated_distribution_perturbation(self):
        a=np.zeros_like(self.image);b=a.copy();a[:,::4]=255;b[:24,::4]=255
        report,_=evaluate(a,b)
        self.assertGreater(report['energies']['statistical']['value'],0.)
        self.assertGreater(report['energies']['spatial']['value'],0.)

    def test_same_coordinates_not_best_patch(self):
        report,_=evaluate(self.image,np.roll(self.image,32,axis=1))
        self.assertGreater(report['energies']['appearance']['value'],0.)
        self.assertEqual(len([r for r in report['error_diagnostics']['regions'] if r['level']=='region']),4)

    def test_soft_mask_exclusion_report_roundtrip(self):
        soft=np.ones((48,64))*.6
        ref=dict(regions=[dict(id='grass',mask=soft,description='ground',reviewed=True,
            reliability=.8,metrics=['appearance','statistical'])],anchors=[anchor()])
        report,evidence=evaluate(self.image,self.image,ref,inventory([anchor()]))
        self.assertEqual(evidence['anchor_exclusion'][10,10],1.)
        with tempfile.TemporaryDirectory() as td:
            write_report(td,report,self.image,self.image,evidence)
            loaded=load_document(Path(td)/'reference_evidence.json')
            np.testing.assert_allclose(loaded['regions'][0]['mask'],soft)
            self.assertTrue((Path(td)/'report.html').exists())
            self.assertEqual(json.loads((Path(td)/'report.json').read_text())['observation_energy'],0.)

    def test_unreviewed_regions_preserve_grid(self):
        ref=dict(regions=[dict(id='unknown',bbox=[0,0,64,48],reviewed=False)])
        patches=[r for r in build_reference(self.image,ref)['regions'] if r['id'].startswith('patch_')]
        self.assertEqual(sum(area_mask(r,(48,64)).sum() for r in patches),48*64)

    def test_invalid_evidence_and_image_size(self):
        for row in [dict(bbox=[0,0,100,100]),dict(mask=np.full((48,64),np.nan))]:
            with self.assertRaises(ValueError):area_mask(row,(48,64))
        with self.assertRaises(ValueError):record('appearance','global','bad',float('nan'))
        with self.assertRaises(ValueError):evaluate(self.image,self.image[:20])

    def test_na_without_evidence(self):
        scores,observation=aggregate([])
        self.assertIsNone(observation)
        self.assertTrue(all(e['value'] is None for e in scores.values()))
        self.assertIsNone(structural_report()['energy'])

    def test_adaptive_formula(self):
        rows=[record('semantic','global','s',.2,.5),record('appearance','global','a',.8,1.)]
        scores,value=aggregate(rows)
        self.assertAlmostEqual(value,(.2+.8)/2)
        rows.append(record('perceptual','global','p',None,1.,'model unavailable'))
        changed,new=aggregate(rows)
        self.assertEqual(new,value)
        self.assertIsNone(changed['perceptual']['q'])
        self.assertEqual(changed['perceptual']['coverage'],0.)

    def test_vlm_unavailable_malformed_exception(self):
        self.assertEqual(vlm_verify('on?',None,None,{})['status'],'unavailable')
        for infer in [lambda *args:'garbage',lambda *args:json.dumps(dict(status='valid',score=2,reason='bad'))]:
            self.assertEqual(vlm_verify('on?',None,None,{},infer)['status'],'unavailable')
        def fail(*args):raise RuntimeError('offline')
        self.assertEqual(vlm_verify('on?',None,None,{},fail)['status'],'unavailable')

    def test_vlm_inside_energy(self):
        ref=dict(verification_questions=[dict(id='material',question='Does visible material differ?',energy='appearance',reviewed=True)])
        callback=lambda *args:json.dumps(dict(status='valid',score=1.,reason='Controlled mock verifier'))
        report,_=evaluate(self.image,self.image,ref,vlm=callback)
        self.assertGreater(report['energies']['appearance']['value'],0.)
        self.assertNotIn('vlm_score',report)

    def test_relation_rules_and_complex_na(self):
        ref=dict(anchors=[anchor(),anchor('b',bbox=(30,8,40,20))],relations=[
            dict(id='lr',subject='a',predicate='left_of',object='b',reviewed=True),
            dict(id='on',subject='a',predicate='on',object='b',reviewed=True)])
        report,_=evaluate(self.image,self.image,ref,inventory(ref['anchors']))
        rows={r['id']:r for r in report['metric_records'] if r['level']=='anchor'}
        self.assertEqual(rows['lr']['value'],0.);self.assertIsNone(rows['on']['value'])
        ref['anchors'][0]['reviewed']=False
        report,_=evaluate(self.image,self.image,ref,inventory(ref['anchors']))
        self.assertEqual(next(r for r in report['metric_records'] if r['id']=='lr')['q'],0.)

    def test_dino_formula_unit_stub(self):
        def extractor(images):return np.array([[1.,0.],[0.,1.]])
        rows,_=compare(self.image,self.image,build_reference(self.image),extract=extractor)
        self.assertTrue(all(r['value']==.5 for r in rows if r['energy']=='perceptual'))

    def test_structural_triage_gate(self):
        geometry=dict(collisions=[dict(unit_ids=['a','b'],status='penetration',value=0.)])
        self.assertIsNone(structural_report(geometry)['energy'])
        triage=dict(pairs=[dict(unit_ids=['a','b'],classification='implausible_penetration',reviewed=False)])
        self.assertIsNone(structural_report(geometry,triage)['energy'])
        triage['pairs'][0]['reviewed']=True
        self.assertEqual(structural_report(geometry,triage)['energy'],1.)
        triage['pairs'][0]['classification']='normal_connection'
        self.assertIsNone(structural_report(geometry,triage)['energy'])

    def test_flatness_requires_expectation(self):
        geometry=dict(components=[dict(name='plane',affine_rank=2)])
        self.assertIsNone(structural_report(geometry)['energy'])
        rules=dict(degeneration=[dict(unit_id='a',components=['plane'],reviewed=True,must_enclose_volume=True)])
        self.assertEqual(structural_report(geometry,rules=rules)['energy'],1.)

    def test_support_needs_coordinate_attachment_evidence(self):
        geometry=dict(support_receivers_complete=True,objects=[dict(unit_id='a',support={},floating=dict(status='floating'))])
        rule=dict(unit_id='a',expected=True,reviewed=True,attachment_known_absent=True)
        self.assertIsNone(structural_report(geometry,rules=dict(support=[rule]))['energy'])
        self.assertEqual(structural_report(geometry,rules=dict(up_axis='+Z',support=[rule]))['energy'],1.)

    def test_runtime_still_blocked_and_review_required(self):
        self.assertFalse(BlenderRuntime.isolated)
        with tempfile.TemporaryDirectory() as td:
            runtime=BlenderRuntime(td,'/missing',benchmark_camera=RENDER)
            with self.assertRaises(PermissionError):runtime.process({},Path(td),1)
            with self.assertRaises(PermissionError):render_cpu(Path(td)/'new',blend='/missing')

    def test_fixed_camera_prompt(self):
        text=get_system_prompt(benchmark_camera=RENDER)
        self.assertIn('T0',text);self.assertIn('intrinsics',text)
        self.assertNotIn('Input view means your estimated scene camera',text)

    def test_duplicate_rendered_ids_rejected(self):
        with self.assertRaises(ValueError):
            match_anchors([anchor()],inventory([anchor(),anchor()]),(48,64))

    def test_conflicting_and_inferred_evidence_excluded(self):
        from e_harness.benchmark_evidence import reliability
        self.assertEqual(reliability(dict(reviewed=True,status='inferred',confidence=.99)),0.)
        ref=deepcopy(self.ref);ref['anchors'][0]['conflicted']=True
        report,_=evaluate(self.image,self.image,ref,inventory([anchor()]))
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertTrue(report['uncertainty']['conflicting_evidence'])

    def test_region_occupancy_uses_independent_same_grid_mask(self):
        region=dict(id='ground',bbox=[0,24,64,48],reviewed=True,layout_evidence=True,metrics=['spatial'])
        observed=dict(region,bbox=[0,0,64,24])
        report,_=evaluate(self.image,self.image,dict(regions=[region]),dict(regions=[observed]))
        occupancy=next(r for r in report['metric_records'] if r['id']=='ground:occupancy')
        self.assertEqual(occupancy['value'],1.)
        missing,_=evaluate(self.image,self.image,dict(regions=[region]))
        self.assertIsNone(next(r for r in missing['metric_records'] if r['id']=='ground:occupancy')['value'])

    def test_saved_evidence_can_be_evaluated_again(self):
        ref=dict(regions=[dict(id='soft',mask=np.ones((48,64))*.6,reviewed=True)])
        report,evidence=evaluate(self.image,self.image,ref)
        with tempfile.TemporaryDirectory() as td:
            write_report(td,report,self.image,self.image,evidence)
            loaded=load_document(Path(td)/'reference_evidence.json')
            again,_=evaluate(self.image,self.image,loaded)
            self.assertEqual(again['observation_energy'],0.)

    def test_vlm_dict_and_uncertain_are_preserved(self):
        out=vlm_verify('visible?',None,None,{},lambda *args:dict(status='uncertain',score=.9,reason='Occluded'))
        self.assertEqual(out['status'],'uncertain');self.assertIsNone(out['score'])

    def test_anchor_appearance_at_reference_position(self):
        changed=self.image.copy();changed[8:20,8:20]=[0,240,20]
        report,_=evaluate(self.image,changed,self.ref,inventory([anchor()]))
        row=next(r for r in report['metric_records'] if r['energy']=='appearance' and r['level']=='anchor')
        self.assertGreater(row['value'],0.)

    def test_dino_preserves_full_frame_and_same_coordinates(self):
        observed=[]
        image=self.image.copy();image[:,-1]=[255,0,0]
        def extractor(images):
            observed.append(images)
            return np.array([[1.,0.],[1.,0.]])
        compare(image,image,build_reference(image),extract=extractor)
        self.assertEqual(observed[0][0].shape,(224,224,3))
        self.assertGreater(observed[0][0][:,-1,0].max(),0)
        np.testing.assert_array_equal(*observed[0])

    def test_flat_components_can_form_three_dimensional_assembly(self):
        geometry=dict(components=[dict(name='front',affine_rank=2),dict(name='side',affine_rank=2)],
            objects=[dict(unit_id='box',affine_rank=3,component_names=['front','side'])])
        rules=dict(degeneration=[dict(unit_id='box',components=['front','side'],reviewed=True,must_enclose_volume=True)])
        self.assertIsNone(structural_report(geometry,rules=rules)['energy'])

    def test_unreviewed_render_candidates_prevent_false_absence(self):
        candidate=anchor();candidate['reviewed']=False
        report,_=evaluate(self.image,self.image,self.ref,inventory([candidate]))
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertEqual(report['error_diagnostics']['anchor_matching'][0]['status'],'unknown')

    def test_dino_available_without_semantics_returns_semantic_na(self):
        def extractor(images):return np.array([[1.,0.],[0.,1.]])
        report,_=evaluate(self.image,255-self.image,extract=extractor)
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertAlmostEqual(report['energies']['perceptual']['value'],.5)

    def test_color_does_not_change_anchor_semantics_with_dino(self):
        def extractor(images):return np.array([[1.,0.],[0.,1.]])
        other=self.image.copy();other[8:20,8:20]=[20,240,50]
        report,_=evaluate(self.image,other,self.ref,inventory([anchor()]),extract=extractor)
        self.assertEqual(report['energies']['semantic']['value'],0.)
        self.assertGreater(report['energies']['perceptual']['value'],0.)
        self.assertGreater(report['energies']['appearance']['value'],0.)

    def test_region_semantics_require_reviewed_categories(self):
        region=dict(id='ground',bbox=[0,0,64,48],category='grass',metrics=['semantic'],reviewed=True)
        observed=dict(region)
        equal,_=evaluate(self.image,self.image,dict(regions=[region]),dict(regions=[observed]))
        self.assertEqual(equal['energies']['semantic']['value'],0.)
        observed['category']='water'
        changed,_=evaluate(self.image,self.image,dict(regions=[region]),dict(regions=[observed]))
        self.assertEqual(changed['energies']['semantic']['value'],1.)
        observed['reviewed']=False
        unknown,_=evaluate(self.image,self.image,dict(regions=[region]),dict(regions=[observed]))
        self.assertIsNone(unknown['energies']['semantic']['value'])

    def test_unreviewed_additions_do_not_change_conditional_error(self):
        base,_=evaluate(self.image,255-self.image,self.ref,inventory([anchor()]))
        ref=deepcopy(self.ref)
        extra=anchor('candidate',bbox=(32,24,44,36));extra.update(reviewed=False,importance=100.)
        ref['anchors'].append(extra)
        ref['regions']=[dict(id='unknown_region',bbox=[0,0,64,48],reviewed=False)]
        ref['verification_questions']=[dict(id='unknown_question',energy='appearance',question='Color?',reviewed=False)]
        changed,_=evaluate(self.image,255-self.image,ref,inventory([anchor()]))
        for k in ENERGIES:self.assertEqual(base['energies'][k]['value'],changed['energies'][k]['value'])
        self.assertEqual(base['observation_energy'],changed['observation_energy'])
        self.assertLess(changed['evidence_coverage'],base['evidence_coverage'])
        self.assertGreater(len(changed['uncertainty']['unknown_evidence']),len(base['uncertainty']['unknown_evidence']))

    def test_reliability_and_importance_only_weight_within_energy(self):
        rows=[record('spatial','anchor','bad',.8,.5,aggregation_weight=4.),
              record('spatial','anchor','good',.2,1.),record('appearance','global','a',.4,.1)]
        scores,value=aggregate(rows)
        self.assertAlmostEqual(scores['spatial']['value'],(.8*2+.2)/3)
        self.assertAlmostEqual(value,(scores['spatial']['value']+.4)/2)
        self.assertAlmostEqual(sum(r['within_energy_weight'] for r in scores['spatial']['participating_records']),1.)
        changed,new=aggregate(rows+[record('spatial','anchor','unknown',None,0.,aggregation_weight=100.)])
        self.assertEqual(new,value)
        self.assertEqual(changed['spatial']['coverage'],2/3)
        self.assertEqual(changed['spatial']['eligible_coverage'],1.)

    def test_anchor_importance_increases_spatial_and_appearance_influence(self):
        second=anchor('b',category='sphere',bbox=(40,8,52,20))
        ref=dict(anchors=[anchor(),second])
        changed=self.image.copy();changed[8:20,8:20]=0
        observed=inventory([anchor(bbox=(24,8,36,20)),second])
        low,_=evaluate(self.image,changed,ref,observed)
        ref['anchors'][0]['importance']=8.
        high,_=evaluate(self.image,changed,ref,observed)
        for k in ['spatial','appearance']:
            self.assertGreater(high['energies'][k]['value'],low['energies'][k]['value'])
        rows=[r for r in high['metric_records'] if r['level']=='anchor' and r['id']=='a']
        self.assertTrue(all(r['q']==1. and r['aggregation_weight']==8. for r in rows))

    def test_importance_affects_missing_anchor_f1(self):
        second=anchor('b',category='sphere',bbox=(40,8,52,20))
        ref=dict(anchors=[anchor(),second])
        low,_=evaluate(self.image,self.image,ref,inventory([second]))
        ref['anchors'][0]['importance']=8.
        high,_=evaluate(self.image,self.image,ref,inventory([second]))
        self.assertGreater(high['energies']['semantic']['value'],low['energies']['semantic']['value'])

    def test_multiscale_distribution_preserves_count_and_coverage(self):
        a=np.zeros((64,64));b=a.copy()
        for y,x in [(8,8),(8,48),(48,8),(48,48)]:a[y:y+4,x:x+4]=1
        for y,x in [(24,24),(24,32),(32,24),(32,32)]:b[y:y+4,x:x+4]=1
        self.assertEqual(a.sum(),b.sum())
        value,scales=distribution_error(a,b,np.ones_like(a))
        self.assertGreater(value,0.)
        self.assertEqual(set(scales),{'4','8','16'})
        self.assertTrue(all(0<=v<=1 for v in scales.values()))

    def test_reviewed_occupancy_is_distinct_from_texture_proxy(self):
        a=np.zeros((48,64));a[8:16,8:16]=1
        b=np.roll(a,24,axis=1)
        region=dict(id='repeat',bbox=[0,0,64,48],reviewed=True,occupancy_reviewed=True,
                    element_occupancy=a,metrics=['statistical'])
        other=dict(region,element_occupancy=b)
        report,_=evaluate(self.image,self.image,dict(regions=[region]),dict(regions=[other]))
        rows={r['id']:r for r in report['metric_records'] if r['energy']=='statistical'}
        self.assertEqual(rows['repeat:texture']['value'],0.)
        self.assertGreater(rows['repeat:distribution']['value'],0.)
        self.assertIn('reviewed element occupancy',rows['repeat:distribution']['method'])
        missing,_=evaluate(self.image,self.image,dict(regions=[region]))
        self.assertEqual(missing['energies']['statistical']['coverage'],.5)
        row=next(r for r in missing['metric_records'] if r['id']=='repeat:distribution')
        self.assertIsNone(row['value'])
        self.assertEqual(row['q'],1.)

    def test_edge_only_statistics_are_labelled_proxy(self):
        report,_=evaluate(self.image,np.roll(self.image,16,axis=1))
        distribution=[r for r in report['metric_records'] if r['energy']=='statistical' and r['id'].endswith(':distribution')]
        self.assertTrue(distribution)
        self.assertTrue(all(r['method']=='Multiscale edge distribution proxy' for r in distribution))

    def test_expected_measurements_and_weights_retained_when_unavailable(self):
        scores,_=aggregate([record('perceptual','global','expected',None,.8)])
        score=scores['perceptual']
        self.assertIsNone(score['value']);self.assertEqual(score['coverage'],0.)
        self.assertEqual(score['expected_metrics'],['global:expected'])
        self.assertEqual(score['unavailable_metrics'],['global:expected'])
        self.assertEqual(score['aggregation_weight'],0.)

    def test_unreviewed_statistical_components_remain_expected(self):
        region=dict(id='unknown',bbox=[0,0,64,48],reviewed=False,metrics=['statistical'])
        report,_=evaluate(self.image,self.image,dict(regions=[region]))
        rows=[r for r in report['metric_records'] if r['id'].startswith('unknown:')]
        self.assertEqual({r['id'] for r in rows},{'unknown:texture','unknown:distribution'})
        self.assertTrue(all(r['q']==0 and r['value'] is None for r in rows))
        self.assertEqual(report['observation_status'],'partial')

    def test_occupancy_roundtrip_and_actual_aggregation_weights(self):
        occupancy=np.zeros((48,64));occupancy[8:20,8:20]=1
        region=dict(id='repeat',bbox=[0,0,64,48],reviewed=True,element_occupancy=occupancy,
                    occupancy_reviewed=True,metrics=['statistical'])
        report,evidence=evaluate(self.image,self.image,dict(regions=[region]),dict(regions=[region]))
        with tempfile.TemporaryDirectory() as td:
            write_report(td,report,self.image,self.image,evidence)
            loaded=load_document(Path(td)/'reference_evidence.json')
            np.testing.assert_array_equal(loaded['regions'][0]['element_occupancy'],occupancy)
        weights=[p['observation_weight'] for e in report['energies'].values() for p in e['participating_records']]
        self.assertAlmostEqual(sum(weights),1.)


if __name__=='__main__':unittest.main()
