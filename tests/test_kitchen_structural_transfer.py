import unittest
from scripts.kitchen_structural_transfer import parse_answers,compare,comparable_answer


class KitchenStructureTest(unittest.TestCase):
    def field(self,answer,visibility):return dict(status='valid',data=dict(answer=answer,visibility=visibility))

    def test_partial_positive_but_not_partial_absence(self):
        self.assertEqual(comparable_answer(self.field('present','partial'))[0],'present')
        self.assertEqual(comparable_answer(self.field('absent','partial'))[0],'unknown')

    def test_unknown_is_local_and_clear_difference_retained(self):
        a=dict(fields=dict(K1=self.field('present','clear'),K2=self.field('unknown','partial')))
        b=dict(fields=dict(K1=self.field('absent','clear'),K2=self.field('present','clear')))
        rows=compare(a,b,[dict(id='K1'),dict(id='K2')])
        self.assertEqual([r['status'] for r in rows],['candidate_structural_layout_mismatch','unknown'])

    def test_missing_items_not_fabricated(self):
        p=parse_answers('{"evidence":[]}')
        self.assertEqual(p['status'],'partial');self.assertEqual(p['fields']['K3']['status'],'unavailable')

    def test_bad_coordinates_reject_only_affected_item(self):
        raw='{"evidence":[{"id":"K1","answer":"present","visibility":"clear","visual_basis":"boundary","boundary_type":"facade_joint","segments":[[0,0,1001,200]]}]}'
        self.assertEqual(parse_answers(raw)['fields']['K1']['status'],'unavailable')


if __name__=='__main__':unittest.main()
