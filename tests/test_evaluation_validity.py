"""CPU audit preparation and review gates; no image recognition/model requests."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from e_harness.benchmark import evaluate
from e_harness.benchmark_evidence import reliability
from e_harness.benchmark_structure import structural_report
from e_harness.verification_adapter import compare_answers, replay, validate_diagnostics
from scripts.evaluation_validity import (collect_rows, duplicate_review_candidates, lineage_strata, prepare,
    prioritize, review_template, summarize_reviews)


def row(pair='pair1', task='task1', eid='e1', energy='semantic', status='satisfied'):
    return dict(audit_id='P001', pair_id=pair, task_id=task, evidence_id=eid,
        region_id='r1', group_id=None, anchor_id=None, energy=energy,
        claim='A visible display is present.', question='Is a display visible?',
        answer_type='yes_no_unknown', categories=[], reference_answer='yes',
        render_answer='yes' if status == 'satisfied' else 'unknown' if status == 'unknown' else 'no',
        frozen_status=status)


def human(row, **labels):
    result = dict(row, review_status='completed', reviewed='true',
                  reviewer_id='synthetic_test_reviewer', reviewed_at_utc='2026-10-25T00:00:00Z')
    result.update(labels)
    return result


class ValidityReviewTests(unittest.TestCase):
    def test_priority_keeps_all_candidates_unknown_and_task_energy_pair_coverage(self):
        rows = [row(), row(eid='e2', status='candidate_violated'), row(eid='e3', status='unknown'),
                row(eid='e4', energy='spatial'), row(pair='pair2'), row(task='task2', pair='pair3')]
        selected = prioritize(rows)
        for item in rows:
            self.assertIn((item['pair_id'], item['evidence_id']), selected)
        self.assertEqual(prioritize(rows), selected)

    def test_empty_reviews_never_create_accuracy_or_energy(self):
        rows = review_template([row(), row(eid='e2', status='candidate_violated')], {})
        result = summarize_reviews(rows, rows)
        self.assertEqual(result['status'], 'pending')
        self.assertFalse(result['energy_contribution'])
        self.assertTrue(all(m['value'] is None for m in result['metrics'].values()))

    def test_explicit_human_labels_count_only_adjudicated_subset(self):
        rows = review_template([row(), row(eid='e2', status='candidate_violated')], {})
        filled = [human(rows[1], candidate_difference_confirmation='confirmed',
                        reference_evidence_validity='valid', render_answer_correctness='uncertain')]
        result = summarize_reviews(rows, filled)
        self.assertEqual(result['metrics']['candidate_confirmation']['value'], 1.)
        self.assertIsNone(result['metrics']['render_vqa_correctness']['value'])
        self.assertEqual(result['metrics']['reference_evidence_validity']['unreviewed_items'], 1)
        self.assertIsNone(result['blind_uncovered_differences']['value'])

    def test_shared_reference_not_counted_twice_and_conflicts_not_voted(self):
        rows = review_template([row(), row(pair='pair2')], {})
        filled = [human(r, reference_evidence_validity='valid') for r in rows]
        result = summarize_reviews(rows, filled)['metrics']['reference_evidence_validity']
        self.assertEqual(result['adjudicated_denominator'], 1)
        filled[1]['reference_evidence_validity'] = 'invalid'
        result = summarize_reviews(rows, filled)['metrics']['reference_evidence_validity']
        self.assertEqual(result['conflicting_items'], 1)
        self.assertIsNone(result['value'])

    def test_machine_field_edit_and_duplicate_human_rows_rejected(self):
        rows = review_template([row()], {})
        filled = human(rows[0], reference_evidence_validity='valid')
        for field in ('question', 'reference_answer', 'frozen_status'):
            changed = dict(filled, **{field: 'changed'})
            with self.assertRaises(ValueError):
                summarize_reviews(rows, [changed])
        with self.assertRaises(ValueError):
            summarize_reviews(rows, [filled, filled])

    def test_unattributed_and_invalid_and_unreviewed_human_labels_rejected(self):
        rows = review_template([row()], {})
        for changed in [dict(rows[0], reference_evidence_validity='valid'),
                human(rows[0], reference_evidence_validity='valid', reviewer_id=''),
                human(rows[0], reference_evidence_validity='GT'), human(rows[0])]:
            with self.assertRaises(ValueError):
                summarize_reviews(rows, [changed])

    def test_duplicates_are_diagnostic_pair_scoped_and_do_not_change_raw_rows(self):
        rows = review_template([row(), row(eid='e2')], {})
        original = deepcopy(rows)
        filled = [human(r, comparison_judgment='reasonable', duplicate_issue_id='issue1') for r in rows]
        result = summarize_reviews(rows, filled)
        self.assertEqual(result['duplicate_associations'][0]['evidence_ids'], ['e1', 'e2'])
        self.assertFalse(result['energy_contribution'])
        self.assertEqual(rows, original)

    def test_shared_scope_hint_never_confirms_or_merges_physical_errors(self):
        first = dict(row(status='candidate_violated'), group_id='g1')
        second = dict(first, evidence_id='e2')
        other = row(eid='e3', status='candidate_violated')
        hints = duplicate_review_candidates([first, second, other])
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]['evidence_ids'], ['e1', 'e2'])
        self.assertIsNone(hints[0]['same_underlying_difference'])
        self.assertFalse(hints[0]['reviewed'])
        self.assertFalse(hints[0]['energy_contribution'])

    def test_reliability_requires_separate_actual_review_not_model_confidence(self):
        candidate = dict(reviewed=False, reliability=1., status='candidate')
        self.assertEqual(reliability(candidate), 0.)
        self.assertEqual(reliability(dict(candidate, reviewed=True, reliability=.7)), .7)
        self.assertEqual(reliability(dict(candidate, reviewed=True, status='unknown')), 0.)

    def test_separate_reviewed_region_files_use_existing_semantic_interface(self):
        image = np.zeros((16, 16, 3), np.uint8)
        region = dict(id='r', bbox=[0, 0, 16, 16], category='display',
                      metrics=['semantic'], reviewed=False, reliability=1.)
        reference = dict(image_size=[16, 16], regions=[region])
        rendered = dict(image_size=[16, 16], regions=[dict(region, category='other')])
        pending, _ = evaluate(image, image, reference, rendered)
        self.assertIsNone(pending['energies']['semantic']['value'])
        # Explicit Synthetic Oracle annotations exercise the API, not real human data.
        reference['regions'][0] = dict(region, reviewed=True, provenance='synthetic_oracle')
        rendered['regions'][0]['reviewed'] = True
        confirmed, _ = evaluate(image, image, reference, rendered)
        self.assertEqual(confirmed['energies']['semantic']['value'], 1.)

    def test_reviewed_boolean_cannot_promote_imported_vqa_to_energy(self):
        protocol = dict(system='test', user='test', schema=dict(type='object',
            properties=dict(e1=dict(type='string', enum=['yes', 'no', 'unknown'])),
            required=['e1'], additionalProperties=False))
        packet = replay('{"e1":"yes"}', protocol, source_kind='mock')
        paired = compare_answers(packet, packet, [dict(evidence_id='e1', field='e1', question='Test?')])
        paired['reviewed'] = True
        paired['results'][0]['reviewed'] = True
        result = validate_diagnostics(paired)
        self.assertFalse(result['reviewed'])
        self.assertFalse(result['energy_contribution'])
        self.assertIsNone(result['results'][0]['value'])

    def test_aabb_and_names_cannot_supply_structural_checks(self):
        metadata = dict(objects=[dict(unit_id='A', name='Shelf', bbox=[0, 0, 1, 1])])
        result = structural_report(metadata)
        self.assertIsNone(result['energy'])
        self.assertTrue(all(not checks for checks in result['checks'].values()))

    def test_real_geometry_still_needs_reviewed_semantic_triage(self):
        oracle = dict(collisions=[dict(unit_ids=['A', 'B'], status='penetration')])
        self.assertIsNone(structural_report(oracle)['energy'])
        triage = dict(pairs=[dict(unit_ids=['A', 'B'], reviewed=True,
                                 classification='implausible_penetration', source='synthetic_oracle')])
        self.assertEqual(structural_report(oracle, triage)['energy'], 1.)


class ValidityPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.source = self.root / 'frozen'
        ref = self.source / 'references' / 'task1'; ref.mkdir(parents=True)
        pair = self.source / 'pairs' / 'pair1'; pair.mkdir(parents=True)
        run = self.root / 'native_run'; run.mkdir()
        Image.new('RGB', (64, 48), 'gray').save(ref / 'reference.png')
        Image.new('RGB', (64, 48), 'blue').save(pair / 'render.png')
        (run / 'config.json').write_text('{"agent":{}}')
        (run / 'scene.blend').write_bytes(b'NOT_OPENED_SYNTHETIC_SENTINEL')
        self.config = dict(pairs=[dict(pair_id='pair1', task_id='task1', run_id='run1', agent='test',
            input_mode='rgb_only_with_generic_protocol', completion='completed',
            provenance=dict(run_config=str(run / 'config.json')),
            reference_rgb=str(ref / 'reference.png'), render_rgb=str(pair / 'render.png'),
            blend=str(run / 'scene.blend'))])
        self.batch = dict(pairs=[dict(pair_id='pair1', scene_validity=dict(camera_protocol='historical_camera',
            formal_eligible=False, pose_matches_T0=False, reason='synthetic camera mismatch'))], coverage={})
        atom = dict(id='e1', claim=row()['claim'], question=row()['question'])
        (ref / 'reference_evidence.json').write_text(json.dumps(dict(image_size=[64, 48],
            regions=[dict(id='r1', bbox=[0, 0, 32, 48])], atomic_evidence=[atom])))
        result = row(); result['status'] = result.pop('frozen_status')
        (pair / 'verification_results.json').write_text(json.dumps(dict(results=[result])))
        (pair / 'geometry.json').write_text('{"status":"unavailable"}')
        (self.source / 'config.frozen.json').write_text(json.dumps(self.config))
        (self.source / 'report.json').write_text(json.dumps(self.batch))

    def tearDown(self):
        self.directory.cleanup()

    def test_end_to_end_offline_packet_preserves_source_and_separates_blind_images(self):
        before = {str(p): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        output = self.root / 'audit'
        prepare(self.source, output)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.source.rglob('*') if p.is_file()})
        with (output / 'human_review_template.csv').open() as stream:
            evidence = list(csv.DictReader(stream))
        self.assertEqual(evidence[0]['review_status'], 'unreviewed')
        with (output / 'blind_difference_template.csv').open() as stream:
            blind = list(csv.DictReader(stream))
        self.assertNotIn('question', blind[0]); self.assertNotIn('pair_id', blind[0])
        self.assertEqual(len(list((output / 'private/stage1_blind').glob('*.png'))), 3)
        self.assertEqual(len(list((output / 'private/stage2_evidence').glob('*.png'))), 1)
        for path in (output / 'private').rglob('*.png'):
            with Image.open(path) as image:
                image.verify()
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertNotIn(str(self.root), (output / 'evidence_validity.json').read_text())

    def test_overwrite_and_source_child_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.source, self.source / 'audit')
        output = self.root / 'audit'; output.mkdir()
        with self.assertRaises(FileExistsError):
            prepare(self.source, output)

    def test_changed_frozen_question_rejected(self):
        packet_path = self.source / 'pairs/pair1/verification_results.json'
        packet = json.loads(packet_path.read_text()); packet['results'][0]['question'] = 'Changed?'
        packet_path.write_text(json.dumps(packet))
        with self.assertRaises(ValueError):
            collect_rows(self.source, self.config)

    def test_continuation_uses_explicit_trajectory_provenance(self):
        second = deepcopy(self.config['pairs'][0]); second['pair_id'] = 'second'
        run2 = self.root / 'second'; run2.mkdir()
        run_config = self.config['pairs'][0]['provenance']['run_config']
        (run2 / 'config.json').write_text(json.dumps(dict(agent=dict(
            load_trajectory=str(Path(run_config).parent / 'agent/session.jsonl')))))
        second['provenance']['run_config'] = str(run2 / 'config.json')
        config = dict(pairs=[self.config['pairs'][0], second])
        batch = deepcopy(self.batch); batch['pairs'].append(dict(batch['pairs'][0], pair_id='second'))
        result = lineage_strata(config, batch)
        self.assertEqual(result[1]['continuation_of'], 'pair1')
        self.assertEqual(result[1]['lineage_id'], result[0]['lineage_id'])


if __name__ == '__main__':
    unittest.main()
