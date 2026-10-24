"""CPU-only atomic state/gate checks; no actual scene semantic judgments."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from e_harness.benchmark_evidence import build_reference,load_document
from e_harness.benchmark_metrics import compare,aggregate,match_anchors
from scripts.region_atomic_pilot import (reference_seeds,dino_variants,atomic_questions,
    validate_atomic_answer,replay_atomic_answers)


def document():
    return dict(regions=[dict(id=r,bbox=[0,0,32,24],metrics=[],reviewed=False,reliability=0.) for r in ('R2','R3')],
                atomic_evidence=reference_seeds(),reviewed=False)


def answer(key,status,observed,finding='matched'):
    return dict(id=key,status=status,observed=observed,finding=finding,reason='Synthetic fixture, not real Render')


def fixture_anchor(key='a',category='lamp',bbox=(4,4,12,12)):
    return dict(id=key,category=category,bbox=list(bbox),importance=1.,reviewed=True,reliability=1.,source='Synthetic raster oracle')


class AtomicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.doc=document();self.questions=atomic_questions(self.doc)
        self.by_id={q['id']:q for q in self.questions}

    def test_seed_provenance_and_loader(self):
        self.assertEqual(len(self.questions),9)
        self.assertEqual(sum(q['region_id']=='R2' for q in self.questions),5)
        for q in self.questions:
            self.assertFalse(q['reviewed']);self.assertEqual(q['reliability'],0.)
            self.assertEqual(q['source_type'],'human_seeded_provisional')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'reference.json';path.write_text(json.dumps(self.doc))
            self.assertEqual(load_document(path)['atomic_evidence'],self.doc['atomic_evidence'])

    def test_reject_bad_reference_types_ids_and_dependencies(self):
        changes=[lambda d:d['atomic_evidence'].append(deepcopy(d['atomic_evidence'][0])),
            lambda d:d['atomic_evidence'][0].update(region_id='R9'),
            lambda d:d['atomic_evidence'][4].update(expected=True),
            lambda d:d['atomic_evidence'][3].update(requires=['does_not_exist']),
            lambda d:d['atomic_evidence'][3].update(requires=['R2_count'])]
        for change in changes:
            d=deepcopy(self.doc);change(d)
            with self.assertRaises(ValueError):atomic_questions(d)

    def test_no_real_verifier_produces_no_claimed_success(self):
        rows=replay_atomic_answers(self.questions)
        self.assertEqual(sum(r['status']=='unavailable' for r in rows),8)
        self.assertEqual(sum(r['status']=='unknown' for r in rows),1)
        self.assertTrue(all(r['score'] is None and not r['scorable'] for r in rows))

    def test_typed_satisfied_and_violated(self):
        q=self.by_id['R2_count']
        self.assertEqual(validate_atomic_answer(answer(q['id'],'satisfied',4),q)['observed'],4)
        self.assertEqual(validate_atomic_answer(answer(q['id'],'violated',3,'count_mismatch'),q)['status'],'violated')
        for data in [answer(q['id'],'satisfied',3),answer(q['id'],'violated',4),answer(q['id'],'satisfied',True),
                     answer(q['id'],'unknown',3),answer(q['id'],'violated',-1)]:
            with self.assertRaises(ValueError):validate_atomic_answer(data,q)

    def test_unknown_reference_cannot_become_valid_score(self):
        q=self.by_id['R3_hob_count']
        rows=replay_atomic_answers([q],[answer(q['id'],'violated',0)],source_kind='mock')
        self.assertEqual(rows[0]['status'],'unknown');self.assertIsNone(rows[0]['score'])

    def test_conflicting_answers_and_duplicates(self):
        q=self.by_id['R2_island'];yes=answer(q['id'],'satisfied',True)
        out=replay_atomic_answers([q],[yes,answer(q['id'],'violated',False,'semantic_mismatch')],source_kind='mock')
        self.assertEqual(out[0]['status'],'unknown');self.assertIn('Conflicting',out[0]['reason'])
        self.assertEqual(len(replay_atomic_answers([q],[yes,yes],source_kind='mock')),1)

    def test_unvalidated_absence_is_not_confirmed_missing(self):
        q=self.by_id['R2_lamp']
        for finding in ('confirmed_missing','not_detected'):
            out=replay_atomic_answers([q],[answer(q['id'],'violated',False,finding)],source_kind='mock')
            self.assertEqual(out[0]['status'],'unknown');self.assertEqual(out[0]['finding'],'not_detected')

    def test_dependency_conflict_does_not_charge_relation_or_count(self):
        raw=[answer('R2_island','satisfied',True),answer('R2_stools','violated',False,'not_detected'),
            answer('R2_count','violated',0,'count_mismatch'),answer('R2_lamp','violated',False,'confirmed_missing'),
            answer('R2_above','violated',False,'none')]
        rows={r['id']:r for r in replay_atomic_answers(self.questions,raw,source_kind='mock')}
        self.assertEqual(rows['R2_count']['status'],'unknown');self.assertEqual(rows['R2_above']['status'],'unknown')
        self.assertTrue(all(r['score'] is None for r in rows.values()))

    def test_malformed_response_and_extra_confidence_rejected(self):
        q=self.by_id['R2_island'];raw=answer(q['id'],'satisfied',True);raw['confidence']=.999
        out=replay_atomic_answers([q],[raw],source_kind='mock')
        self.assertEqual(out[0]['status'],'unavailable');self.assertIn('Malformed',out[0]['reason'])
        with self.assertRaises(ValueError):replay_atomic_answers([q],[answer('other','satisfied',True)])

    def test_misplaced_is_present_and_existing_matcher_preserves_it(self):
        q=self.by_id['R2_lamp'];row=answer(q['id'],'satisfied',True,'misplaced')
        self.assertEqual(validate_atomic_answer(row,q)['status'],'satisfied')
        sem,_,matches,_,_=match_anchors([fixture_anchor()],dict(anchors=[fixture_anchor('r',bbox=(24,12,31,23))]),(24,32))
        self.assertEqual(matches[0]['status'],'misplaced');self.assertEqual(sem,0.)

    def test_existing_matcher_distinguishes_class_mismatch_and_nondetection(self):
        sem,_,matches,_,_=match_anchors([fixture_anchor()],dict(anchors=[fixture_anchor('r',category='chair')]),(24,32))
        self.assertEqual(matches[0]['status'],'semantic_mismatch');self.assertEqual(sem,1.)
        sem,_,matches,_,_=match_anchors([fixture_anchor()],dict(anchors=[]),(24,32))
        self.assertEqual(matches[0]['status'],'unknown');self.assertIsNone(sem)

    def test_reviewed_synthetic_missing_charged_once_in_existing_core(self):
        a=np.zeros((24,32,3),np.uint8)
        ref=build_reference(a,dict(anchors=[fixture_anchor()]))
        observed=dict(anchors=[],anchor_verdicts=[dict(reference_id='a',status='confirmed_missing',
            reviewed=True,reliability=1.,verification_type='synthetic_oracle',evidence_scope='input_view',source='Synthetic oracle')])
        rows,_=compare(a,a,ref,observed)
        secondary=[r for r in rows if r['level']=='anchor' and r['id']=='a']
        self.assertEqual({r['energy'] for r in secondary},{'spatial','appearance','perceptual'})
        self.assertTrue(all(r['value'] is None for r in secondary))
        self.assertEqual(aggregate(rows)[0]['semantic']['value'],1.)

    def test_unreviewed_questions_never_invoke_verifier_or_score(self):
        a=np.zeros((24,32,3),np.uint8);d=deepcopy(self.doc);d['verification_questions']=self.questions
        def fail(*args):raise AssertionError('Must not invoke a verifier for q=0')
        rows,_=compare(a,a,build_reference(a,d),vlm=fail)
        selected=[r for r in rows if r['id'] in self.by_id]
        self.assertEqual(len(selected),9)
        self.assertTrue(all(r['q']==0 and r['value'] is None for r in selected))
        energies,_=aggregate(selected)
        for name in ('semantic','spatial','statistical'):
            self.assertIsNone(energies[name]['value']);self.assertEqual(energies[name]['coverage'],0.)

    def test_dino_input_diagnostics_keep_shared_interior_and_roi_unchanged(self):
        a=np.full((24,32,3),180,np.uint8);b=np.full_like(a,90)
        mask=np.zeros((24,32),bool);mask[2:20,3:12]=True;mask[14:20,12:26]=True;before=mask.copy()
        variants=dino_variants(a,b,mask)
        np.testing.assert_array_equal(mask,before)
        x0,y0,x1,y1=3,2,26,20;m=mask[y0:y1,x0:x1]
        for name in ('common_gray_crop','bbox_context'):
            x,y,_=variants[name]
            self.assertTrue((x[m]==180).all());self.assertTrue((y[m]==90).all())
        self.assertTrue((variants['common_gray_crop'][0][~m]==127).all())
        self.assertTrue((variants['full_frame_black'][0][~mask]==0).all())


if __name__=='__main__':unittest.main()
