"""Offline geometry, independent prediction, transport and rendering checks."""
from copy import deepcopy
import ast
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from PIL import Image

from scripts.vlm_direct_grounding import (validate_direct,native_coordinates,masks_for,
    request_payload,prompt_for,reserve,SYSTEM,schema_for,ROOT)
from scripts import vlm_direct_grounding as direct
from scripts.coarse_roi_experiment import raster_polygons
from scripts.region_grounding_experiment import method
from scripts.region_first_generalization import panel_grid
from e_harness.benchmark_evidence import load_document
from benchmark.vlm import VLMClient


class DirectGroundingTests(unittest.TestCase):
    def fixture(self):
        return {'regions':[dict(id='R'+str(i),bbox=[50,50,950,950],polygons=[[[100,100],[800,100],[800,800],[100,800]]]) for i in range(1,5)]}

    def test_cross_scene_prompt_schema_and_geometry_match_original_experiment(self):
        frozen=(ROOT/'results/vlm_direct_grounding_bw0073/source_snapshot/vlm_direct_grounding.py').read_text()
        tree=ast.parse(frozen)
        for name in ('prompt_for','schema_for','cross','intersects','validate_direct',
                     'native_coordinates','masks_for','request_payload'):
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.get_source_segment(frozen,node),inspect.getsource(getattr(direct,name)).strip())
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SYSTEM' for t in n.targets))
        self.assertEqual(ast.literal_eval(assignment.value),SYSTEM)
        saved=json.loads((ROOT/'results/vlm_direct_grounding_bw0073/region_plan.json').read_text())
        self.assertEqual(prompt_for(saved),json.loads((ROOT/'results/vlm_direct_grounding_bw0073/prompt.json').read_text())['user'])

    def test_two_region_plan_keeps_exact_ids_without_inventing_four(self):
        answer=self.fixture();answer['regions']=answer['regions'][:2]
        ids=['R1','R2'];self.assertEqual(validate_direct(answer,ids),answer)
        schema=schema_for(ids)['properties']['regions']
        self.assertEqual(schema['minItems'],2);self.assertEqual(schema['maxItems'],2)
        self.assertEqual(schema['items']['properties']['id']['enum'],ids)
        with self.assertRaises(ValueError):validate_direct(self.fixture(),ids)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rgb=np.full((80,100,3),150,np.uint8)
            masks=[np.asarray(masks_for(native_coordinates(row,[100,80]),(100,80))[1]) for row in answer['regions']]
            method(root,'two_regions',rgb,answer['regions'],np.stack(masks),source='offline two-region fixture')
            self.assertEqual(len(load_document(root/'two_regions/evidence.json')['regions']),2)
            Image.open(root/'two_regions/overlay.png').verify()

    def test_rejected_response_stops_direct_masks_without_partial_salvage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'experiment';out.mkdir()
            rgb=np.full((80,100,3),150,np.uint8);image=Image.fromarray(rgb)
            plan=[dict(id='R'+str(i),name='saved group',location='visible side',content='saved content') for i in (1,2)]
            masks=np.ones((2,80,100),bool)
            method(root,'historical',rgb,plan,masks,source='offline fixture')
            image.save(out/'reference.png')
            direct.save(out/'input.json',dict(task_id='bw_9064',native_image_size=[100,80],historical_evidence=str(root/'historical/evidence.json')))
            direct.save(out/'region_plan.json',dict(regions=plan))
            direct.save(out/'vlm_response.json',dict(status='unavailable',validation_error='Expected 3–8 vertices',raw_answer='rejected fixture',reviewed=False))
            direct.render(out)
            self.assertTrue((out/'comparison.png').exists())
            self.assertTrue((out/'per_region/R1.png').exists())
            self.assertFalse((out/'direct_regions.json').exists())
            self.assertFalse((out/'native_coordinates.json').exists())
            for key in ('B_direct_box','C_direct_polygon','B_direct_box_native','C_direct_polygon_native'):
                self.assertFalse((out/key).exists())
            self.assertIn('未接受部分结果',(out/'comparison.html').read_text())

    def test_complete_ids_exact_fields_and_no_auto_repairs(self):
        answer=self.fixture();before=deepcopy(answer)
        clean=validate_direct(answer,['R1','R2','R3','R4']);self.assertEqual(answer,before)
        self.assertEqual(clean,before)
        for mutation in ('duplicate','missing','extra','range','order','bool','nonfinite'):
            bad=self.fixture()
            if mutation=='duplicate':bad['regions'][1]['id']='R1'
            if mutation=='missing':bad['regions'].pop()
            if mutation=='extra':bad['regions'][0]['confidence']=.99
            if mutation=='range':bad['regions'][0]['bbox'][0]=-1
            if mutation=='order':bad['regions'][0]['bbox']=[500,100,200,400]
            if mutation=='bool':bad['regions'][0]['bbox'][0]=True
            if mutation=='nonfinite':bad['regions'][0]['bbox'][0]=float('inf')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_direct(bad,['R1','R2','R3','R4'])

    def test_degenerate_self_intersecting_and_vertex_limits_are_rejected(self):
        invalid=[[[0,0],[300,300],[600,600]],[[0,0],[500,0],[0,0],[0,500]],
                 [[500,0],[800,1000],[0,400],[1000,400],[200,1000]],
                 [[0,0],[1000,1000]],[[i*100,100] for i in range(9)]]
        for polygon in invalid:
            answer=self.fixture();answer['regions'][0]['polygons']=[polygon]
            with self.assertRaises(ValueError):validate_direct(answer,['R1','R2','R3','R4'])
        answer=self.fixture();answer['regions'][0]['polygons'][0].append([100,100])
        self.assertEqual(validate_direct(answer,['R1','R2','R3','R4']),answer)

    def test_full_extent_native_mapping_and_pixel_center_boundaries(self):
        row=dict(id='R1',bbox=[0,0,1000,1000],polygons=[[[0,0],[1000,0],[1000,1000],[0,1000]]])
        mapped=native_coordinates(row,[111,79]);a,b=masks_for(mapped,(111,79))
        self.assertEqual(mapped['bbox'],[0,0,111,79]);self.assertTrue(np.asarray(a).all());self.assertTrue(np.asarray(b).all())
        row['bbox']=[100.1,200.2,800.3,900.4];row['polygons']=[[[100.1,200.2],[800.3,200.2],[800.3,900.4],[100.1,900.4]]]
        mapped=native_coordinates(row,[111,79]);a,b=masks_for(mapped,(111,79))
        np.testing.assert_array_equal(np.asarray(a),np.asarray(b))
        reference=raster_polygons((79,111),[{'vertices':mapped['polygons'][0]}])
        np.testing.assert_array_equal(np.asarray(b),reference)

    def test_two_disconnected_polygons_do_not_fill_gap_or_define_box(self):
        row=dict(id='R1',bbox=[200,200,700,700],polygons=[[[0,0],[200,0],[200,200],[0,200]],
                  [[800,800],[1000,800],[1000,1000],[800,1000]]])
        mapped=native_coordinates(row,[100,100]);box,polygon=masks_for(mapped,(100,100))
        a,b=np.asarray(box),np.asarray(polygon)
        self.assertTrue(a[50,50]);self.assertFalse(b[50,50]);self.assertTrue(b[5,5] and b[95,95])
        self.assertFalse(np.array_equal(a,b));self.assertEqual(mapped['bbox'],[20,20,70,70])

    def test_unknown_and_independently_unavailable_outputs_remain_empty(self):
        answer=self.fixture();answer['regions'][0].update(bbox=None,polygons=[])
        answer['regions'][1]['bbox']=None
        validate_direct(answer,['R1','R2','R3','R4'])
        a,b=masks_for(native_coordinates(answer['regions'][0],[100,80]),(100,80))
        self.assertIsNone(a.getbbox());self.assertIsNone(b.getbbox())
        with self.assertRaises(ValueError):masks_for(dict(id='x',bbox=[.1,.1,.2,.2],polygons=[]),(100,80))

    def test_native_mask_loader_and_real_visualization_paths_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rgb=np.full((80,100,3),150,np.uint8);rows=self.fixture()['regions'];masks=[]
            for row in rows:
                box,_=masks_for(native_coordinates(row,[100,80]),(100,80));masks.append(np.asarray(box))
            method(root,'direct_box',rgb,rows,np.stack(masks),source='offline fixture')
            loaded=load_document(root/'direct_box/evidence.json')
            self.assertTrue(all(r['reviewed'] is False and r['reliability']==0 for r in loaded['regions']))
            im=Image.fromarray(rgb)
            panel_grid([('Reference',im),('A',im),('B',Image.open(root/'direct_box/overlay.png')),('C',im)],root/'comparison.png')
            Image.open(root/'comparison.png').verify()
            self.assertTrue(all((root/'direct_box'/(r['id']+'_overlay.png')).is_file() for r in rows))

    def test_one_call_contract_uses_saved_plan_and_single_rgb_offline(self):
        plan={'regions':[dict(id='R'+str(i),name='existing group '+str(i),location='visible side',content='saved description '+str(i)) for i in range(1,5)]}
        prompt=prompt_for(plan);answer=self.fixture()
        for row in plan['regions']:self.assertIn(row['content'],prompt)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);Image.new('RGB',(100,80),'gray').save(root/'reference.png');seen=[]
            client=VLMClient(root/'vlm_requests.json',api_key='offline-only',base_url='https://api.ofox.ai/v1',model='openai/gpt-6-sol',request_limit=1)
            def post(url,*,json,**kwargs):
                body=request_payload(json,prompt);seen.append(body)
                self.assertEqual(body['messages'][0]['content'],SYSTEM);self.assertEqual(len(body['messages'][1]['content']),2)
                self.assertEqual(body['temperature'],.1);self.assertEqual(body['max_tokens'],2200);self.assertNotIn('response_format',body)
                return SimpleNamespace(status_code=200,json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':__import__('json').dumps(answer)}}]})
            packet=client.call([root/'reference.png'],prompt,'offline',session=SimpleNamespace(post=post),
                              max_tokens=2200,token_parameter='max_tokens',retry_network=False)
            validate_direct(packet['parsed_answer'],[r['id'] for r in plan['regions']])
            self.assertEqual(len(seen),1)
            with self.assertRaises(ValueError):reserve(root)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);reserve(root)
            with self.assertRaises(FileExistsError):reserve(root)


if __name__=='__main__':unittest.main()
