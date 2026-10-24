"""CPU Oracle files test associations/abstention; these tests do not launch Blender."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from e_harness.benchmark_config import FIXED_T0, RENDER, ROOT, write_json
from e_harness.benchmark_offline import run_manifest
from e_harness.benchmark_trusted import freeze_reference, verify_execution
from e_harness.verification_adapter import compare_answers, replay
from scripts.group_abstention_calibration import frozen_protocol


class TrustedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'fixture';self.folder.mkdir()
        self.config=deepcopy(RENDER);self.config['resolution']=[32,24]
        shape=(24,32);ids=np.zeros(shape,np.uint16);ids[8:20,3:10]=1;ids[10:20,20:28]=2
        self.ids=ids
        Image.fromarray(np.full(shape+(3,),90,np.uint8)).save(self.folder/'render.png')
        np.save(self.folder/'object_id.npy',ids);np.save(self.folder/'component_id.npy',ids)
        depth=np.full(shape,np.nan,np.float32);depth[ids>0]=6.
        np.save(self.folder/'depth_camera_z.npy',depth)
        np.save(self.folder/'normal_world.npy',np.zeros(shape+(3,),np.float32))
        (self.folder/'render_masks').mkdir()
        for i,key in enumerate(('anchor','other'),1):
            Image.fromarray((ids==i).astype('uint8')*255).save(self.folder/'render_masks'/(key+'.png'))
        camera=dict(matrix_world=FIXED_T0,type='PERSP',lens_mm=42)
        actual=dict(cycles_device='CPU',engine='CYCLES',samples=8,percentage=100,
            resolution_x=32,resolution_y=24,use_border=False,use_crop_to_border=False)
        self.meta=dict(camera=camera,device='CPU',threads=2,samples=8,image_size=[32,24],
            intrinsics_pixels=[[32,0,16],[0,32,12],[0,0,1]],valid_depth_pixel_count=int((ids>0).sum()),
            semantic_ids={'1':'anchor','2':'other'},components=[dict(name=k) for k in ('anchor','other')],
            position_reprojection_max_error_pixels=0.)
        self.execution=dict(source_kind='source_controlled_fixture',fixture='baseline',
            camera_before_export=camera,camera_after_export=camera,render_after_export=actual,
            autoexec_enabled=False,agent_python_executed=False,geometry_from_same_scene=True,blender_version='synthetic_oracle')
        write_json(self.folder/'export_metadata.json',self.meta)
        write_json(self.folder/'execution.json',self.execution)
        write_json(self.folder/'job.json',dict(fixture='baseline',blend=None,output=str(self.folder),render=self.config))
        write_json(self.folder/'geometry.json',dict(components=[dict(name=k) for k in ('anchor','other')]))
        self.launch=dict(success=True,cleanup_complete=True,returncode=0,
            command=['--factory-startup','--disable-autoexec','--python',str(ROOT/'e_harness/runtime/benchmark_blender.py')])

    def verify(self):return verify_execution(self.folder,'baseline',self.config,self.launch)

    def test_complete_same_run_associations_but_no_formal_grade(self):
        result=self.verify()
        self.assertTrue(result['geometry_available'])
        self.assertTrue(result['pose_matches_T0'])
        self.assertFalse(result['formal_eligible'])
        self.assertFalse(result['reviewed'])

    def test_failed_cleanup_stops_before_evaluation(self):
        self.launch['cleanup_complete']=False
        with self.assertRaisesRegex(ValueError,'cleanup'):self.verify()

    def test_other_helper_not_trusted(self):
        self.launch['command'][-1]='/some/other.py'
        with self.assertRaisesRegex(ValueError,'approved'):self.verify()

    def test_scene_and_job_must_match_current_controller(self):
        job=json.loads((self.folder/'job.json').read_text());job['fixture']='moved'
        write_json(self.folder/'job.json',job)
        with self.assertRaisesRegex(ValueError,'Actual job'):self.verify()

    def test_matching_boolean_cannot_replace_actual_t0(self):
        self.meta['camera']=dict(self.meta['camera'],matrix_world=deepcopy(FIXED_T0))
        self.meta['camera']['matrix_world'][2][3]=1.5
        self.meta['fixed_extrinsics_enforced']=True
        write_json(self.folder/'export_metadata.json',self.meta)
        with self.assertRaisesRegex(ValueError,'T0'):self.verify()

    def test_rgb_and_depth_grids_must_match(self):
        np.save(self.folder/'depth_camera_z.npy',np.ones((12,16),np.float32))
        with self.assertRaisesRegex(ValueError,'RGB grid'):self.verify()

    def test_mask_cannot_be_bbox_proxy_or_other_id(self):
        Image.new('L',(32,24),255).save(self.folder/'render_masks/anchor.png')
        with self.assertRaisesRegex(ValueError,'ID PNG'):self.verify()

    def test_geometry_cannot_come_from_another_scene(self):
        write_json(self.folder/'geometry.json',dict(components=[dict(name='different')]))
        with self.assertRaisesRegex(ValueError,'different scene'):self.verify()

    def test_geometry_unavailable_does_not_invent_geometry_success(self):
        write_json(self.folder/'geometry.json',dict(status='unavailable',reason='Oracle unavailable'))
        self.assertFalse(self.verify()['geometry_available'])

    def test_reference_frozen_from_baseline_only(self):
        evidence=freeze_reference(self.folder,self.root)
        before=(self.root/'reference_evidence.json').read_bytes()
        # Moving later Render support does not relocate frozen Reference scopes.
        Image.new('L',(32,24),255).save(self.folder/'render_masks/anchor.png')
        self.assertEqual((self.root/'reference_evidence.json').read_bytes(),before)
        self.assertTrue(all(not row['reviewed'] and row['reliability']==0 for row in evidence['regions']))


class VerificationPairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('ref','render','different'):
            Image.new('RGB',(32,24),'gray').save(self.root/(name+'.png'))
        self.manifest=dict(reference_rgb='ref.png',render_rgb='render.png',vlm_verification='answers.json',
            coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='Synthetic unit test'))
        protocol=frozen_protocol();protocol={k:protocol[k] for k in ('system','user','schema')}
        packets=[replay('{"horizontal_stack":"yes","upright_books":"yes"}',protocol,source_kind='mock') for _ in range(2)]
        self.answers=compare_answers(*packets,[dict(evidence_id='books_horizontal_stack',field='horizontal_stack',question='Q1')])

    def evaluate(self):
        write_json(self.root/'answers.json',self.answers);write_json(self.root/'manifest.json',self.manifest)
        return run_manifest(self.root/'manifest.json',self.root/'out')

    def test_legacy_answers_without_pair_kept_unmatched(self):
        report=self.evaluate();diagnostic=report['diagnostics']['vlm_verification']
        self.assertEqual(diagnostic['status'],'unavailable')
        self.assertIsNone(diagnostic['evidence'])
        self.assertIsNotNone(diagnostic['unmatched_evidence'])
        self.assertEqual(report['energies']['appearance']['value'],0.)

    def test_other_images_never_assigned_to_current_pair(self):
        self.answers['image_pair']=dict(reference_rgb='different.png',render_rgb='render.png')
        self.assertFalse(self.evaluate()['diagnostics']['vlm_verification']['applicable_to_current_pair'])

    def test_explicit_mock_pair_import_is_diagnostic_only(self):
        self.answers['image_pair']=dict(reference_rgb='ref.png',render_rgb='render.png')
        report=self.evaluate();diagnostic=report['diagnostics']['vlm_verification']
        self.assertTrue(diagnostic['applicable_to_current_pair'])
        self.assertEqual(diagnostic['evidence']['reference']['source_kind'],'mock')
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertFalse(diagnostic['energy_contribution'])

    def test_actual_model_source_conflict_overrides_pair_declaration(self):
        self.answers['image_pair']=dict(reference_rgb='ref.png',render_rgb='render.png')
        self.answers['reference']['image_binding']=dict(source_rgb='different.png')
        self.assertFalse(self.evaluate()['diagnostics']['vlm_verification']['applicable_to_current_pair'])

    def test_missing_geometry_vlm_and_fake_trust_flag_keep_rgb(self):
        self.manifest.update(geometry='missing.json',vlm_verification=None,
            trusted_execution=True,provenance={'fixed_extrinsics_enforced':True})
        report=self.evaluate()
        self.assertIsNone(report['structural_energy'])
        self.assertEqual(report['energies']['appearance']['value'],0.)
        self.assertFalse(report['formal_eligible'])


if __name__=='__main__':unittest.main()
