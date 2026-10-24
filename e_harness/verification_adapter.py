"""Small, diagnostic-only visual answer transport; never produces Energy values.

Book answer parsing/comparison stays in the existing controlled experiment.
No provider API key is read and no model command is executed through a shell.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

from PIL import Image

from .model_client import token_counts


def contract(document):
    """Allowlist the model input: coordinator labels/metadata must stay outside it."""
    if not isinstance(document, dict) or set(document) != {'system', 'user', 'schema'}:
        raise ValueError('Only system, user and schema may enter the model contract; labels are forbidden')
    if not all(isinstance(document[k], str) and document[k].strip() for k in ('system', 'user')):
        raise ValueError('Nonempty frozen system/user text required')
    from scripts.group_statistical_controls import SCHEMA
    if document['schema'] != SCHEMA:
        raise ValueError('This minimal pilot supports the existing two-question book schema only')
    return deepcopy(document)


def parse_answer(raw):
    from scripts.group_statistical_controls import parse_prediction
    try:
        return parse_prediction(raw)
    except (ValueError, TypeError) as exc:
        return dict(status='unavailable', fields={}, schema_errors=[str(exc)])


def scrub_error(text):
    """Error text only: never persist auth headers, key-like strings or image bodies."""
    text = re.sub(r'(?i)(authorization\s*[:=]\s*)[^\r\n]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)\b(?:bearer\s+\S+|sk-[A-Za-z0-9_-]+)', '[REDACTED]', text)
    text = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', '[IMAGE OMITTED]', text)
    return text


def answer_packet(raw, *, backend, source_kind, protocol, model=None, metadata=None):
    packet = dict(backend=backend, source_kind=source_kind, model_requested=model,
        model_observed=None, actual_input=contract(protocol), raw_answer=raw,
        parsed=parse_answer(raw), metadata=deepcopy(metadata or {}), reviewed=False,
        energy_contribution=False, usage='provisional/debug')
    packet['status'] = packet['parsed']['status']
    return packet


def replay(raw, protocol, *, source_kind, model=None):
    if source_kind not in ('mock', 'historical_real'):
        raise ValueError('Replay must explicitly identify mock or historical_real')
    return answer_packet(raw, backend='replay', source_kind=source_kind,
        protocol=protocol, model=model, metadata=dict(new_model_calls=0))


def import_subagent(document, protocol):
    """Import a recorded answer, not an automatic Desktop subagent invocation."""
    actual = document.get('actual_input', {})
    recorded_prompt = actual.get('message', '')
    protocol = contract(protocol)
    if not all(protocol[k] in recorded_prompt for k in ('system', 'user')):
        raise ValueError('Recorded subagent input does not contain the frozen prompt')
    raw = document.get('raw_answer')
    if not isinstance(raw, str):
        raise ValueError('Recorded raw_answer text required; parsed predictions are not raw answers')
    packet = answer_packet(raw, backend='subagent_import', source_kind='historical_real',
        protocol=protocol, model=actual.get('model'), metadata=dict(new_model_calls=0,
        recorded_input=deepcopy(actual), original_usage=deepcopy(document.get('usage')),
        input_isolation='Historical supplied record only; strict filesystem isolation not established'))
    packet['model_observed'] = deepcopy(document.get('model_observed'))
    return packet


def compare_answers(reference, rendered, questions, *, image_pair=None):
    from scripts.group_statistical_controls import answer_value, compare_values
    rows, ids, fields = [], set(), set()
    for question in questions:
        eid, field = question['evidence_id'], question['field']
        if eid in ids or field in fields or field not in ('horizontal_stack', 'upright_books'):
            raise ValueError('Evidence IDs and answer fields must be unique and supported')
        ids.add(eid); fields.add(field)
        # Process failure invalidates its output; missing fields alone preserve valid siblings.
        values = [answer_value(p['parsed'], field) if p['status'] in ('valid', 'partial') else None
                  for p in (reference, rendered)]
        rows.append(dict(evidence_id=eid, field=field, region_id=question.get('region_id'),
            group_id=question.get('group_id'), energy=question.get('energy'),
            claim=question.get('claim'), question=question['question'],
            provenance=deepcopy(question.get('provenance')), reference_answer=values[0],
            render_answer=values[1], status=compare_values(*values), reviewed=False,
            value=None, scorable=False, energy_contribution=False,
            uncertainty='VLM answer is not GT; mismatches require independent review'))
    if image_pair is None and all(p.get('image_binding') for p in (reference, rendered)):
        image_pair = dict(reference_rgb=reference['image_binding']['source_rgb'],
                          render_rgb=rendered['image_binding']['source_rgb'])
    return dict(reference=reference, render=rendered, results=rows, image_pair=deepcopy(image_pair), reviewed=False,
        usage='provisional/debug', energy_contribution=False, formal_eligible=False)


def validate_diagnostics(document):
    """Recompute comparisons on import; never trust externally supplied verdicts."""
    if not isinstance(document, dict) or not isinstance(document.get('results'), list):
        raise ValueError('Expected adapter reference/render/results document')
    packets = []
    for side in ('reference', 'render'):
        old = document[side]
        if old.get('backend') not in ('codex_cli', 'subagent_import', 'replay'):
            raise ValueError('Unknown verification backend')
        if old.get('source_kind') not in ('mock', 'historical_real', 'live_model'):
            raise ValueError('Explicit answer provenance required')
        packet = deepcopy(old)
        packet['parsed'] = parse_answer(old.get('raw_answer'))
        if old.get('status') in ('valid', 'partial'):
            packet['status'] = packet['parsed']['status']
        packet.update(reviewed=False, energy_contribution=False)
        packets.append(packet)
    if packets[0]['actual_input'] != packets[1]['actual_input']:
        raise ValueError('Both sides must use exactly the same frozen contract')
    contract(packets[0]['actual_input'])
    return compare_answers(*packets, document['results'], image_pair=document.get('image_pair'))


def cli_options(runtime):
    # A separate provider ID is required: 0.163.0 forbids overriding built-in openai.
    # Saved ChatGPT auth is used; no env_key, API key or auth file copy is involved.
    provider = ('{name="OpenAI verification",wire_api="responses",'
        'base_url="https://chatgpt.com/backend-api/codex",requires_openai_auth=true,'
        'request_max_retries=0,stream_max_retries=0,supports_websockets=false}')
    options = {'model_provider': 'verification_openai', 'sqlite_home': str(runtime),
        'log_dir': str(runtime), 'web_search': 'disabled', 'project_doc_max_bytes': 0,
        'features.shell_tool': False, 'tools.view_image': False, 'features.multi_agent': False,
        'features.hooks': False, 'features.apps': False, 'features.plugins': False,
        'features.memories': False, 'features.goals': False, 'features.shell_snapshot': False,
        'shell_environment_policy.inherit': 'none', 'model_reasoning_effort': 'low'}
    args = ['-c', 'model_providers.verification_openai='+provider]
    for key, value in options.items():
        args += ['-c', key+'='+json.dumps(value)]
    return args


def cli_environment():
    # Preserve normal auth location, do not export project credentials or override HOME.
    allowed = ('HOME', 'CODEX_HOME', 'PATH', 'USER', 'LOGNAME', 'LANG', 'LC_ALL',
               'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
               'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
    return {k: os.environ[k] for k in allowed if k in os.environ}


def run_process(args, *, cwd, stdin, timeout):
    """One launch, no retries; kill the complete child process group on timeout."""
    process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, shell=False, env=cli_environment(), start_new_session=True)
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise


def probe_cli(image, protocol, *, executable='codex', timeout=35):
    """Local-only input construction, version and login checks. No inference."""
    protocol = contract(protocol)
    result = dict(model_calls=0, strict_blind_test=False, filesystem_read_confined=False)
    try:
        with tempfile.TemporaryDirectory(prefix='projecte-cli-probe-') as directory:
            root = Path(directory); work = root/'input'; runtime = root/'state'
            work.mkdir(); runtime.mkdir()
            staged = work/(uuid.uuid4().hex+'.png')
            with Image.open(image) as im:
                rgb = im.convert('RGB'); rgb.save(staged)
            for name, args in (('version', ['--version']), ('login', ['login', 'status'])):
                code, out, err = run_process([executable, *args], cwd=work, stdin='', timeout=timeout)
                if name == 'version':
                    result['cli_version'] = out.strip() if code == 0 else None
                else:
                    result['logged_in'] = code == 0 and 'logged in' in (out+err).lower()
                    result['auth_method'] = 'ChatGPT' if 'chatgpt' in (out+err).lower() else 'unknown'
                if code:
                    raise ValueError(name+' check failed: '+scrub_error(err))
            prompt = 'System:\n'+protocol['system']+'\n\nUser:\n'+protocol['user']
            code, out, err = run_process([executable, '--no-daemon', '-a', 'never',
                *cli_options(runtime), 'debug', 'prompt-input', '--image', str(staged), '--', prompt],
                cwd=work, stdin='', timeout=timeout)
            if code:
                raise ValueError('Local input check failed: '+scrub_error(err))
            messages = json.loads(out)  # Contains Base64 in memory only, never persisted.
            parts = [p for m in messages for p in m.get('content', [])]
            images = [p for p in parts if p.get('type') == 'input_image']
            texts = [p.get('text', '') for p in parts if p.get('type') == 'input_text']
            import base64
            import io
            same_pixels = False
            if len(images) == 1:
                data = base64.b64decode(images[0]['image_url'].split(',', 1)[1])
                with Image.open(io.BytesIO(data)) as received:
                    same_pixels = received.convert('RGB').tobytes() == rgb.tobytes() and received.size == rgb.size
            leaks = [word for word in ('construction_expected', 'source_construction',
                'clear_T1', 'clear_T2', 'verification_results.json') if any(word in t for t in texts)]
            exact_prompt = any(t == prompt for t in texts)
            result.update(image_attachments=len(images), decoded_pixels_equal=same_pixels,
                frozen_prompt_present=exact_prompt, forbidden_context_terms=leaks,
                message_roles=[m.get('role') for m in messages],
                global_cli_context_present=any(m.get('role') == 'developer' for m in messages),
                input_text_characters=sum(len(t) for t in texts),
                model_input_saved_without_base64=True)
            result['status'] = 'available' if same_pixels and exact_prompt and not leaks and result['logged_in'] else 'unavailable'
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        result.update(status='unavailable', error=scrub_error(f'{type(exc).__name__}: {exc}'))
    return result


def codex_answer(image, protocol, *, ledger, model='gpt-6-sol', timeout=180,
                 executable='codex'):
    """Maximum two attempts per caller ledger, even after failure. No tool execution."""
    protocol = contract(protocol)
    packet = answer_packet(None, backend='codex_cli', source_kind='live_model',
        protocol=protocol, model=model)
    packet.update(request_submitted=None, elapsed_seconds=0., token_usage=token_counts(None),
        isolation=dict(strict_blind_test=False, filesystem_read_confined=False,
            tools_disabled=True, project_cwd=False,
            reason='Temporary cwd and disabled tools reduce exposure; read-only sandbox can read beyond cwd; CLI global context/auth still exists'))
    image = Path(image).resolve()
    try:
        if len(ledger) >= 2 or any(r['image']==str(image) for r in ledger):
            raise ValueError('Two-request budget exhausted or image already attempted; no retry')
        if not 0 < timeout <= 300:
            raise ValueError('Timeout must be in (0, 300] seconds')
        with Image.open(image) as im:
            im.verify()
            packet['image_binding'] = dict(source_rgb=str(image), image_size=list(im.size))
        if shutil.which(executable) is None:
            raise FileNotFoundError('Codex executable unavailable')
    except (OSError, ValueError) as exc:
        packet.update(status='unavailable', request_submitted=False, error=scrub_error(str(exc)))
        return packet
    attempt = dict(image=str(image), status='reserved', model=model)
    ledger.append(attempt)  # Reserve before launch, including failures/timeouts.
    tick = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='projecte-verifier-') as directory:
            root = Path(directory); work = root/'input'; runtime = root/'state'
            work.mkdir(mode=0o700); runtime.mkdir(mode=0o700)
            staged = work/(uuid.uuid4().hex+'.png')
            # Decode to PNG to avoid names, EXIF, comments or other hidden label metadata.
            with Image.open(image) as im:
                im.convert('RGB').save(staged)
                image_size = list(im.size)
            prompt = 'System:\n'+protocol['system']+'\n\nUser:\n'+protocol['user']
            (work/'question.txt').write_text(prompt)
            (work/'schema.json').write_text(json.dumps(protocol['schema'], ensure_ascii=False))
            args = [executable, '--no-daemon', '-a', 'never', *cli_options(runtime),
                'exec', '--ignore-user-config', '--model', model, '--sandbox', 'read-only',
                '--skip-git-repo-check', '--ephemeral', '--image', str(staged),
                '--output-schema', str(work/'schema.json'), '--output-last-message', str(runtime/'answer.json'),
                '--json', '--', '-']
            packet['invocation'] = dict(argv=args, stdin=prompt, staged_image=staged.name,
                image_size=image_size, shell=False, automatic_retries=0,
                stdin_contains_expected_labels=False, necessary_input_files=sorted(p.name for p in work.iterdir()))
            code, stdout, stderr = run_process(args, cwd=work, stdin=prompt, timeout=timeout)
            packet['exit_code'] = code
            packet['stderr'] = scrub_error(stderr)
            events = []
            for line in stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                events.append(event)
            # Keep final answers, status, usage and model metadata, not reasoning/tool contents.
            packet['event_types'] = [e.get('type') for e in events]
            for event in events:
                if event.get('type') == 'turn.completed':
                    packet['token_usage'] = token_counts(event.get('usage'))
                    packet['reported_usage'] = event.get('usage')
                if event.get('model'):
                    packet['model_observed'] = event['model']
            tool_events = [e for e in events if e.get('item', {}).get('type') in
                ('command_execution', 'mcp_tool_call', 'web_search', 'file_change')]
            raw = (runtime/'answer.json').read_text() if (runtime/'answer.json').is_file() else None
            packet.update(raw_answer=raw, parsed=parse_answer(raw),
                status='unavailable' if code or tool_events else parse_answer(raw)['status'],
                unexpected_tool_events=bool(tool_events),
                cli_errors=[scrub_error(json.dumps(e,ensure_ascii=False)) for e in events
                            if e.get('type') in ('error', 'turn.failed')])
            if code == 0 and raw is not None:
                packet['request_submitted'] = True
            if tool_events:
                packet['error'] = 'Unexpected tool activity: output withheld'
    except (OSError, subprocess.TimeoutExpired) as exc:
        packet.update(status='unavailable', error=scrub_error(f'{type(exc).__name__}: {exc}'))
    packet['elapsed_seconds'] = time.monotonic()-tick
    attempt.update(status=packet['status'], elapsed_seconds=packet['elapsed_seconds'])
    return packet
