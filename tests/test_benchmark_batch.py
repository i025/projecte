"""CPU synthetic contracts only. No CLI/model/Blender execution in these tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from e_harness.benchmark_batch import (ROOT, agent_protocol, aggregate_scenes, call_once, dino_check,
    generate_scene, load_config, prepare, read, save, write_outputs)
from e_harness.benchmark_offline import run_manifest
from e_harness.verification_adapter import replay
from scripts.reference_vlm_pilot import planning_protocol


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.output=self.root/'out'
        self.config=deepcopy(read(ROOT/'configs/benchmark_v01.yaml'))
        self.config['samples']=self.config['samples'][:2]
        self.config['output']=str(self.output)
        for index,row in enumerate(self.config['samples']):
            path=self.root/f'input{index}.png';Image.new('RGB',(64,48),'silver').save(path)
            row['reference_rgb']=str(path);row.pop('task_document',None)
        self.image=self.root/'input0.png'

    def packet(self,image,protocol,**kwargs):
        if protocol==planning_protocol():
            raw=json.dumps(dict(regions=[dict(id='R1',name='Visible scope',description='Visible scene',bbox=[0,0,1000,1000])],
                groups=[],anchors=[],evidence=[dict(id='E1',region_id='R1',group_id=None,anchor_id=None,
                    type='semantic',claim='Reference-only candidate fact',question='Is a visible target present?',
                    answer_type='yes_no_unknown')]))
        elif 'blender_python' in protocol['schema']['properties']:
            raw=json.dumps(dict(blender_python="import bpy\nraise RuntimeError('MUST NEVER EXECUTE')"))
        else:
            raw='{"E1":"unknown"}'
        p=replay(raw,protocol,source_kind='mock');p.update(model_requested='unit-test-mock',elapsed_seconds=0.,token_usage={})
        return p

    def test_valid_frozen_config_and_policy(self):
        p=self.root/'config.yaml';save(p,self.config)
        self.assertEqual(load_config(p),self.config)
        self.config['camera_matrix'][0][3]=1;save(p,self.config)
        with self.assertRaisesRegex(ValueError,'T0'):load_config(p)

    def test_generation_budget_rejects_extra_rounds(self):
        self.config['agent']['repairs']=1;p=self.root/'config.yaml';save(p,self.config)
        with self.assertRaisesRegex(ValueError,'one bounded'):load_config(p)

    def test_new_experiment_can_configure_another_cli_model(self):
        self.config['agent']['model']='different-cli-model'
        p=self.root/'config.yaml';save(p,self.config)
        self.assertEqual(load_config(p)['agent']['model'],'different-cli-model')

    def test_unique_safe_ids_and_local_rights_required(self):
        p=self.root/'config.yaml'
        for change in ('duplicate','path','rights'):
            c=deepcopy(self.config)
            if change=='duplicate':c['samples'][1]['id']=c['samples'][0]['id']
            if change=='path':c['samples'][0]['id']='../unsafe'
            if change=='rights':c['samples'][0]['local_evaluation_basis']=''
            save(p,c)
            with self.assertRaises(ValueError):load_config(p)

    def test_prepare_freezes_before_model_and_preserves_all_sources(self):
        self.config['samples'][1]['reference_rgb']=str(self.root/'missing.png')
        dataset=prepare(self.config,self.output)
        self.assertEqual(len(dataset['samples']),2)
        self.assertEqual(dataset['samples'][1]['status'],'unavailable')
        self.assertTrue((self.output/'protocols.json').exists())
        self.assertEqual(list(self.output.glob('*/*response.json')),[])
        self.assertEqual(prepare(self.config,self.output),dataset)

    def test_changed_frozen_config_cannot_resume(self):
        prepare(self.config,self.output);self.config['max_edge']=256
        with self.assertRaisesRegex(ValueError,'Frozen'):prepare(self.config,self.output)

    def test_missing_frozen_image_blocks_resume_before_any_model_call(self):
        ds=prepare(self.config,self.output)
        (self.output/ds['samples'][0]['reference_rgb']).unlink()
        with patch('e_harness.benchmark_batch.codex_answer',side_effect=AssertionError('No model')):
            with self.assertRaises(FileNotFoundError):prepare(self.config,self.output)

    def test_optional_dino_failure_is_unavailable_not_fake_score(self):
        ds=prepare(self.config,self.output)
        with patch('e_harness.benchmark_batch.local_dino_extractor',side_effect=KeyError('bad local model config')):
            check=dino_check(self.config,self.output,ds)
        self.assertEqual(check['status'],'unavailable')
        self.assertIsNone(check['energy_value'])

    def test_task_image_link_mismatch_retained_not_guessed(self):
        task=self.root/'task.json';save(task,dict(task_id='wrong',reference_images=[]))
        self.config['samples'][0]['task_document']=str(task)
        ds=prepare(self.config,self.output)
        self.assertEqual(ds['samples'][0]['status'],'unavailable')
        self.assertIn('mismatch',ds['samples'][0]['error'])

    def test_agent_prompt_has_only_common_task_no_reference_answers(self):
        prompt=json.dumps(agent_protocol(self.config))
        for text in ('Reference-only candidate fact','construction_expected','reference_evidence','R1','E1','bw_'):
            self.assertNotIn(text,prompt)
        self.assertIn('camera-to-world T0',prompt)

    def test_interrupted_reservation_never_retries(self):
        folder=self.root/'calls';folder.mkdir();save(folder/'plan.reservation.json',{})
        with patch('e_harness.benchmark_batch.codex_answer',side_effect=AssertionError('No retry')):
            p=call_once(folder,'plan',self.image,planning_protocol(),self.config)
        self.assertEqual(p['status'],'unavailable')

    def test_real_stage_transport_is_bounded_once_and_contract_is_fixed(self):
        folder=self.root/'calls';folder.mkdir()
        with patch('e_harness.benchmark_batch.codex_answer',side_effect=self.packet) as call:
            call_once(folder,'plan',self.image,planning_protocol(),self.config)
            call_once(folder,'plan',self.image,planning_protocol(),self.config)
        self.assertEqual(call.call_count,1)
        self.assertEqual(call.call_args.kwargs['max_requests'],1)
        changed=planning_protocol();changed['user']+='different'
        with self.assertRaisesRegex(ValueError,'contract'):call_once(folder,'plan',self.image,changed,self.config)

    def test_generated_python_never_executes_and_resume_never_repeats_model(self):
        sample=prepare(self.config,self.output)['samples'][0]
        with patch('e_harness.benchmark_batch.codex_answer',side_effect=self.packet) as calls:
            row=generate_scene(sample,self.output,self.config)
            again=generate_scene(sample,self.output,self.config)
        self.assertEqual(calls.call_count,3)
        self.assertEqual(row,again)
        self.assertEqual(row['agent'],'valid_python_unexecuted')
        self.assertEqual(row['reference_verification'],'valid')
        self.assertFalse(row['formal_eligible'])
        self.assertTrue(all(r['value'] is None for r in row['energies'].values()))
        self.assertIn('MUST NEVER EXECUTE',(self.output/sample['id']/'generated_scene.py').read_text())

    def test_failed_planning_does_not_stop_independent_agent_generation(self):
        sample=prepare(self.config,self.output)['samples'][0]
        def answer(image,protocol,**kw):
            if protocol==planning_protocol():return replay('not JSON',protocol,source_kind='mock')
            return self.packet(image,protocol,**kw)
        with patch('e_harness.benchmark_batch.codex_answer',side_effect=answer) as calls:
            row=generate_scene(sample,self.output,self.config)
        self.assertEqual(calls.call_count,2)
        self.assertEqual(row['agent'],'valid_python_unexecuted')
        self.assertEqual(row['planning'],'unavailable')

    def test_failures_and_na_remain_full_denominator(self):
        rows=[dict(agent='valid_python_unexecuted',energies={'appearance':{'value':.4}}),
              dict(agent='unavailable',energies={'appearance':{'value':None}})]
        result=aggregate_scenes(rows)
        self.assertEqual(result['total_samples'],2)
        self.assertEqual(result['energies']['appearance']['availability_fraction'],.5)
        self.assertEqual(result['energies']['appearance']['conditional_mean'],.4)
        self.assertIsNone(result['energies']['semantic']['conditional_mean'])

    def test_output_has_explicit_na_not_zero_error(self):
        ds=prepare(self.config,self.output);rows=[]
        with patch('e_harness.benchmark_batch.codex_answer',side_effect=self.packet):
            for sample in ds['samples']:rows.append(generate_scene(sample,self.output,self.config))
        result=write_outputs(self.config,self.output,ds,rows,{'reasons':['no qualified runtime']},{'status':'unavailable'})
        self.assertEqual(result['model_cost']['attempts'],6)
        self.assertIn('N/A',(self.output/'per_scene_results.csv').read_text())
        self.assertNotIn('reviewed:true',(self.output/'audit_packet.md').read_text())
        self.assertFalse(list(self.output.glob('*.html')))

    def test_explicit_extractor_reuses_existing_energy_without_review_promotion(self):
        manifest=dict(reference_rgb=str(self.image),render_rgb=str(self.image),
            coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='synthetic unit contract only'))
        p=self.root/'manifest.json';save(p,manifest)
        def unit_extractor(images):return np.tile([1.,2.,3.],(len(images),1))
        with self.assertRaisesRegex(ValueError,'provenance'):
            run_manifest(p,self.root/'bad',extract=unit_extractor)
        report=run_manifest(p,self.root/'evaluation',extract=unit_extractor,
            extract_provenance={'source_kind':'unit-test mock, not real DINO'})
        self.assertAlmostEqual(report['energies']['perceptual']['value'],0.,places=12)
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertFalse(report['formal_eligible'])
        self.assertFalse(report['diagnostics']['vlm_verification']['applicable_to_current_pair'])
        save(self.root/'tiny.json',dict(image_size=[64,48],regions=[dict(
            id='tiny',bbox=[0,0,1,1],reviewed=False,reliability=0.,metrics=['perceptual'])]))
        manifest['reference_evidence']='tiny.json';save(p,manifest)
        report=run_manifest(p,self.root/'tiny_evaluation',extract=unit_extractor,
            extract_provenance={'source_kind':'unit-test mock, not real DINO'})
        tiny=next(r for r in report['diagnostics']['fixed_region_measurements'] if r['id']=='tiny')
        self.assertIsNone(tiny['perceptual'])
        self.assertIn('Insufficient',tiny['perceptual_reason'])


if __name__=='__main__':unittest.main()
