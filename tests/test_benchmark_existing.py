"""Existing-scene orchestration uses tiny CPU fixtures, never real verifier/model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from e_harness import benchmark_existing as existing
from e_harness.verification_adapter import compare_answers, parse_answer, replay
from scripts.reference_vlm_pilot import evidence_from_plan, planning_protocol


def plan():
    return dict(regions=[dict(id='R1', name='Display', description='Visible display scope',
        bbox=[80, 80, 920, 920])], groups=[], anchors=[], evidence=[
        dict(id='E1', region_id='R1', group_id=None, anchor_id=None, type='semantic',
            claim='PRIVATE_REFERENCE_CLAIM', question='Which visible content category is present?',
            answer_type='categorical_unknown', categories=['books', 'vinyl_sleeves']),
        dict(id='E2', region_id='R1', group_id=None, anchor_id=None, type='spatial',
            claim='PRIVATE_SPATIAL_CLAIM', question='Are the visible displays beside one another?',
            answer_type='yes_no_unknown', categories=[])])


def packet(value, protocol):
    return replay(json.dumps(value), protocol, source_kind='mock')


def evidence(document=None):
    protocol = planning_protocol('existing_scene_v1', evidence_budget=10)
    return evidence_from_plan(packet(document or plan(), protocol), (64, 48),
        protocol_version='existing_scene_v1', evidence_budget=10)


class ExistingSceneBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/'input.png'
        Image.new('RGB', (64, 48), (80, 95, 110)).save(self.image)
        self.config = dict(model='gpt-6-sol', timeout_seconds=180, max_edge=768,
            evidence_budget=10, protocol_version='existing_scene_v1', dino_model='not-loaded')

    def dataset(self, count=2):
        rendered=self.root/'original_render.png'
        Image.new('RGB',(80,60),'darkgray').save(rendered)
        return dict(self.config,pairs=[dict(pair_id='pair_'+str(i),task_id='scene_a',run_id='synthetic',
            reference_rgb=str(self.image),render_rgb=str(rendered),completion='synthetic_test') for i in range(count)])

    def run_mock(self, config, document=None, answers=None):
        output=self.root/'batch'
        actual=[]
        def fake(image,protocol,**kwargs):
            actual.append((str(image),deepcopy(protocol),kwargs['request_id']))
            if kwargs['request_id']=='planning_response':value=plan() if document is None else document
            else:
                frozen=output/'references/scene_a/reference_evidence.json'
                self.assertEqual(frozen.stat().st_mode&0o777,0o444)
                value=dict(E1='books',E2='yes') if answers is None else answers
            response=packet(value,protocol)
            response['image_binding']=dict(source_rgb=str(image),image_size=[64,48])
            return response
        def features(images):
            return np.asarray([[float(np.asarray(im).mean())+1,2.,3.] for im in images])
        with patch.object(existing,'codex_answer',side_effect=fake):
            result=existing.run_dataset(config,output,extract=features,
                extract_provenance=dict(backend='mock',real_inference=False))
        return result,actual,output

    def test_actual_offline_entry_shares_reference_and_independently_verifies_renders(self):
        result,actual,output=self.run_mock(self.dataset(3))
        self.assertEqual(result['evaluated_pairs'],3)
        self.assertEqual([a[2] for a in actual],
                         ['planning_response','reference_answers']+['render_answers']*3)
        self.assertTrue(all(row['pilot_passed'] for row in result['pairs']))
        self.assertTrue(all(a[1]==actual[1][1] for a in actual[2:]))
        self.assertEqual(result['coverage']['perceptual']['measured_pairs'],3)
        self.assertEqual(result['coverage']['semantic']['measured_pairs'],0)
        self.assertTrue(all(not row['formal_eligible'] for row in result['pairs']))
        for name in ('report.json','summary.md','per_pair_results.csv','evidence_audit.md'):
            self.assertTrue((output/name).is_file())
        frozen=output/'references/scene_a/reference_evidence.json'
        with patch.object(existing,'codex_answer',side_effect=AssertionError('No retry')),patch.object(
                existing,'LocalDino',side_effect=AssertionError('No model')):
            replayed=existing.run_dataset(self.dataset(3),output,
                extract=lambda images:(_ for _ in ()).throw(AssertionError('No repeat inference')),
                extract_provenance=dict(backend='mock'))
        self.assertEqual(replayed['pairs'],result['pairs'])
        self.assertFalse(json.loads(frozen.read_text())['reviewed'])

    def test_unknown_answers_remain_unknown_not_numeric_semantic_penalties(self):
        result,_,output=self.run_mock(self.dataset(),answers=dict(E1='ambiguous',E2='unknown'))
        self.assertEqual(result['verification_states'],{'unknown':4})
        self.assertTrue(all(r['energies']['semantic']['value'] is None for r in result['pairs']))

    def test_missing_answer_preserves_valid_sibling_and_image_measurements(self):
        result,_,output=self.run_mock(self.dataset(),answers=dict(E1='books'))
        self.assertEqual(result['verification_states'],{'satisfied':2,'unavailable':2})
        self.assertTrue(all(r['energies']['appearance']['value'] is not None for r in result['pairs']))

    def test_invalid_plan_keeps_rgb_and_prevents_expansion_or_retry(self):
        result,actual,_=self.run_mock(self.dataset(3),document={})
        self.assertEqual(result['evaluated_pairs'],2)
        self.assertEqual(len(actual),1)
        self.assertEqual(result['pairs'][-1]['status'],'not_run')
        self.assertEqual(result['coverage']['perceptual']['fraction'],2/3)
        self.assertTrue(all(r['energies']['semantic']['value'] is None for r in result['pairs'][:2]))

    def test_no_facts_skips_vqa_without_manufacturing_answers(self):
        document=plan();document['evidence']=[]
        result,actual,output=self.run_mock(self.dataset(),document=document)
        self.assertEqual(len(actual),1)
        self.assertEqual(result['verification_states'],{})
        self.assertEqual(result['evaluated_pairs'],2)
        self.assertFalse((output/'references/scene_a/reference_answers.json').exists())

    def test_resume_rejects_changed_config(self):
        result,_,output=self.run_mock(self.dataset())
        config=self.dataset();config['evidence_budget']=9
        with self.assertRaisesRegex(ValueError,'Frozen'):
            existing.run_dataset(config,output,extract=lambda x:x,extract_provenance=dict(backend='mock'))

    def test_intermediate_reuse_requires_exact_content(self):
        target=self.root/'intermediate.json'
        existing.ensure_saved(target,dict(state='unknown'))
        existing.ensure_saved(target,dict(state='unknown'))
        with self.assertRaises(ValueError):existing.ensure_saved(target,dict(state='satisfied'))

    def test_reserved_attempts_count_even_without_a_response(self):
        root=self.root/'batch';folder=root/'references/scene_a';folder.mkdir(parents=True)
        (folder/'planning_response.reservation.json').write_text('{}')
        result=existing.summarize(self.dataset(),root,[])
        self.assertEqual(result['actual_model_attempts'],1)
        self.assertEqual(result['calls'][0]['status'],'unavailable')

    def test_saved_answer_binding_mismatch_is_not_reused(self):
        protocol,_=existing.verification_input(existing.category_policy(evidence()))
        response=packet(dict(E1='books',E2='yes'),protocol)
        response['image_binding']=dict(source_rgb=str(self.root/'wrong.png'))
        (self.root/'render_answers.json').write_text(json.dumps(response))
        with patch.object(existing,'codex_answer',side_effect=AssertionError('No retry')):
            with self.assertRaisesRegex(ValueError,'another image'):
                existing.call_once(self.root,'render_answers',self.image,protocol,self.config)

    def test_category_completion_is_reference_only_copy(self):
        original = evidence()
        before = deepcopy(original)
        completed = existing.category_policy(original)
        self.assertEqual(original, before)
        first = completed['atomic_evidence'][0]
        self.assertEqual(first['raw_categories'], ['books', 'vinyl_sleeves'])
        self.assertEqual(first['categories'], ['books', 'vinyl_sleeves', 'absent', 'other'])
        self.assertEqual(completed['atomic_evidence'][1]['categories'], [])
        self.assertFalse(completed['reviewed'])
        self.assertTrue(all(not row['reviewed'] for row in completed['atomic_evidence']))

    def test_full_planner_category_budget_retains_all_options(self):
        document = plan()
        document['evidence'][0]['categories'] = ['class_'+str(i) for i in range(12)]
        completed = existing.category_policy(evidence(document))
        protocol, questions = existing.verification_input(completed)
        options = protocol['schema']['properties']['E1']['enum']
        self.assertEqual(options, ['class_'+str(i) for i in range(12)] +
                         ['absent', 'other', 'unknown', 'ambiguous'])
        self.assertEqual(len(questions[0]['categories']), 14)
        self.assertEqual(parse_answer('{"E1":"absent","E2":"yes"}',
            protocol['schema'])['status'], 'valid')

    def test_category_completion_does_not_duplicate_existing_absence(self):
        document = plan()
        document['evidence'][0]['categories'] = ['books', 'other', 'absent']
        completed = existing.category_policy(evidence(document))
        self.assertEqual(completed['atomic_evidence'][0]['categories'], ['books', 'other', 'absent'])

    def test_frozen_verifier_has_absence_other_and_abstention_without_claims(self):
        completed = existing.category_policy(evidence())
        protocol, questions = existing.verification_input(completed)
        self.assertNotIn('PRIVATE_REFERENCE_CLAIM', protocol['user'])
        self.assertNotIn('PRIVATE_SPATIAL_CLAIM', protocol['user'])
        self.assertIn('absent', protocol['user'])
        self.assertIn('other', protocol['user'])
        first = packet(dict(E1='books', E2='yes'), protocol)
        for answer, expected_status in (('absent', 'candidate_violated'),
                ('other', 'candidate_violated'), ('ambiguous', 'unknown'), ('unknown', 'unknown')):
            with self.subTest(answer=answer):
                rendered = packet(dict(E1=answer, E2='yes'), protocol)
                compared = compare_answers(first, rendered, questions)
                self.assertEqual(compared['results'][0]['status'], expected_status)
                self.assertEqual(compared['results'][1]['status'], 'satisfied')
                self.assertTrue(all(not row['reviewed'] and not row['energy_contribution']
                    and row['value'] is None for row in compared['results']))

    def test_call_once_reserves_before_one_attempt_and_reuses_raw_packet(self):
        protocol, _ = existing.verification_input(existing.category_policy(evidence()))
        answer = packet(dict(E1='books', E2='yes'), protocol)
        def fake(image, actual, **kwargs):
            self.assertEqual(Path(image), self.image)
            self.assertEqual(actual, protocol)
            self.assertTrue((self.root/'reference_answers.reservation.json').is_file())
            self.assertEqual(kwargs['max_requests'], 1)
            self.assertEqual(kwargs['ledger'], [])
            self.assertEqual(kwargs['model'], self.config['model'])
            return deepcopy(answer)
        with patch.object(existing, 'codex_answer', side_effect=fake) as called:
            first = existing.call_once(self.root, 'reference_answers', self.image, protocol, self.config)
            second = existing.call_once(self.root, 'reference_answers', self.image, protocol, self.config)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(first, answer)
        self.assertEqual(second, answer)

    def test_reserved_interruption_never_retries(self):
        protocol, _ = existing.verification_input(existing.category_policy(evidence()))
        reservation = self.root/'render_answers.reservation.json'
        reservation.write_text(json.dumps(dict(stage='render_answers', image=str(self.image),
            actual_input=protocol, model=self.config['model'])))
        with patch.object(existing, 'codex_answer', side_effect=AssertionError('No retry')):
            result = existing.call_once(self.root, 'render_answers', self.image, protocol, self.config)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['actual_input'], protocol)

    def test_existing_packet_with_different_contract_is_not_silently_reused(self):
        protocol, _ = existing.verification_input(existing.category_policy(evidence()))
        result = packet(dict(E1='books', E2='yes'), protocol)
        result['actual_input']['user'] += ' unexpected change'
        (self.root/'render_answers.json').write_text(json.dumps(result))
        with patch.object(existing, 'codex_answer', side_effect=AssertionError('No retry')):
            with self.assertRaises(ValueError):
                existing.call_once(self.root, 'render_answers', self.image, protocol, self.config)


if __name__ == '__main__':
    unittest.main()
