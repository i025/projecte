"""CPU protocol/abstention contracts; no image/model observations."""
import json
import unittest

from scripts.group_abstention_calibration import frozen_protocol,assess
from scripts.group_statistical_controls import USER as OLD_USER,parse_prediction,answer_value


class AbstentionProtocolTests(unittest.TestCase):
    def test_new_questions_do_not_ask_whether_clearly_seen(self):
        protocol=frozen_protocol()
        self.assertIn('Q1：图中是否存在至少两本水平叠放的书籍？',protocol['user'])
        self.assertIn('Q2：图中是否存在竖直站立摆放的书籍？',protocol['user'])
        self.assertNotIn('清楚看到',protocol['user'])
        self.assertIn('清楚看到',OLD_USER)
        self.assertNotEqual(protocol['user'],OLD_USER)

    def test_no_requires_clear_evidence_and_unknown_covers_insufficient_visibility(self):
        protocol=frozen_protocol()
        self.assertEqual(protocol['definitions'],dict(
            yes='有充分可见证据确认该排列存在。',
            no='相关书架区域足够清晰，能够确认该排列不存在。',
            unknown='由于模糊、遮挡或类别歧义，无法可靠判断。'))
        for key,text in protocol['definitions'].items():
            self.assertIn(key+'：'+text,protocol['system'])
        self.assertIn('不要把“没有清楚看到”直接等同于“不存在”',protocol['system'])

    def test_two_exact_single_enum_fields_and_fresh_protocol(self):
        first=frozen_protocol();second=frozen_protocol()
        self.assertEqual(first,second)
        schema=first['schema']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']),{'horizontal_stack','upright_books'})
        for field in schema['required']:
            self.assertEqual(schema['properties'][field]['enum'],['yes','no','unknown'])
        first['schema']['required'].clear()
        self.assertEqual(len(frozen_protocol()['schema']['required']),2)

    def test_clear_control_candidate_matches_and_directional_errors(self):
        self.assertEqual(assess('yes','yes'),'correct')
        self.assertEqual(assess('no','no'),'correct')
        self.assertEqual(assess('no','yes'),'false_positive')
        self.assertEqual(assess('yes','no'),'false_negative')

    def test_blurred_unreviewed_label_never_becomes_correct_or_error(self):
        for prediction in ('yes','no'):
            self.assertEqual(assess(None,prediction),'expected_unreviewed')
        self.assertEqual(assess(None,'unknown'),'unknown')
        self.assertEqual(assess(None,None),'unavailable')

    def test_unknown_not_correct_and_unavailable_not_model_abstention(self):
        for expected in ('yes','no',None):
            self.assertEqual(assess(expected,'unknown'),'unknown')
            self.assertEqual(assess(expected,None),'unavailable')

    def test_raw_unknown_is_preserved_and_not_an_invented_negative(self):
        packet=parse_prediction('{"horizontal_stack":"unknown","upright_books":"yes"}')
        self.assertEqual(packet['status'],'valid')
        self.assertEqual(answer_value(packet,'horizontal_stack'),'unknown')
        self.assertEqual(answer_value(packet,'upright_books'),'yes')

    def test_invalid_enum_is_unavailable_without_losing_the_other_field(self):
        packet=parse_prediction(json.dumps(dict(horizontal_stack='yes|no|unknown',upright_books='yes')))
        self.assertEqual(packet['status'],'partial')
        self.assertIsNone(answer_value(packet,'horizontal_stack'))
        self.assertEqual(answer_value(packet,'upright_books'),'yes')


if __name__=='__main__':unittest.main()
