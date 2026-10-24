import json
import unittest

from scripts.records_group_verification import parse_answer, compare, QUESTIONS


def packet(**overrides):
    values = dict.fromkeys(QUESTIONS, 'yes')
    values.update(overrides)
    return parse_answer(json.dumps(values))


class RecordsVerificationTests(unittest.TestCase):
    def test_agreement_is_provisional_not_energy(self):
        rows = compare(packet(), packet())
        self.assertEqual([r['status'] for r in rows], ['satisfied'] * 3)
        for row in rows:
            self.assertFalse(row['reviewed'])
            self.assertFalse(row['scorable'])
            self.assertIsNone(row['score'])
            self.assertIsNone(row['value'])

    def test_distribution_change_is_candidate_only(self):
        rows = compare(packet(), packet(multiple_sections='no'))
        self.assertEqual([r['status'] for r in rows], ['satisfied', 'candidate_violated', 'satisfied'])

    def test_missing_group_does_not_trigger_three_penalties(self):
        rows = compare(packet(), packet(present='no', multiple_sections='no', upright_display='no'))
        self.assertEqual([r['status'] for r in rows], ['candidate_violated', 'unknown', 'unknown'])
        self.assertEqual(rows[1]['render_answer'], 'no')
        self.assertEqual(rows[1]['independent_comparison'], 'candidate_violated')

    def test_unknown_is_not_absence_or_agreement(self):
        rows = compare(packet(present='unknown'), packet(present='unknown'))
        self.assertEqual([r['status'] for r in rows], ['unknown'] * 3)

    def test_invalid_field_preserves_other_answers(self):
        first = packet(multiple_sections='yes|no|unknown')
        self.assertEqual(first['status'], 'partial')
        self.assertEqual([r['status'] for r in compare(first, packet())], ['satisfied', 'unavailable', 'satisfied'])

    def test_missing_dependency_preserves_raw_but_withholds_comparison(self):
        first = parse_answer('{"multiple_sections":"yes","upright_display":"yes"}')
        rows = compare(first, packet())
        self.assertEqual([r['status'] for r in rows], ['unavailable'] * 3)
        self.assertEqual(rows[1]['reference_answer'], 'yes')

    def test_duplicate_key_and_invalid_envelope_are_unavailable(self):
        for raw in ('{"present":"yes","present":"no"}', '[]', 'not JSON', None):
            first = parse_answer(raw)
            self.assertEqual(first['status'], 'unavailable')
            self.assertEqual([r['status'] for r in compare(first, packet())], ['unavailable'] * 3)

    def test_types_and_extra_fields_are_not_silently_valid(self):
        first = packet(present=True)
        self.assertEqual(first['fields']['present']['validation_status'], 'unavailable')
        first = packet(unexpected='answer')
        self.assertEqual(first['status'], 'partial')
        self.assertEqual(first['unexpected_fields'], ['unexpected'])


if __name__ == '__main__':
    unittest.main()
