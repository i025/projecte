"""Offline contracts for the two-request R2 VLM pilot; no real network or keys."""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from PIL import Image
import requests

from scripts import region_atomic_vlm as atomic
from benchmark.vlm import VLMClient


class AtomicVLMTests(unittest.TestCase):
    def answers(self, **changes):
        return {**dict(q1='yes', q2=4, q3='yes'), **changes}

    def packet(self, **changes):
        return dict(status='valid', answers=self.answers(**changes))

    def png_url(self, color):
        buffer=io.BytesIO(); Image.new('RGB', (24, 16), color).save(buffer, format='PNG')
        return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')

    def payload(self):
        return dict(model=atomic.MODEL, max_tokens=atomic.MAX_TOKENS, response_format={'type':'json_object'},
            messages=[dict(role='system', content='old generic client system'), dict(role='user', content=[
                dict(type='text', text=atomic.USER),
                dict(type='image_url', image_url=dict(url=self.png_url('gray'), detail='high')),
                dict(type='image_url', image_url=dict(url=self.png_url('white'), detail='high'))])])

    def assert_non_scoring(self, rows):
        self.assertEqual([r['id'] for r in rows], ['q1','q2','q3'])
        for row in rows:
            self.assertIsNone(row['score']); self.assertIs(row['scorable'], False)
            self.assertIs(row['reviewed'], False)

    def test_exact_json_and_single_whole_fence(self):
        expected=self.answers()
        for raw in (json.dumps(expected), '```json\n'+json.dumps(expected)+'\n```'):
            self.assertEqual(atomic.parse_answers(raw), expected)
        for raw in ('[]', '{}', json.dumps({**expected,'explanation':'extra'}),
                    'prefix '+json.dumps(expected), json.dumps(expected)+' trailing',
                    '{"q1":"no","q1":"yes","q2":4,"q3":"yes"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): atomic.parse_answers(raw)

    def test_strict_categories_counts_and_nonfinite(self):
        for key, bad in [('q1',True),('q1','YES'),('q1','no '),('q1',None),
                         ('q3',False),('q3','above'),('q2',True),('q2',4.0),
                         ('q2',-1),('q2','4'),('q2',None),('q2',float('nan')),
                         ('q2',float('inf'))]:
            with self.subTest(key=key,bad=bad), self.assertRaises(ValueError):
                atomic.parse_answers(json.dumps(self.answers(**{key:bad})))
        self.assertEqual(atomic.parse_answers(json.dumps(self.answers(q2=0)))['q2'],0)
        self.assertEqual(atomic.parse_answers(json.dumps(dict(q1='unknown',q2='unknown',q3='unknown'))),
                         dict(q1='unknown',q2='unknown',q3='unknown'))

    def test_equal_known_answers_are_satisfied_but_not_energy(self):
        rows=atomic.compare_answer_packets(self.packet(), self.packet())
        self.assert_non_scoring(rows)
        self.assertEqual([r['status'] for r in rows], ['satisfied']*3)

    def test_explicit_differences_remain_candidates(self):
        rows=atomic.compare_answer_packets(self.packet(), self.packet(q2=3,q3='no'))
        self.assert_non_scoring(rows)
        self.assertEqual([r['status'] for r in rows], ['satisfied','candidate_violated','candidate_violated'])

    def test_unknown_answers_are_not_missing_or_zero(self):
        rows=atomic.compare_answer_packets(self.packet(q2='unknown'), self.packet(q3='unknown'))
        self.assert_non_scoring(rows)
        self.assertEqual([r['status'] for r in rows], ['satisfied','unknown','unknown'])

    def test_island_presence_prerequisite_suppresses_duplicate_penalties(self):
        for q1 in ('no','unknown'):
            for reference, render in ((self.packet(q1=q1),self.packet()),
                                       (self.packet(),self.packet(q1=q1)),
                                       (self.packet(q1=q1,q2=0),self.packet(q1=q1,q2=0))):
                rows=atomic.compare_answer_packets(reference,render)
                self.assert_non_scoring(rows)
                self.assertEqual([r['status'] for r in rows][1:],['unknown','unknown'])
        rows=atomic.compare_answer_packets(self.packet(),self.packet(q1='no',q2=0,q3='no'))
        self.assertEqual(rows[0]['status'],'candidate_violated')

    def test_one_failed_side_makes_all_questions_unavailable(self):
        missing=dict(status='unavailable',error='synthetic failure')
        for reference,render in ((missing,self.packet()),(self.packet(),missing),(missing,missing)):
            rows=atomic.compare_answer_packets(reference,render)
            self.assert_non_scoring(rows)
            self.assertEqual([r['status'] for r in rows],['unavailable']*3)

    def test_failed_packet_can_explicitly_have_null_answers(self):
        failed=dict(status='unavailable',answers=None,error='synthetic request failure')
        for reference,render in ((failed,self.packet()),(self.packet(),failed),(failed,failed)):
            rows=atomic.compare_answer_packets(reference,render)
            self.assert_non_scoring(rows)
            self.assertEqual([r['status'] for r in rows],['unavailable']*3)

    def test_payload_uses_identical_neutral_protocol_and_two_real_pngs(self):
        payload=self.payload(); before=deepcopy(payload)
        result=atomic.request_payload(payload)
        self.assertEqual(payload,before)
        self.assertEqual(result['messages'][0]['content'],atomic.SYSTEM)
        self.assertEqual(result['messages'][1]['content'][0]['text'],atomic.USER)
        self.assertEqual(result['messages'][1]['content'][1:],payload['messages'][1]['content'][1:])
        self.assertEqual(result['temperature'],.1); self.assertNotIn('response_format',result)
        self.assertEqual(atomic.MODEL,'openai/gpt-6-sol'); self.assertEqual(atomic.MAX_TOKENS,800)

    def test_payload_rejects_wrong_prompt_image_count_and_false_png(self):
        cases=[]
        bad=self.payload();bad['messages'][1]['content'][0]['text']='Reference should contain four stools';cases.append(bad)
        bad=self.payload();bad['messages'][1]['content'].pop();cases.append(bad)
        bad=self.payload();bad['messages'][1]['content'].append(bad['messages'][1]['content'][-1]);cases.append(bad)
        for invalid in ('https://example.invalid/image.png','data:image/jpeg;base64,AAAA',
                        'data:image/png;base64,not-base64!',
                        'data:image/png;base64,'+base64.b64encode(b'not a PNG').decode('ascii')):
            bad=self.payload();bad['messages'][1]['content'][1]['image_url']['url']=invalid;cases.append(bad)
        for payload in cases:
            with self.subTest(payload=payload['messages'][1]['content'][0]),self.assertRaises(ValueError):
                atomic.request_payload(payload)

    def test_reservation_is_exclusive_per_side_and_rejects_bad_side(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            with self.assertRaises(ValueError):atomic.reserve(out,'other')
            self.assertEqual(list(out.iterdir()),[])
            atomic.reserve(out,'reference')
            before=(out/'reference_attempt.json').read_bytes()
            with self.assertRaises(FileExistsError):atomic.reserve(out,'reference')
            self.assertEqual((out/'reference_attempt.json').read_bytes(),before)
            atomic.reserve(out,'render')
            self.assertEqual(len(list(out.glob('*_attempt.json'))),2)

    def test_full_client_ledger_blocks_new_reservation(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'vlm_requests.json').write_text('[{},{}]')
            with self.assertRaises(ValueError):atomic.reserve(out,'reference')
            self.assertFalse((out/'reference_attempt.json').exists())

    def client_fixture(self, out):
        paths=[]
        for name,color in [('full','gray'),('marked','white')]:
            path=out/(name+'.png');Image.new('RGB',(24,16),color).save(path);paths.append(path)
        client=VLMClient(out/'vlm_requests.json',api_key='synthetic-secret-never-log',
            base_url='https://api.ofox.ai/v1',model=atomic.MODEL,request_limit=2)
        return client,paths

    def test_actual_client_two_calls_then_budget_stop_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);client,paths=self.client_fixture(out);seen=[]
            def post(url,*,json,**kwargs):
                seen.append(atomic.request_payload(json))
                self.assertFalse(kwargs['allow_redirects'])
                return SimpleNamespace(status_code=200,json=lambda:dict(model=atomic.MODEL,
                    usage=dict(prompt_tokens=100,completion_tokens=12,total_tokens=112),
                    choices=[dict(finish_reason='stop',message=dict(content=__import__('json').dumps(self.answers())))]))
            for side in ('reference','render'):
                packet=client.call(paths,atomic.USER,'offline:'+side,session=SimpleNamespace(post=post),
                    max_tokens=atomic.MAX_TOKENS,token_parameter='max_tokens',retry_network=False)
                self.assertEqual(atomic.parse_answers(packet['raw_answer']),self.answers())
            blocked=client.call(paths,atomic.USER,'offline:blocked',session=SimpleNamespace(post=post),
                max_tokens=atomic.MAX_TOKENS,token_parameter='max_tokens',retry_network=False)
            self.assertEqual(blocked['error'],'request_budget_exhausted');self.assertEqual(len(seen),2)
            text=(out/'vlm_requests.json').read_text();rows=json.loads(text)
            self.assertEqual(len(rows),2)
            self.assertTrue(all(r['automatic_network_retry_enabled'] is False for r in rows))
            self.assertTrue(all(r['usage']['total_tokens']==112 for r in rows))
            self.assertTrue(all(r['latency_seconds']>=0 for r in rows))
            self.assertNotIn('synthetic-secret-never-log',text);self.assertNotIn('Authorization',text)
            self.assertNotIn('data:image',text);self.assertNotIn('base64',text)

    def test_network_failure_consumes_one_attempt_without_retry_or_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);client,paths=self.client_fixture(out);calls=[]
            def post(*args,**kwargs):
                calls.append(True)
                raise requests.ConnectionError('Authorization: Bearer synthetic-secret-never-log')
            packet=client.call(paths,atomic.USER,'offline:failure',session=SimpleNamespace(post=post),
                max_tokens=atomic.MAX_TOKENS,token_parameter='max_tokens',retry_network=False)
            self.assertEqual(len(calls),1);self.assertEqual(packet['evaluation_status'],'not_evaluable')
            self.assertEqual(packet['error'],'ConnectionError')
            ledger=(out/'vlm_requests.json').read_text()
            self.assertEqual(len(json.loads(ledger)),1)
            self.assertNotIn('synthetic-secret-never-log',ledger);self.assertNotIn('Authorization',ledger)


if __name__=='__main__':unittest.main()
