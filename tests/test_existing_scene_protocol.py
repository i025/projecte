"""Versioned Reference-only evidence protocol; offline fixtures, never model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from e_harness.verification_adapter import (answer_schema, compare_answers, contract,
    parse_answer, replay, validate_diagnostics)
from scripts.reference_vlm_pilot import (EXISTING_SCENE_PROTOCOL, LEGACY_PROTOCOL,
    evidence_from_plan, planning_protocol, verification_protocol, run)
from e_harness.benchmark_batch import planning_options, prepare, generate_scene
from e_harness.benchmark_config import FIXED_T0


def closed(properties):
    return dict(type='object', properties=properties, required=list(properties),
                additionalProperties=False)


def legacy_contract():
    """Independent fixture of the originally published M2 planning input."""
    text=dict(type='string', minLength=1, maxLength=300)
    identifier=dict(type='string', pattern='^[A-Za-z][A-Za-z0-9_]{0,31}$')
    optional=dict(anyOf=[identifier, dict(type='null')])
    box=dict(type='array', items=dict(type='number', minimum=0, maximum=1000),
             minItems=4, maxItems=4)
    schema=closed(dict(
        regions=dict(type='array', minItems=1, maxItems=4, items=closed(dict(
            id=identifier, name=text, description=text, bbox=box))),
        groups=dict(type='array', maxItems=2, items=closed(dict(
            id=identifier, region_id=identifier, name=text, scope=text))),
        anchors=dict(type='array', maxItems=2, items=closed(dict(
            id=identifier, region_id=identifier, category=text, bbox=box))),
        evidence=dict(type='array', minItems=1, maxItems=3, items=closed(dict(
            id=identifier, region_id=identifier, group_id=optional, anchor_id=optional,
            type=dict(type='string', enum=['semantic','spatial','statistical']),
            claim=text, question=text,
            answer_type=dict(type='string', enum=['yes_no_unknown','count_unknown']))))))
    return dict(
        system='你是参考图像证据规划器。只根据当前RGB图像提取少量可见、可验证的评价证据。不要猜测不可见内容。只输出JSON。',
        user='提出1–4个粗粒度功能评价区域，可包含多个物体，背景无需强制覆盖。bbox为0–1000归一化xyxy粗范围。'
        '仅在有必要时提出少量集合Group或显著Anchor，允许groups和anchors为空；Anchor框必须是其自身可见范围。'
        '最多3条原子命题，每条只表达一个明确可见事实，附一个中立、独立看图即可回答的问题。'
        '问题不能透露预期答案，不要求比较图像或总体评分。答案类型为yes_no_unknown或count_unknown（非负整数或unknown）。'
        '使用唯一ASCII ID并正确引用region_id，未用group_id或anchor_id填null。不要枚举全部物体，不输出答案、置信度或推理。',
        schema=schema)


def new_plan():
    return dict(regions=[dict(id='R1',name='Display area',description='Visible display area',
        bbox=[100,100,900,900])], groups=[], anchors=[], evidence=[
        dict(id='E1',region_id='R1',group_id=None,anchor_id=None,type='semantic',
            claim='PRIVATE_REFERENCE_CLAIM',question='Is a display visible?',
            answer_type='yes_no_unknown',categories=[]),
        dict(id='E2',region_id='R1',group_id=None,anchor_id=None,type='statistical',
            claim='PRIVATE_COUNT_CLAIM',question='How many visible display sections are there?',
            answer_type='count_unknown',categories=[]),
        dict(id='E3',region_id='R1',group_id=None,anchor_id=None,type='statistical',
            claim='PRIVATE_CATEGORY_CLAIM',question='What is the main visible arrangement?',
            answer_type='categorical_unknown',categories=['upright','horizontal','mixed'])])


def candidate(plan=None, budget=None):
    protocol=planning_protocol(EXISTING_SCENE_PROTOCOL,evidence_budget=budget)
    packet=replay(json.dumps(new_plan() if plan is None else plan),protocol,source_kind='mock')
    return evidence_from_plan(packet,(200,100),protocol_version=EXISTING_SCENE_PROTOCOL,
                              evidence_budget=budget)


class ExistingSceneProtocolTests(unittest.TestCase):
    def setUp(self):
        self.evidence=candidate()
        self.protocol,self.questions=verification_protocol(self.evidence)

    def pair(self, reference=None, rendered=None):
        first=json.dumps(dict(E1='yes',E2=2,E3='mixed')) if reference is None else reference
        second=json.dumps(dict(E1='yes',E2=2,E3='upright')) if rendered is None else rendered
        return compare_answers(replay(first,self.protocol,source_kind='mock'),
            replay(second,self.protocol,source_kind='mock'),self.questions)

    def test_new_run_freezes_categories_before_both_independent_vqa_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m1=root/'m1';output=root/'new_protocol'
            for side in ('baseline','changed'):
                (m1/side).mkdir(parents=True)
                Image.new('RGB',(64,48),'gray').save(m1/side/'render.png')
            calls=[]
            def fake(image,protocol,*,ledger,request_id,**kwargs):
                calls.append(deepcopy(protocol));ledger.append(dict(image=str(image),request_id=request_id))
                if request_id=='planning_response':value=new_plan()
                else:
                    self.assertEqual((output/'reference_evidence.json').stat().st_mode & 0o777,0o444)
                    value=dict(E1='yes',E2=2,E3='mixed' if request_id=='reference_answers' else 'upright')
                packet=replay(json.dumps(value),protocol,source_kind='mock')
                packet['image_binding']=dict(source_rgb=str(image),image_size=[64,48])
                return packet
            with patch('scripts.reference_vlm_pilot.codex_answer',side_effect=fake),patch(
                    'scripts.reference_vlm_pilot.probe_cli',return_value={'status':'available'}):
                run(m1,output,protocol_version=EXISTING_SCENE_PROTOCOL,evidence_budget=8)
            self.assertEqual(len(calls),3)
            self.assertEqual(calls[0],planning_protocol(EXISTING_SCENE_PROTOCOL,evidence_budget=8))
            self.assertEqual(calls[1],calls[2])
            report=json.loads((output/'report.json').read_text())
            self.assertIsNone(report['energies']['semantic']['value'])
            results=json.loads((output/'verification_results.json').read_text())['results']
            self.assertEqual(results[-1]['status'],'candidate_violated')
            self.assertFalse(results[-1]['energy_contribution'])

    def test_no_observable_evidence_does_not_manufacture_vqa_or_break_rgb(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m1=root/'m1';output=root/'empty'
            for side in ('baseline','changed'):
                (m1/side).mkdir(parents=True)
                Image.new('RGB',(64,48),'gray').save(m1/side/'render.png')
            plan=new_plan();plan['evidence']=[]
            packet=replay(json.dumps(plan),planning_protocol(EXISTING_SCENE_PROTOCOL),source_kind='mock')
            with patch('scripts.reference_vlm_pilot.codex_answer',return_value=packet) as call,patch(
                    'scripts.reference_vlm_pilot.probe_cli',return_value={'status':'available'}):
                run(m1,output,protocol_version=EXISTING_SCENE_PROTOCOL)
            self.assertEqual(call.call_count,1)
            report=json.loads((output/'report.json').read_text())
            self.assertIsNotNone(report['energies']['appearance']['value'])
            self.assertEqual(json.loads((output/'reference_evidence.json').read_text())['atomic_evidence'],[])
            self.assertFalse((output/'reference_answers.json').exists())

    def test_batch_freezes_selected_protocol_and_rejects_switching_on_resume(self):
        config=dict(camera_matrix=FIXED_T0,max_edge=64,agent=dict(model='gpt-6-sol',timeout_seconds=30),
            samples=[dict(id='s1',reference_rgb='unused.png')],
            planning=dict(protocol_version=EXISTING_SCENE_PROTOCOL,evidence_budget=8))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';output=root/'batch'
            Image.new('RGB',(64,48),'gray').save(source)
            config['samples'][0]['reference_rgb']=str(source)
            dataset=prepare(config,output)
            contracts=json.loads((output/'protocols.json').read_text())
            self.assertEqual(contracts['planning'],planning_protocol(EXISTING_SCENE_PROTOCOL,evidence_budget=8))
            seen=[]
            def call(folder,stage,image,protocol,config):
                seen.append((stage,deepcopy(protocol)))
                value=new_plan() if stage=='planning_response' else (
                    dict(blender_python='import bpy\n# retained unexecuted') if stage=='agent_response'
                    else dict(E1='yes',E2=2,E3='mixed'))
                return replay(json.dumps(value),protocol,source_kind='mock')
            with patch('e_harness.benchmark_batch.call_once',side_effect=call):
                generate_scene(dataset['samples'][0],output,dict(config,execution_limits={}))
            self.assertEqual(seen[0][1],contracts['planning'])
            self.assertIn('categorical_unknown',seen[-1][1]['user'])
            self.assertEqual(prepare(config,output),dataset)
            altered=deepcopy(config);altered['planning']['evidence_budget']=9
            with self.assertRaisesRegex(ValueError,'Frozen'):prepare(altered,output)
            for settings in ({'protocol_version':'bad'}, {'expected':'yes'}):
                with self.assertRaises(ValueError):planning_options(dict(config,planning=settings))

    def test_imported_answer_space_metadata_cannot_disagree_with_actual_schema(self):
        for field,value in (('categories',['wrong_space']),('answer_type','yes_no_unknown'),
                            ('protocol_version',LEGACY_PROTOCOL)):
            document=self.pair();document['results'][2][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_diagnostics(document)

    def test_legacy_planning_input_remains_exactly_frozen(self):
        self.assertEqual(LEGACY_PROTOCOL,'m2_legacy')
        self.assertEqual(planning_protocol(),legacy_contract())
        self.assertEqual(planning_protocol(LEGACY_PROTOCOL),legacy_contract())
        self.assertNotEqual(planning_protocol(EXISTING_SCENE_PROTOCOL),legacy_contract())

    def test_legacy_verification_input_remains_exactly_frozen(self):
        plan=new_plan();plan['evidence']=plan['evidence'][:2]
        for row in plan['evidence']:row.pop('categories')
        packet=replay(json.dumps(plan),legacy_contract(),source_kind='mock')
        evidence=evidence_from_plan(packet,(200,100))
        actual,_=verification_protocol(evidence)
        regions=[dict(id='R1',name='Display area',bbox=[20.0,10.0,180.0,90.0])]
        expected=dict(system='你是视觉证据验证器。只根据当前图片回答问题，不猜测不可见内容。'
            'yes表示有充分证据，no表示能够确认不存在或关系不成立，证据不足时用unknown。只输出JSON。',
            user='独立观察当前图片并回答以下中立问题。区域框仅表示固定评价范围（当前图片像素xyxy），'
            '不是其中对象的检测框；必要时可参考完整图像，移出区域不等于不存在。\n区域：'+
            json.dumps(regions,ensure_ascii=False)+'\nE1：Is a display visible? 答案类型：yes_no_unknown\n'
            'E2：How many visible display sections are there? 答案类型：count_unknown'
            '\nyes_no_unknown只用yes/no/unknown；count_unknown只用非负整数或unknown。'
            '无法可靠判断时用unknown。只输出以问题ID为字段的JSON，不解释。',
            schema=closed(dict(E1=dict(type='string',enum=['yes','no','unknown']),
                E2=dict(anyOf=[dict(type='integer',minimum=0),dict(type='string',enum=['unknown'])]))))
        self.assertEqual(actual,expected)

    def test_new_version_and_budget_are_recorded_without_review_promotion(self):
        self.assertEqual(EXISTING_SCENE_PROTOCOL,'existing_scene_v1')
        self.assertEqual(self.evidence['evidence_protocol'],dict(
            version=EXISTING_SCENE_PROTOCOL,evidence_budget=10))
        self.assertFalse(self.evidence['reviewed'])
        for row in self.evidence['regions']+self.evidence['atomic_evidence']:
            self.assertFalse(row['reviewed'])
            self.assertEqual(row['reliability'],0)

    def test_budget_is_a_limit_not_an_evidence_quota(self):
        plan=new_plan();plan['evidence']=[]
        result=candidate(plan,budget=1)
        self.assertEqual(result['atomic_evidence'],[])
        plan['evidence']=new_plan()['evidence']
        with self.assertRaises(ValueError):candidate(plan,budget=2)
        plan['evidence']=[dict(new_plan()['evidence'][0],id='E'+str(i)) for i in range(10)]
        self.assertEqual(len(candidate(plan)['atomic_evidence']),10)
        plan['evidence'].append(dict(plan['evidence'][0],id='E10'))
        with self.assertRaises(ValueError):candidate(plan)

    def test_budget_rejects_noninteger_out_of_range_and_unknown_versions(self):
        for value in (0,11,-1,True,2.5,'3'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                planning_protocol(EXISTING_SCENE_PROTOCOL,evidence_budget=value)
        with self.assertRaises(ValueError):planning_protocol('not_a_protocol')

    def test_one_to_five_regions_without_mandatory_groups(self):
        plan=new_plan();plan['evidence']=[]
        for count in (1,5):
            plan['regions']=[dict(new_plan()['regions'][0],id='R'+str(i)) for i in range(count)]
            self.assertEqual(len(candidate(plan)['regions']),count)
        for count in (0,6):
            plan['regions']=[dict(new_plan()['regions'][0],id='R'+str(i)) for i in range(count)]
            with self.subTest(count=count),self.assertRaises(ValueError):candidate(plan)
        self.assertEqual(self.evidence['groups'],[])

    def test_categories_are_frozen_and_schema_has_abstention_options(self):
        self.assertEqual(self.evidence['atomic_evidence'][2]['categories'],
                         ['upright','horizontal','mixed'])
        definition=self.protocol['schema']['properties']['E3']
        self.assertEqual(definition,dict(type='string',
            enum=['upright','horizontal','mixed','unknown','ambiguous']))
        self.assertEqual(self.questions[2]['answer_type'],'categorical_unknown')
        self.assertEqual(self.questions[2]['categories'],['upright','horizontal','mixed'])
        self.assertIn('upright',self.protocol['user'])

    def test_invalid_categorical_spaces_and_noncategory_options_rejected(self):
        invalid=([],['upright','upright'],[''],[' '],['unknown'],['ambiguous'],[1],
                 ['label'+str(i) for i in range(13)])
        for choices in invalid:
            plan=new_plan();plan['evidence'][2]['categories']=choices
            with self.subTest(choices=choices),self.assertRaises(ValueError):candidate(plan)
        for kind in ('yes_no_unknown','count_unknown'):
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                answer_schema(kind,['unexpected'])

    def test_categorical_categories_are_required_and_not_silently_inferred(self):
        plan=new_plan();plan['evidence'][2].pop('categories')
        with self.assertRaises(ValueError):candidate(plan)
        with self.assertRaises(ValueError):answer_schema('categorical_unknown')

    def test_unknown_answer_type_does_not_silently_become_count(self):
        with self.assertRaises(ValueError):answer_schema('floating_point')
        evidence=deepcopy(self.evidence)
        evidence['atomic_evidence'][0]['answer_type']='floating_point'
        with self.assertRaises(ValueError):verification_protocol(evidence)

    def test_expected_labels_and_claims_are_excluded_from_verification_input(self):
        evidence=deepcopy(self.evidence)
        evidence['construction_expected']='PRIVATE_CONSTRUCTION_LABEL'
        evidence['atomic_evidence'][2].update(expected='PRIVATE_EXPECTED_LABEL',
            reference_answer='PRIVATE_REFERENCE_ANSWER',render_answer='PRIVATE_RENDER_ANSWER')
        protocol,_=verification_protocol(evidence)
        text=json.dumps(protocol,ensure_ascii=False)
        for term in ('PRIVATE_REFERENCE_CLAIM','PRIVATE_COUNT_CLAIM','PRIVATE_CATEGORY_CLAIM',
                     'PRIVATE_CONSTRUCTION_LABEL','PRIVATE_EXPECTED_LABEL',
                     'PRIVATE_REFERENCE_ANSWER','PRIVATE_RENDER_ANSWER'):
            self.assertNotIn(term,text)
        for row in evidence['atomic_evidence']:self.assertIn(row['question'],protocol['user'])
        self.assertEqual(contract(protocol),protocol)

    def test_no_filled_answer_example_in_new_prompts(self):
        for protocol in (planning_protocol(EXISTING_SCENE_PROTOCOL),self.protocol):
            text=protocol['system']+'\n'+protocol['user']
            self.assertNotRegex(text,r'"[^"]+"\s*:\s*"(?:yes|no)"')

    def test_contract_version_or_budget_cannot_be_misassociated(self):
        packet=replay(json.dumps(new_plan()),planning_protocol(EXISTING_SCENE_PROTOCOL),
                      source_kind='mock')
        with self.assertRaises(ValueError):evidence_from_plan(packet,(200,100))
        with self.assertRaises(ValueError):evidence_from_plan(packet,(200,100),
            protocol_version=EXISTING_SCENE_PROTOCOL,evidence_budget=8)

    def test_unknown_and_ambiguous_are_abstentions_without_numeric_penalty(self):
        for first,second in (('mixed','unknown'),('mixed','ambiguous'),
                             ('ambiguous','ambiguous'),('unknown','upright')):
            with self.subTest(first=first,second=second):
                pair=self.pair(json.dumps(dict(E1='yes',E2=2,E3=first)),
                               json.dumps(dict(E1='yes',E2=2,E3=second)))
                row=pair['results'][2]
                self.assertEqual(row['status'],'unknown')
                self.assertIsNone(row['value'])
                self.assertFalse(row['energy_contribution'])

    def test_category_mismatch_is_candidate_only_and_preserves_original_answers(self):
        pair=self.pair()
        row=pair['results'][2]
        self.assertEqual(row['status'],'candidate_violated')
        self.assertEqual(row['reference_answer'],'mixed')
        self.assertEqual(row['render_answer'],'upright')
        self.assertFalse(row['scorable'])
        self.assertFalse(pair['formal_eligible'])

    def test_illegal_or_missing_category_does_not_erase_valid_siblings(self):
        for rendered in (dict(E1='yes',E2=2,E3='not_a_frozen_choice'),dict(E1='yes',E2=2)):
            with self.subTest(rendered=rendered):
                pair=self.pair(rendered=json.dumps(rendered))
                self.assertEqual([r['status'] for r in pair['results']],
                                 ['satisfied','satisfied','unavailable'])

    def test_different_category_space_rejected_even_when_actual_values_overlap(self):
        first=replay('{"E1":"yes","E2":2,"E3":"upright"}',self.protocol,source_kind='mock')
        changed=deepcopy(self.protocol)
        changed['schema']['properties']['E3']['enum'].insert(0,'diagonal')
        second=replay(first['raw_answer'],changed,source_kind='mock')
        with self.assertRaises(ValueError):compare_answers(first,second,self.questions)

    def test_per_answer_raw_json_validation_source_and_review_are_auditable(self):
        raw=' { "E1": "yes", "E2": 2, "E3": "upright" }\n'
        pair=self.pair(rendered=raw)
        detail=pair['results'][2]['render_verification']
        self.assertEqual(detail['raw_json'],raw)
        self.assertEqual(detail['raw_value'],'upright')
        self.assertEqual(detail['validation_status'],'valid')
        self.assertEqual(detail['source'],dict(backend='replay',source_kind='mock',
            model_requested=None,model_observed=None))
        self.assertEqual(detail['human_review'],dict(status='unreviewed',reviewed=False,notes=None))
        self.assertEqual(pair['results'][2]['reference_verification']['raw_value'],'mixed')

    def test_invalid_raw_answer_value_is_preserved_separately_from_validated_value(self):
        raw='{"E1":"yes","E2":2,"E3":"diagonal"}'
        detail=self.pair(rendered=raw)['results'][2]['render_verification']
        self.assertEqual(detail['raw_json'],raw)
        self.assertEqual(detail['raw_value'],'diagonal')
        self.assertEqual(detail['validation_status'],'unavailable')

    def test_import_recomputes_answers_and_cannot_promote_human_review(self):
        pair=self.pair()
        row=pair['results'][2]
        row.update(status='satisfied',reviewed=True,value=0,energy_contribution=True)
        row['render_verification'].update(raw_json='forged',raw_value='mixed')
        row['render_verification']['source']['backend']='forged'
        row['render_verification']['human_review'].update(status='approved',reviewed=True)
        cleaned=validate_diagnostics(pair)['results'][2]
        self.assertEqual(cleaned['status'],'candidate_violated')
        self.assertFalse(cleaned['reviewed'])
        self.assertEqual(cleaned['render_verification']['raw_value'],'upright')
        self.assertEqual(cleaned['render_verification']['source']['backend'],'replay')
        self.assertEqual(cleaned['render_verification']['human_review']['status'],'unreviewed')


if __name__=='__main__':
    unittest.main()
