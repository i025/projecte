"""No model or network: real subprocess behavior is stubbed at the transport boundary."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from e_harness.verification_adapter import (answer_packet, cli_options, codex_answer,
    compare_answers, contract, import_subagent, replay, run_process, scrub_error, validate_diagnostics)
from e_harness.benchmark_offline import run_manifest
from scripts.group_abstention_calibration import frozen_protocol


def inputs():
    p = frozen_protocol()
    return {k: p[k] for k in ('system', 'user', 'schema')}


def questions():
    return [dict(evidence_id='books_'+f, field=f, group_id='G_books', region_id='R_shelf',
        question=q, energy='statistical', reviewed=False)
        for f,q in [('horizontal_stack','图中是否存在至少两本水平叠放的书籍？'),
                    ('upright_books','图中是否存在竖直站立摆放的书籍？')]]


YES = '{"horizontal_stack":"yes","upright_books":"yes"}'
NO = '{"horizontal_stack":"no","upright_books":"yes"}'


class VerificationAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/'source-positive.png'
        Image.new('RGB',(48,32),'gray').save(self.image)
        self.protocol = inputs()

    def pair(self, first=YES, second=NO):
        return compare_answers(replay(first,self.protocol,source_kind='mock'),
            replay(second,self.protocol,source_kind='mock'),questions())

    def test_replay_never_launches_process(self):
        with patch('subprocess.Popen', side_effect=AssertionError('No model')):
            pair = self.pair()
        self.assertEqual([r['status'] for r in pair['results']],['candidate_violated','satisfied'])
        self.assertEqual(pair['reference']['source_kind'],'mock')
        self.assertTrue(all(r['value'] is None and not r['scorable'] and not r['reviewed'] for r in pair['results']))

    def test_bad_json_and_duplicate_keys(self):
        for raw in ('{bad', '[]', '{"horizontal_stack":"yes","horizontal_stack":"no"}'):
            with self.subTest(raw=raw):
                pair = self.pair(second=raw)
                self.assertEqual([r['status'] for r in pair['results']],['unavailable']*2)

    def test_missing_invalid_field_preserves_sibling(self):
        for raw in ('{"upright_books":"yes"}', '{"horizontal_stack":3,"upright_books":"yes"}'):
            pair = self.pair(second=raw)
            self.assertEqual([r['status'] for r in pair['results']],['unavailable','satisfied'])

    def test_unknown_has_no_penalty(self):
        pair = self.pair(second='{"horizontal_stack":"unknown","upright_books":"yes"}')
        self.assertEqual(pair['results'][0]['status'],'unknown')
        self.assertIsNone(pair['results'][0]['value'])

    def test_unavailable_process_cannot_reuse_partial_answer(self):
        pair=self.pair(); pair['render']['status']='unavailable'
        clean=validate_diagnostics(pair)
        self.assertEqual([r['status'] for r in clean['results']],['unavailable']*2)

    def test_import_is_not_inference(self):
        document=dict(raw_answer=YES, actual_input=dict(model='gpt-6-sol',
            message=self.protocol['system']+'\n'+self.protocol['user']),model_observed=['gpt-6-sol'])
        with patch('subprocess.Popen',side_effect=AssertionError('No model')):
            packet=import_subagent(document,self.protocol)
        self.assertEqual(packet['backend'],'subagent_import')
        self.assertEqual(packet['metadata']['new_model_calls'],0)
        self.assertEqual(packet['raw_answer'],YES)
        self.assertEqual(packet['model_observed'],['gpt-6-sol'])

    def test_import_wrong_frozen_prompt_rejected(self):
        with self.assertRaisesRegex(ValueError,'frozen prompt'):
            import_subagent(dict(raw_answer=YES,actual_input={'message':'different'}),self.protocol)

    def test_contract_excludes_expected_and_other_side(self):
        for key in ('expected','construction_expected','render_answer','sample_condition'):
            with self.assertRaisesRegex(ValueError,'labels'):
                contract(dict(self.protocol,**{key:'yes'}))

    def test_mismatched_question_contract_rejected(self):
        pair=self.pair();pair['render']['actual_input']['user']+=' changed'
        with self.assertRaisesRegex(ValueError,'same frozen'):
            validate_diagnostics(pair)

    def test_imported_verdict_is_recomputed_review_not_promoted(self):
        pair=self.pair();pair['results'][0].update(status='satisfied',value=0,reviewed=True)
        self.assertEqual(validate_diagnostics(pair)['results'][0]['status'],'candidate_violated')
        self.assertFalse(validate_diagnostics(pair)['results'][0]['reviewed'])

    def test_duplicate_evidence_ids_rejected(self):
        pair=self.pair();pair['results'].append(deepcopy(pair['results'][0]))
        with self.assertRaises(ValueError):validate_diagnostics(pair)

    def test_missing_image_and_executable_do_not_launch(self):
        with patch('e_harness.verification_adapter.run_process', side_effect=AssertionError('No launch')):
            packet=codex_answer(self.root/'absent.png',self.protocol,ledger=[])
            self.assertFalse(packet['request_submitted'])
            packet=codex_answer(self.image,self.protocol,ledger=[],executable='/nonexistent/codex')
            self.assertFalse(packet['request_submitted'])
            self.assertEqual(packet['status'],'unavailable')

    def test_cli_uses_image_schema_readonly_random_name_and_disabled_tools(self):
        def process(args,*,cwd,stdin,timeout):
            self.assertNotEqual(cwd,self.root)
            self.assertEqual(sorted(p.suffix for p in cwd.iterdir()),['.json','.png','.txt'])
            staged=Path(args[args.index('--image')+1])
            self.assertNotIn('positive',staged.name)
            with Image.open(staged) as im:self.assertEqual(im.size,(48,32))
            self.assertEqual(args[args.index('--sandbox')+1],'read-only')
            self.assertEqual(args[-2:],['--','-'])  # --image accepts variadic arguments!
            self.assertIn('features.shell_tool=false',args)
            self.assertIn('tools.view_image=false',args)
            self.assertIn('request_max_retries=0', ' '.join(args))
            self.assertIn('stream_max_retries=0', ' '.join(args))
            self.assertIn('--ignore-user-config',args)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)
            self.assertNotIn('source-positive',stdin)
            Path(args[args.index('--output-last-message')+1]).write_text(YES)
            return 0,json.dumps(dict(type='turn.completed',usage=dict(input_tokens=11,output_tokens=4))),''
        with patch('shutil.which',return_value='/codex'),patch('e_harness.verification_adapter.run_process',side_effect=process):
            packet=codex_answer(self.image,self.protocol,ledger=[])
        self.assertEqual(packet['status'],'valid')
        self.assertEqual(packet['token_usage']['input_tokens'],11)
        self.assertIsNone(packet['model_observed'])  # requested model is not an observed snapshot
        self.assertFalse(packet['isolation']['strict_blind_test'])

    def test_timeout_no_retry_and_budget_reserved(self):
        ledger=[]
        with patch('shutil.which',return_value='/codex'),patch('e_harness.verification_adapter.run_process',
            side_effect=subprocess.TimeoutExpired('codex',1)) as process:
            packet=codex_answer(self.image,self.protocol,ledger=ledger,timeout=1)
            duplicate=codex_answer(self.image,self.protocol,ledger=ledger)
        self.assertEqual(process.call_count,1)
        self.assertEqual(packet['status'],'unavailable')
        self.assertEqual(len(ledger),1)
        self.assertFalse(duplicate['request_submitted'])
        ledger.append({'image':'second','status':'unavailable'})
        self.assertFalse(codex_answer(self.image,self.protocol,ledger=ledger)['request_submitted'])

    def test_timeout_kills_process_group_without_shell(self):
        from unittest.mock import Mock
        child=Mock(pid=123456)
        child.communicate.side_effect=[subprocess.TimeoutExpired('codex',1), ('','')]
        with patch('subprocess.Popen',return_value=child) as launch, patch('os.killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                run_process(['codex','exec'],cwd=self.root,stdin='frozen',timeout=1)
        self.assertFalse(launch.call_args.kwargs['shell'])
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertEqual(kill.call_args.args[0],123456)

    def test_model_unavailable_is_not_a_negative_visual_answer(self):
        with patch('shutil.which',return_value='/codex'),patch('e_harness.verification_adapter.run_process',
            return_value=(1, '{"type":"error","message":"model not available"}', '')) as process:
            packet=codex_answer(self.image,self.protocol,ledger=[])
        self.assertEqual(process.call_count,1)
        self.assertEqual(packet['status'],'unavailable')
        self.assertIsNone(packet['raw_answer'])

    def test_error_redaction(self):
        message=scrub_error('Authorization: Bearer secret\nsk-test-secret data:image/png;base64,QUJD')
        self.assertNotIn('secret',message)
        self.assertNotIn('QUJD',message)

    def test_process_error_and_tool_activity_withheld(self):
        for code,events in ((1,[]),(0,[{'type':'item.completed','item':{'type':'command_execution'}}])):
            def process(args,**kwargs):
                Path(args[args.index('--output-last-message')+1]).write_text(YES)
                return code,'\n'.join(json.dumps(e) for e in events),'failure'
            with patch('shutil.which',return_value='/codex'),patch('e_harness.verification_adapter.run_process',side_effect=process):
                self.assertEqual(codex_answer(self.image,self.protocol,ledger=[])['status'],'unavailable')

    def test_manifest_results_do_not_change_energy(self):
        manifest=dict(reference_rgb=str(self.image),render_rgb=str(self.image),
            coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='Synthetic same canvas'))
        path=self.root/'manifest.json';path.write_text(json.dumps(manifest))
        baseline=run_manifest(path,self.root/'baseline')
        packet=self.pair(); (self.root/'verification.json').write_text(json.dumps(packet))
        manifest['vlm_verification']='verification.json';path.write_text(json.dumps(manifest))
        report=run_manifest(path,self.root/'attached')
        self.assertEqual(baseline['energies'],report['energies'])
        self.assertEqual(report['diagnostics']['vlm_verification']['evidence']['results'][0]['status'],'candidate_violated')
        self.assertIsNone(report['energies']['semantic']['value'])
        self.assertFalse(report['diagnostics']['vlm_verification']['energy_contribution'])
        self.assertIn('books_horizontal_stack',(self.root/'attached/summary.md').read_text())
        # An invalid optional verification input preserves all RGB results.
        (self.root/'verification.json').write_text('{}')
        report=run_manifest(path,self.root/'broken')
        self.assertEqual(baseline['energies'],report['energies'])
        self.assertEqual(report['diagnostics']['vlm_verification']['status'],'unavailable')


if __name__ == '__main__':
    unittest.main()
