"""M2: three bounded CLI calls over saved first-party M1 RGB, then static evaluation.

Offline replay uses the existing Manifest entry, never this live driver. Run reserves each
stage on disk before invoking it; interrupted attempts cannot be retried there.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import textwrap
import uuid

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_offline import run_manifest
from e_harness.verification_adapter import (codex_answer, compare_answers, contract,
    parse_answer, probe_cli, validate_diagnostics)


def save(path, document):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def read(path):
    return json.loads(Path(path).read_text())


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


TEXT = dict(type='string', minLength=1, maxLength=300)
ID = dict(type='string', pattern='^[A-Za-z][A-Za-z0-9_]{0,31}$')
OPTIONAL_ID = dict(anyOf=[ID, dict(type='null')])
BOX = dict(type='array', items=dict(type='number', minimum=0, maximum=1000), minItems=4, maxItems=4)


def planning_protocol():
    """No scene vocabulary, fixture labels, object names or expected change in this input."""
    schema = obj(dict(
        regions=dict(type='array', minItems=1, maxItems=4, items=obj(dict(
            id=ID, name=TEXT, description=TEXT, bbox=BOX))),
        groups=dict(type='array', maxItems=2, items=obj(dict(id=ID, region_id=ID, name=TEXT, scope=TEXT))),
        anchors=dict(type='array', maxItems=2, items=obj(dict(id=ID, region_id=ID, category=TEXT, bbox=BOX))),
        evidence=dict(type='array', minItems=1, maxItems=3, items=obj(dict(
            id=ID, region_id=ID, group_id=OPTIONAL_ID, anchor_id=OPTIONAL_ID,
            type=dict(type='string', enum=['semantic', 'spatial', 'statistical']),
            claim=TEXT, question=TEXT,
            answer_type=dict(type='string', enum=['yes_no_unknown', 'count_unknown']))))))
    return contract(dict(system='你是参考图像证据规划器。只根据当前RGB图像提取少量可见、可验证的评价证据。不要猜测不可见内容。只输出JSON。',
        user='提出1–4个粗粒度功能评价区域，可包含多个物体，背景无需强制覆盖。bbox为0–1000归一化xyxy粗范围。'
        '仅在有必要时提出少量集合Group或显著Anchor，允许groups和anchors为空；Anchor框必须是其自身可见范围。'
        '最多3条原子命题，每条只表达一个明确可见事实，附一个中立、独立看图即可回答的问题。'
        '问题不能透露预期答案，不要求比较图像或总体评分。答案类型为yes_no_unknown或count_unknown（非负整数或unknown）。'
        '使用唯一ASCII ID并正确引用region_id，未用group_id或anchor_id填null。不要枚举全部物体，不输出答案、置信度或推理。',
        schema=schema))


def evidence_from_plan(packet, size):
    """Validate full plan and references before freezing; never repair model coordinates."""
    if packet.get('actual_input') != planning_protocol():
        raise ValueError('Planning input differs from the frozen Reference-only contract')
    parsed = parse_answer(packet.get('raw_answer'), planning_protocol()['schema'])
    if packet.get('status') != 'valid' or parsed['status'] != 'valid':
        raise ValueError('Planning unavailable/invalid: '+str(parsed.get('schema_errors')))
    plan = parsed['document']
    regions = {r['id'] for r in plan['regions']}
    groups = {r['id']:r for r in plan['groups']}
    anchors = {r['id']:r for r in plan['anchors']}
    rows = [*plan['regions'], *plan['groups'], *plan['anchors'], *plan['evidence']]
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)) or any(k.startswith('patch_') for k in ids):
        raise ValueError('All candidate IDs must be unique and must not use fallback patch IDs')
    for row in [*plan['groups'], *plan['anchors'], *plan['evidence']]:
        if row['region_id'] not in regions:
            raise ValueError('Unknown Region endpoint')
    for row in plan['evidence']:
        for key, lookup in (('group_id', groups), ('anchor_id', anchors)):
            if row[key] is not None and (row[key] not in lookup or
                    lookup[row[key]]['region_id'] != row['region_id']):
                raise ValueError('Unknown or cross-Region '+key)
    result = dict(image_size=list(size), regions=[], anchors=[], groups=deepcopy(plan['groups']),
        atomic_evidence=deepcopy(plan['evidence']), inventory_complete=False, reviewed=False,
        usage='provisional/debug', source='Reference-only Codex CLI planning; not GT',
        provenance=dict(backend='codex_cli', planning_response='planning_response.json',
                        input_side='reference_only', expected_answers_supplied=False))
    for kind in ('regions', 'anchors'):
        for row in plan[kind]:
            x1,y1,x2,y2 = row['bbox']
            if x1 >= x2 or y1 >= y2:
                raise ValueError('Degenerate/reversed model bbox: '+row['id'])
            box = [round(v*size[i%2]/1000, 6) for i,v in enumerate(row['bbox'])]
            if box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError('Degenerate pixel bbox')
            clean = dict(row, bbox=box, raw_bbox_0_1000=deepcopy(row['bbox']),
                         reviewed=False, reliability=0., status='candidate',
                         provenance='Reference-only CLI output; no object-name or geometry input')
            if kind == 'regions':
                clean['metrics'] = ['appearance','spatial','statistical','perceptual']
            else:
                clean['importance'] = 1.
            result[kind].append(clean)
    for row in [*result['groups'], *result['atomic_evidence']]:
        row.update(reviewed=False, reliability=0., status='candidate',
                   provenance='Reference-only CLI planning; automatic, unreviewed')
    return result


def verification_protocol(evidence):
    """Claims/answers are excluded. Both sides receive identical neutral questions."""
    fields, questions = {}, []
    for row in evidence['atomic_evidence']:
        field = row['id']
        fields[field] = (dict(type='string', enum=['yes','no','unknown'])
            if row['answer_type']=='yes_no_unknown' else
            dict(anyOf=[dict(type='integer', minimum=0), dict(type='string', enum=['unknown'])]))
        questions.append(dict(evidence_id=field, field=field, region_id=row['region_id'],
            group_id=row['group_id'], anchor_id=row['anchor_id'], energy=row['type'],
            claim=row['claim'], question=row['question'], provenance=row['provenance'], reviewed=False))
    prompt = '\n'.join(row['id']+'：'+row['question']+' 答案类型：'+row['answer_type']
                       for row in evidence['atomic_evidence'])
    regions = [{k:row[k] for k in ('id','name','bbox')} for row in evidence['regions']]
    user = ('独立观察当前图片并回答以下中立问题。区域框仅表示固定评价范围（当前图片像素xyxy），'
        '不是其中对象的检测框；必要时可参考完整图像，移出区域不等于不存在。\n区域：'+
        json.dumps(regions, ensure_ascii=False)+'\n'+prompt+
        '\nyes_no_unknown只用yes/no/unknown；count_unknown只用非负整数或unknown。'
        '无法可靠判断时用unknown。只输出以问题ID为字段的JSON，不解释。')
    return contract(dict(system='你是视觉证据验证器。只根据当前图片回答问题，不猜测不可见内容。'
        'yes表示有充分证据，no表示能够确认不存在或关系不成立，证据不足时用unknown。只输出JSON。',
        user=user, schema=obj(fields))), questions


def overview(path, images, evidence, comparison):
    try:
        font_path='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
        font=ImageFont.truetype(font_path, 21)
    except OSError:
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
    width=1240
    texts=['M2 | saved M1 RGB + real CLI | unreviewed / provisional / debug',
        'Reference-only planning frozen before independent VQA. No new Blender execution.',
        'Verbatim frozen questions: verification_results.json (no post-hoc changes).']
    for row in comparison.get('results', []):
        # Do not render unreadable replacement glyphs on hosts without a CJK font.
        label=row['question'] if row['question'].isascii() else row['energy']+' evidence'
        texts += [row['evidence_id']+' / '+row['region_id']+' | '+label,
                  'Reference: '+str(row['reference_answer'])+' | Changed: '+str(row['render_answer'])+
                  ' | '+row['status']+' | no Energy contribution']
    lines=[line for text in texts for line in textwrap.wrap(text, width=86)]
    canvas=Image.new('RGB',(width,690+len(lines)*32),'white'); draw=ImageDraw.Draw(canvas)
    palette=['#d44020','#226ed5','#238e50','#8e4fa1']
    for i,(title,image_path) in enumerate(zip(('Baseline Reference','Changed Render'), images)):
        with Image.open(image_path) as im:
            im=im.convert('RGB'); scale=560/im.width
            im=im.resize((560,round(im.height*scale)),Image.Resampling.NEAREST)
        layer=ImageDraw.Draw(im)
        for index,row in enumerate(evidence.get('regions', [])):
            box=[round(v*scale) for v in row['bbox']]
            layer.rectangle(box, outline=palette[index%len(palette)],width=3)
            layer.text((box[0]+4,box[1]+2),row['id'],fill=palette[index%len(palette)],font=font)
        canvas.paste(im,(25+i*620,70));draw.text((25+i*620,20),title,fill='black',font=font)
    for i,line in enumerate(lines):
        draw.text((25,665+i*32),line,fill='black',font=font)
    canvas.save(path)


def finish(output):
    """Offline replay of saved real packets only; never call a model here."""
    output=Path(output).resolve(); inputs=read(output/'inputs.json')
    evidence=read(output/'reference_evidence.json')
    protocol,questions=verification_protocol(evidence)
    packets=[read(output/name) for name in ('reference_answers.json','render_answers.json')]
    if any(p['actual_input'] != protocol for p in packets):
        raise ValueError('Saved VQA contract differs from frozen Reference evidence')
    images=[output/inputs[k] for k in ('reference_rgb','render_rgb')]
    comparison=compare_answers(*packets,questions,
        image_pair=dict(reference_rgb=str(images[0]),render_rgb=str(images[1])))
    comparison=validate_diagnostics(comparison)
    save(output/'verification_results.json',comparison)
    m1=Path(inputs['prior_m1_directory'])
    manifest=dict(reference_rgb=inputs['reference_rgb'], render_rgb=inputs['render_rgb'],
        reference_evidence='reference_evidence.json', vlm_verification='verification_results.json',
        geometry=str(m1/'changed/geometry.json'), render_metadata=str(m1/'changed/export_metadata.json'),
        diagnostics=dict(groups='reference_evidence.json'),
        coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',
            basis='Saved paired M1 RGB, same exported camera/K/grid; no alignment or ROI movement'),
        camera_comparability='saved_same_controlled_fixture_camera_not_new_execution',
        evidence_category='unreviewed_candidate', provenance=dict(
            previous_execution_chain=str(m1/'execution_chain.json'), new_blender_executions=0,
            trust_note='Prior M1 execution retained; replay is not a new trusted execution'))
    save(output/'offline_manifest.json',manifest)
    report=run_manifest(output/'offline_manifest.json',output/'offline_evaluation')
    root_report=deepcopy(report)
    root_report['coordinates']['valid_mask']='offline_evaluation/valid_pixels.png'
    save(output/'report.json',root_report)
    overview(output/'comparison.png',images,evidence,comparison)
    return report,comparison


def write_summary(output, report, comparison):
    def number(value):
        return 'N/A' if value is None else str(value)
    lines=['# M2 Reference Evidence + Real VLM End-to-End', '',
        '**reviewed:false · provisional/debug · no formal Benchmark score.**', '',
        'Saved first-party M1 RGB → Reference-only CLI planning → frozen evidence → independent '
        'Reference/Changed VQA → deterministic comparison → existing Offline Evaluator.', '',
        'No new Blender execution, Ofox, GPU, SAM/SLIC/DINO or Agent code. Prior M1 receipts are '
        'provenance only; static replay remains pose_consistent_unverified.', '',
        '## Actual calls', '', '| Stage | Source | Status | Input tokens | Output tokens | Seconds |',
        '| --- | --- | --- | --- | --- | --- |']
    for stage in ('planning_response','reference_answers','render_answers'):
        packet=read(output/(stage+'.json')); tokens=packet.get('token_usage',{})
        lines.append('| '+' | '.join(map(str,[stage,packet['source_kind'],packet['status'],
            tokens.get('input_tokens'),tokens.get('output_tokens'),packet.get('elapsed_seconds')]))+' |')
    models=sorted({str(read(output/(stage+'.json')).get('model_requested')) for stage in
                   ('planning_response','reference_answers','render_answers')})
    lines += ['', 'Requested model(s): '+', '.join(models)+'; observed remote snapshot may be null. '
        'Token counts are CLI-reported usage (including platform context), not Ofox billing. '
        'No retry. Temporary cwd and tools disabled do not guarantee filesystem confinement.', '',
        '## Frozen questions and actual answers', '',
        '| ID / Region / Group / Anchor | Question | Reference | Changed | Comparison |',
        '| --- | --- | --- | --- | --- |']
    for row in comparison['results']:
        fields=[' / '.join(number(row.get(k)) for k in ('evidence_id','region_id','group_id','anchor_id')),
                row['question'],number(row['reference_answer']),number(row['render_answer']),row['status']]
        lines.append('| '+' | '.join(f.replace('|','\\|').replace('\n',' ') for f in fields)+' |')
    lines += ['', 'These are model answers, not GT. Same count/order can miss metric displacement; '
        'satisfied does not establish reconstruction fidelity. No after-the-fact question edits.', '',
        '## Existing measurements', '', '| Energy | Conditional debug value |', '| --- | --- |']
    lines += [f"| {key} | {number(value['value'])} |" for key,value in report['energies'].items()]
    lines += ['', 'Structural: '+number(report['structural_energy'])+
        '. Geometry is diagnostic; unreviewed structural checks are not scored. '
        'Spatial/Statistical numeric image proxies are distinct from VQA answers. '
        'All automatic semantic evidence has reliability zero, with no Energy contribution.', '',
        '## Reproduce without model calls', '', '```bash',
        'python3 -B -m e_harness.benchmark offline --manifest '+str(output/'offline_manifest.json')+
        ' --output /tmp/projecte-m2-replay-new',
        "python3 -B -m unittest discover -s tests -p 'test_reference_vlm_pilot.py'", '```', '',
        'Use the documented dependencies and a new output directory. Live driver execution '
        'requires separate authorization for up to three requests. Strong input isolation, '
        'verifiable model snapshots, independent human review and harder evidence-validity '
        'experiments remain necessary. Runtime remains blocked.']
    (output/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def planning_failure(m1, output, reference, detail):
    """Keep RGB/Geometry evaluation available without manufacturing a plan or VQA."""
    rendered='images/'+uuid.uuid4().hex+'.png'
    with Image.open(m1/'changed/render.png') as image:
        image.convert('RGB').save(output/rendered)
    save(output/'failure.json',dict(error=detail,reviewed=False,usage='provisional/debug'))
    save(output/'verification_results.json',dict(status='unavailable',results=[],reason=detail,
        reviewed=False,energy_contribution=False,usage='provisional/debug'))
    manifest=dict(reference_rgb=reference,render_rgb=rendered,
        geometry=str(m1/'changed/geometry.json'),render_metadata=str(m1/'changed/export_metadata.json'),
        coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='Saved paired M1 RGB'),
        provenance=dict(new_blender_executions=0,planning_failure=detail))
    save(output/'offline_manifest.json',manifest)
    report=run_manifest(output/'offline_manifest.json',output/'offline_evaluation')
    report['coordinates']['valid_mask']='offline_evaluation/valid_pixels.png'
    save(output/'report.json',report)
    overview(output/'comparison.png',[output/reference,output/rendered],{}, {})
    (output/'summary.md').write_text('# M2 planning unavailable\n\nreviewed:false; provisional/debug.\n\n'+
        detail+'\n\nNo VQA attempted. RGB/Geometry evaluation retained; no plan or answers invented. '
        'No new Blender execution or formal qualification.\n')


def run(m1, output, *, model='gpt-6-sol', timeout=180):
    m1,output=Path(m1).resolve(),Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'images').mkdir()
    reference='images/'+uuid.uuid4().hex+'.png'
    with Image.open(m1/'baseline/render.png') as image:
        size=image.size; image.convert('RGB').save(output/reference)
    protocol=planning_protocol()
    save(output/'planning_protocol.json',protocol)
    probe=probe_cli(output/reference,protocol)
    save(output/'cli_preflight.json',probe)
    if probe['status'] != 'available':
        planning_failure(m1,output,reference,'CLI preflight unavailable; zero model attempts')
        return
    ledger=[]
    def call(image, protocol, stage):
        # Exclusive reservation survives crashes. No resume/retry mode is provided.
        save(output/(stage+'_reserved.json'),dict(stage=stage,model=model,automatic_retries=0))
        packet=codex_answer(image,protocol,ledger=ledger,model=model,timeout=timeout,
                            max_requests=3,request_id=stage)
        save(output/(stage+'.json'),packet)
        save(output/(stage+'_ledger.json'),deepcopy(ledger))
        return packet
    planning=call(output/reference,protocol,'planning_response')
    try:
        evidence=evidence_from_plan(planning,size)
    except ValueError as exc:
        planning_failure(m1,output,reference,str(exc))
        return
    save(output/'reference_evidence.json',evidence)
    frozen=(output/'reference_evidence.json').read_bytes()
    (output/'reference_evidence.json').chmod(0o444)
    protocol,questions=verification_protocol(evidence)
    save(output/'verification_protocol.json',protocol)
    save(output/'verification_questions.json',questions)
    # Changed pixels are first read only after the Reference candidate file is frozen.
    rendered='images/'+uuid.uuid4().hex+'.png'
    with Image.open(m1/'changed/render.png') as image:
        if image.size != size:
            raise ValueError('Saved M1 images are not on the same coordinate grid')
        image.convert('RGB').save(output/rendered)
    save(output/'inputs.json',dict(reference_rgb=reference,render_rgb=rendered,
        prior_m1_directory=str(m1),new_blender_executions=0,reviewed=False))
    call(output/reference,protocol,'reference_answers')
    call(output/rendered,protocol,'render_answers')
    if (output/'reference_evidence.json').read_bytes() != frozen:
        raise ValueError('Frozen Reference evidence was modified')
    report,comparison=finish(output)
    write_summary(output,report,comparison)
    save(output/'integration_checks.json',dict(
        actual_model_attempts=len(ledger), ledger=ledger, automatic_retries=0,
        reference_frozen_before_changed_read=True, frozen_bytes_unchanged=True,
        identical_verification_contract=True, strict_filesystem_isolation=False,
        vlm_pair_status=report['diagnostics']['vlm_verification']['status'],
        questions_linked_to_existing_regions=True, groups_optional=True,
        new_blender_executions=0, prior_execution_not_recertified=True,
        all_vlm_results_unreviewed=True, vlm_energy_contribution=False, formal_eligible=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['run'])
    parser.add_argument('--m1', type=Path, default=ROOT/'results/trusted_blender_e2e_pilot')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='gpt-6-sol')
    parser.add_argument('--timeout', type=float, default=180)
    args=parser.parse_args()
    run(args.m1,args.output,model=args.model,timeout=args.timeout)


if __name__=='__main__':
    main()
