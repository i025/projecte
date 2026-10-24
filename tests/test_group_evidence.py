"""CPU-only Group ownership, canonical aliases and bounded historical replay."""
from copy import deepcopy
import json
import unittest

from e_harness.benchmark_metrics import aggregate
from scripts.group_evidence_pilot import (
    bound_legacy_answers, group_energy_rows, group_questions,
)
from scripts.region_atomic_pilot import replay_atomic_answers


def atom(key, energy='semantic', expected=True, requires=()):
    return dict(
        id=key, region_id='R1', group_id='G1', owner_id='G1',
        canonical_fact_id='fixture:'+key, type=energy,
        claim='Synthetic proposition '+key, question='Synthetic question '+key+'?',
        expected=expected, answer_type='count' if energy == 'statistical' else 'boolean',
        requires=list(requires), status='unknown' if expected is None else 'candidate',
        source='Synthetic CPU fixture; no image observation',
        scope='Visible synthetic input only', provenance=dict(render_used=False),
        reviewed=False, reliability=0.,
    )


def document():
    atoms = [atom('presence'), atom('count', 'statistical', 2, ['presence']),
             atom('unknown', 'spatial', None)]
    return dict(
        scene_id='synthetic',
        regions=[dict(id='R1', bbox=[0, 0, 32, 24], metrics=[],
                      reviewed=False, reliability=0.)],
        semantic_groups=[dict(
            group_id='G1', region_id='R1', name='Synthetic collection',
            scope='Visible synthetic input only', provenance=dict(render_used=False),
            evidence=[a['id'] for a in atoms], reviewed=False, reliability=0.,
        )],
        atomic_evidence=atoms,
    )


def add_alias(case, *, first=False):
    alias = deepcopy(case['atomic_evidence'][0])
    alias.update(id='presence_alias', alias_of='presence')
    case['atomic_evidence'].insert(0 if first else len(case['atomic_evidence']), alias)
    case['semantic_groups'][0]['evidence'].append(alias['id'])
    return alias


def packet(side, answers=None):
    values = dict(q1='yes', q2=2, q3='yes') if answers is None else answers
    return dict(side=side, source='real_vlm', status='valid',
                answers=deepcopy(values), response=dict(raw_answer=json.dumps(values)))


class GroupEvidenceTests(unittest.TestCase):
    def test_groups_require_neither_masks_nor_member_inventory(self):
        case = document()
        original = deepcopy(case)
        questions, aliases = group_questions(case)
        self.assertEqual(case, original)
        self.assertEqual(aliases, [])
        self.assertEqual(len(questions), 3)
        for question in questions:
            self.assertEqual(question['level'], 'region')
            self.assertEqual(question['group_id'], 'G1')
            self.assertEqual(question['owner_id'], 'G1')
            self.assertEqual(question['context_id'], 'synthetic:R1')
            self.assertIs(question['reviewed'], False)
            self.assertEqual(question['reliability'], 0.)
        case['semantic_groups'][0]['member_instance_ids'] = None
        self.assertEqual(len(group_questions(case)[0]), 3)

    def test_wrong_parent_group_and_evidence_ownership_are_rejected(self):
        changes = [
            lambda c: c['semantic_groups'][0].update(region_id='R9'),
            lambda c: c['atomic_evidence'][0].update(group_id='G9'),
            lambda c: c['atomic_evidence'][0].update(owner_id='G9'),
            lambda c: c['atomic_evidence'][0].update(region_id='R9'),
            lambda c: c['semantic_groups'][0]['evidence'].append('presence'),
            lambda c: c['semantic_groups'][0]['evidence'].remove('presence'),
            lambda c: c['semantic_groups'][0]['evidence'].append('unlisted_atom'),
            lambda c: c['atomic_evidence'][0].update(anchor_refs=['unknown_anchor']),
        ]
        for change in changes:
            with self.subTest(change=change):
                case = document()
                change(case)
                with self.assertRaises(ValueError):
                    group_questions(case)
        case = document()
        case['regions'].append(dict(id='R2'))
        case['atomic_evidence'][0]['region_id'] = 'R2'
        with self.assertRaises(ValueError):
            group_questions(case)

    def test_candidate_review_reliability_and_reference_provenance_cannot_upgrade(self):
        for target in ('group', 'atom'):
            for field, value in (('reviewed', True), ('reliability', .5)):
                with self.subTest(target=target, field=field):
                    case = document()
                    row = case['semantic_groups'][0] if target == 'group' else case['atomic_evidence'][0]
                    row[field] = value
                    with self.assertRaises(ValueError):
                        group_questions(case)
        case = document()
        case['atomic_evidence'][0]['provenance']['render_used'] = True
        with self.assertRaises(ValueError):
            group_questions(case)

    def test_unavailable_and_reference_unknown_remain_distinct_and_unscored(self):
        questions, _ = group_questions(document())
        results = replay_atomic_answers(questions)
        states = {r['id']: r['status'] for r in results}
        self.assertEqual(states, dict(presence='unavailable', count='unavailable', unknown='unknown'))
        rows = group_energy_rows(questions, results)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['q'] == 0 and r['value'] is None and
                            r['reviewed'] is False and r['scorable'] is False for r in rows))
        self.assertEqual({r['id']: r['verification_status'] for r in rows}, states)
        energies, observation = aggregate(rows)
        self.assertIsNone(observation)
        self.assertTrue(all(e['value'] is None for e in energies.values()))

    def test_mock_satisfied_observations_never_become_energy(self):
        questions, _ = group_questions(document())
        raw = [dict(id='presence', status='satisfied', observed=True, finding='matched',
                    reason='Synthetic mock'),
               dict(id='count', status='satisfied', observed=2, finding='matched',
                    reason='Synthetic mock')]
        results = replay_atomic_answers(questions, raw, source_kind='mock')
        self.assertEqual(results[0]['status'], 'satisfied')
        rows = group_energy_rows(questions, results)
        self.assertTrue(all(r['value'] is None and r['q'] == 0 and not r['scorable'] for r in rows))
        self.assertIsNone(aggregate(rows)[1])

    def test_explicit_alias_creates_one_question_and_record_in_either_order(self):
        for first in (False, True):
            with self.subTest(alias_first=first):
                case = document()
                add_alias(case, first=first)
                questions, aliases = group_questions(case)
                self.assertEqual([a['alias_of'] for a in aliases], ['presence'])
                self.assertEqual(sum(q['id'] == 'presence' for q in questions), 1)
                self.assertNotIn('presence_alias', {q['id'] for q in questions})
                rows = group_energy_rows(questions, replay_atomic_answers(questions))
                self.assertEqual(len(rows), len(document()['atomic_evidence']))
                self.assertEqual(sum(r['canonical_fact_id'] == 'fixture:presence' for r in rows), 1)

    def test_contradictory_alias_and_duplicate_canonical_fact_are_rejected(self):
        changes = [dict(expected=False), dict(owner_id='other'), dict(scope='A different population'),
                   dict(requires=['presence']), dict(anchor_refs=['a'])]
        for change in changes:
            with self.subTest(change=change):
                case = document()
                case['optional_anchors'] = [dict(id='a')]
                alias = add_alias(case, first=True)
                alias.update(change)
                with self.assertRaises(ValueError):
                    group_questions(case)
        case = document()
        alias = add_alias(case)
        alias.pop('alias_of')
        with self.assertRaises(ValueError):
            group_questions(case)

    def test_dependency_cannot_reference_a_removed_alias(self):
        case = document()
        add_alias(case)
        case['atomic_evidence'][1]['requires'] = ['presence_alias']
        with self.assertRaises(ValueError):
            group_questions(case)

    def test_energy_rows_require_exactly_one_result_per_canonical_question(self):
        questions, _ = group_questions(document())
        results = replay_atomic_answers(questions)
        for changed in (results[:-1], results + [deepcopy(results[0])],
                        results + [dict(id='unrelated', status='satisfied', reason='Fixture')]):
            with self.subTest(ids=[r['id'] for r in changed]):
                with self.assertRaises(ValueError):
                    group_energy_rows(questions, changed)


class BoundLegacyAnswerTests(unittest.TestCase):
    def assert_unavailable(self, reference, rendered, binding=True):
        rows = bound_legacy_answers(reference, rendered, binding_verified=binding)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['status'] == 'unavailable' for r in rows))
        self.assertTrue(all(r['value'] is None and r['score'] is None and r['q'] == 0 for r in rows))

    def test_matching_real_packets_preserve_old_contract_without_scoring(self):
        rows = bound_legacy_answers(packet('reference'), packet('render'), binding_verified=True)
        self.assertEqual({r['id'] for r in rows}, {'q1', 'q2', 'q3'})
        self.assertTrue(all(r['status'] == 'satisfied' for r in rows))
        self.assertTrue(all(r['replay_only'] is True and r['new_group_question_verified'] is False and
                            r['reviewed'] is False and not r['scorable'] and
                            r['value'] is None and r['score'] is None and r['q'] == 0 for r in rows))

    def test_source_side_raw_parse_and_context_binding_are_mandatory(self):
        for side in ('reference', 'render'):
            for change in (dict(source='mock'), dict(source=None), dict(side='other'),
                           dict(response={}), dict(response=dict(raw_answer='not JSON')),
                           dict(response=dict(raw_answer='{"q1":"yes","q1":"no","q2":2,"q3":"yes"}')),
                           dict(answers=dict(q1='yes', q2=3, q3='yes'))):
                with self.subTest(side=side, change=change):
                    packets = dict(reference=packet('reference'), render=packet('render'))
                    packets[side].update(change)
                    self.assert_unavailable(packets['reference'], packets['render'])
        for binding in (False, None, 'false', 1):
            with self.subTest(binding=binding):
                self.assert_unavailable(packet('reference'), packet('render'), binding)

    def test_boolean_cannot_impersonate_stored_integer_count(self):
        reference = packet('reference', dict(q1='yes', q2=1, q3='yes'))
        reference['answers']['q2'] = True
        self.assert_unavailable(reference, packet('render'))

    def test_unknown_and_both_side_presence_prerequisites_are_preserved(self):
        reference = packet('reference', dict(q1='yes', q2='unknown', q3='unknown'))
        rows = bound_legacy_answers(reference, packet('render'), binding_verified=True)
        self.assertEqual([r['status'] for r in rows], ['satisfied', 'unknown', 'unknown'])
        for missing_side in ('reference', 'render'):
            with self.subTest(missing_side=missing_side):
                packets = dict(reference=packet('reference'), render=packet('render'))
                packets[missing_side] = packet(missing_side, dict(q1='no', q2=2, q3='yes'))
                rows = bound_legacy_answers(packets['reference'], packets['render'], binding_verified=True)
                self.assertEqual(rows[0]['status'], 'candidate_violated')
                self.assertEqual([r['status'] for r in rows[1:]], ['unknown', 'unknown'])
                self.assertTrue(all(r['value'] is None for r in rows))

    def test_old_packets_cannot_answer_new_group_questions(self):
        questions, _ = group_questions(document())
        rows = bound_legacy_answers(packet('reference'), packet('render'), binding_verified=True)
        self.assertTrue({q['id'] for q in questions}.isdisjoint({r['id'] for r in rows}))
        with self.assertRaises(ValueError):
            group_energy_rows(questions, rows)
        with self.assertRaises(ValueError):
            replay_atomic_answers(questions, rows, source_kind='historical_replay')


if __name__ == '__main__':
    unittest.main()
