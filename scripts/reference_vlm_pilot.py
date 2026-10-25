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
    parse_answer, probe_cli, validate_diagnostics, answer_schema,
    LEGACY_PROTOCOL, EXISTING_SCENE_PROTOCOL, VERIFICATION_SYSTEM)


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


PLANNING_SYSTEM = '''你是 Project e 的单图像评价证据规划器。

你的任务是仅依据当前 Reference RGB，提取适合评价三维场景重建质量的可观察证据。
你看不到被评测 Agent 的 Render、Blender 场景、对象名称或任何预期错误。

请按以下原则工作：
- 首先识别约 1–5 个有评价意义的粗粒度 Region，简单场景允许只有一个。Region 是评价范围，不是精确物体 Mask。
- 对重复或成组内容，例如书籍、唱片、柜体、桌椅组合等，必要时建立 Semantic Group。一个 Group 可以包含多个物体，无须枚举每个实例。
- 对特别重要、且需要投影位置测量的对象，可以选择少量 Anchor。
- 为主要 Region 或 Group 选择有区分力的原子证据，不要只集中于物体存在和数量。
- 在确实可观察时，考虑对象类别、显著属性、离散空间关系、局部排列、结构分隔、相对布局及尺度特征。
- 不强制每个 Region 具备所有类型的证据，也不强制图片一定包含 Group。
- 每个问题仅检查一个明确事实；避免含糊的“是否合理”“是否相似”“是否重建正确”。
- 只能根据可见信息提问。遮挡、类别混淆或细节不足时，必须允许 unknown。
- left_of/right_of 等方向关系定义为当前输入相机视角下的投影关系。
- 不得将不可见的内部构造、真实物理连接或三维深度推断当作直接观察。
- 不得根据被测 Render 选择、更换或修改证据。
- 输出符合 Schema 的 JSON，不输出期望的验证答案。

根据图像复杂度，优先形成少量高质量的原子证据，而不是生成冗长问题清单。
证据预算是上限，具体是否生成取决于可观察性。'''


def planning_protocol(protocol_version=LEGACY_PROTOCOL, *, evidence_budget=None):
    """No scene vocabulary, fixture labels, object names or expected change in this input."""
    if protocol_version == EXISTING_SCENE_PROTOCOL:
        budget = 10 if evidence_budget is None else evidence_budget
        if type(budget) is not int or not 1 <= budget <= 10:
            raise ValueError('Evidence budget must be an integer in 1..10')
        schema = obj(dict(
            regions=dict(type='array', minItems=1, maxItems=5, items=obj(dict(
                id=ID, name=TEXT, description=TEXT, bbox=BOX))),
            groups=dict(type='array', maxItems=5, items=obj(dict(id=ID, region_id=ID, name=TEXT, scope=TEXT))),
            anchors=dict(type='array', maxItems=3, items=obj(dict(id=ID, region_id=ID, category=TEXT, bbox=BOX))),
            evidence=dict(type='array', maxItems=budget, items=obj(dict(
                id=ID, region_id=ID, group_id=OPTIONAL_ID, anchor_id=OPTIONAL_ID,
                type=dict(type='string', enum=['semantic', 'spatial', 'statistical']),
                claim=TEXT, question=TEXT,
                answer_type=dict(type='string', enum=['yes_no_unknown', 'count_unknown', 'categorical_unknown']),
                categories=dict(type='array', maxItems=12,
                    items=dict(type='string', minLength=1, maxLength=64)))))))
        return contract(dict(system=PLANNING_SYSTEM,
            user='仅根据当前 Reference RGB 规划评价证据，最多 '+str(budget)+' 条原子命题；不要为填满预算生成问题。'
            'Region bbox 使用0–1000归一化xyxy粗范围；Anchor bbox仅表示其自身可见范围。'
            '使用唯一ASCII ID并正确引用region_id，未用group_id或anchor_id填null。groups和anchors允许为空。'
            '证据类型为semantic、spatial或statistical。answer_type为yes_no_unknown、count_unknown或categorical_unknown。'
            '类别型问题的categories必须在此Reference-only阶段给出1–12个互异、简短、中立的候选类别，'
            '不包括保留的unknown或ambiguous；其他答案类型的categories填空数组。'
            '类别集合不代表期望答案；不要输出expected、答案、置信度或推理。'
            '连续投影位置、相对面积和间距应由可靠RGB定位及确定性测量获得，不要求视觉验证器估算精确坐标。',
            schema=schema))
    if protocol_version != LEGACY_PROTOCOL or evidence_budget not in (None, 3):
        raise ValueError('Unknown protocol or attempted change to the frozen legacy budget')
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


def evidence_from_plan(packet, size, *, protocol_version=LEGACY_PROTOCOL, evidence_budget=None):
    """Validate full plan and references before freezing; never repair model coordinates."""
    protocol = planning_protocol(protocol_version, evidence_budget=evidence_budget)
    if packet.get('actual_input') != protocol:
        raise ValueError('Planning input differs from the frozen Reference-only contract')
    parsed = parse_answer(packet.get('raw_answer'), protocol['schema'])
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
        answer_schema(row['answer_type'], row.get('categories'))
        for key, lookup in (('group_id', groups), ('anchor_id', anchors)):
            if row[key] is not None and (row[key] not in lookup or
                    lookup[row[key]]['region_id'] != row['region_id']):
                raise ValueError('Unknown or cross-Region '+key)
    result = dict(image_size=list(size), regions=[], anchors=[], groups=deepcopy(plan['groups']),
        atomic_evidence=deepcopy(plan['evidence']), inventory_complete=False, reviewed=False,
        usage='provisional/debug', source='Reference-only Codex CLI planning; not GT',
        provenance=dict(backend='codex_cli', planning_response='planning_response.json',
                        input_side='reference_only', expected_answers_supplied=False))
    if protocol_version != LEGACY_PROTOCOL:
        result['evidence_protocol'] = dict(version=protocol_version,
            evidence_budget=protocol['schema']['properties']['evidence']['maxItems'])
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
    settings = evidence.get('evidence_protocol', dict(version=LEGACY_PROTOCOL))
    version = settings['version']
    planning_protocol(version, evidence_budget=settings.get('evidence_budget'))
    fields, questions = {}, []
    for row in evidence['atomic_evidence']:
        field = row['id']
        if field in fields:
            raise ValueError('Duplicate evidence ID')
        if version == LEGACY_PROTOCOL and row['answer_type'] not in ('yes_no_unknown', 'count_unknown'):
            raise ValueError('Legacy protocol does not support this answer_type')
        fields[field] = answer_schema(row['answer_type'], row.get('categories'))
        questions.append(dict(evidence_id=field, field=field, region_id=row['region_id'],
            group_id=row['group_id'], anchor_id=row['anchor_id'], energy=row['type'],
            claim=row['claim'], question=row['question'], provenance=row['provenance'], reviewed=False))
        if version == EXISTING_SCENE_PROTOCOL:
            questions[-1].update(answer_type=row['answer_type'], categories=deepcopy(row['categories']),
                                 protocol_version=version)
    if version == EXISTING_SCENE_PROTOCOL:
        # Deliberate allowlist: no claim, Reference answer, expected value or reviewer labels.
        neutral = [{k:row[k] for k in ('id','region_id','group_id','anchor_id','question','answer_type','categories')}
                   for row in evidence['atomic_evidence']]
        regions = [{k:row[k] for k in ('id','name','bbox')} for row in evidence['regions']]
        user = ('独立观察当前提供的一张图像，回答以下冻结的中立问题。'
            '区域框为原图像素xyxy固定评价范围，两侧使用相同坐标及完整图像上下文。\n区域定义：'+
            json.dumps(regions, ensure_ascii=False)+'\n问题与答案空间：'+json.dumps(neutral, ensure_ascii=False)+
            '\nyes_no_unknown仅用yes/no/unknown；count_unknown仅用非负整数或unknown；'
            'categorical_unknown仅从冻结categories或ambiguous/unknown中选择。'
            '不要估算连续投影距离或面积，不输出总体评分。只输出以问题ID为字段的JSON。')
        return contract(dict(system=VERIFICATION_SYSTEM, user=user, schema=obj(fields))), questions
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


def planning_failure(m1, output, reference, detail, *, evidence=None):
    """Keep RGB/Geometry evaluation available without manufacturing a plan or VQA."""
    rendered='images/'+uuid.uuid4().hex+'.png'
    with Image.open(m1/'changed/render.png') as image:
        image.convert('RGB').save(output/rendered)
    save(output/('failure.json' if evidence is None else 'verification_unavailable.json'),
         dict(reason=detail,reviewed=False,usage='provisional/debug'))
    save(output/'verification_results.json',dict(status='unavailable',results=[],reason=detail,
        reviewed=False,energy_contribution=False,usage='provisional/debug'))
    manifest=dict(reference_rgb=reference,render_rgb=rendered,
        geometry=str(m1/'changed/geometry.json'),render_metadata=str(m1/'changed/export_metadata.json'),
        coordinates=dict(convention='reference_pixel_xyxy',render_mapping='identity',basis='Saved paired M1 RGB'),
        provenance=dict(new_blender_executions=0,planning_failure=detail))
    if evidence is not None:
        manifest['reference_evidence']='reference_evidence.json'
        del manifest['provenance']['planning_failure']
        manifest['provenance'].update(planning_status='valid', verification_status='unavailable_no_questions')
    save(output/'offline_manifest.json',manifest)
    report=run_manifest(output/'offline_manifest.json',output/'offline_evaluation')
    report['coordinates']['valid_mask']='offline_evaluation/valid_pixels.png'
    save(output/'report.json',report)
    overview(output/'comparison.png',[output/reference,output/rendered],evidence or {}, {})
    title = '# Planning valid; no observable atomic questions' if evidence is not None else '# M2 planning unavailable'
    (output/'summary.md').write_text(title+'\n\nreviewed:false; provisional/debug.\n\n'+
        detail+'\n\nNo VQA attempted. RGB/Geometry evaluation retained; no plan or answers invented. '
        'No new Blender execution or formal qualification.\n')


def run(m1, output, *, model='gpt-6-sol', timeout=180,
        protocol_version=LEGACY_PROTOCOL, evidence_budget=None):
    protocol=planning_protocol(protocol_version, evidence_budget=evidence_budget)
    m1,output=Path(m1).resolve(),Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'images').mkdir()
    reference='images/'+uuid.uuid4().hex+'.png'
    with Image.open(m1/'baseline/render.png') as image:
        size=image.size; image.convert('RGB').save(output/reference)
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
        evidence=evidence_from_plan(planning,size,protocol_version=protocol_version,evidence_budget=evidence_budget)
    except ValueError as exc:
        planning_failure(m1,output,reference,str(exc))
        return
    save(output/'reference_evidence.json',evidence)
    frozen=(output/'reference_evidence.json').read_bytes()
    (output/'reference_evidence.json').chmod(0o444)
    if not evidence['atomic_evidence']:
        planning_failure(m1,output,reference,'No observable atomic questions; no VQA attempts',evidence=evidence)
        return
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
    parser.add_argument('--protocol-version', choices=[LEGACY_PROTOCOL, EXISTING_SCENE_PROTOCOL],
                        default=EXISTING_SCENE_PROTOCOL)
    parser.add_argument('--evidence-budget', type=int, default=None,
                        help='New protocol: maximum 1..10 questions, not a quota (default 10)')
    args=parser.parse_args()
    run(args.m1,args.output,model=args.model,timeout=args.timeout,
        protocol_version=args.protocol_version,evidence_budget=args.evidence_budget)


if __name__=='__main__':
    main()
