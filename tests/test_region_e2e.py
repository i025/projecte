"""Offline contract, budget and frozen-grounding checks; never uses real keys."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image

from scripts.region_first_e2e import (SYSTEM,USER,MODEL,region_request,reserve,
    rectangle_from_plan,sanitized,check_frozen)
from e_harness.benchmark_evidence import validate_region_first_plan
from benchmark.vlm import VLMClient


class RegionE2ETests(unittest.TestCase):
    def test_real_client_one_image_payload_and_exact_successful_contract_offline(self):
        plan={'regions':[dict(id='R1',name='visible collection',location='left',content='visible objects'),
                         dict(id='R2',name='another area',location='right',content='other visible objects')]}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);Image.new('RGB',(32,24),(100,140,170)).save(path/'reference.png')
            client=VLMClient(path/'ledger.json',api_key='offline-test-secret',base_url='https://api.ofox.ai/v1',model=MODEL,request_limit=2)
            seen=[]
            def post(url,*,json,**kwargs):
                body=region_request(json);seen.append(body)
                self.assertEqual(body['messages'][0]['content'],SYSTEM)
                self.assertEqual(body['messages'][1]['content'][0]['text'],USER)
                self.assertEqual(len(body['messages'][1]['content']),2)
                self.assertTrue(body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
                self.assertEqual(body['model'],MODEL);self.assertEqual(body['max_tokens'],1500)
                self.assertNotIn('response_format',body);self.assertEqual(kwargs['allow_redirects'],False)
                return SimpleNamespace(status_code=200,json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':__import__('json').dumps(plan)}}]})
            packet=client.call([path/'reference.png'],USER,'offline-only',session=SimpleNamespace(post=post),
                              max_tokens=1500,token_parameter='max_tokens',retry_network=False)
            self.assertEqual(validate_region_first_plan(packet['parsed_answer']),plan)
            self.assertEqual(len(seen),1);self.assertFalse(client.records[0]['automatic_network_retry_enabled'])
            self.assertNotIn('offline-test-secret',(path/'ledger.json').read_text())

    def test_reservations_disallow_same_image_retry_and_total_more_than_two(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'bw_9064').mkdir();(path/'bw_0073').mkdir()
            reserve(path,'bw_9064')
            with self.assertRaises(FileExistsError):reserve(path,'bw_9064')
            (path/'vlm_requests.json').write_text(json.dumps([{},{}]))
            with self.assertRaisesRegex(ValueError,'budget'):reserve(path,'bw_0073')

    def test_cached_predictions_not_historical_prompt_boxes_define_rectangle(self):
        region=dict(id='R1',name='chair area',location='left lower',content='chair')
        pool=[dict(id='c',category='chair',bbox=[10,50,30,70],prompt_bbox=[70,0,99,25])]
        box,record=rectangle_from_plan(region,pool,[100,80])
        self.assertEqual(box,[10,50,30,70]);self.assertEqual(record['matched_candidate_ids'],['c'])
        changed=dict(region,id='R5');self.assertEqual(rectangle_from_plan(changed,pool,[100,80])[0],box)

    def test_unrecognized_vocabulary_and_ambiguous_location_are_explicit_failures(self):
        pool=[dict(id='c',category='cabinets',bbox=[10,20,70,60])]
        box,row=rectangle_from_plan(dict(id='R1',name='cabinets',location='right',content='cabinets'),pool,[100,80])
        self.assertIsNone(box);self.assertEqual(row['status'],'Grounding Failure')
        box,row=rectangle_from_plan(dict(id='R1',name='chair',location='central',content='chair'),
                                   [dict(id='d',category='chair',bbox=[10,20,70,60])],[100,80])
        self.assertIsNone(box)

    def test_response_sanitization_and_frozen_sources(self):
        clean=sanitized(dict(raw='test-secret Bearer another-secret',Authorization='private',
                             usage={'prompt_tokens':3},nested=[{'api_key':'private'}]),'test-secret')
        self.assertNotIn('private',str(clean));self.assertNotIn('test-secret',str(clean))
        self.assertNotIn('another-secret',str(clean));self.assertEqual(clean['usage']['prompt_tokens'],3)
        self.assertEqual(len(check_frozen()),2)


if __name__=='__main__':unittest.main()
