"""CPU-only integration contracts; Oracle pixels/labels are not visual model tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from e_harness.benchmark import evaluate, main, render_cpu
from e_harness.benchmark_config import FIXED_T0, RENDER, camera_check, camera_pose, write_json
from e_harness.benchmark_offline import fit_render, prepare_images, run_manifest


class OfflineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = np.full((48, 64, 3), 90, np.uint8)
        self.a[10:30, 12:40] = [210, 50, 35]
        Image.fromarray(self.a).save(self.root/'ref.png')
        Image.fromarray(self.a).save(self.root/'render.png')
        self.reference = dict(image_size=[64,48], reviewed=False, regions=[dict(
            id='R1', bbox=[8,8,44,34], reviewed=False, reliability=0., metrics=['semantic','appearance','perceptual'])])
        write_json(self.root/'evidence.json', self.reference)
        self.manifest = dict(reference_rgb='ref.png', render_rgb='render.png',
            reference_evidence='evidence.json', evidence_category='synthetic_oracle',
            coordinates=dict(convention='reference_pixel_xyxy', render_mapping='identity', basis='Known same synthetic canvas'))

    def run_case(self, name='output', **changes):
        manifest = dict(self.manifest, **changes)
        write_json(self.root/'manifest.json', manifest)
        return run_manifest(self.root/'manifest.json', self.root/name)

    def test_complete_input_and_cli_outputs(self):
        metadata = dict(camera=dict(matrix_world=FIXED_T0), resolution=[64,48], fixed_extrinsics_enforced=True)
        write_json(self.root/'camera.json', metadata)
        self.manifest['render_metadata'] = 'camera.json'
        write_json(self.root/'manifest.json', self.manifest)
        self.assertEqual(main(['offline','--manifest',str(self.root/'manifest.json'),
                               '--output',str(self.root/'out')]), 0)
        for name in ('report.json','summary.md','comparison.png','integration_checks.json','valid_pixels.png'):
            self.assertTrue((self.root/'out'/name).is_file())
        self.assertEqual(list((self.root/'out').glob('*.html')), [])
        report = json.loads((self.root/'out/report.json').read_text())
        self.assertEqual(report['energies']['appearance']['value'], 0.)
        self.assertFalse(report['formal_eligible'])
        self.assertEqual(report['scene_validity']['camera_protocol'], 'pose_consistent_unverified')

    def test_group_candidates_never_enter_energy_or_change_review(self):
        baseline = self.run_case('baseline')
        group = dict(reviewed=False, results=[dict(status='candidate_violated', expected='yes', actual='no')])
        write_json(self.root/'group.json', group)
        attached = self.run_case('attached', diagnostics={'groups':'group.json'})
        self.assertEqual(baseline['energies'], attached['energies'])
        self.assertEqual(attached['diagnostics']['groups']['evidence'], group)
        self.assertFalse(attached['diagnostics']['groups']['energy_contribution'])
        self.assertFalse(attached['reference_evidence']['regions'][0]['reviewed'])
        self.assertIsNone(attached['energies']['semantic']['value'])

    def test_optional_unavailable_or_malformed_keeps_rgb(self):
        (self.root/'bad.json').write_text('{not JSON')
        report = self.run_case(diagnostics={'groups':'bad.json','structural_layout':'missing.json'},
                               geometry='bad.json', render_evidence='bad.json')
        self.assertEqual(report['energies']['appearance']['value'], 0.)
        self.assertIsNone(report['structural_energy'])
        self.assertEqual(report['diagnostics']['structural_layout']['status'], 'unavailable')
        self.assertEqual(report['diagnostics']['groups']['status'], 'unavailable')

    def test_bad_structural_schema_does_not_discard_observation(self):
        write_json(self.root/'geometry.json', dict(collisions=[{}]))
        report = self.run_case(geometry='geometry.json')
        self.assertEqual(report['energies']['appearance']['value'], 0.)
        self.assertIsNone(report['structural_energy'])
        self.assertEqual(report['provenance']['optional_inputs']['structural_inputs']['status'], 'unavailable')

    def test_wrong_shaped_optional_render_evidence_keeps_rgb(self):
        for index, content in enumerate(('[]', 'null')):
            with self.subTest(content=content):
                (self.root/'wrong.json').write_text(content)
                report = self.run_case('wrong_'+str(index),render_evidence='wrong.json')
                self.assertEqual(report['energies']['appearance']['value'], 0.)
                self.assertEqual(report['provenance']['optional_inputs']['render_evidence']['status'], 'unavailable')

    def test_unknown_na_never_becomes_zero(self):
        report = self.run_case()
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertIsNone(report['energies']['perceptual']['value'])
        self.assertLess(report['evidence_coverage'], 1.)
        self.assertEqual(report['energies']['perceptual']['participating_records'], [])

    def test_boolean_camera_claim_cannot_certify(self):
        for metadata in (dict(fixed_extrinsics_enforced=True),
                         dict(fixed_extrinsics_enforced=True, fixed_T0=FIXED_T0),
                         dict(fixed_extrinsics_enforced=True, camera=dict(matrix_world=FIXED_T0))):
            report,_ = evaluate(self.a,self.a,render_metadata=metadata)
            self.assertNotEqual(report['scene_validity']['status'], 'valid')
            self.assertFalse(report['scene_validity']['formal_eligible'])

    def test_rigid_non_t0_is_rejected_before_render_launch(self):
        config = deepcopy(RENDER)
        config['matrix_world'][2][3] = 1.5
        camera_pose(config['matrix_world'])  # valid rigid matrix
        with self.assertRaisesRegex(ValueError, 'prescribed'):
            render_cpu(self.root/'must_not_launch', fixture='baseline', config=config)
        self.assertFalse((self.root/'must_not_launch').exists())

    def test_historical_camera_retains_actual_pose(self):
        matrix = deepcopy(FIXED_T0); matrix[2][3] = 1.5
        write_json(self.root/'camera.json', dict(T_c2w=matrix, fixed_extrinsics_enforced=True))
        report = self.run_case(render_metadata='camera.json')
        self.assertEqual(report['usage'], 'provisional/debug')
        self.assertEqual(report['scene_validity']['camera_protocol'], 'historical_camera')
        self.assertEqual(report['scene_validity']['actual_poses']['T_c2w'][2][3], 1.5)
        self.assertFalse(report['scene_validity']['pose_matches_T0'])

    def test_conflicting_or_nonrigid_camera_metadata_is_not_valid(self):
        other = deepcopy(FIXED_T0); other[0][3] = 2.
        check = camera_check(dict(T_c2w=other, camera={'matrix_world':FIXED_T0}))
        self.assertFalse(check['pose_matches_T0'])
        check = camera_check(dict(T_c2w=[[1,2],[3,4]]))
        self.assertFalse(check['pose_matches_T0'])
        self.assertTrue(any('rigid' in r for r in check['reasons']))

    def test_bad_optional_resolution_does_not_discard_rgb(self):
        write_json(self.root/'camera.json', dict(T_c2w=FIXED_T0,
            render=dict(resolution_x='bad',resolution_y=48,percentage='invalid')))
        report = self.run_case(render_metadata='camera.json')
        self.assertEqual(report['energies']['appearance']['value'], 0.)
        self.assertFalse(report['formal_eligible'])
        self.assertTrue(any('resolution fields' in r for r in report['scene_validity']['reasons']))

    def test_size_mismatch_requires_explicit_conversion_basis(self):
        Image.new('RGB',(32,16)).save(self.root/'render.png')
        with self.assertRaisesRegex(ValueError, 'Identity requires'):
            self.run_case()
        coords = dict(self.manifest['coordinates'], render_mapping='uniform_fit', basis='')
        with self.assertRaisesRegex(ValueError, 'basis required'):
            self.run_case(coordinates=coords)

    def test_uniform_fit_reuses_previous_transform_and_fixed_masks(self):
        image = Image.new('RGBA', (40,20), (120,120,120,255))
        image.save(self.root/'render.png')
        _, expected_valid, expected_transform = fit_render(image, (64,48))
        coords = dict(self.manifest['coordinates'], render_mapping='uniform_fit', expected_transform=expected_transform)
        report = self.run_case(coordinates=coords)
        np.testing.assert_array_equal(np.asarray(Image.open(self.root/'output/valid_pixels.png'))>0,expected_valid)
        self.assertEqual(report['reference_evidence']['regions'][0]['bbox'], [8,8,44,34])
        self.assertEqual(report['coordinates']['applied_transform']['offset_xy'], [0,8])
        self.assertEqual(report['coordinates']['measurement_pixels'], 64*31)

    def test_transform_drift_and_evidence_grid_mismatch_rejected(self):
        coords = dict(self.manifest['coordinates'], expected_transform={'offset_xy':[1,0]})
        with self.assertRaisesRegex(ValueError, 'transform differs'):
            self.run_case(coordinates=coords)
        self.reference['image_size'] = [128,96]
        write_json(self.root/'evidence.json', self.reference)
        with self.assertRaises(ValueError):
            self.run_case()

    def test_invalid_pixels_and_gradient_stencils_do_not_contribute(self):
        valid = np.ones(self.a.shape[:2],bool); valid[:, :8] = False
        altered = self.a.copy(); altered[:, :8] = 255
        baseline,_ = evaluate(self.a,self.a,valid_mask=valid)
        report,_ = evaluate(self.a,altered,valid_mask=valid)
        self.assertEqual(report['energies'], baseline['energies'])
        # Invalid border on the right also tests gradient dependence of the last valid column.
        valid = np.ones(self.a.shape[:2],bool); valid[:, -8:] = False
        altered = self.a.copy(); altered[:, -8:] = 255
        report,_ = evaluate(self.a,altered,valid_mask=valid)
        for k in ('appearance','spatial','statistical'):
            self.assertEqual(report['energies'][k]['value'], 0.)

    def test_alpha_is_not_observation(self):
        rgba = np.dstack((self.a, np.full(self.a.shape[:2],255,np.uint8)))
        rgba[:,:8,:3] = 255; rgba[:,:8,3] = 0
        Image.fromarray(rgba).save(self.root/'render.png')
        report = self.run_case()
        self.assertEqual(report['energies']['appearance']['value'], 0.)
        self.assertEqual(report['coordinates']['valid_pixels'], 48*56)

    def test_overlapping_reviewed_scopes_kept_without_double_aggregation(self):
        reference = dict(regions=[dict(id=key, bbox=[8,8,44,34], reviewed=True,
                                      metrics=['appearance']) for key in ('R1','R2')])
        altered = self.a.copy(); altered[12:20,12:20] = 0
        report,_ = evaluate(self.a,altered,reference,withhold_region_overlaps=True)
        self.assertEqual(report['error_diagnostics']['overlap_aggregation_withheld'], ['R1','R2'])
        candidates = [r for r in report['metric_records'] if r['id'] in ('R1','R2')]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(r['value'] is not None and not r['aggregation_eligible'] for r in candidates))
        participants = report['energies']['appearance']['participating_records']
        self.assertFalse(any(r['id'] in ('R1','R2') for r in participants))
        # The duplicate scope does not change any already eligible error.
        single = deepcopy(reference); single['regions'] = single['regions'][:1]
        single['regions'][0]['conflicted'] = True
        # q=0 candidate additions also cannot perturb the effective error.
        base,_ = evaluate(self.a,altered)
        candidate,_ = evaluate(self.a,altered,single,withhold_region_overlaps=True)
        for k in base['energies']:
            self.assertEqual(base['energies'][k]['value'],candidate['energies'][k]['value'])

    def test_existing_output_is_never_overwritten(self):
        self.run_case()
        old = (self.root/'output/report.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_case()
        self.assertEqual(old,(self.root/'output/report.json').read_bytes())

    def test_q0_overlap_cannot_withhold_existing_reviewed_measurement(self):
        region = dict(id='R1',bbox=[8,8,44,34],reviewed=True,metrics=['appearance'])
        altered = self.a.copy();altered[12:20,12:20] = 0
        baseline,_ = evaluate(self.a,altered,dict(regions=[region]),withhold_region_overlaps=True)
        candidate = dict(id='candidate',bbox=[8,8,44,34],reviewed=False,reliability=0.)
        added,_ = evaluate(self.a,altered,dict(regions=[region,candidate]),withhold_region_overlaps=True)
        for key in baseline['energies']:
            self.assertEqual(baseline['energies'][key]['value'],added['energies'][key]['value'])
        self.assertEqual(added['error_diagnostics']['overlap_aggregation_withheld'], [])


if __name__ == '__main__':
    unittest.main()
