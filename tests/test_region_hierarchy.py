"""CPU raster fixtures: boundaries, hierarchy, parsing and the existing API gateway."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from e_harness.benchmark_evidence import (merge_slic_regions, validate_region_hierarchy,
    validate_vlm_region_response, load_document, reliability)
from benchmark.vlm import VLMClient


class RegionHierarchyTests(unittest.TestCase):
    def fixture(self):
        labels=np.repeat(np.arange(8)[None,:],12,axis=0)
        image=np.full((12,8,3),120,np.uint8)
        image[:,4:]=[225,20,20]
        return image,labels

    def test_adjacent_only_full_coverage_repeatable_original_unchanged(self):
        image,labels=self.fixture(); before=labels.copy()
        first=merge_slic_regions(image,labels); second=merge_slic_regions(image,labels)
        for level in ('fine','medium','coarse'):
            np.testing.assert_array_equal(first['levels'][level],second['levels'][level])
            self.assertEqual(first['levels'][level].shape,labels.shape)
            self.assertTrue((first['levels'][level]>=0).all())
        np.testing.assert_array_equal(before,labels)
        self.assertEqual(len(np.unique(first['levels']['coarse'])),2)
        for event in first['events']:
            self.assertTrue(any(abs(i-j)==1 for i in event['left'] for j in event['right']))

    def test_anchor_guard_stops_merging_same_colour_object_and_background(self):
        image,labels=self.fixture(); image[:]=120
        mask=labels<4
        result=merge_slic_regions(image,labels,anchor_masks=[mask])
        self.assertEqual(len(np.unique(result['levels']['coarse'])),2)
        self.assertGreater(result['rejected']['anchor_guard'],0)

    def test_feature_recomputed_without_mutating_supplied_features(self):
        image,labels=self.fixture(); feature=np.eye(8); before=feature.copy()
        result=merge_slic_regions(image,labels,features=feature)
        np.testing.assert_array_equal(feature,before)
        self.assertEqual(result['parameters']['weights']['feature'],.25)
        self.assertTrue(all(np.isfinite(e['feature']) for e in result['events']))

    def test_gradient_chain_has_bounded_cluster_colour_radius(self):
        labels=np.repeat(np.arange(16)[None,:],8,axis=0)
        image=np.repeat(np.linspace(10,240,16).astype(np.uint8)[None,:,None],8,axis=0)
        image=np.repeat(image,3,axis=2)
        result=merge_slic_regions(image,labels)
        self.assertGreater(len(np.unique(result['levels']['coarse'])),1)
        self.assertTrue(all(e['colour_radius']<=.34 for e in result['events']))

    def test_hierarchy_references_cycles_and_review_flags(self):
        nodes=[dict(id='p',child_ids=['c'],parent_ids=[],reviewed=False),
               dict(id='c',parent_ids=['p'],child_ids=[],reviewed=False)]
        self.assertTrue(validate_region_hierarchy(nodes)['acyclic'])
        nodes[1]['child_ids']=['p'];nodes[0]['parent_ids']=['c']
        with self.assertRaisesRegex(ValueError,'Cyclic'): validate_region_hierarchy(nodes)
        with self.assertRaises(ValueError): validate_region_hierarchy([dict(id='x',reviewed=True)])
        with self.assertRaises(ValueError): validate_region_hierarchy([dict(id='x',reviewed=False,region_ids=['missing'])])

    def test_group_unknown_and_invalid_ids_fail_without_repair(self):
        answer=dict(groups=[dict(name='books',region_ids=['r1','r3'],reviewed=True)],uncertain_region_ids=['r2'])
        clean=validate_vlm_region_response(answer,'group',['r1','r2','r3'])
        self.assertFalse(clean['groups'][0]['reviewed']);self.assertEqual(clean['groups'][0]['reliability'],0)
        self.assertEqual(answer['groups'][0]['reviewed'],True)
        with self.assertRaises(ValueError): validate_vlm_region_response(answer,'group',['r1','r2'])
        answer['uncertain_region_ids']=['r1']
        with self.assertRaises(ValueError): validate_vlm_region_response(answer,'group',['r1','r2','r3'])
        with self.assertRaises(ValueError): validate_vlm_region_response(dict(groups=['broken item']),'group',['r1'])

    def test_plan_no_bbox_or_confidence_import_unknown_allowed(self):
        answer=dict(regions=[],anchors=[dict(id='a',name='chair',location='left',need_mask=True,
                    bbox=[0,0,4,4],reviewed=True,confidence=.99)],relations=[],uncertain=['background unknown'])
        clean=validate_vlm_region_response(answer,'plan')
        self.assertNotIn('bbox',clean['anchors'][0]);self.assertNotIn('confidence',clean['anchors'][0])
        self.assertEqual(reliability(clean['anchors'][0]),0)
        answer['relations']=[dict(subject='a',predicate='on',object='missing')]
        with self.assertRaises(ValueError): validate_vlm_region_response(answer,'plan')

    def test_existing_loader_preserves_overlapping_masks_without_review(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); Image.fromarray(np.ones((8,12),np.uint8)*255).save(path/'mask.png')
            rows=[dict(id=x,mask='mask.png',reviewed=False,reliability=0.) for x in ['coarse','group']]
            (path/'evidence.json').write_text(json.dumps(dict(image_size=[12,8],regions=rows,anchors=[])))
            doc=load_document(path/'evidence.json')
            self.assertTrue(all(r['mask'].shape==(8,12) and reliability(r)==0 for r in doc['regions']))

    def test_label_map_adapter_level_filter_and_original_coordinates(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); labels=np.arange(24,dtype=np.uint16).reshape(4,6)%3
            Image.fromarray(labels).save(path/'labels.png')
            rows=[dict(id='fine',label_map='labels.png',label_value=2,level='fine',reviewed=False,reliability=0.),
                  dict(id='coarse',label_map='labels.png',label_value=0,level='coarse',reviewed=False,reliability=0.)]
            (path/'evidence.json').write_text(json.dumps(dict(image_size=[6,4],regions=rows,anchors=[])))
            doc=load_document(path/'evidence.json',levels={'fine'})
            self.assertEqual(len(doc['regions']),1)
            np.testing.assert_array_equal(doc['regions'][0]['mask'],labels==2)
            self.assertEqual(reliability(doc['regions'][0]),0.)

    def test_misnested_real_reply_shape_is_rejected_not_salvaged(self):
        answer=dict(regions=[dict(id='r1',name='wall',location='back',kind='continuous'),
                            dict(anchors=[dict(id='a1',name='chair',need_mask=True)])])
        with self.assertRaises(ValueError): validate_vlm_region_response(answer,'plan')

    def test_contradictory_or_cyclic_vlm_relations_rejected(self):
        answer=dict(regions=[dict(id=x,name='surface',location='visible',kind='continuous') for x in ['r1','r2']],
                    anchors=[],relations=[dict(subject='r1',predicate='left_of',object='r2'),
                                          dict(subject='r1',predicate='right_of',object='r2')])
        with self.assertRaises(ValueError): validate_vlm_region_response(answer,'plan')
        answer['relations']=[dict(subject='r1',predicate='contains',object='r2'),
                             dict(subject='r2',predicate='contains',object='r1')]
        with self.assertRaises(ValueError): validate_vlm_region_response(answer,'plan')

    def test_gateway_sends_image_bytes_json_and_enforces_persistent_budget(self):
        import httpx
        seen=[]
        def handle(request):
            body=json.loads(request.content);seen.append(body)
            data=body['messages'][1]['content'][1]['image_url']['url'].split(',',1)[1]
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(data))).size,(13,9))
            return httpx.Response(200,json=dict(choices=[dict(finish_reason='stop',message=dict(content='{"regions":[]}'))],
                                               usage=dict(total_tokens=9)))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);Image.new('RGB',(13,9)).save(path/'rgb.png')
            client=VLMClient(path/'ledger.json',api_key='test-private-key',base_url='https://example.invalid/v1',
                             model='test-vision',request_limit=1,transport=httpx.MockTransport(handle))
            self.assertEqual(client.call([path/'rgb.png'],'JSON only','test',retry_network=False)['evaluation_status'],'answered')
            self.assertEqual(client.call([path/'rgb.png'],'JSON only','test',retry_network=False)['error'],'request_budget_exhausted')
            self.assertNotIn('test-private-key',(path/'ledger.json').read_text())
            self.assertEqual(len(seen),1)

    def test_gateway_failure_is_unavailable_no_retry_or_fabricated_answer(self):
        import httpx
        for status,content in [(401,'private error body'),(200,'not JSON')]:
            def handle(request):
                if status!=200: return httpx.Response(status,text=content)
                return httpx.Response(200,json=dict(choices=[dict(finish_reason='stop',message=dict(content=content))]))
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp);Image.new('RGB',(8,8)).save(path/'rgb.png')
                client=VLMClient(path/'ledger.json',api_key='secret-fixture',base_url='https://example.invalid/v1',
                                 model='fixture',request_limit=4,transport=httpx.MockTransport(handle))
                result=client.call([path/'rgb.png'],'JSON only','failure',retry_network=False)
                self.assertEqual(result['evaluation_status'],'not_evaluable')
                self.assertEqual(len(client.records),1)
                self.assertNotIn('parsed_answer',result)
                self.assertNotIn('private error body',(path/'ledger.json').read_text())


class RegionFirstTests(unittest.TestCase):
    def plan(self,n=2):
        return dict(regions=[dict(id=f'R{i+1}',name=f'区域{i+1}',location='画面某处',content='可见内容') for i in range(n)])

    def test_schema_accepts_only_two_to_five_coarse_descriptions(self):
        from e_harness.benchmark_evidence import validate_region_first_plan,REGION_FIRST_SCHEMA
        for n in (2,3,5):self.assertEqual(validate_region_first_plan(self.plan(n)),self.plan(n))
        for n in (0,1,6):
            with self.assertRaises(ValueError):validate_region_first_plan(self.plan(n))
        self.assertFalse(REGION_FIRST_SCHEMA['additionalProperties'])
        self.assertEqual(REGION_FIRST_SCHEMA['properties']['regions']['minItems'],2)
        self.assertEqual(REGION_FIRST_SCHEMA['properties']['regions']['maxItems'],5)

    def test_rejects_extra_tasks_bbox_confidence_review_flags_and_missing_fields(self):
        from e_harness.benchmark_evidence import validate_region_first_plan
        from copy import deepcopy
        for field in ['anchors','relations','groups']:
            bad=self.plan();bad[field]=[]
            with self.assertRaises(ValueError):validate_region_first_plan(bad)
        for field in ['mask','bbox','confidence','reviewed']:
            bad=self.plan();bad['regions'][0][field]=True
            with self.assertRaises(ValueError):validate_region_first_plan(bad)
        for field in ['id','name','location','content']:
            bad=deepcopy(self.plan());bad['regions'][0].pop(field)
            with self.assertRaises(ValueError):validate_region_first_plan(bad)

    def test_rejects_duplicate_ids_empty_strings_misnested_items_and_bad_json(self):
        from e_harness.benchmark_evidence import validate_region_first_plan
        from benchmark.vlm import parse_json
        for edit in [lambda x:x['regions'][1].update(id='R1'),lambda x:x['regions'][0].update(name='   '),
                     lambda x:x['regions'].__setitem__(0,'bad item'),lambda x:x['regions'][0].update(id='outside')]:
            bad=self.plan();edit(bad)
            with self.assertRaises(ValueError):validate_region_first_plan(bad)
        for raw in ['{"regions":', '{"regions":NaN}', '[]', 'text {"regions":[]}']:
            with self.assertRaises(ValueError):validate_region_first_plan(parse_json(raw))

    def test_real_image_payload_prompts_json_mode_disabled_and_one_attempt_budget(self):
        import httpx
        from types import SimpleNamespace
        from scripts.region_first_pilot import region_request,SYSTEM,USER,MODEL
        seen=[]
        def post(url,*,json,**kwargs):
            body=region_request(json);seen.append(body)
            self.assertNotIn('response_format',body)
            self.assertEqual(body['model'],MODEL)
            self.assertEqual(body['messages'][0]['content'],SYSTEM)
            self.assertEqual(body['messages'][1]['content'][0]['text'],USER)
            self.assertEqual(len(body['messages'][1]['content']),2)
            data=body['messages'][1]['content'][1]['image_url']['url'].split(',',1)[1]
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(data))).size,(19,11))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':__import__('json').dumps(self.plan())}}]})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);Image.new('RGB',(19,11)).save(path/'rgb.png')
            client=VLMClient(path/'ledger.json',api_key='offline-placeholder',base_url='https://example.invalid/v1',model=MODEL,request_limit=1)
            result=client.call([path/'rgb.png'],USER,'test',session=SimpleNamespace(post=post),max_tokens=1500,token_parameter='max_tokens',retry_network=False)
            self.assertEqual(result['evaluation_status'],'answered')
            result=client.call([path/'rgb.png'],USER,'test',session=SimpleNamespace(post=post),max_tokens=1500,retry_network=False)
            self.assertEqual(result['error'],'request_budget_exhausted');self.assertEqual(len(seen),1)

    def test_request_rejects_multiple_images_and_paths_without_mutating_input(self):
        from scripts.region_first_pilot import region_request,USER
        payload=dict(messages=[dict(role='system',content='old'),dict(role='user',content=[dict(type='text',text=USER),
                       dict(type='image_url',image_url=dict(url='data:image/png;base64,AA=='))])],response_format=dict(type='json_object'))
        self.assertNotIn('response_format',region_request(payload));self.assertIn('response_format',payload)
        payload['messages'][1]['content'].append(payload['messages'][1]['content'][1])
        with self.assertRaises(ValueError):region_request(payload)
        payload['messages'][1]['content'].pop();payload['messages'][1]['content'][1]['image_url']['url']='/tmp/image.png'
        with self.assertRaises(ValueError):region_request(payload)


class GroundingConflictTests(unittest.TestCase):
    def test_consensus_is_symmetric_duplicate_invariant_and_never_adds_pixels(self):
        from e_harness.benchmark_evidence import consensus_sam_candidates
        a=np.zeros((9,11),bool);a[1:7,1:7]=True
        b=np.zeros((9,11),bool);b[3:8,3:9]=True
        rows=[dict(id='x',category='monitor',mask=a,method='text'),dict(id='y',category='monitor',mask=b,method='visual')]
        first=consensus_sam_candidates(rows)[0];second=consensus_sam_candidates(rows[::-1]+rows[:1])[0]
        np.testing.assert_array_equal(first['mask'],a&b)
        np.testing.assert_array_equal(first['mask'],second['mask'])
        self.assertFalse(first['reviewed']);self.assertEqual(first['reliability'],0.)
        np.testing.assert_array_equal(rows[0]['mask'],a)

    def test_single_source_is_not_converted_to_absence_when_other_source_missing(self):
        from e_harness.benchmark_evidence import consensus_sam_candidates
        mask=np.ones((5,7),bool)
        row=consensus_sam_candidates([dict(id='x',category='vinyl records',mask=mask,method='visual')])[0]
        self.assertEqual(row['status'],'single_source_unverified')
        np.testing.assert_array_equal(row['mask'],mask)

    def test_conflict_resolution_is_order_invariant_and_never_adds_support(self):
        from e_harness.benchmark_evidence import resolve_region_conflicts
        masks=np.zeros((3,12,16),bool)
        masks[0,1:8,1:11]=True;masks[1,4:11,5:15]=True;masks[2,2:10,7:10]=True
        scores=np.stack([masks[0]*.8,masks[1]*.6,masks[2]*.95])
        result=resolve_region_conflicts(masks,scores)
        order=[2,0,1];other=resolve_region_conflicts(masks[order],scores[order])
        np.testing.assert_array_equal(result['masks'][order],other['masks'])
        np.testing.assert_array_equal(result['unassigned'],other['unassigned'])
        self.assertFalse((result['masks']&~masks).any())
        self.assertTrue((result['masks'].sum(axis=0)<=1).all())
        self.assertTrue((result['unassigned']==~result['masks'].any(axis=0)).all())

    def test_equal_or_weak_conflicts_abstain_not_first_id_wins(self):
        from e_harness.benchmark_evidence import resolve_region_conflicts
        masks=np.ones((2,8,9),bool)
        for scores in [None,np.ones_like(masks,float)*.8,np.stack([masks[0]*.8,masks[1]*.79])]:
            result=resolve_region_conflicts(masks,scores)
            self.assertFalse(result['masks'].any());self.assertTrue(result['unassigned'].all())
            self.assertTrue((result['reason']==3).all())

    def test_unsupported_and_missing_region_are_unassigned_not_zero_error(self):
        from e_harness.benchmark_evidence import resolve_region_conflicts
        masks=np.zeros((2,8,9),bool);masks[0,:3,:3]=True
        result=resolve_region_conflicts(masks,np.zeros(masks.shape))
        self.assertFalse(result['masks'][1].any())
        self.assertTrue((result['reason'][3:]==0).all())
        self.assertEqual(int(result['unassigned'].sum()),8*9-9)

    def test_semantic_specificity_uses_description_not_region_id_or_raw_score(self):
        from e_harness.benchmark_evidence import ground_region_candidates
        rows=[dict(id='Z',name='bookshelf',content='books',location=''),
              dict(id='A',name='monitor',content='monitor beside bookshelf',location='')]
        mask=np.ones((8,9),bool)
        candidates=[dict(id='candidate',category='bookshelf',mask=mask,raw_model_score=.99)]
        union=ground_region_candidates(rows,candidates,(8,9),specific=False)
        filtered=ground_region_candidates(rows,candidates,(8,9),specific=True)
        self.assertTrue(union['masks'].all());self.assertTrue(filtered['masks'][0].all())
        self.assertFalse(filtered['masks'][1].any())
        candidates[0]['raw_model_score']=.001
        again=ground_region_candidates(rows[::-1],candidates,(8,9),specific=True)
        np.testing.assert_array_equal(filtered['masks'][::-1],again['masks'])
        np.testing.assert_array_equal(filtered['scores'][::-1],again['scores'])
        self.assertFalse(again['reviewed'])

    def test_plan_prompts_follow_content_without_object_instance_enumeration(self):
        from e_harness.benchmark_evidence import region_sam3_prompts
        plan=[dict(id='changed_id',name='任意区域',content='书籍、唱片、台灯',location='上方')]
        prompt=region_sam3_prompts(plan)[0]
        self.assertEqual(set(prompt['prompts']),{'books collection','vinyl records','lamp'})
        self.assertNotIn('R1',str(prompt));self.assertFalse(prompt['reviewed'])

    def test_malformed_mask_and_scores_are_rejected(self):
        from e_harness.benchmark_evidence import ground_region_candidates,resolve_region_conflicts
        with self.assertRaises(ValueError):
            ground_region_candidates([dict(id='r',name='monitor',content='',location='')],
                 [dict(id='c',category='monitor',mask=np.ones((3,4)))],(4,3))
        with self.assertRaises(ValueError):resolve_region_conflicts(np.ones((2,3,4)),np.full((2,3,4),np.nan))
        with self.assertRaises(ValueError):resolve_region_conflicts(np.ones((2,3,4)),margin=0)


class CoarseROITests(unittest.TestCase):
    def test_layout_reordering_and_input_nonmutation_with_overlap_retained(self):
        from scripts.coarse_roi_experiment import rectangles, coarse_polygons
        rgb=np.full((90,130,3),100,np.uint8);rgb[45:]=170;rgb[:,70:]+=20
        boxes=[[3,5,95,57],[14,35,119,85],[78,8,128,65]]
        hints=rectangles(rgb.shape[:2],[[10,10,30,25],[20,67,40,80],[110,15,123,31]])
        before=rgb.copy();original_hints=hints.copy();original_boxes=[b[:] for b in boxes]
        for snap in (False,True):
            a,_=coarse_polygons(rgb,boxes,hints,snap=snap)
            permutation=[2,0,1]
            b,_=coarse_polygons(rgb,[boxes[i] for i in permutation],hints[permutation],snap=snap)
            np.testing.assert_array_equal(a,b[np.argsort(permutation)])
            self.assertTrue((a.sum(axis=0)>1).any())
        np.testing.assert_array_equal(rgb,before);np.testing.assert_array_equal(hints,original_hints)
        self.assertEqual(boxes,original_boxes)

    def test_flat_image_keeps_context_not_just_seed_object(self):
        from scripts.coarse_roi_experiment import rectangles, coarse_polygons
        rgb=np.full((40,60,3),120,np.uint8);boxes=[[5,6,53,36]]
        hint=rectangles((40,60),[[23,19,30,24]])
        result,log=coarse_polygons(rgb,boxes,hint,snap=True)
        np.testing.assert_array_equal(result,rectangles((40,60),boxes))
        self.assertGreater(result.sum(),10*hint.sum());self.assertEqual(log['adjusted_boxes'],boxes)

    def test_coincident_windows_retain_ambiguity_without_order_priority(self):
        from scripts.coarse_roi_experiment import rectangles, coarse_polygons
        boxes=[[4,3,24,18]]*2;rgb=np.full((22,31,3),140,np.uint8)
        hints=rectangles((22,31),[[6,4,10,8],[18,13,22,17]])
        masks,log=coarse_polygons(rgb,boxes,hints)
        np.testing.assert_array_equal(masks,rectangles((22,31),boxes))
        np.testing.assert_array_equal(masks,coarse_polygons(rgb,boxes,hints[::-1])[0][::-1])
        self.assertIn('coincident',log['pair_decisions'][0]['reason'])

    def test_edge_snap_cannot_cross_cached_content_guard(self):
        from scripts.coarse_roi_experiment import rectangles, coarse_polygons
        rgb=np.zeros((100,120,3),np.uint8);rgb[15:85,20:100]=255
        boxes=[[5,5,115,95]];hint=rectangles((100,120),[[8,8,112,92]])
        result,_=coarse_polygons(rgb,boxes,hint,snap=True)
        self.assertTrue(result[hint].all())

    def test_polygon_roundtrip_with_notches_disconnected_components_and_holes(self):
        from scripts.coarse_roi_experiment import polygon_loops, raster_polygons
        mask=np.zeros((24,31),bool);mask[2:20,3:28]=True
        mask[3:7,5:10]=False;mask[13:,20:]=False;mask[21:23,28:30]=True
        loops=polygon_loops(mask)
        self.assertTrue(any(p['hole'] for p in loops))
        self.assertLess(sum(len(p['vertices']) for p in loops),30)
        np.testing.assert_array_equal(mask,raster_polygons(mask.shape,loops))
        for m in (np.eye(8,dtype=bool),np.zeros((4,6),bool),np.ones((4,6),bool)):
            np.testing.assert_array_equal(m,raster_polygons(m.shape,polygon_loops(m)))

    def test_audit_allocation_does_not_double_count_or_assign_background(self):
        from scripts.coarse_roi_experiment import rectangles, allocation_shares
        masks=rectangles((20,30),[[0,0,20,15],[10,5,25,20],[9,4,22,17]])
        shares=allocation_shares(masks)
        np.testing.assert_allclose(shares.sum(axis=0),masks.any(axis=0),atol=1e-6)
        np.testing.assert_array_equal(shares[:,~masks.any(axis=0)],0)
        np.testing.assert_array_equal(shares[::-1],allocation_shares(masks[::-1]))

    def test_missing_content_hints_are_recorded_without_borrowing_other_region(self):
        from scripts.coarse_roi_experiment import content_hints
        rows=[dict(id='any',name='工作区',content='显示器、台灯'),
              dict(id='other',name='展示书架',content='书籍'),
              dict(id='last',name='音响区',content='书架上的唱片和唱盘')]
        candidates=[dict(id='c',category='bookshelf',bbox=[0,0,20,20],
                         source_document='cache',prompt_source='historical reference bbox')]
        masks,records=content_hints(rows,candidates,(30,40),[[0,0,20,20]]*3)
        self.assertFalse(masks.any());self.assertIn('lamp',records[0]['unmatched_concepts'])
        self.assertIn('turntable',records[2]['unmatched_concepts'])
        self.assertNotIn('bookshelf',records[2]['unmatched_concepts'])


class RegionGeneralizationTests(unittest.TestCase):
    def test_common_patch_uses_no_neighbors_and_does_not_assign_background(self):
        from scripts.region_first_generalization import interior_patch
        from scripts.coarse_roi_experiment import rectangles
        a=rectangles((100,160),[[5,5,90,95],[70,30,155,90]])
        b=rectangles((100,160),[[8,8,85,93],[75,33,153,88]])
        common=a[0]&b[0]&(a.sum(0)==1)&(b.sum(0)==1)
        box=interior_patch(common);self.assertIsNotNone(box)
        support=rectangles(common.shape,[box])[0]
        self.assertTrue(common[support].all());self.assertFalse((support&a[1]).any())
        self.assertIsNone(interior_patch(np.zeros((20,30),bool)))

    def test_simulation_changes_only_declared_patch_and_strength_is_monotonic(self):
        from scripts.region_first_generalization import perturb
        from e_harness.benchmark_metrics import numerical_errors
        rng=np.random.default_rng(8);rgb=rng.integers(60,190,size=(40,60,3),dtype=np.uint8)
        box=[10,10,30,30];outside=np.ones((40,60),bool);outside[10:30,10:30]=False
        before=rgb.copy();errors=[]
        for strength in (0.,.25,.5,1.):
            changed=perturb(rgb,box,'color',strength)
            np.testing.assert_array_equal(changed[outside],rgb[outside])
            errors.append(numerical_errors(rgb,changed,~outside)[0]['appearance'])
        self.assertEqual(errors[0],0.);self.assertTrue(np.all(np.diff(errors)>0))
        blur=perturb(rgb,box,'blur',1.);np.testing.assert_array_equal(blur[outside],rgb[outside])
        np.testing.assert_array_equal(rgb,before)
        with self.assertRaises(ValueError):perturb(rgb,box,'unknown',1.)

    def test_boundary_touching_roi_patch_stays_in_image_and_edit_is_nonempty(self):
        from scripts.region_first_generalization import interior_patch,perturb
        for common in (np.ones((40,60),bool),np.indices((40,60))[0]<8,
                       np.indices((40,60))[1]<12):
            box=interior_patch(common)
            self.assertIsNotNone(box)
            x0,y0,x1,y1=box
            self.assertTrue(0<=x0<x1<=60 and 0<=y0<y1<=40)
            self.assertTrue(common[y0:y1,x0:x1].all())
            rgb=np.full((40,60,3),120,np.uint8)
            self.assertTrue((perturb(rgb,box,'color',1.)!=rgb).any())
        with self.assertRaises(ValueError):perturb(rgb,[-2,0,4,4],'color',1.)

    def test_global_rgb_l1_dilution_matches_support_area_and_dense_accounting(self):
        from scripts.region_first_generalization import perturb
        from scripts.coarse_roi_experiment import rectangles
        from e_harness.benchmark_metrics import numerical_errors
        rgb=np.full((40,60,3),120,np.uint8);roi=rectangles((40,60),[[10,10,30,30]])[0]
        changed=perturb(rgb,[12,12,20,20],'color',1.)
        local=numerical_errors(rgb,changed,roi)[0]['appearance']
        whole=numerical_errors(rgb,changed,np.ones((40,60),bool))[0]['appearance']
        self.assertAlmostEqual(whole,local*roi.mean())
        masks=rectangles((40,60),[[0,0,30,20],[30,0,60,20],[0,20,30,40],[30,20,60,40]])
        tiles=[numerical_errors(rgb,changed,m)[0]['appearance'] for m in masks]
        self.assertAlmostEqual(np.mean(tiles),whole)
        self.assertGreater(max(tiles),whole)

    def test_one_scale_mapping_for_every_scene_without_coordinate_overrides(self):
        from scripts.region_first_generalization import scale_box
        self.assertEqual(scale_box([20,10,180,90],[200,100],[100,50]),[10,5,90,45])
        self.assertEqual(scale_box([0,0,7952,4333],[7952,4333],[1536,837]),[0,0,1536,837])


if __name__=='__main__': unittest.main()
