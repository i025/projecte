"""Synthetic CPU contracts only; fixtures are never observations or real answers.

No credentials, shell startup files, GPU, models, Blender, or real network are
used. Every image, answer, key, and response below is a synthetic test fixture.
"""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import requests

from scripts import group_vlm_verification as group
from benchmark.vlm import VLMClient


class GroupVLMTests(unittest.TestCase):
    def answers(self, **changes):
        return dict(present='yes', shelf_sections='2', arrangement='mixed') | changes

    def packet(self, **changes):
        return group.parse_fields(json.dumps(self.answers(**changes)))

    def png_url(self, color='gray', size=(24, 16), image_format='PNG'):
        buffer = io.BytesIO()
        Image.new('RGB', size, color).save(buffer, format=image_format)
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')

    def payload(self, size=(24, 16)):
        return dict(model=group.MODEL, max_tokens=1, temperature=.9, stream=False,
                    response_format=dict(type='json_object'), messages=[
                        dict(role='system', content='Synthetic generic client system'),
                        dict(role='user', content=[dict(type='text', text=group.USER),
                            dict(type='image_url', image_url=dict(url=self.png_url(size=size), detail='high')),
                            dict(type='image_url', image_url=dict(url=self.png_url('white', size), detail='high'))])])

    def assert_non_scoring(self, rows):
        self.assertEqual([row['id'] for row in rows], ['present', 'shelf_sections', 'arrangement'])
        self.assertEqual([row['energy'] for row in rows], ['semantic', 'spatial', 'statistical'])
        for row in rows:
            self.assertIs(row['scorable'], False)
            self.assertIs(row['reviewed'], False)
            self.assertIsNone(row['score'])
            self.assertIsNone(row['value'])
            self.assertEqual(row['q'], 0.)
            self.assertEqual(row['usage'], 'provisional/debug')
            self.assertEqual(row['region_id'], 'R2')
            self.assertEqual(row['group_id'], 'bw_0074_R2_books')

    def test_exact_json_and_single_whole_fence(self):
        expected = self.answers()
        raw = json.dumps(expected)
        for text in (raw, ' \n' + raw + '\n ', '```json\n' + raw + '\n```', '```\n' + raw + '\n```'):
            with self.subTest(text=text):
                packet = group.parse_fields(text)
                self.assertEqual(packet['status'], 'valid')
                self.assertEqual(packet['answers'], expected)
                self.assertTrue(packet['schema_valid'])
                self.assertEqual(packet['schema_errors'], [])
                for name, value in expected.items():
                    self.assertEqual(packet['fields'][name]['value'], value)
                    self.assertEqual(packet['fields'][name]['validation_status'], 'valid')
                    self.assertIsNone(packet['fields'][name]['error'])

    def test_every_string_enum_is_accepted_including_unknown(self):
        self.assertEqual(group.ENUMS, dict(present=['yes', 'no', 'unknown'],
            shelf_sections=['0', '1', '2', '3+', 'unknown'],
            arrangement=['upright', 'horizontal', 'mixed', 'unknown']))
        for name, allowed in group.ENUMS.items():
            for value in allowed:
                with self.subTest(name=name, value=value):
                    packet = self.packet(**{name: value})
                    self.assertEqual(packet['status'], 'valid')
                    self.assertEqual(packet['answers'][name], value)
        packet = self.packet(**{name: 'unknown' for name in group.ENUMS})
        self.assertEqual(packet['status'], 'valid')
        self.assertEqual(packet['answers'], dict.fromkeys(group.ENUMS, 'unknown'))

    def test_non_object_non_json_duplicate_and_nonfinite_are_rejected(self):
        answer = json.dumps(self.answers())
        rejected = [None, {}, [], 1, True, 'null', 'true', '123', '"answer"', '[]',
                    'prefix ' + answer, answer + ' trailing', answer + answer,
                    '```json\n' + answer + '\n```\nextra',
                    '```json\n' + answer + '\n```\n```json\n' + answer + '\n```',
                    "{'present':'yes'}", '{"present":"yes",}',
                    '{"present":"no","present":"yes","shelf_sections":"2","arrangement":"mixed"}',
                    '{"nested":{"a":1,"a":2}}',
                    '{"present":NaN}', '{"shelf_sections":Infinity}',
                    '{"arrangement":-Infinity}', '{"extra":{"nested":NaN}}']
        for raw in rejected:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                group.parse_fields(raw)

    def test_missing_fields_only_remove_their_own_availability(self):
        for missing in group.ENUMS:
            answers = self.answers()
            del answers[missing]
            packet = group.parse_fields(json.dumps(answers))
            with self.subTest(missing=missing):
                self.assertEqual(packet['status'], 'partial')
                self.assertFalse(packet['schema_valid'])
                self.assertEqual(packet['answers'], answers)
                self.assertEqual(packet['fields'][missing]['validation_status'], 'unavailable')
                self.assertIsNone(packet['fields'][missing]['value'])
                self.assertFalse(packet['fields'][missing]['field_present'])
                self.assertEqual(packet['fields'][missing]['error'], 'Missing field')
                self.assertTrue(all(packet['fields'][key]['validation_status'] == 'valid' for key in answers))
        empty = group.parse_fields('{}')
        self.assertEqual(empty['status'], 'partial')
        self.assertEqual(empty['answers'], {})
        self.assertTrue(all(field['validation_status'] == 'unavailable' for field in empty['fields'].values()))

    def test_invalid_types_and_enums_are_independent_not_coerced(self):
        invalid = dict(present=[True, False, 0, None, [], {}, 'YES', 'yes ', 'uncertain'],
                       shelf_sections=[0, 1, 2, 3, 2., True, None, [], '3', '2 ', 'many'],
                       arrangement=[True, None, [], {}, 'Upright', 'upright ', 'vertical'])
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    packet = self.packet(**{name: value})
                    self.assertEqual(packet['status'], 'partial')
                    self.assertEqual(packet['answers'], {k: v for k, v in self.answers().items() if k != name})
                    field = packet['fields'][name]
                    self.assertEqual(field['validation_status'], 'unavailable')
                    self.assertIsNone(field['value'])
                    self.assertEqual(field['raw_value'], value)
                    self.assertTrue(field['field_present'])
                    self.assertEqual(field['error'], 'Invalid enum/type')

    def test_additional_fields_are_schema_errors_but_keep_valid_answers(self):
        packet = group.parse_fields(json.dumps(self.answers(explanation='Synthetic extra fixture')))
        self.assertEqual(packet['status'], 'partial')
        self.assertFalse(packet['schema_valid'])
        self.assertEqual(packet['answers'], self.answers())
        self.assertTrue(packet['schema_errors'])
        self.assertIn('explanation', ' '.join(packet['schema_errors']))
        self.assertTrue(all(field['validation_status'] == 'valid' for field in packet['fields'].values()))
        rows = group.compare_fields(packet, self.packet())
        self.assertEqual([row['status'] for row in rows], ['satisfied'] * 3)
        self.assert_non_scoring(rows)

    def test_comparison_saves_both_answers_without_scores(self):
        reference = self.packet()
        rendered = self.packet(present='no', shelf_sections='3+', arrangement='upright')
        before = deepcopy((reference, rendered))
        rows = group.compare_fields(reference, rendered)
        self.assertEqual((reference, rendered), before)
        self.assertEqual([row['status'] for row in rows], ['candidate_violated'] * 3)
        self.assert_non_scoring(rows)
        for row in rows:
            self.assertEqual(row['reference_answer'], reference['answers'][row['id']])
            self.assertEqual(row['render_answer'], rendered['answers'][row['id']])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'synthetic_comparison.json'
            group.save(output, dict(fixture='Synthetic; not image evidence',
                                    reference=reference, render=rendered, rows=rows))
            saved = json.loads(output.read_text())
            self.assertEqual(saved['reference']['answers'], self.answers())
            self.assertEqual(saved['render']['answers'], rendered['answers'])
            self.assertEqual(saved['rows'], rows)

    def test_equal_known_fields_are_satisfied_and_unknown_abstains(self):
        rows = group.compare_fields(self.packet(), self.packet())
        self.assertEqual([row['status'] for row in rows], ['satisfied'] * 3)
        self.assert_non_scoring(rows)
        for name in group.ENUMS:
            for reference, rendered in ((self.packet(**{name: 'unknown'}), self.packet()),
                                        (self.packet(), self.packet(**{name: 'unknown'}))):
                with self.subTest(name=name):
                    rows = group.compare_fields(reference, rendered)
                    self.assert_non_scoring(rows)
                    self.assertEqual({row['id']: row['status'] for row in rows},
                                     {key: 'unknown' if key == name else 'satisfied' for key in group.ENUMS})

    def test_partial_validation_keeps_other_comparisons_available(self):
        for name in group.ENUMS:
            for reference, rendered in ((self.packet(**{name: None}), self.packet()),
                                        (self.packet(), self.packet(**{name: None}))):
                with self.subTest(name=name):
                    rows = group.compare_fields(reference, rendered)
                    self.assert_non_scoring(rows)
                    self.assertEqual({row['id']: row['status'] for row in rows},
                                     {key: 'unavailable' if key == name else 'satisfied' for key in group.ENUMS})
                    unavailable = next(row for row in rows if row['id'] == name)
                    self.assertTrue(unavailable['reference_field_error'] or unavailable['render_field_error'])

    def test_request_failure_is_unavailable_and_not_unknown(self):
        failed = dict(status='unavailable', answers=None, error='Synthetic failure')
        for reference, rendered in ((failed, self.packet()), (self.packet(), failed), (failed, failed)):
            rows = group.compare_fields(reference, rendered)
            self.assert_non_scoring(rows)
            self.assertEqual([row['status'] for row in rows], ['unavailable'] * 3)

    def test_payload_uses_same_protocol_and_leaves_original_unchanged(self):
        payload = self.payload()
        before = deepcopy(payload)
        result = group.request_payload(payload)
        self.assertEqual(payload, before)
        self.assertEqual(result['messages'][0], dict(role='system', content=group.SYSTEM))
        self.assertEqual(result['messages'][1], payload['messages'][1])
        self.assertEqual(result['model'], 'openai/gpt-6-sol')
        self.assertEqual(result['temperature'], .1)
        self.assertEqual(result['max_tokens'], 600)
        self.assertNotIn('response_format', result)
        self.assertIs(result['stream'], False)
        self.assertEqual(group.request_payload(result), result)
        result['messages'][1]['content'][0]['text'] = 'Synthetic mutation'
        self.assertEqual(payload, before)

    def test_payload_accepts_matching_pngs_up_to_1024_pixels(self):
        for size in ((1024, 558), (558, 1024), (24, 16)):
            with self.subTest(size=size):
                result = group.request_payload(self.payload(size))
                self.assertEqual(len(result['messages'][1]['content']), 3)

    def test_payload_rejects_wrong_prompt_roles_model_counts_and_images(self):
        cases = []
        bad = self.payload(); bad['messages'][1]['content'][0]['text'] = 'Synthetic leading expected answer'; cases.append(bad)
        bad = self.payload(); bad['messages'][1]['role'] = 'assistant'; cases.append(bad)
        bad = self.payload(); bad['model'] = 'synthetic-other-model'; cases.append(bad)
        bad = self.payload(); bad['messages'].pop(); cases.append(bad)
        bad = self.payload(); bad['messages'][1]['content'].pop(); cases.append(bad)
        bad = self.payload(); bad['messages'][1]['content'].append(deepcopy(bad['messages'][1]['content'][-1])); cases.append(bad)
        bad = self.payload(); bad['messages'][1]['content'][1]['type'] = 'text'; cases.append(bad)
        bad = self.payload(); bad['messages'][1]['content'][1]['image_url']['url'] = self.png_url(size=(25, 16)); cases.append(bad)
        cases.append(self.payload(size=(1025, 16)))
        cases.append(self.payload(size=(16, 1025)))
        for url in ('https://example.invalid/synthetic.png', 'data:image/jpeg;base64,AAAA',
                    'data:image/png;base64,not-base64!',
                    'data:image/png;base64,' + base64.b64encode(b'Synthetic non-image').decode('ascii'),
                    self.png_url(image_format='JPEG')):
            bad = self.payload(); bad['messages'][1]['content'][1]['image_url']['url'] = url; cases.append(bad)
        for index, bad in enumerate(cases):
            before = deepcopy(bad)
            with self.subTest(case=index), self.assertRaises(ValueError):
                group.request_payload(bad)
            self.assertEqual(bad, before)

    def test_redaction_removes_keys_bearers_sensitive_headers_and_image_echoes(self):
        key = 'KnownKey-Synthetic-DoNotUse'
        image_token = base64.b64encode(b'\xffSynthetic image echo fixture').decode('ascii')
        original = dict(message='Key=' + key + ' Authorization: bEaReR SyntheticOtherToken',
            Headers=dict(trace='Synthetic sensitive header dictionary'),
            request_headers=dict(Authorization='Bearer ' + key),
            Authorization='Bearer ' + key, Proxy_Authorization='SyntheticProxyToken',
            API_KEY=key, x_api_key=key, access_token='SyntheticAccess',
            refresh_token='SyntheticRefresh', secret='SyntheticSecret',
            nested=[dict(text='Raw image: ' + image_token,
                         escaped=image_token.replace('/', '\\/'),
                         url='data:image/png;base64,' + image_token),
                    'data:image/jpeg;base64,QUJDREVGRw==', 'Safe synthetic text'])
        before = deepcopy(original)
        result = group.redact(original, key, image_tokens=(image_token,))
        self.assertEqual(original, before)
        self.assertEqual(set(result), {'message', 'nested'})
        text = json.dumps(result)
        for forbidden in (key, 'SyntheticOtherToken', 'SyntheticProxyToken', 'Synthetic sensitive',
                          'SyntheticAccess', 'SyntheticRefresh', 'SyntheticSecret',
                          image_token, image_token.replace('/', '\\/'), 'data:image', 'QUJDREVGRw=='):
            self.assertNotIn(forbidden, text)
        self.assertIn('Safe synthetic text', text)
        self.assertIn('[redacted]', text)
        self.assertIn('[image payload redacted]', text)

    def client_fixture(self, out):
        paths = []
        for name, color in (('full', 'gray'), ('marked', 'white')):
            path = out / (name + '.png')
            Image.new('RGB', (24, 16), color).save(path)
            paths.append(path)
        client = VLMClient(out / 'vlm_requests.json', api_key='KnownKey-Synthetic-DoNotUse',
            base_url='https://example.invalid/v1', model=group.MODEL, request_limit=2)
        return client, paths

    def test_stub_client_two_call_budget_no_real_network_or_secret_logging(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            client, images = self.client_fixture(out)
            seen = []
            def post(url, *, json, **kwargs):
                seen.append(group.request_payload(json))
                self.assertFalse(kwargs['allow_redirects'])
                self.assertEqual(url, 'https://example.invalid/v1/chat/completions')
                return SimpleNamespace(status_code=200, json=lambda: dict(model=group.MODEL,
                    usage=dict(prompt_tokens=100, completion_tokens=12, total_tokens=112),
                    choices=[dict(finish_reason='stop', message=dict(content=__import__('json').dumps(self.answers())))]))
            with patch('requests.Session.request', side_effect=AssertionError('Real network forbidden')), \
                 patch('httpx.Client.post', side_effect=AssertionError('Real network forbidden')):
                for side in ('reference', 'render'):
                    result = client.call(images, group.USER, 'Synthetic offline:' + side,
                        session=SimpleNamespace(post=post), max_tokens=600,
                        token_parameter='max_tokens', retry_network=False)
                    self.assertEqual(result['evaluation_status'], 'answered')
                    self.assertEqual(group.parse_fields(result['raw_answer'])['answers'], self.answers())
                stopped = client.call(images, group.USER, 'Synthetic blocked',
                    session=SimpleNamespace(post=post), max_tokens=600,
                    token_parameter='max_tokens', retry_network=False)
            self.assertEqual(stopped['error'], 'request_budget_exhausted')
            self.assertEqual(len(seen), 2)
            self.assertTrue(all(payload['temperature'] == .1 and payload['max_tokens'] == 600 for payload in seen))
            text = (out / 'vlm_requests.json').read_text()
            records = json.loads(text)
            self.assertEqual(len(records), 2)
            self.assertTrue(all(row['automatic_network_retry_enabled'] is False for row in records))
            self.assertTrue(all(row['network_retry'] is False for row in records))
            self.assertTrue(all(row['usage']['total_tokens'] == 112 for row in records))
            self.assertTrue(all(row['latency_seconds'] >= 0 for row in records))
            for secret in ('KnownKey-Synthetic-DoNotUse', 'Authorization', 'data:image', 'base64'):
                self.assertNotIn(secret, text)

    def test_stub_network_failure_consumes_one_attempt_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            client, images = self.client_fixture(out)
            calls = []
            def post(*args, **kwargs):
                calls.append(True)
                raise requests.ConnectionError('Authorization: Bearer KnownKey-Synthetic-DoNotUse')
            with patch('requests.Session.request', side_effect=AssertionError('Real network forbidden')), \
                 patch('httpx.Client.post', side_effect=AssertionError('Real network forbidden')):
                result = client.call(images, group.USER, 'Synthetic failure',
                    session=SimpleNamespace(post=post), max_tokens=600,
                    token_parameter='max_tokens', retry_network=False)
            self.assertEqual(calls, [True])
            self.assertEqual(result['evaluation_status'], 'not_evaluable')
            self.assertEqual(result['error'], 'ConnectionError')
            ledger = (out / 'vlm_requests.json').read_text()
            records = json.loads(ledger)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['outcome'], 'network_error')
            self.assertFalse(records[0]['automatic_network_retry_enabled'])
            self.assertNotIn('KnownKey-Synthetic-DoNotUse', ledger)
            self.assertNotIn('Authorization', ledger)


if __name__ == '__main__':
    unittest.main()
