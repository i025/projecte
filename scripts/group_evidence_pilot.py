"""Offline organization of frozen Semantic Groups; no inference or new scores."""
import argparse
from copy import deepcopy
import csv
import html
import json
from pathlib import Path
import re
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_evidence import load_document, reliability
from e_harness.benchmark_metrics import aggregate, record
from scripts.region_atomic_pilot import atomic_questions, replay_atomic_answers
from scripts.region_atomic_vlm import parse_answers, compare_answer_packets
from scripts.region_real_render import fit_render, measures, masked_view, heatmap


def group_questions(case):
    """Add Group ownership to existing region-level typed questions.

    Groups organize evidence; they do not add a scoring level. Explicit aliases
    retain their provenance but do not create duplicate questions/metric rows.
    """
    groups = case['semantic_groups']
    ids = [g['group_id'] for g in groups]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate Semantic Group ID')
    regions = {r['id']: r for r in case['regions']}
    by_group = {g['group_id']: g for g in groups}
    for group in groups:
        if group['region_id'] not in regions or not all(group.get(k) for k in ('name', 'scope', 'provenance')):
            raise ValueError('Group requires a parent Region, scope and provenance')
        if group['provenance'].get('render_used') is not False:
            raise ValueError('Semantic Groups require explicit Reference-only provenance')
        if group.get('reviewed') is not False or group.get('reliability') != 0:
            raise ValueError('Pilot candidates must remain unreviewed with reliability=0')
        if group.get('member_instance_ids') is not None:
            raise ValueError('This pilot uses collection evidence, not a member inventory')
    questions = atomic_questions(case)
    atoms = {a['id']: a for a in case['atomic_evidence']}
    if any(atoms[key].get('alias_of') for a in atoms.values() for key in a.get('requires', [])):
        raise ValueError('Prerequisites must reference canonical facts, not display aliases')
    listed = [key for g in groups for key in g['evidence']]
    if len(listed) != len(set(listed)) or set(listed) != set(atoms):
        raise ValueError('Each atomic evidence ID must be owned by exactly one Group')
    optional_anchors = {a['id'] for a in case.get('optional_anchors', [])}
    owners, canonical, aliases = [], {}, []
    for question in questions:
        atom = atoms[question['id']]
        group = by_group.get(atom.get('group_id'))
        if (group is None or question['region_id'] != group['region_id'] or
                atom['id'] not in group['evidence']):
            raise ValueError('Atomic evidence belongs to a different Group/Region')
        if atom.get('reviewed') is not False or atom.get('reliability') != 0:
            raise ValueError('Pilot atomic candidates cannot acquire review/reliability')
        if atom.get('provenance', {}).get('render_used') is not False:
            raise ValueError('Reference claims require explicit Reference-only provenance')
        if any(key not in optional_anchors for key in atom.get('anchor_refs', [])):
            raise ValueError('Unknown optional Anchor endpoint')
        fact = atom.get('canonical_fact_id')
        if not isinstance(fact, str) or not fact.strip() or not atom.get('owner_id'):
            raise ValueError('Canonical fact and one explicit owner required')
        if atom.get('alias_of'):
            target = atoms.get(atom['alias_of'])
            same = ('canonical_fact_id', 'owner_id', 'region_id', 'type', 'claim', 'question',
                    'expected', 'answer_type', 'scope', 'requires', 'anchor_refs')
            if target is None or target.get('alias_of') or any(atom.get(k) != target.get(k) for k in same):
                raise ValueError('Alias must preserve the same fact, question and owner')
            aliases.append(dict(id=atom['id'], alias_of=target['id'], canonical_fact_id=fact,
                                group_id=group['group_id'], reason='Display alias; no additional metric row'))
            continue
        if fact in canonical:
            raise ValueError('Duplicate fact needs an explicit alias, not another score')
        if atom['owner_id'] != group['group_id']:
            raise ValueError('Canonical fact must have its Group as the sole owner')
        canonical[fact] = atom['id']
        question.update(group_id=group['group_id'], canonical_fact_id=fact, owner_id=atom['owner_id'],
                        context_id=case['scene_id']+':'+group['region_id'], scope=atom['scope'],
                        anchor_refs=atom.get('anchor_refs', []), reviewed=False, reliability=0.)
        # A qualitative arrangement answer is not a density/area measurement.
        question['criteria'].pop('not_element_density_or_distribution', None)
        question['criteria'].update(group_scope=group['scope'], not_quantitative_density_or_occupancy_measurement=True,
            qualitative_distribution_only=question['energy'] == 'statistical' and question['answer_type'] == 'boolean',
            no_numeric_error_mapping=True)
        owners.append(question)
    for alias in aliases:
        if canonical.get(alias['canonical_fact_id']) != alias['alias_of']:
            raise ValueError('Alias has no canonical owner question')
    return owners, aliases


def group_energy_rows(questions, results):
    """Existing Energy records, all N/A: offline replies never upgrade review."""
    by_id = {r['id']: r for r in results}
    if len(by_id) != len(results) or set(by_id) != {q['id'] for q in questions}:
        raise ValueError('Exactly one verification result per canonical question required')
    return [record(q['energy'], 'region', q['id'], None, 0., by_id[q['id']]['reason'],
                   group_id=q['group_id'], canonical_fact_id=q['canonical_fact_id'],
                   owner_id=q['owner_id'], verification_status=by_id[q['id']]['status'],
                   reviewed=False, scorable=False, method='Group atomic evidence; no calibrated score mapping')
            for q in questions]


def bound_legacy_answers(reference, rendered, *, binding_verified):
    """Replay only the old three-question contract, never new Group questions."""
    packets = [deepcopy(reference), deepcopy(rendered)]
    reason = None
    if binding_verified is not True:
        reason = 'Historical RGB/ROI/question context is not bound to these inputs'
    for side, packet in zip(('reference', 'render'), packets):
        if packet.get('side') != side or packet.get('source') != 'real_vlm':
            reason = 'Historical response side/source is not an actual matching VLM response'
        if packet.get('status') == 'valid':
            try:
                parsed = parse_answers(packet['response']['raw_answer'])
                stored = parse_answers(json.dumps(packet['answers']))
                if parsed != stored:
                    raise ValueError('Stored raw and parsed answers disagree')
            except (ValueError, KeyError, TypeError) as exc:
                reason = 'Invalid historical packet: '+str(exc)
    if reason:
        packets = [dict(status='unavailable'), dict(status='unavailable')]
    rows = compare_answer_packets(*packets)
    for row in rows:
        row.update(source_kind='historical_real_vlm_replay', replay_only=True,
                   new_group_question_verified=False, score=None, value=None, q=0., reviewed=False)
        if reason:
            row['reason'] = reason
    return rows


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def read(path):
    return json.loads(path.read_text())


def table(rows):
    if not rows:
        return ''
    keys = list(rows[0])
    def cell(value):
        if value is None:
            return 'N/A'
        return f'{value:.6f}' if isinstance(value, float) else str(value)
    return '<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in keys)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+html.escape(cell(row[k]))+'</td>' for k in keys)+'</tr>' for row in rows)+'</table>'


def panel_row(panels, path, width):
    height=round(panels[0][1].height*width/panels[0][1].width)
    canvas=Image.new('RGB',(width*len(panels),height+36),'#18212e')
    draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
    for n,(title,image) in enumerate(panels):
        draw.text((n*width+8,8),title,font=font,fill='white')
        canvas.paste(image.resize((width,height)),(n*width,36))
    canvas.save(path)


def paired_images(case):
    """Read historical RGB only. No camera/content alignment or code execution."""
    reference = np.asarray(Image.open(case['reference_image']).convert('RGB'))
    if list(reference.shape[1::-1]) != case['image_size']:
        raise ValueError('Reference grid changed')
    if case['scene_id'] == 'bw_0073':
        source = ROOT/'results/region_first_real_render_bw0073'
        audit = read(source/'pair_audit.json')
        if not np.array_equal(reference, np.asarray(Image.open(source/'reference.png').convert('RGB'))):
            raise ValueError('Cached Reference differs')
        rendered = np.asarray(Image.open(source/'render.png').convert('RGB'))
        valid = np.asarray(Image.open(source/'render_valid.png').convert('L')) > 0
        return reference, rendered, valid, dict(audit, source_pair_audit=str(source/'pair_audit.json'))
    info = read(ROOT/'results/vlm_direct_grounding_cross_scene/bw_0074/input.json')
    run_id = info['provenance']['run_ids'][0]
    with (ROOT/'results/blenderworld_runs_inventory/selected.csv').open(encoding='utf-8-sig') as stream:
        pair = next(r for r in csv.DictReader(stream) if r['task_id'] == case['scene_id'] and r['run_id'] == run_id)
    original, staged, rendered_path = (Path(pair[k]).resolve() for k in
                                     ('original_reference_image', 'reference_image', 'render_file'))
    if original != Path(info['reference_rgb']).resolve() or original.read_bytes() != staged.read_bytes():
        raise ValueError('Reference input association differs')
    if not np.array_equal(reference, np.asarray(Image.open(original).convert('RGB'))):
        raise ValueError('Cached Reference does not equal original RGB')
    run = Path(info['provenance']['run_config']).parent
    config, result, manifest = [read(run/name) for name in ('config.json', 'result.json', 'artifacts/manifest.json')]
    inputs = Path(info['provenance']['input_json'])
    inp = read(inputs)
    if (Path(config['task']['path']).resolve() != inputs.parents[2].resolve() or inp['task_id'] != case['scene_id']
            or 'references/image_01.jpg' not in inp['files'] or
            staged != (inputs.parent/'references/image_01.jpg').resolve()):
        raise ValueError('Run/task/input metadata association differs')
    if not any(row['destination'] == 'artifacts/workspace/exports' and row['status'] == 'ok' for row in manifest):
        raise ValueError('No successful exported artifact association')
    if rendered_path.parent != (run/'artifacts/workspace/exports').resolve():
        raise ValueError('Render is outside the declared export directory')
    actual = Image.open(rendered_path)
    rendered, valid, transform = fit_render(actual, tuple(case['image_size']))
    return reference, rendered, valid, dict(task_id=case['scene_id'], run_id=run_id, agent=pair['agent'],
        reference_rgb=str(original), staged_reference=str(staged), render_rgb=str(rendered_path),
        run_config=str(run/'config.json'), artifact_manifest=str(run/'artifacts/manifest.json'),
        input_metadata=str(inputs), metadata_correspondence_verified=True,
        original_staged_bytes_equal=True, render_native_size=list(actual.size), reference_native_size=case['image_size'],
        run_exception=result.get('exception_info'),
        png_metadata={k:actual.info.get(k) for k in ('Camera', 'Scene', 'File')},
        reference_camera='unknown', actual_blend_camera_reverified=False, camera_protocol='historical_camera',
        camera_alignment_confirmed=False, final_blend_png_sync='unknown', comparison_transform=transform,
        observed_canvas_fraction=float(valid.mean()), official_benchmark_eligible=False,
        usage='provisional/debug', reviewed=False)


def legacy_context(case):
    source = ROOT/'results/region_atomic_vlm_r2_bw0073'
    paired = ROOT/'results/region_first_real_render_bw0073'
    inp, protocol = read(source/'inputs.json'), read(source/'protocol.json')
    same_reference = Path(case['reference_image']).read_bytes() == (source/'reference.png').read_bytes()
    same_render = (paired/'render.png').read_bytes() == (source/'render.png').read_bytes()
    current_roi = np.asarray(Image.open(case['roi_source']).convert('L')) > 0
    old_roi = np.asarray(Image.open(source/inp['roi_polygon']).convert('L')) > 0
    same_roi = bool(np.array_equal(current_roi, old_roi))
    from scripts.region_atomic_vlm import SYSTEM, USER
    binding = (same_reference and same_render and same_roi and inp['common_grid'] == case['image_size']
               and inp['roi_changed'] is False and inp['full_context_preserved'] is True
               and protocol['system'] == SYSTEM and protocol['user'] == USER)
    reference, rendered = read(source/'reference_answers.json'), read(source/'render_answers.json')
    rows = bound_legacy_answers(reference, rendered, binding_verified=binding)
    return dict(binding_verified=bool(binding), source=str(source), reference_bytes_equal=same_reference,
        render_bytes_equal=same_render, decoded_roi_membership_equal=same_roi, no_hash_computed_by_runner=True,
        scope='Old near-camera-side stool count overlaps current Group; no per-member identity or new property validation',
        original_response_files=[str(source/(side+'_answers.json')) for side in ('reference', 'render')],
        original_prompt_file=str(source/'protocol.json'), results=rows,
        new_paid_requests=0, candidate_group_mapping_only=True,
        note='Q1 island and Q3 lamp relation are historical context, not new Group evidence; q2 count agreement is not GT')


def run(source, output):
    if output.exists() and any(p.name not in {'reference_groups_frozen.json', 'reference_freeze_receipt.json'} for p in output.iterdir()):
        raise FileExistsError('Choose a fresh output; historical results are never overwritten')
    output.mkdir(parents=True, exist_ok=True)
    frozen = source/'reference_groups_frozen.json'
    original_bytes = frozen.read_bytes()
    if source.resolve() != output.resolve():
        shutil.copyfile(frozen, output/frozen.name)
        shutil.copyfile(source/'reference_freeze_receipt.json', output/'reference_freeze_receipt.json')
    (output/frozen.name).chmod(0o444)
    document = read(frozen)
    all_questions, all_results, all_records, summaries, page = [], [], [], [], []
    for case in document['cases']:
        folder = output/case['scene_id']; folder.mkdir()
        questions, aliases = group_questions(case)
        # Existing loader reads the normal per-image Region document and preserves
        # Semantic Group side information. No new mask loader or scoring layer.
        save(folder/'reference_evidence.json', case)
        loaded = load_document(folder/'reference_evidence.json')
        roi = loaded['regions'][0]['mask'] > 0
        assert list(roi.shape[::-1]) == case['image_size'] and roi.any()
        a, b, valid, audit = paired_images(case)
        assert a.shape == b.shape and valid.shape == roi.shape
        Image.fromarray(a).save(folder/'reference.png'); Image.fromarray(b).save(folder/'render.png')
        Image.fromarray(np.uint8(roi)*255).save(folder/'fixed_roi.png')
        save(folder/'pair_audit.json', audit)
        observed = roi & valid
        appearance, _, unavailable_reason = measures(a, b, observed)
        perceptual, perceptual_source = None, None
        if case['scene_id'] == 'bw_0073':
            cached_path = ROOT/'results/region_first_real_render_bw0073/metrics.json'
            cached = next(r for r in read(cached_path)['rows'] if r['id'] == 'polygon_R2')
            old_roi = np.asarray(Image.open(ROOT/'results/region_first_real_render_bw0073/measurement_rois/polygon_R2.png').convert('L')) > 0
            if not np.array_equal(roi, old_roi) or not np.isclose(appearance, cached['appearance'], atol=1e-12):
                raise ValueError('Cached Perceptual context/appearance no longer matches')
            perceptual, perceptual_source = cached['perceptual'], str(cached_path)+'#/rows[id=polygon_R2]'
        region_measurement = dict(scene_id=case['scene_id'], region_id=case['region_id'],
            appearance=appearance, perceptual=perceptual, perceptual_source=perceptual_source,
            perceptual_unavailable_reason=None if perceptual is not None else 'No cached measurement for this pair/ROI; no model run',
            semantic=None, spatial=None, statistical=None, q=0., reviewed=False, formal_eligible=False,
            roi_source=case['roi_source'], roi_pixels=int(roi.sum()), observed_pixels=int(observed.sum()),
            group_specific_visual_scores=False, region_losses_summed=False, usage='provisional/debug')
        save(folder/'region_only.json', region_measurement)
        results = replay_atomic_answers(questions)
        for row, question in zip(results, questions):
            row.update(group_id=question['group_id'], canonical_fact_id=question['canonical_fact_id'],
                       scene_id=case['scene_id'], value=None, q=0., usage='provisional/debug')
        records = group_energy_rows(questions, results)
        energy, observation = aggregate(records)
        applicability = []
        for group in case['semantic_groups']:
            subset = [q for q in questions if q['group_id'] == group['group_id']]
            applicability.append(dict(group_id=group['group_id'], region_id=group['region_id'],
                match_state='Unknown', reason='No independently reviewed Group correspondence verifier',
                semantic=dict(applicable=True, value=None, evidence_ids=[q['id'] for q in subset if q['energy']=='semantic'],
                              reason='Mask-free VQA is possible in principle; no real response for these properties'),
                spatial_discrete=dict(applicable=True, value=None, evidence_ids=[q['id'] for q in subset if q['energy']=='spatial'],
                                      reason='Projected discrete relations need a real verifier and visible endpoints'),
                spatial_continuous=dict(value=None, reason='No reliable independent two-side Group localization; Region centre not used'),
                statistical=dict(applicable=True, value=None, evidence_ids=[q['id'] for q in subset if q['energy']=='statistical'],
                    reason='Qualitative questions/exact count unknown; no validated density, area or distribution measure'),
                group_mask_required_for_semantic=False, quantitative_area_density_available=False,
                reviewed=False, score=None, scorable=False))
        save(folder/'energy_applicability.json', dict(groups=applicability, energy_records=records,
            aggregate_new_atomic_only=energy, observation_energy=observation,
            note='N/A records for the new question plan only; not a replacement Benchmark coverage or score'))
        save(folder/'verification_questions.json', dict(questions=questions, aliases=aliases))
        save(folder/'verification_results.json', dict(results=results, actual_new_vlm_responses=0,
            mocks_used=False, formal_observation_energy=None))
        # Coarse Group scope only when already frozen on the Reference side.
        candidates = []
        for group in case['semantic_groups']:
            if group.get('candidate_bbox'):
                view = Image.fromarray(a).copy(); draw=ImageDraw.Draw(view)
                draw.rectangle(group['candidate_bbox'], outline=(20, 150, 240), width=3)
                view.save(folder/(group['group_id']+'_scope.png'))
                candidates.append(group['group_id']+'_scope.png')
        ys, xs = np.nonzero(roi)
        crop=(slice(ys.min(), ys.max()+1), slice(xs.min(), xs.max()+1))
        heat = heatmap(np.abs(a.astype(float)-b.astype(float)).mean(2)/255, observed)
        panel_row([('Reference / frozen Region', Image.fromarray(masked_view(a,roi)[crop])),
                    ('Historical Agent / same coordinates', Image.fromarray(masked_view(b,roi)[crop])),
                    ('RGB difference, not semantic GT', Image.fromarray(heat[crop]))], folder/'region_comparison.png', width=560)
        panel_row([('Reference / fixed Region', Image.fromarray(masked_view(a,roi))),
                    ('Historical Render / same Region', Image.fromarray(masked_view(b,roi)))], folder/'overview.png', width=680)
        all_questions += [dict(q, scene_id=case['scene_id']) for q in questions]
        all_results += results; all_records += records
        summary = dict(scene_id=case['scene_id'], region_id=case['region_id'], region_name=case['region_name'],
            semantic_groups=len(case['semantic_groups']), optional_anchors=len(case['optional_anchors']),
            new_questions=len(questions), new_real_verified=0,
            unavailable=sum(r['status']=='unavailable' for r in results), unknown=sum(r['status']=='unknown' for r in results),
            appearance=appearance, perceptual=perceptual, semantic=None, spatial=None, statistical=None)
        summaries.append(summary)
        page.append(dict(case=case, measurement=region_measurement, questions=questions, results=results,
                         applicability=applicability, candidates=candidates))
    legacy = legacy_context(document['cases'][0])
    save(output/'historical_vlm_replay.json', legacy)
    save(output/'verification_questions.json', dict(questions=all_questions,
        note='New questions only; the old three are replayed separately without new API calls'))
    save(output/'verification_results.json', dict(new_results=all_results, historical_replay_file='historical_vlm_replay.json',
        new_real_verifications=0, mocks_used=False, formal_observation_energy=None, reviewed=False))
    save(output/'comparison.json', dict(region_only=summaries,
        region_plus_groups=[dict(scene_id=r['scene_id'], region_id=r['region_id'],
            same_visual_measurements=r['scene_id']+'/region_only.json',
            new_questions=r['new_questions'], new_real_verified=r['new_real_verified'],
            unavailable=r['unavailable'], unknown=r['unknown']) for r in summaries],
        numeric_region_measurements_duplicated=False, region_scores_added_or_summed=False,
        new_group_quantitative_energy=None, note='Same visual measurements; Group-aware adds typed, mostly unavailable evidence, not a new score'))
    with (output/'summary.csv').open('x', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    write_review(output, page, summaries, legacy)
    checks = validate_outputs(output, original_bytes)
    print(json.dumps(dict(output=str(output), checks=checks, region_only=summaries), ensure_ascii=False, indent=2))


def validate_outputs(output, original_frozen_bytes=None):
    """Lightweight validation, also usable after visualization has completed."""
    frozen = output/'reference_groups_frozen.json'
    document = read(frozen)
    questions = read(output/'verification_questions.json')['questions']
    results = read(output/'verification_results.json')['new_results']
    snapshots_equal, rois_equal, rows_na = [], [], []
    for case in document['cases']:
        folder=output/case['scene_id']
        snapshots_equal.append(read(folder/'reference_evidence.json') == case)
        rois_equal.append(bool(np.array_equal(np.asarray(Image.open(case['roi_source']).convert('L')) > 0,
                                             np.asarray(Image.open(folder/'fixed_roi.png').convert('L')) > 0)))
        rows=read(folder/'energy_applicability.json')['energy_records']
        rows_na.append(all(r['value'] is None and r['q']==0 and r['reviewed'] is False for r in rows))
    candidates=[row for c in document['cases'] for name in ('semantic_groups','atomic_evidence','optional_anchors') for row in c[name]]
    unchanged=(frozen.read_bytes()==original_frozen_bytes) if original_frozen_bytes is not None else all(snapshots_equal)
    checks=dict(frozen_reference_unchanged=unchanged, saved_reference_snapshots_equal=all(snapshots_equal),
        fixed_roi_membership_unchanged=all(rois_equal),
        all_candidates_unreviewed=all(r['reviewed'] is False and r['reliability']==0 and reliability(r)==0 for r in candidates),
        all_new_energy_records_na=all(rows_na), new_questions=len(questions),
        new_unavailable=sum(r['status']=='unavailable' for r in results), new_unknown=sum(r['status']=='unknown' for r in results),
        new_real_verifications=0, historical_answer_comparisons=len(read(output/'historical_vlm_replay.json')['results']),
        formal_group_scores_available=0, paid_requests=0, segmentation_or_large_model_runs=0, blender_runs=0,
        mocks_in_real_results=False, formal_sources_unchanged={name:(ROOT/'e_harness'/name).read_bytes()==
            (ROOT/'results/region_first_real_render_bw0073/source_snapshot'/name).read_bytes()
            for name in ('benchmark_evidence.py','benchmark_metrics.py','benchmark_config.py')})
    assert all(checks[key] for key in ('frozen_reference_unchanged','saved_reference_snapshots_equal',
                                     'fixed_roi_membership_unchanged','all_candidates_unreviewed','all_new_energy_records_na'))
    assert all(checks['formal_sources_unchanged'].values())
    links=re.findall(r'(?:src|href)="([^"]+)"',(output/'comparison.html').read_text())
    assert all((output/link).is_file() for link in links if link != 'validation.json')
    checks.update(html_local_links_resolved=len(links), passed=True)
    save(output/'validation.json', checks)
    assert all((output/link).is_file() for link in links)
    return checks


def write_review(output, cases, summaries, legacy):
    # These post-freeze static observations are explicitly NOT verifier replies.
    audit_candidates = [
        dict(scene_id='bw_0073', group_id='bw_0073_R2_chairs',
             observation='两图保留横排椅子；Reference侧架、脚踏及连接更复杂，Render靠背/坐垫和杆架更简化。',
             candidate_question_ids=['bw_0073_R2_chairs_frame','bw_0073_R2_chairs_one_row'],
             uncertainty='是否满足“主要为细长杆件”仍需验证；宽泛布尔问题即使两侧yes也可能漏掉结构差异。'),
        dict(scene_id='bw_0074', group_id='bw_0074_R2_books',
             observation='Render能辨认多组书籍，主要为竖立书脊状块列；Reference中的水平书堆和正面大开本封面未见同等清晰对应。',
             candidate_question_ids=['bw_0074_R2_books_orientations','bw_0074_R2_books_front_cover','bw_0074_R2_books_below_frame'],
             uncertainty='可见性、类别和框画端点仍不确定；不能把当前未辨认直接判为Confirmed Missing。'),
        dict(scene_id='bw_0074', group_id='bw_0074_R2_framed_images',
             observation='Render可见左侧较小框画和中央较大框体；中央内容简化且有遮挡，飞机题材和小幅纵向框画对应不清楚。',
             candidate_question_ids=['bw_0074_R2_framed_images_airplane','bw_0074_R2_framed_images_relative_position'],
             uncertainty='不能以任意两幅框画替换冻结命题的端点；精确总数两侧不可确认。')]
    save(output/'static_review_candidates.json', dict(items=audit_candidates,
        source='Assistant static paired-image review after Reference freeze', actual_vlm_verification=False,
        reviewed=False, reliability=0., reference_claims_modified=False, usage='provisional/debug'))
    new_states = [dict(scene_id=item['case']['scene_id'], group_id=r['group_id'], id=r['id'], status=r['status'])
                  for item in cases for r in item['results']]
    legacy_rows = [{k:r[k] for k in ('id','energy','question','reference_answer','render_answer','status')}
                   for r in legacy['results']]
    snippets = ['''<!doctype html><meta charset="utf-8"><title>Group-aware evidence pilot</title>
<style>body{font:16px system-ui;max-width:1450px;margin:24px auto;padding:0 18px;line-height:1.65}img{max-width:100%}table{border-collapse:collapse;width:100%;margin:15px 0}td,th{border:1px solid #bbb;padding:7px;text-align:left;vertical-align:top}.note{background:#fff0ce;padding:16px}.group{border-left:5px solid #4099ba;padding:8px 18px;margin:20px 0}small{color:#555}a{color:#1759a0}.pair{display:flex;gap:12px}.pair>div{width:50%}</style>
<h1>Region-first · Group-aware · Anchor-on-demand</h1>
<p class="note">provisional/debug。3个Reference Group、1个可选Anchor、10条新原子候选，全部reviewed=false、q=0。9条unavailable、1条Reference unknown。旧3条真实VLM回答独立重放，不能代答新问题。没有新API或模型推理，没有正式总分。</p>
<p><a href="report.md">报告与复现命令</a> · <a href="reference_groups_frozen.json">冻结Reference</a> · <a href="reference_freeze_receipt.json">冻结记录</a> · <a href="verification_questions.json">新问题</a> · <a href="verification_results.json">新结果</a> · <a href="historical_vlm_replay.json">历史真实回答</a> · <a href="static_review_candidates.json">静态审核候选</a> · <a href="validation.json">检查</a></p>
<h2>Region-only 与 Region + Groups</h2><p>下表视觉数值两种组织方式完全相同，保留一份；不按Group复制或求和。未运行新的Perceptual模型。Group仅增加具体可核验事实和不可用原因。</p>''', table(summaries)]
    for item in cases:
        case = item['case']; scene = case['scene_id']; rows = {r['id']:r for r in item['results']}
        snippets += [f'<h2>{scene} / {html.escape(case["region_id"])} {html.escape(case["region_name"])}</h2>',
            f'<div class="pair"><div>Reference RGB<img src="{scene}/reference.png"></div><div>Agent Render（历史全图等比适配）<img src="{scene}/render.png"></div></div>',
            '<p>冻结Coarse ROI，仅作上下文与固定坐标像素评价；不是Group/物体Mask。未对Render做内容配准。</p>',
            f'<img src="{scene}/overview.png"><img src="{scene}/region_comparison.png">',
            f'<p><a href="{scene}/pair_audit.json">图像/相机来源</a> · <a href="{scene}/energy_applicability.json">Energy适用性</a> · <a href="{scene}/region_only.json">Region视觉诊断</a></p>']
        for group in case['semantic_groups']:
            snippets += [f'<div class="group"><h3>{html.escape(group["name"])} <small>{group["group_id"]}</small></h3>',
                '<p>'+html.escape(group['scope'])+'</p>',
                '<p>来源：Reference-only assistant候选，human_seeded_provisional；不是自动提取或人工GT。'+html.escape(group['uncertainty'])+'</p>']
            evidence = []
            for atom in case['atomic_evidence']:
                if atom['group_id'] != group['group_id']:
                    continue
                result = rows[atom.get('alias_of') or atom['id']]
                evidence.append(dict(Energy=atom['type'], claim=atom['claim'], question=atom['question'],
                    Reference_candidate_expected=atom['expected'], verification=result['status'],
                    source=('Display alias of '+atom['alias_of']) if atom.get('alias_of') else
                           'Reference-only draft; no real response', score=None))
            snippets += [table(evidence)]
            filename=group['group_id']+'_scope.png'
            if filename in item['candidates']:
                snippets += [f'<p>蓝框只展示既有Reference粗支持范围：含背景/空隙；不能用于中心、面积或密度测量，也没有复制为Render对象位置。</p><img src="{scene}/{filename}">']
            else:
                snippets += ['<p>没有可靠Group定位。语义描述可供VQA；连续位置、面积和密度为N/A。</p>']
            snippets += ['<p>人工审核：□ Correct　□ Needs Correction　□ Remove　□ Uncertain。当前没有任何自动批准。</p></div>']
        if case['optional_anchors']:
            snippets += ['<p>可选Anchor：岛台主体，仅作关系端点。复用未审核Reference粗框，不新增存在性或Appearance/Perceptual分数，不要求为每把椅子建Anchor。</p>']
        if case.get('exclusions'):
            snippets += ['<p>范围排除：唱片与音响在历史Plan中属于R3，本轮不将其并入R2。</p>']
    snippets += ['<h2>历史真实VLM回放：只限旧问题</h2>', table(legacy_rows),
        '<p>旧Q2为“近相机一侧高脚椅数”，与当前有靠背椅集合范围重叠但未验证成员一致；4→4不能验证框架、排列或密度。旧Q3没有独立吊灯可见性字段。三条satisfied表示回答一致，不是GT、不是Group重建质量良好。</p>',
        '<h2>新问题可用状态</h2>', table(new_states),
        '<h2>冻结后静态审核候选：不是VLM验证</h2>', table(audit_candidates),
        '<h2>去重、缺失和限制</h2><p>Group只组织，不额外评分；一条canonical fact一个owner，其他引用只能显式alias，不产生新记录。Anchor缺失若未来经审核确认，只在同一事实的Semantic owner记录一次，依赖的计数/关系保持N/A。检测未检出、VLM不确定或超出ROI均不等于Confirmed Missing。两图相机未对齐，所有结果仅离线诊断。</p>',
        '<p>没有可靠Group Mask，未报告精确面积、密度或连续分布；定性统计问题没有映射为数字Energy。新增证据不能使现有条件误差改变，也不能将本轮问题可用率冒充全Benchmark Coverage。</p>']
    (output/'comparison.html').write_text('\n'.join(snippets))
    new_unavailable=sum(r['status']=='unavailable' for item in cases for r in item['results'])
    new_unknown=sum(r['status']=='unknown' for item in cases for r in item['results'])
    report = f'''# Group-level Evidence & Evaluation Pilot

本轮只研究bw_0073中央岛台区、bw_0074展示书架区。两份真实Region Plan均确认目标ID为R2。3个Semantic Group、10条新原子命题、1个可选岛台Anchor，未列举或匹配全部物体；所有真实候选reviewed:false、reliability:0。没有新增评分层级、公式、权重或Group总分。

## Reference冻结及范围

Reference-only子任务独立查看原RGB和历史Reference材料，先写reference_groups_frozen.json并设为只读，再检查Render。主代理此前已经知道历史Render，整体不是严格盲测。来源标human_seeded_provisional，实际为助手目视草拟，不伪称新VLM提取或独立人工GT。冻结记录见reference_freeze_receipt.json；后续没有按Render修补命题或ROI。

- bw_0073/R2：一个高脚椅集合，关注可见细杆框架、椅背相对台面位置、横排组织。岛台仅因关系问题作为一个可选Anchor；不逐把创建ID。吊灯不新增本轮Anchor，旧吊灯问题仅保留历史上下文。
- bw_0074/R2：书籍陈列集合、独立装框图像集合。书籍不逐本计数；竖立/平放、封面朝向及书堆与框画关系作为候选证据。框画精确总数Unknown，不把“至少两幅”冒充确切计数。
- 唱片集合属于bw_0074的R3“唱片与音响区”，本轮排除，没有因探索提示而补入R2。地球仪、植物、小摆件等由Region/Global/Dense兜底，不为凑数建实例清单。
- bw_0073复用Direct Polygon R2；bw_0074复用已冻结B2 R2。后者历史Direct Polygon响应曾不合法，本轮不修补或重建ROI、不宣称B2是Group精确Mask。不同ROI表示是既有条件，本轮不比较Grounding优劣。

## 实际数据流与结果

Reference Region → Semantic Groups → Atomic Evidence → typed Questions → offline Verification → Energy Applicability已运行。

新增10问：{new_unavailable}条unavailable、{new_unknown}条unknown、0条真实新验证，没有使用Mock填充结果。Reference未知精确框画数量在验证前就保持Unknown，其余没有对应真实回复，不能得到Semantic/Spatial/Statistical数值。所有Group对应状态Unknown；静态看到类似对象不自动升级Matched或Confirmed Missing。

历史真实三问已经重新严格解析并绑定：原始/缓存RGB直接字节比较、ROI解码成员比较（编码可能不同）、历史Prompt和输入上下文核对；不靠文件名或自行填写expected认定匹配。旧答案两侧均yes/4/yes，3条satisfied，只表示回答一致。q2只限定近相机侧可见高脚椅，不能自动代答当前Group的框架、排列、遮挡或密度；q1/q3不是新Group验证。没有新的付费请求或模型自我验证。

Region-only真实视觉诊断：

| Scene / Region | Appearance | Perceptual | 本轮来源 |
| --- | ---: | ---: | --- |
| bw_0073 / R2 | {summaries[0]['appearance']:.6f} | {summaries[0]['perceptual']:.6f} | Appearance轻量重算并与缓存核对；Perceptual只重用同图同ROI旧值 |
| bw_0074 / R2 | {summaries[1]['appearance']:.6f} | N/A | 新读可信历史PNG，现有numerical_errors；未找到该配对/ROI可重用Perceptual值，不运行DINO |

Region + Groups保留上述同一份视觉测量，不复制、不相加；增加10个可核验命题的类型、归属、来源和不可用原因。新Group三类Energy均N/A。当前结果只证明数据组织和程序门控可运行，未证明分割/语义准确率或错误检出率提升。

## 分能量适用性

1. Semantic：集合无需精确Mask即可提出具体VQA问题，例如椅架形态、书籍类别、飞机框画内容。接口能够处理；新问题无真实验证器回复，尚未证明自动语义验证可靠。旧岛台存在yes/yes不验证书籍或椅子关键属性。
2. Spatial：离散“椅背在台面下方”“书堆在飞机框画下方”可供VQA。连续中心、范围、比例必须有两侧独立可靠定位，当前全部N/A；没有使用Region ROI中心替代Group中心。Reference椅子粗框只作图示，Render没有据它复制对象位置。
3. Statistical：集合方向、横排规律可用定性问题避免逐成员ID；这些回答还需真实验证且不等于精确分布数字。椅子旧数量4→4是有限历史观察；书籍总数、Group面积、密度、占据图均不可测。不能把图像梯度统计称为书籍密度，也未新增计数差归一化公式。
4. Appearance/Perceptual：继续只做固定Region内的连续视觉响应，不拆算为书籍/椅子Group得分。颜色、纹理、细结构简化仍更适合连续视觉诊断；DINO受裁剪/黑底/面积及长宽比影响，旧值只在同图同ROI内复用，不跨Group面积比较。

## 真实Render的静态审核候选与漏检

详见static_review_candidates.json，均为冻结后助手静态观察，不是真实VLM响应、独立人工GT或已确认重建错误。

- bw_0073：都保留横排椅子，但框架连接/脚踏等形态不同；新框架问题更具体，不过宽泛的“主要细杆”仍可能两侧yes，不能保证捕捉所有差异。
- bw_0074书籍：可见书籍，但水平堆叠、正面大开本的对应不清楚；冻结的方向/封面命题可针对性检查。是否真实违反仍未知。
- bw_0074框画：能看到框体，但飞机题材和纵向小框画的对应受遮挡/简化影响；语义端点未知时关系也未知，不能硬判空间错位或缺失。

## Group、Anchor与重叠如何去重

Group是组织信息，不直接新增Energy行。每个原子事实只有canonical_fact_id及owner_id，显式alias保留审核信息但不再次生成问题/指标记录。已有Region Appearance/Perceptual只计算一份，Group没有复制像素损失。同一对象的Group presence与Anchor presence将来必须明确同一事实owner；已确认缺失只由该Semantic owner计一次，依赖的数量和关系不再完整处罚。检测器未检出不等于Confirmed Missing。

本轮没有把两个重叠Region的损失相加：每个场景只评一个冻结R2、两个不同场景分别报告。bw_0074书籍和框画的语义定义排除彼此，仍不能假定有互斥精确Mask。未来跨Region重叠实体也应沿用同一事实owner，不通过新增候选行改变正式聚合。

原有stage='group'表示多个Region归并，因此不用于这里的Semantic Group。保留现有三层计算架构，用semantic_groups侧字段组织Region内命题，Question仍level=region。reuse atomic_questions、replay_atomic_answers、load_document、record和aggregate，正式核心源码不变。N/A记录的aggregate仅显示本轮计划可用性，不代表完整Benchmark Coverage；Unknown和不可用没有删除。

## 相机与数据限制

bw_0073历史相机高1.5m，正式2m，Reference相机未知。bw_0074没有检查到独立最终相机JSON；PNG元数据可追溯到同Run导出blend，最终参数与逐项同步未重渲染验证，Reference相机也未知。只复用/进行全图等比居中留边，不裁剪、不搜索、不做内容对齐。所有结果provisional/debug，不能作正式三维重建Error GT。

## 测试与复现

新增tests/test_group_evidence.py覆盖Group归属、无Mask/无成员ID、Unknown/Unavailable、alias去重/冲突、不能升级审核、Mock不产分、历史side/source/raw/context绑定及旧问题不能代答新问题。实际测试日志见tests.txt（交付前写入），结构/引用/ROI与冻结检查见validation.json。

在项目根目录只用CPU重放（新目录必须不存在）：

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python -B scripts/group_evidence_pilot.py --source {output} --output results/group_level_evidence_pilot_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p test_group_evidence.py -v
```

重放读冻结草稿及历史回复，不重新提取或验证Group。0次新API，0次SAM/SLIC/DINO/大型模型，0次GPU/Blender/Agent运行。没有修改正式公式、权重、相机协议或历史产物，没有提交Git。未执行项：新真实VQA、精确Group Grounding/密度、独立人工审核、正式评分；原因分别是未授权请求、缺可靠定位与Mask、尚待审核、相机/证据不满足协议。

## 执行偏差

一个只读子任务曾额外计算文件摘要作比对，不符合项目此前避免哈希校验的约束；已停止，未保存摘要、未写入历史文件，也未用作本轮证据或评分依据。主流程仅做元数据、直接字节及ROI成员核对，未重复计算摘要。

主要自动化瓶颈仍是Reference候选的可靠提取、具体问题的真实验证，以及连续测量所需的Group定位；不是必须先完成整个场景的实例清单。当前少量Group已能表达具体待验证差异，但真实检出能力尚待后续审核和授权验证。
'''
    (output/'report.md').write_text(report)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'results/group_level_evidence_pilot')
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    run(args.source.resolve(), args.output.resolve())
