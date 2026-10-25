"""Generic diagnostic contracts and M2 orchestration; no actual inference/rendering."""
from copy import deepcopy
import builtins
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from e_harness.benchmark_evidence import build_reference
from e_harness.benchmark_offline import run_manifest
from e_harness.verification_adapter import (answer_packet, codex_answer, compare_answers,
    contract, parse_answer, replay, validate_diagnostics)
from scripts.reference_vlm_pilot import (evidence_from_plan, finish, obj, overview,
    planning_protocol, run, save, verification_protocol)


def plan():
    return dict(regions=[dict(id='R1',name='Visible foreground',description='A coarse visible area',
        bbox=[10,10,950,950])],groups=[],anchors=[],evidence=[
        dict(id='E1',region_id='R1',group_id=None,anchor_id=None,type='semantic',
            claim='An observable form is present',question='Is a solid form visible?',answer_type='yes_no_unknown'),
        dict(id='E2',region_id='R1',group_id=None,anchor_id=None,type='statistical',
            claim='There are two forms',question='How many solid forms are visible?',answer_type='count_unknown')])


def packet(document, protocol):
    return replay(json.dumps(document),protocol,source_kind='mock')


def evidence(document=None):
    return evidence_from_plan(packet(document or plan(),planning_protocol()),(64,48))


class ReferenceVLMPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.image=self.root/'input.png';Image.new('RGB',(64,48),'gray').save(self.image)
        self.evidence=evidence();self.protocol,self.questions=verification_protocol(self.evidence)

    def pair(self, first=None, second=None):
        return compare_answers(packet(first or dict(E1='yes',E2=2),self.protocol),
            packet(second or dict(E1='no',E2=2),self.protocol),self.questions)

    def test_generic_schema_reuses_deterministic_states(self):
        pair=self.pair()
        self.assertEqual([r['status'] for r in pair['results']],['candidate_violated','satisfied'])
        self.assertTrue(all(r['value'] is None and not r['reviewed'] for r in pair['results']))
        self.assertEqual(validate_diagnostics(pair)['results'],pair['results'])

    def test_unknown_never_numeric(self):
        pair=self.pair(second=dict(E1='unknown',E2='unknown'))
        self.assertEqual([r['status'] for r in pair['results']],['unknown']*2)
        self.assertTrue(all(r['value'] is None for r in pair['results']))

    def test_missing_count_preserves_other_field(self):
        pair=self.pair(second=dict(E1='yes'))
        self.assertEqual([r['status'] for r in pair['results']],['satisfied','unavailable'])

    def test_illegal_answers_do_not_become_zero(self):
        for value in (True,-1,1.5,[],{}):
            with self.subTest(value=value):
                pair=self.pair(second=dict(E1='yes',E2=value))
                self.assertEqual(pair['results'][1]['status'],'unavailable')

    def test_malformed_generic_json_and_duplicate_keys(self):
        for raw in ('not JSON','[]','{"E1":"yes","E1":"no"}','{"E2":NaN}'):
            with self.subTest(raw=raw):
                self.assertEqual(parse_answer(raw,self.protocol['schema'])['status'],'unavailable')

    def test_schema_references_invalid_types_and_open_objects_rejected(self):
        for schema in ({'$ref':'https://example.invalid/schema'},dict(type='mistake'),
                       dict(type='object',properties={'E':{}},required=['E'])):
            with self.subTest(schema=schema),self.assertRaises(ValueError):
                contract(dict(self.protocol,schema=schema))

    def test_planner_schema_has_no_fixture_vocabulary_or_answers(self):
        prompt=json.dumps(planning_protocol(),ensure_ascii=False).lower()
        for term in ('changed','baseline','blender','fixture','construction_expected','red','cube'):
            self.assertIsNone(re.search(r'\b'+term+r'\b',prompt))

    def test_plan_loaded_by_existing_core_without_optional_group(self):
        doc=build_reference(np.zeros((48,64,3),np.uint8),self.evidence)
        self.assertEqual(doc['groups'],[])
        self.assertEqual(len(doc['regions']),5)  # candidate plus existing dense grid
        self.assertTrue(all(not row['reviewed'] for row in self.evidence['regions']))

    def test_optional_group_anchor_links_preserved(self):
        p=plan();p['groups']=[dict(id='G1',region_id='R1',name='Forms',scope='Visible forms')]
        p['anchors']=[dict(id='A1',region_id='R1',category='form',bbox=[50,50,500,500])]
        p['evidence'][0].update(group_id='G1',anchor_id='A1')
        doc=evidence(p);protocol,questions=verification_protocol(doc)
        pair=compare_answers(packet(dict(E1='yes',E2=2),protocol),packet(dict(E1='yes',E2=2),protocol),questions)
        self.assertEqual(pair['results'][0]['group_id'],'G1')
        self.assertEqual(pair['results'][0]['anchor_id'],'A1')

    def test_invalid_plan_ids_links_boxes_rejected_not_repaired(self):
        for change in ('duplicate','region','group','reversed','outside','too_many'):
            p=plan()
            if change=='duplicate':p['evidence'][0]['id']='R1'
            if change=='region':p['evidence'][0]['region_id']='missing'
            if change=='group':p['evidence'][0]['group_id']='missing'
            if change=='reversed':p['regions'][0]['bbox']=[500,0,100,1000]
            if change=='outside':p['regions'][0]['bbox'][0]=-1
            if change=='too_many':p['evidence']*=2
            with self.subTest(change=change),self.assertRaises(ValueError):evidence(p)

    def test_no_reference_claim_answer_leaked_into_vqa(self):
        self.assertNotIn('There are two forms',self.protocol['user'])
        self.assertNotIn('An observable form',self.protocol['user'])
        self.assertNotIn('claim',self.protocol['user'])
        self.assertEqual(contract(self.protocol),self.protocol)

    def test_image_pair_mismatch_fails_only_diagnostic(self):
        pair=self.pair();pair['image_pair']=dict(reference_rgb=str(self.image),render_rgb='/wrong.png')
        save(self.root/'verification.json',pair)
        manifest=dict(reference_rgb=str(self.image),render_rgb=str(self.image),
            coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='synthetic same grid'),
            vlm_verification='verification.json')
        save(self.root/'manifest.json',manifest)
        report=run_manifest(self.root/'manifest.json',self.root/'evaluation')
        self.assertEqual(report['diagnostics']['vlm_verification']['status'],'unavailable')
        self.assertIsNotNone(report['energies']['appearance']['value'])
        self.assertIsNone(report['energies']['semantic']['value'])

    def test_missing_optional_validator_dependency_keeps_rgb(self):
        pair=self.pair();save(self.root/'verification.json',pair)
        manifest=dict(reference_rgb=str(self.image),render_rgb=str(self.image),
            coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='same grid'),
            vlm_verification='verification.json')
        save(self.root/'manifest.json',manifest)
        original=builtins.__import__
        def unavailable(name,*args,**kwargs):
            if name=='verification_adapter':raise ImportError('Optional validator dependency unavailable')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=unavailable):
            report=run_manifest(self.root/'manifest.json',self.root/'no-validator')
        self.assertEqual(report['diagnostics']['vlm_verification']['status'],'unavailable')
        self.assertIsNotNone(report['energies']['appearance']['value'])

    def test_failed_side_with_raw_output_is_unavailable(self):
        pair=self.pair();pair['render']['status']='unavailable'
        self.assertEqual([r['status'] for r in validate_diagnostics(pair)['results']],['unavailable']*2)

    def test_planning_objects_cannot_be_compared_as_atomic_answers(self):
        p=packet(plan(),planning_protocol())
        with self.assertRaisesRegex(ValueError,'atomic'):
            compare_answers(p,p,[dict(evidence_id='x',field='regions',question='test')])

    def test_three_unique_task_budget_no_retry_same_image_different_task(self):
        ledger=[]
        def process(args,**kwargs):
            Path(args[args.index('--output-last-message')+1]).write_text('{"E1":"yes","E2":2}')
            return 0,'',''
        with patch('shutil.which',return_value='/codex'),patch(
                'e_harness.verification_adapter.run_process',side_effect=process) as mocked:
            for stage in ('planning','reference','changed'):
                self.assertEqual(codex_answer(self.image,self.protocol,ledger=ledger,
                    request_id=stage,max_requests=3)['status'],'valid')
            denied=codex_answer(self.image,self.protocol,ledger=ledger,request_id='fourth',max_requests=3)
            self.assertFalse(denied['request_submitted'])
        self.assertEqual(mocked.call_count,3)

    def test_duplicate_stage_and_timeout_reserve_budget(self):
        ledger=[]
        with patch('shutil.which',return_value='/codex'),patch(
                'e_harness.verification_adapter.run_process',side_effect=subprocess.TimeoutExpired('codex',1)) as mocked:
            first=codex_answer(self.image,self.protocol,ledger=ledger,request_id='planning',max_requests=3)
            second=codex_answer(self.image,self.protocol,ledger=ledger,request_id='planning',max_requests=3)
        self.assertEqual(mocked.call_count,1)
        self.assertEqual(first['status'],'unavailable');self.assertFalse(second['request_submitted'])

    def test_model_unavailable_keeps_other_observations(self):
        with patch('shutil.which',return_value=None):
            result=codex_answer(self.image,self.protocol,ledger=[])
        self.assertEqual(result['status'],'unavailable')
        pair=compare_answers(packet(dict(E1='yes',E2=2),self.protocol),result,self.questions)
        self.assertEqual([r['status'] for r in pair['results']],['unavailable']*2)

    def test_full_mock_orchestration_without_models_or_geometry(self):
        m1=self.root/'m1'
        for side in ('baseline','changed'):
            (m1/side).mkdir(parents=True)
            Image.new('RGB',(64,48),'gray').save(m1/side/'render.png')
        output=self.root/'m2'
        calls=[]
        def fake(image,protocol,*,ledger,request_id,**kwargs):
            calls.append(request_id); ledger.append(dict(image=str(image),request_id=request_id))
            value=plan() if len(calls)==1 else dict(E1='yes',E2=2)
            if len(calls)>1:
                self.assertTrue((output/'reference_evidence.json').is_file())
                self.assertEqual(read_only_mode(output/'reference_evidence.json'),0o444)
            result=packet(value,protocol)
            result['image_binding']=dict(source_rgb=str(image),image_size=[64,48])
            return result
        with patch('scripts.reference_vlm_pilot.codex_answer',side_effect=fake),patch(
                'scripts.reference_vlm_pilot.probe_cli',return_value={'status':'available'}):
            run(m1,output)
        report=json.loads((output/'report.json').read_text())
        self.assertEqual(calls,['planning_response','reference_answers','render_answers'])
        self.assertIsNotNone(report['energies']['appearance']['value'])
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertEqual(report['diagnostics']['vlm_verification']['status'],'available')
        self.assertFalse(report['formal_eligible'])
        self.assertEqual(report['provenance']['blender_executions'],0)
        with self.assertRaises(FileExistsError):run(m1,output)

    def test_unavailable_planning_retains_rgb_without_inventing_evidence(self):
        m1=self.root/'m1'
        for side in ('baseline','changed'):
            (m1/side).mkdir(parents=True)
            Image.new('RGB',(64,48),'gray').save(m1/side/'render.png')
        output=self.root/'failed'
        with patch('scripts.reference_vlm_pilot.probe_cli',return_value={'status':'unavailable'}),patch(
                'scripts.reference_vlm_pilot.codex_answer',side_effect=AssertionError('No calls')):
            run(m1,output)
        report=json.loads((output/'report.json').read_text())
        self.assertIsNotNone(report['energies']['appearance']['value'])
        self.assertFalse((output/'reference_evidence.json').exists())
        self.assertEqual(json.loads((output/'verification_results.json').read_text())['status'],'unavailable')


def read_only_mode(path):
    return path.stat().st_mode & 0o777


if __name__=='__main__':unittest.main()
