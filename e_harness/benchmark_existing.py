"""Evaluate saved Agent RGB pairs; no Agent generation or Blender execution path."""
from collections import Counter
from copy import deepcopy
import argparse
import csv
import json
from pathlib import Path
import re
import time

import numpy as np
from PIL import Image

from .benchmark_config import ENERGIES
from .benchmark_evidence import local_dino_extractor
from .benchmark_offline import fit_render, run_manifest
from .verification_adapter import answer_packet, codex_answer, compare_answers, probe_cli
from scripts.reference_vlm_pilot import (EXISTING_SCENE_PROTOCOL, evidence_from_plan,
    planning_protocol, verification_protocol)


CATEGORY_POLICY = 'reference_only_missing_other_v1'
CATEGORY_RULES = ('\n类别题中的absent仅用于当前图像足够清楚、能确认所问目标不存在；'
    'other仅用于清楚可辨、但属于所列类别之外的内容。遮挡、身份不明或证据不足用unknown或ambiguous，'
    '不得将未检出当作absent。关系题必要对象不可见时仍用unknown。')


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def ensure_saved(path, value):
    """Resume only an identical saved intermediate; never overwrite scientific data."""
    if Path(path).exists():
        if read(path) != value:
            raise ValueError('Saved intermediate differs from frozen inputs: '+Path(path).name)
    else:
        save(path, value)


def category_policy(evidence):
    """Neutral fallbacks frozen before opening any Render; raw planner stays intact."""
    result = deepcopy(evidence)
    for row in result['atomic_evidence']:
        if row['answer_type'] == 'categorical_unknown':
            row['raw_categories'] = deepcopy(row['categories'])
            row['categories'] += [c for c in ('absent', 'other') if c not in row['categories']]
    result['category_policy'] = CATEGORY_POLICY
    return result


def verification_input(evidence):
    protocol, questions = verification_protocol(evidence)
    if evidence.get('category_policy') != CATEGORY_POLICY:
        raise ValueError('Reference-only categorical policy must be frozen')
    protocol['user'] += CATEGORY_RULES
    return protocol, questions


def call_once(folder, stage, image, protocol, config):
    """Reservation survives interruption; no automatic retry, even across resume."""
    folder = Path(folder)
    packet_path, reserved = folder/(stage+'.json'), folder/(stage+'.reservation.json')
    if packet_path.exists():
        packet = read(packet_path)
        if packet.get('actual_input') != protocol:
            raise ValueError('Saved call differs from frozen contract')
        binding=packet.get('image_binding')
        if binding and Path(binding['source_rgb']).resolve() != Path(image).resolve():
            raise ValueError('Saved answer is bound to another image')
        return packet
    if reserved.exists():
        packet = answer_packet(None, backend='codex_cli', source_kind='live_model', protocol=protocol,
                               model=config['model'])
        packet.update(status='unavailable', error='Interrupted reserved attempt; not retried', request_submitted=None)
        return packet
    save(reserved, dict(stage=stage, image=str(image), automatic_retries=0))
    print('VLM start: '+folder.name+'/'+stage, flush=True)
    packet = codex_answer(image, protocol, ledger=[], model=config['model'],
        timeout=config['timeout_seconds'], max_requests=1, request_id=stage)
    save(packet_path, packet)
    print('VLM end: '+folder.name+'/'+stage+' '+packet['status'], flush=True)
    return packet


def reference_plan(pair, root, config):
    folder = root/'references'/pair['task_id']
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/'reference.png'
    # Reference decoding only. No Render, Geometry, task brief or object names enter planning.
    with Image.open(pair['reference_rgb']) as original:
        native_size = list(original.size)
        image = original.convert('RGB')
        image.thumbnail((config['max_edge'], config['max_edge']), Image.Resampling.LANCZOS)
        if target.exists():
            with Image.open(target) as old:
                if old.size != image.size or old.convert('RGB').tobytes() != image.tobytes():
                    raise ValueError('Same task ID has a different frozen Reference RGB')
        else:
            image.save(target)
    if not (folder/'source.json').exists():
        save(folder/'source.json', dict(source_rgb=pair['reference_rgb'], native_size=native_size,
            common_size=list(image.size), transform='Aspect-preserving Reference thumbnail; no content search',
            model_input='Reference RGB only; no task brief, Render, Geometry or object names', reviewed=False))
    settings = dict(protocol_version=config['protocol_version'], evidence_budget=config['evidence_budget'])
    protocol = planning_protocol(**settings)
    planning = call_once(folder, 'planning_response', target, protocol, config)
    evidence_file = folder/'reference_evidence.json'
    evidence = category_policy(evidence_from_plan(planning, image.size, **settings))
    if evidence_file.exists():
        if read(evidence_file) != evidence:
            raise ValueError('Frozen Reference evidence changed')
    else:
        save(evidence_file, evidence)
        evidence_file.chmod(0o444)
    if not evidence['atomic_evidence']:
        return folder, evidence, None, []
    verification, questions = verification_input(evidence)
    packet = call_once(folder, 'reference_answers', target, verification, config)
    return folder, evidence, packet, questions


def evaluate_pair(pair, root, config, extract, extract_provenance):
    folder = root/'pairs'/pair['pair_id']
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'result.json').exists():
        return read(folder/'result.json')
    if (folder/'failure.json').exists():
        return read(folder/'failure.json')
    reference_folder, evidence, ref_packet, questions = None, None, None, []
    planning_error = None
    try:
        reference_folder, evidence, ref_packet, questions = reference_plan(pair, root, config)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        planning_error = f'{type(exc).__name__}: {exc}'
        reference_folder = root/'references'/pair['task_id']
    reference = reference_folder/'reference.png'
    frozen = (reference_folder/'reference_evidence.json').read_bytes() if evidence else None
    # First read of this Render in the evaluation chain follows the Reference freeze.
    with Image.open(reference) as image:
        size = image.size
    with Image.open(pair['render_rgb']) as image:
        rendered, valid, transform = fit_render(image, size)
    render_path = folder/'render.png'
    if not render_path.exists():
        Image.fromarray(rendered).save(render_path)
        Image.fromarray(valid.astype('uint8')*255).save(folder/'valid_pixels.png')
    else:
        with Image.open(render_path) as image:
            if not np.array_equal(np.asarray(image.convert('RGB')), rendered):
                raise ValueError('Saved Render pixels differ; never reuse an answer on a changed image')
        with Image.open(folder/'valid_pixels.png') as image:
            if not np.array_equal(np.asarray(image.convert('L')), valid.astype('uint8')*255):
                raise ValueError('Saved valid-pixel support differs')
    comparison = None
    if questions:
        protocol, _ = verification_input(evidence)
        rendered_packet = call_once(folder, 'render_answers', render_path, protocol, config)
        comparison = compare_answers(ref_packet, rendered_packet, questions,
            image_pair=dict(reference_rgb=str(reference), render_rgb=str(render_path)))
        ensure_saved(folder/'verification_results.json', comparison)
    if frozen is not None and (reference_folder/'reference_evidence.json').read_bytes() != frozen:
        raise ValueError('Frozen Reference evidence changed during Render verification')
    metadata = deepcopy((pair.get('camera_metadata') or {}).get('document', {}))
    original_metadata = deepcopy(metadata)
    # Preserve the original camera record, and label the deterministic RGB-domain
    # adaptation explicitly. This is not a new camera or an execution attestation.
    metadata['historical_native_metadata'] = original_metadata
    metadata['resolution'] = list(size)
    metadata['resolution_scope'] = 'Prepared RGB common grid; native camera metadata retained separately'
    if 'K' in metadata:
        metadata['historical_native_K'] = metadata.pop('K')
    ensure_saved(folder/'camera.json', metadata)
    # Existing raw Scene Graph bounds are not evaluated collision/support Geometry.
    geometry = deepcopy(pair.get('geometry') or dict(status='unavailable', reason='No reliable bound geometry cache'))
    if isinstance(geometry,str):geometry=read(geometry)
    ensure_saved(folder/'geometry.json', geometry)
    auxiliary = dict(scene_graph=pair.get('scene_graph_cache'), visibility=pair.get('group_visibility_cache'),
        reviewed=False, energy_contribution=False, interpretation='Cached generated-side evidence only; names/bounds are not category or visibility GT')
    if pair.get('group_visibility_cache'):
        auxiliary['visibility_statistics'] = read(pair['group_visibility_cache']['source'])
    if pair.get('scene_graph_cache'):
        graph = read(pair['scene_graph_cache']['source'])
        if Path(graph['source_blend']).resolve() != Path(pair['blend']).resolve():
            raise ValueError('Cached Scene Graph belongs to another blend')
        auxiliary['scene_graph_statistics'] = dict(object_count=len(graph['objects']),
            types=dict(Counter(r['type'] for r in graph['objects'])),
            source_blend=graph['source_blend'], evaluated_collision_support_geometry=False)
    ensure_saved(folder/'structural_diagnostics.json', auxiliary)
    manifest = dict(reference_rgb=str(reference), render_rgb=str(render_path), valid_pixels='valid_pixels.png',
        geometry='geometry.json', render_metadata='camera.json', evidence_category='historical_diagnostic',
        coordinates=dict(convention='reference_pixel_xyxy', render_mapping='identity',
            basis='Reference thumbnail; saved Render uniformly fit once with centered invalid padding, no crop/registration'),
        camera_comparability='historical_camera; actual input camera unknown; no trusted execution binding',
        diagnostics=dict(structural_layout='structural_diagnostics.json'),
        provenance=dict(pair_id=pair['pair_id'], task_id=pair['task_id'], run_id=pair['run_id'],
            native_reference=pair['reference_rgb'], native_render=pair['render_rgb'], native_render_transform=transform,
            source_checks=pair.get('provenance'), completion=pair.get('completion'),
            new_agent_executions=0, new_blender_executions=0, alignment_search=False))
    if evidence:
        manifest['reference_evidence'] = str(reference_folder/'reference_evidence.json')
        manifest['diagnostics']['groups'] = str(reference_folder/'reference_evidence.json')
    if comparison:
        manifest['vlm_verification'] = 'verification_results.json'
    ensure_saved(folder/'manifest.json', manifest)
    before = getattr(extract, 'images', None)
    if (folder/'evaluation/report.json').exists():
        report=read(folder/'evaluation/report.json')
    else:
        report = run_manifest(folder/'manifest.json', folder/'evaluation', extract=extract,
                              extract_provenance=extract_provenance)
    numeric = report['energies']
    # No static pair may acquire formal eligibility; missing/unknown evidence remains N/A.
    passed = (evidence is not None and bool(questions) and
        ref_packet['status'] in ('valid', 'partial') and comparison['render']['status'] in ('valid', 'partial')
        and report['diagnostics']['vlm_verification']['status']=='available'
        and numeric['appearance']['value'] is not None and numeric['perceptual']['value'] is not None
        and numeric['semantic']['value'] is None and not report['formal_eligible'])
    result = dict(pair_id=pair['pair_id'], task_id=pair['task_id'], run_id=pair['run_id'],
        completion=pair.get('completion'), status='evaluated', pilot_passed=bool(passed),
        evaluation_directory=str(folder/'evaluation'), energies=numeric, structural=report['structure'],
        structural_energy=report['structural_energy'], observation_energy=report['observation_energy'],
        scene_validity=report['scene_validity'], source_camera_metadata=original_metadata,
        native_render_transform=transform, valid_pixels=int(valid.sum()),
        verification_states=dict(Counter(r['status'] for r in (comparison or {}).get('results', []))),
        planning_error=planning_error, question_count=len(questions),
        atomic_types=dict(Counter(r['type'] for r in (evidence or {}).get('atomic_evidence', []))),
        region_count=len((evidence or {}).get('regions', [])), group_count=len((evidence or {}).get('groups', [])),
        dino_images=(getattr(extract,'images',None)-before) if before is not None else None,
        roi_overlap=report['diagnostics']['region_overlap'], formal_eligible=False, reviewed=False, usage='provisional/debug')
    save(folder/'result.json', result)
    return result


class LocalDino:
    """One local CPU model per batch; count actual inference, never substitute features."""
    def __init__(self, directory):
        import torch
        torch.set_num_threads(2)
        self.extract = local_dino_extractor(directory, device='cpu')
        self.calls, self.images, self.seconds = 0, 0, 0.

    def __call__(self, images):
        tick = time.monotonic()
        value = self.extract(images)
        self.calls += 1
        self.images += len(images)
        self.seconds += time.monotonic()-tick
        return value


def summarize(config, root, rows):
    paths = sorted((root/'references').glob('*/*_response.json')) + sorted((root/'references').glob('*/reference_answers.json')) + sorted((root/'pairs').glob('*/render_answers.json'))
    calls = [dict(source=str(p.relative_to(root)), **{k:read(p).get(k) for k in
        ('status','model_requested','model_observed','token_usage','elapsed_seconds','request_submitted','error')}) for p in paths]
    for reservation in sorted(root.glob('*/*/*.reservation.json')):
        if not reservation.with_name(reservation.name.replace('.reservation.json','.json')).exists():
            calls.append(dict(source=str(reservation.relative_to(root)),status='unavailable',
                error='Interrupted reserved attempt; not retried',request_submitted=None))
    coverage = {}
    for energy in [*ENERGIES, 'structural']:
        valid = [r for r in rows if r.get('status')=='evaluated' and
                 (r.get('structural_energy') if energy=='structural' else r['energies'][energy]['value']) is not None]
        coverage[energy] = dict(measured_pairs=len(valid), selected_pairs=len(config['pairs']),
            fraction=len(valid)/len(config['pairs']), formal_scored_pairs=0,
            interpretation=('Texture/edge proxy, not semantic layout/density' if energy in ('spatial','statistical')
                            else 'Conditional image measure' if energy in ('appearance','perceptual') else 'Reviewed evidence required'))
        if energy!='structural':
            measured=sum(r.get('energies',{}).get(energy,{}).get('valid_count',0) for r in rows)
            planned=sum(r.get('energies',{}).get(energy,{}).get('applicable_count',0) for r in rows)
            coverage[energy].update(valid_metric_records=measured, planned_metric_records=planned,
                metric_record_coverage=measured/planned if planned else None)
    reasons, verification = {}, {}
    for row in rows:
        if row['status'] != 'evaluated':continue
        report=read(Path(row['evaluation_directory'])/'report.json')
        for metric in report['metric_records']:
            if metric['value'] is None:
                reasons.setdefault(metric['energy'], Counter())[metric.get('reason') or 'Unknown'] += 1
        document=report['diagnostics']['vlm_verification'].get('evidence') or {}
        for item in document.get('results',[]):
            verification.setdefault(item.get('energy','unspecified'), Counter())[item['status']] += 1
    verification={k:dict(planned=sum(v.values()), usable=v['satisfied']+v['candidate_violated'],
        unknown=v['unknown'], unavailable=v['unavailable'], states=dict(v), formal_scored=0)
        for k,v in verification.items()}
    return dict(pairs=rows, coverage=coverage, calls=calls, verification_coverage=verification,
        unavailable_reasons={k:dict(v) for k,v in reasons.items()},
        selected_pairs=len(config['pairs']), evaluated_pairs=sum(r['status']=='evaluated' for r in rows),
        unique_references=len({p['task_id'] for p in config['pairs']}),
        maximum_model_attempts=2*len({p['task_id'] for p in config['pairs']})+len(config['pairs']),
        actual_model_attempts=len(calls), automatic_retries=0,
        token_usage={k:sum((c.get('token_usage') or {}).get(k) or 0 for c in calls)
                     for k in ('input_tokens','output_tokens')},
        elapsed_model_seconds=sum(c.get('elapsed_seconds') or 0 for c in calls),
        verification_states=dict(sum((Counter(r.get('verification_states',{})) for r in rows), Counter())),
        reviewed=False, usage='provisional/debug', formal_eligible=False)


def write_tables(root, summary):
    fields=['pair_id','task_id','completion','status',*ENERGIES,
            *[k+'_coverage' for k in ENERGIES],'structural','question_count','pilot_passed']
    with (root/'per_pair_results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in summary['pairs']:
            values={k:row.get(k) for k in fields if k not in ENERGIES and k!='structural'}
            values.update({k:row.get('energies',{}).get(k,{}).get('value') for k in ENERGIES})
            values.update({k+'_coverage':row.get('energies',{}).get(k,{}).get('coverage') for k in ENERGIES})
            values['structural']=row.get('structural_energy');writer.writerow(values)
    audit=['# Existing Scene Evidence Audit','','All human review fields: **unreviewed**. '
        'Model differences are candidates, not reconstruction-error GT. Historical cameras differ; '
        'occlusion and category confusion remain possible. Images and derivatives are server-only.','',
        '| Pair / Evidence / Region / Group | Frozen question | Reference | Render | Status | Human review |',
        '| --- | --- | --- | --- | --- | --- |']
    for row in summary['pairs']:
        file=root/'pairs'/row['pair_id']/'verification_results.json'
        if not file.exists():continue
        for item in read(file)['results']:
            values=[' / '.join(str(v) for v in [row['pair_id'],item['evidence_id'],item.get('region_id'),item.get('group_id')]),
                item['question'],item['reference_answer'],item['render_answer'],item['status'],'unreviewed']
            audit.append('| '+' | '.join(str(v).replace('|','\\|').replace('\n',' ') for v in values)+' |')
    (root/'evidence_audit.md').write_text('\n'.join(audit)+'\n')
    lines=['# Existing-Scene Benchmark — actual historical pairs','','**reviewed:false; provisional/debug; no formal score.**','',
        f"Evaluated {summary['evaluated_pairs']}/{summary['selected_pairs']} pairs from {summary['unique_references']} Reference images.",
        'Saved Agent scenes were not executed, generated, rendered or realigned. '
        'Incomplete checkpoints remain labelled. Reference-only plans were frozen before independent Render VQA; '
        'each shared Reference plan/VQA is reused without using another Render answer.','',
        '| Energy | Measured pairs | Selected pairs | Pair availability | Metric-record coverage | Formal scored |',
        '| --- | --- | --- | --- | --- | --- |']
    for key,item in summary['coverage'].items():
        ratio=item.get('metric_record_coverage')
        text='N/A' if ratio is None else f'{ratio:.4f}'
        lines.append(f"| {key} | {item['measured_pairs']} | {item['selected_pairs']} | {item['fraction']:.4f} | {text} | 0 |")
    lines += ['', 'Spatial/Statistical numbers above are existing image-edge/texture proxies, '
        'not verified object layout, density or group arrangement. Semantic and Structural require reviewed '
        'compatible evidence and remain N/A where unavailable. DINO is real local CPU inference, not semantic evidence.', '',
        '## Real VLM diagnostics', '',json.dumps(summary['verification_coverage'],ensure_ascii=False,indent=2),'',
        f"Attempts: {summary['actual_model_attempts']} / maximum {summary['maximum_model_attempts']}; automatic retries: 0. "
        f"Reported input/output tokens: {summary['token_usage']['input_tokens']} / {summary['token_usage']['output_tokens']}; "
        f"summed model seconds: {summary['elapsed_model_seconds']:.3f}.", '',
        'Requested gpt-6-sol via existing Codex CLI. Observed snapshots may be unavailable. CLI usage includes '
        'platform context, not Ofox billing. Temporary cwd and disabled tools do not establish strict filesystem isolation. '
        'Planning, Reference and each Render are separate calls with the exact recorded neutral contract. '
        'No Reference answers, scene/task briefs or Blender names enter a Render prompt.', '',
        'Category spaces retain raw planner choices and freeze explicit absent/other options before any Render read. '
        'Unknown/ambiguous are abstentions. Unreviewed answers never enter formal Energy. '
        'Continuous object-level distances remain N/A without reliable RGB-only localization/correspondence.', '',
        '## Review and reproduction', '',
        '[Per-pair measurements](per_pair_results.csv) · [Evidence audit](evidence_audit.md) · [Full batch data](report.json). '
        'Individual pairs/<pair_id>/evaluation/report.json and raw VQA JSON retain failures, reason strings, '
        'fixed ROI, overlaps and source/coordinate checks. Server-only PNG/Mask derivatives are withheld until redistribution is authorized.', '',
        '```bash',
        'OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 python3 -B -m e_harness.benchmark_existing --config /path/to/private-pairs-config.json --output /path/to/new-results',
        '```', '',
        'Requires existing local data, DINO weights, sibling scene-benchmark and Codex CLI login. '
        'A new output entails real model requests and requires authorization. An unchanged output may resume '
        'saved stages without retrying reservations; no raw packet or frozen evidence is overwritten. '
        'The public checkout contains no third-party images or complete server run inventory. '
        'Historical camera/PNG-blend synchronization, independent review and validated RGB grounding still block official Benchmark scores. Runtime stays blocked.']
    (root/'summary.md').write_text('\n'.join(lines)+'\n')


def run_dataset(config, output, *, extract=None, extract_provenance=None):
    output = Path(output).resolve()
    if config.get('protocol_version', EXISTING_SCENE_PROTOCOL) != EXISTING_SCENE_PROTOCOL:
        raise ValueError('Existing Scene runner uses existing_scene_v1')
    config = dict(model='gpt-6-sol', timeout_seconds=240, max_edge=768, evidence_budget=10,
                  protocol_version=EXISTING_SCENE_PROTOCOL) | deepcopy(config)
    pairs = config['pairs']; identifiers = [r['pair_id'] for r in pairs]
    if (not pairs or len(set(identifiers))!=len(identifiers) or
            any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,120}',v) for v in identifiers+
                [r['task_id'] for r in pairs]) or not 64 <= config['max_edge'] <= 1536):
        raise ValueError('Require unique safe pair/task IDs and bounded image size')
    planning_protocol(config['protocol_version'], evidence_budget=config['evidence_budget'])
    frozen = output/'config.frozen.json'
    if output.exists():
        if read(frozen) != config:
            raise ValueError('Frozen config changed; use a new output directory')
    else:
        output.mkdir(parents=True, mode=0o700)
        save(frozen, config)
    if extract is None:
        extract = LocalDino(config['dino_model'])
        extract_provenance = dict(backend='local_DINOv2', model=config['dino_model'], device='cpu',
            threads=2, local_files_only=True, real_inference=True, downloaded=False)
    if not extract_provenance:
        raise ValueError('Explicit local extractor provenance required')
    rows=[]
    for index,pair in enumerate(pairs):
        if index == 2 and not all(r.get('pilot_passed') for r in rows):
            rows += [dict(pair_id=p['pair_id'],status='not_run',reason='Two-pair pilot did not pass; expansion withheld') for p in pairs[index:]]
            break
        print('PAIR start: '+pair['pair_id'],flush=True)
        try:
            result=evaluate_pair(pair,output,config,extract,extract_provenance)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            result=dict(pair_id=pair['pair_id'],status='failed',error=f'{type(exc).__name__}: {exc}',
                        reviewed=False,usage='provisional/debug')
            save(output/'pairs'/pair['pair_id']/'failure.json',result)
        rows.append(result)
        print('PAIR end: '+pair['pair_id']+' '+result['status'],flush=True)
    summary=summarize(config,output,rows)
    summary['dino_activity']=dict(current_process={k:getattr(extract,k,None) for k in ('calls','images','seconds')},
        recorded_pair_images=sum(r.get('dino_images') or 0 for r in rows),
        interpretation='Process counters reset on resume; recorded per-pair measurements retain their own provenance')
    # Derived summaries may be recomputed on resume; raw packets/evidence never overwritten.
    (output/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write_tables(output,summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run_dataset(read(args.config),args.output)


if __name__ == '__main__':
    main()
