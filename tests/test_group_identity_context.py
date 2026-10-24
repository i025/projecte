import unittest

from scripts.group_identity_context import parse_identity, compare_categories, CATEGORIES


class GroupIdentityTests(unittest.TestCase):
    def test_all_five_categories_preserved(self):
        for category in CATEGORIES:
            self.assertEqual(parse_identity('{"category":"'+category+'"}'),dict(status='valid',category=category))

    def test_invalid_response_unavailable_not_absent(self):
        for raw in (None, 'not JSON', '[]', '{}', '{"category":true}',
                    '{"category":"books|vinyl_sleeves"}', '{"category":"books","explanation":"x"}',
                    '{"category":"books","category":"absent"}'):
            packet=parse_identity(raw)
            self.assertEqual(packet['status'],'unavailable')
            self.assertIsNone(packet['category'])

    def test_ambiguous_is_unknown_even_if_both_agree(self):
        p=parse_identity('{"category":"ambiguous"}')
        self.assertEqual(compare_categories(p,p)['status'],'unknown')
        self.assertFalse(compare_categories(p,p)['raw_label_changed'])

    def test_loss_of_identifiability_keeps_label_change_without_confirmed_mismatch(self):
        a=parse_identity('{"category":"vinyl_sleeves"}')
        b=parse_identity('{"category":"ambiguous"}')
        result=compare_categories(a,b)
        self.assertEqual(result['status'],'unknown')
        self.assertTrue(result['raw_label_changed'])

    def test_explicit_different_categories_are_only_candidates(self):
        result=compare_categories(parse_identity('{"category":"books"}'),parse_identity('{"category":"vinyl_sleeves"}'))
        self.assertEqual(result['status'],'candidate_violated')
        self.assertFalse(result['scorable'])
        self.assertFalse(result['reviewed'])
        self.assertIsNone(result['value'])

    def test_cropped_out_or_request_failure_is_unavailable(self):
        p=parse_identity('{"category":"absent"}')
        self.assertEqual(compare_categories(p,p,comparable=False)['status'],'unavailable')
        self.assertEqual(compare_categories(parse_identity(None),p)['status'],'unavailable')


if __name__=='__main__':unittest.main()
