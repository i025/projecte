import unittest
from scripts.structural_visual_controls import parse_answer,classify


class VisualControlsTest(unittest.TestCase):
    def label(self,value):return dict(answer_candidate=value,human_visibility_review='not_independently_reviewed_construction_label')

    def test_strict_answer_schema(self):
        self.assertEqual(parse_answer('{"internal_divider":"present"}')['value'],'present')
        for raw in ['{"internal_divider":"present|absent|unknown"}','{"internal_divider":"yes"}','{"internal_divider":"present","extra":1}','{"internal_divider":"present","internal_divider":"absent"}']:
            self.assertEqual(parse_answer(raw)['status'],'unavailable')

    def test_false_positive_negative_and_abstention(self):
        for predicted,expected,status in [('present','absent','false_positive'),('absent','present','false_negative'),('unknown','present','abstained')]:
            self.assertEqual(classify(dict(status='valid',value=predicted),self.label(expected))['status'],status)

    def test_occluded_pending_not_scored_as_correct(self):
        label=dict(answer_candidate='unknown',human_visibility_review='unreviewed')
        for value in ('present','absent','unknown'):
            self.assertEqual(classify(dict(status='valid',value=value),label)['status'],'not_scored_visibility_review_pending')

    def test_unavailable_not_replaced_by_expected(self):
        self.assertEqual(classify(parse_answer('bad json'),self.label('present'))['status'],'unavailable')


if __name__=='__main__':unittest.main()
