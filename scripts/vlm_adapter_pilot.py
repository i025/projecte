"""Two existing synthetic images; explicit backend, no automatic model retries."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import uuid

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_config import write_json
from e_harness.benchmark_offline import run_manifest
from e_harness.verification_adapter import (codex_answer, compare_answers, contract,
    import_subagent, probe_cli, replay)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    (output/'images').mkdir()
    source = ROOT/'results/group_abstention_calibration/verification_results.json'
    saved = json.loads(source.read_text())
    protocol = contract({k: saved['protocol'][k] for k in ('system', 'user', 'schema')})
    questions = [dict(evidence_id='books_'+field, field=field, region_id='R_shelf', group_id='G_books',
        energy='statistical', question=question, reviewed=False,
        provenance='Reference-side book arrangement protocol, reused unchanged from group_abstention_calibration')
        for field, question in [('horizontal_stack', '图中是否存在至少两本水平叠放的书籍？'),
                                ('upright_books', '图中是否存在竖直站立摆放的书籍？')]]
    images, imports, expected = [], [], []
    for key in ('clear_T1', 'clear_T2'):
        sample = saved['protocol']['samples'][key]
        destination = output/'images'/(uuid.uuid4().hex+'.png')
        origin = Path(sample['image'])
        if not origin.is_file():
            origin = ROOT/'results/group_abstention_calibration/images'/origin.name
        shutil.copyfile(origin, destination)
        images.append(str(destination.resolve()))
        imports.append(import_subagent(saved['cases'][key]['raw_response'], protocol))
        expected.append(deepcopy(sample['source_construction']))
    # Labels are frozen separately; only the three-key contract enters any model.
    write_json(output/'frozen_inputs.json', dict(protocol=protocol, questions=questions,
        images=images, expected=expected, expected_kind='construction_expected, not independently reviewed',
        pair_kind='synthetic_controls_not_real_Agent_Render', source=str(source), reviewed=False))
    (output/'frozen_inputs.json').chmod(0o444)
    write_json(output/'historical_import.json', compare_answers(*imports, questions))
    mocked = [replay(raw, protocol, source_kind='mock') for raw in
        ('{"horizontal_stack":"unknown","upright_books":"yes"}', '{"upright_books":"yes"}')]
    write_json(output/'mock_transport_check.json', compare_answers(*mocked, questions))


def render(output, bundle, inputs):
    font = lambda size: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
    canvas = Image.new('RGB', (1840, 1090), '#f6f8fa'); draw = ImageDraw.Draw(canvas)
    draw.text((24, 16), 'VLM Verification Adapter | existing synthetic controls | unreviewed / debug', fill='#182c45', font=font(27))
    draw.text((24, 62), 'Same frozen questions: horizontal stack (2+ books)?  Upright books?', fill='black', font=font(23))
    for i, side in enumerate(('reference', 'render')):
        x = 24+i*920; packet = bundle[side]
        draw.text((x, 108), 'Synthetic input '+str(i+1)+' | '+packet['backend'], fill='black', font=font(24))
        with Image.open(inputs['images'][i]) as im:
            im = im.convert('RGB'); im.thumbnail((896,704)); canvas.paste(im,(x,150))
        values = packet['parsed'].get('fields', {})
        answers = ' / '.join(str(values.get(f, {}).get('value')) for f in ('horizontal_stack', 'upright_books'))
        expected = inputs['expected'][i]
        texts = [f'Actual H/U: {answers} | status: {packet["status"]}',
            f'Construction expected H/U: {expected["horizontal_stack"]} / {expected["upright_books"]}',
            f'Model requested: {packet.get("model_requested")} | Energy: N/A',
            'Human review: UNREVIEWED. Not a Reference/Agent reconstruction pair.']
        if packet.get('error'):
            texts.append('Error: '+packet['error'][:110])
        for n,line in enumerate(texts):
            draw.text((x, 875+n*34), line, fill='#182c45', font=font(19))
    draw.text((24, 1050), 'Comparison: '+', '.join(r['field']+'='+r['status'] for r in bundle['results']),
        fill='#893d17', font=font(20))
    canvas.save(output/'comparison.png')


def finish(output, backend):
    inputs = json.loads((output/'frozen_inputs.json').read_text())
    protocol, questions = inputs['protocol'], inputs['questions']
    historical = json.loads((output/'historical_import.json').read_text())
    ledger = []
    checks = dict(backend=backend, real_request_budget=2, historical_import_complete=True,
        reviewed=False, runtime_changed=False, energy_formulas_changed=False,
        no_ofox=True, no_new_desktop_subagents=True, strict_blind_test=False)
    if backend == 'codex_cli':
        probe = probe_cli(inputs['images'][0], protocol)
        checks['cli_probe'] = probe
        if probe['status'] == 'available':
            packets = []
            for index, image in enumerate(inputs['images']):
                packet = codex_answer(image, protocol, ledger=ledger)
                packets.append(packet)
                # Keep completed answers even if a later invocation is interrupted.
                write_json(output/('cli_answer_'+str(index+1)+'.json'), packet)
            bundle = compare_answers(*packets, questions)
        else:
            bundle = historical
            checks['fallback'] = 'subagent_import; real programmatic inference blocked by local probe'
    elif backend == 'subagent_import':
        bundle = historical
    else:
        packets = [replay(historical[k]['raw_answer'], protocol, source_kind='historical_real',
            model=historical[k]['model_requested']) for k in ('reference','render')]
        bundle = compare_answers(*packets, questions)
    bundle.update(pair_kind=inputs['pair_kind'], expected_labels=inputs['expected'],
        expected_labels_source='Frozen before current inference; construction_expected, unreviewed')
    checks.update(cli_attempts=ledger, real_model_attempts=len(ledger),
        all_results_diagnostic_only=all(not r['scorable'] and r['value'] is None for r in bundle['results']))
    write_json(output/'verification_results.json', bundle)
    manifest = dict(reference_rgb=inputs['images'][0], render_rgb=inputs['images'][1],
        vlm_verification='verification_results.json', evidence_category='synthetic_oracle',
        camera_comparability='Synthetic same-camera controls, not a reconstruction evaluation',
        coordinates=dict(convention='reference_pixel_xyxy', render_mapping='identity',
            basis='Existing self-authored clear T1/T2 use the same canvas and camera'),
        provenance=dict(pair_kind=inputs['pair_kind'], no_new_images_generated=True))
    write_json(output/'offline_manifest.json', manifest)
    report = run_manifest(output/'offline_manifest.json', output/'offline_report')
    checks.update(offline_appearance_available=report['energies']['appearance']['value'] is not None,
        semantic_energy=report['energies']['semantic']['value'],
        perceptual_energy=report['energies']['perceptual']['value'],
        imported_diagnostics_in_report=report['diagnostics']['vlm_verification']['status'],
        formal_eligible=report['formal_eligible'])
    write_json(output/'integration_checks.json', checks)
    render(output, bundle, inputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','finish'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backend', choices=['replay','subagent_import','codex_cli'], default='replay')
    args = parser.parse_args(); output = args.output.resolve()
    if args.action == 'prepare':
        prepare(output)
    else:
        if (output/'verification_results.json').exists() or (output/'offline_report').exists():
            raise FileExistsError('Completed/attempted experiment output exists; do not rerun')
        # Reserve before inference, including interrupts/timeouts: finishing is never retryable.
        reservation = output/'attempt_started.json'
        with reservation.open('x') as stream:
            json.dump(dict(backend=args.backend, maximum_new_requests=2), stream)
        finish(output, args.backend)


if __name__ == '__main__':
    main()
