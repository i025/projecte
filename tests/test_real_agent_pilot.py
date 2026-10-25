"""M3 adapters use synthetic pixels/Mock historical-shaped records; no model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from e_harness.benchmark_evidence import build_reference
from scripts.real_agent_offline_pilot import candidate, questions_from_prompt, replay_api, audit_rows


class RealAgentPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'historical';self.folder.mkdir()
        self.protocol=dict(system='Independent image answers. JSON only.',
            user='Q1：Is a visible target present?\nQ2：How many?\nQ3：Is it above?')
        schema=dict(type='object',additionalProperties=False,required=['q1','q2','q3'],properties=dict(
            q1=dict(type='string',enum=['yes','no','unknown']),
            q2=dict(anyOf=[dict(type='integer',minimum=0),dict(type='string',enum=['unknown'])]),
            q3=dict(type='string',enum=['yes','no','unknown'])))
        self.write('protocol.json',self.protocol);self.write('schema.json',schema)
        for side,color in (('reference','gray'),('render','white')):
            Image.new('RGB',(64,48),color).save(self.root/(side+'.png'))
            Image.new('RGB',(64,48),color).save(self.folder/(side+'.png'))
        self.pair=dict(scene='test_scene',reference_rgb=str(self.root/'reference.png'),
            render_rgb=str(self.root/'render.png'),common_size=[64,48])
        self.records(dict(q1='yes',q2=4,q3='yes'),dict(q1='yes',q2=2,q3='unknown'),
            ['satisfied','candidate_violated','unknown'])

    def write(self,name,data):
        (self.folder/name).write_text(json.dumps(data))

    def records(self,reference,render,statuses):
        for side,value in (('reference',reference),('render',render)):
            self.write(side+'_answers.json',dict(status='valid',source='real_vlm',
                response=dict(raw_answer=json.dumps(value),model='unit-test-mock',source='vlm_api')))
        self.write('verification_results.json',dict(results=[dict(id=k,region_id='R2',
            group_id='G',energy=e,status=s) for k,e,s in zip(('q1','q2','q3'),
            ('semantic','statistical','spatial'),statuses)]))
        self.write('inputs.json',dict(test_fixture='mock only',common_grid=[64,48]))

    def test_replay_retains_raw_answers_and_deterministic_statuses(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No model')):
            result=replay_api(self.folder,self.pair)
        self.assertEqual([r['status'] for r in result['results']],['satisfied','candidate_violated','unknown'])
        self.assertEqual(result['reference']['raw_answer'],json.dumps(dict(q1='yes',q2=4,q3='yes')))
        self.assertEqual(result['reference']['metadata']['original_backend'],'Ofox API')
        self.assertEqual(result['reference']['metadata']['new_cli_calls'],0)
        self.assertTrue(all(r['value'] is None and not r['reviewed'] and not r['energy_contribution'] for r in result['results']))

    def test_missing_field_preserves_other_comparisons(self):
        self.records(dict(q1='yes',q2=4,q3='yes'),dict(q1='yes',q3='unknown'),
            ['satisfied','unavailable','unknown'])
        result=replay_api(self.folder,self.pair)
        self.assertEqual([r['status'] for r in result['results']],['satisfied','unavailable','unknown'])

    def test_mock_not_promoted_to_real_historical(self):
        document=json.loads((self.folder/'reference_answers.json').read_text());document['source']='mock'
        self.write('reference_answers.json',document)
        with self.assertRaisesRegex(ValueError,'real API'):replay_api(self.folder,self.pair)

    def test_image_lineage_mismatch_rejected(self):
        Image.new('RGB',(64,48),'black').save(self.folder/'render.png')
        with self.assertRaisesRegex(ValueError,'RGB differs'):replay_api(self.folder,self.pair)

    def test_old_verdict_not_silently_changed(self):
        self.records(dict(q1='yes',q2=4,q3='yes'),dict(q1='yes',q2=2,q3='unknown'),
            ['satisfied','satisfied','unknown'])
        with self.assertRaisesRegex(ValueError,'verdict differs'):replay_api(self.folder,self.pair)

    def test_null_optional_mask_removed_without_changing_frozen_candidate(self):
        original=dict(id='A',category='island',bbox=[2,2,20,20],mask=None,reviewed=False,reliability=0.)
        before=deepcopy(original);adapted=candidate(original)
        self.assertEqual(original,before);self.assertNotIn('mask',adapted)
        result=build_reference(np.zeros((48,64,3),np.uint8),dict(image_size=[64,48],anchors=[adapted]))
        self.assertFalse(result['anchors'][0]['reviewed']);self.assertEqual(result['anchors'][0]['reliability'],0.)

    def test_reviewed_evidence_not_downgraded(self):
        with self.assertRaises(ValueError):candidate(dict(reviewed=True,bbox=[1,1,4,4]))

    def test_question_text_extracted_without_answer_example(self):
        text='1. 第一问题？\n2. 第二问题？\n3. 第三问题？\n{"present":"yes"}'
        self.assertEqual(questions_from_prompt(text),['第一问题？','第二问题？','第三问题？'])

    def test_conditional_geometry_does_not_hide_image_only_unknown(self):
        structure=dict(rows=[dict(id='V1',description='Internal divider',reference=dict(value='present'),
            render=dict(value='unknown'),result=dict(status='candidate_structural_layout_mismatch',
                image_only_status='unknown',reason='conditional geometry only'))])
        rows=audit_rows('bw_0074',dict(results=[]),[],structure)
        self.assertEqual(rows[0]['status'],'candidate_structural_layout_mismatch')
        self.assertEqual(rows[0]['image_only_status'],'unknown')
        self.assertFalse(rows[0]['reviewed']);self.assertIsNone(rows[0]['value'])


if __name__=='__main__':unittest.main()
