"""Prepare a two-stage human audit from saved batch results; no inference or scoring.

Only Pillow and the standard library are used. Images and the coordinator key stay
private; the seven top-level audit documents contain no image bytes or host paths.
"""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


BASE_COMMIT = '77d9ec422cb240bb6c092bd2b56b2078efa4698b'
HUMAN_FIELDS = {
    'reference_observability': ('observable', 'not_observable', 'uncertain'),
    'reference_evidence_validity': ('valid', 'invalid', 'uncertain'),
    'reference_answer_correctness': ('correct', 'incorrect', 'uncertain'),
    'render_observability': ('observable', 'not_observable', 'uncertain'),
    'render_answer_correctness': ('correct', 'incorrect', 'uncertain'),
    'comparison_judgment': ('reasonable', 'unreasonable', 'uncertain'),
    'candidate_difference_confirmation': ('confirmed', 'not_confirmed', 'uncertain', 'not_applicable'),
    'satisfied_false_negative': ('yes', 'no', 'uncertain', 'not_applicable'),
    'abstention_appropriateness': ('reasonable', 'unreasonable', 'uncertain', 'not_applicable'),
    'camera_confound': ('yes', 'no', 'uncertain'),
    'occlusion_confound': ('yes', 'no', 'uncertain'),
    'category_confusion': ('yes', 'no', 'uncertain'),
}
FREE_HUMAN_FIELDS = ('reviewer_id', 'reviewed_at_utc', 'image_support',
                     'duplicate_issue_id', 'blind_difference_ids', 'notes')


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_csv(path, rows):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def collect_rows(source, config):
    """Copy frozen machine fields; never reinterpret or repair model answers."""
    rows = []
    for index, pair in enumerate(config['pairs'], 1):
        packet = read_json(source / 'pairs' / pair['pair_id'] / 'verification_results.json')
        evidence = read_json(source / 'references' / pair['task_id'] / 'reference_evidence.json')
        by_id = {r['id']: r for r in evidence['atomic_evidence']}
        seen = set()
        for result in packet['results']:
            eid = result['evidence_id']
            if eid in seen or eid not in by_id:
                raise ValueError('Duplicate or unbound evidence ID')
            seen.add(eid)
            atom = by_id[eid]
            if result['question'] != atom['question'] or result['claim'] != atom['claim']:
                raise ValueError('Question/claim differs from frozen Reference evidence')
            if result['status'] not in ('satisfied', 'candidate_violated', 'unknown', 'unavailable'):
                raise ValueError('Unexpected frozen comparison status')
            rows.append(dict(audit_id=f'P{index:03d}', pair_id=pair['pair_id'],
                task_id=pair['task_id'], evidence_id=eid, region_id=result.get('region_id'),
                group_id=result.get('group_id'), anchor_id=result.get('anchor_id'),
                energy=result['energy'], claim=result['claim'], question=result['question'],
                answer_type=result.get('answer_type'), categories=result.get('categories', []),
                reference_answer=result['reference_answer'], render_answer=result['render_answer'],
                frozen_status=result['status']))
        if seen != set(by_id):
            raise ValueError('Frozen evidence missing a paired verification result')
    return rows


def prioritize(rows):
    """All non-satisfied; deterministic coverage sample of satisfied, no accuracy claim."""
    selected = {(r['pair_id'], r['evidence_id']): 'all_' + r['frozen_status']
                for r in rows if r['frozen_status'] != 'satisfied'}
    satisfied = [r for r in rows if r['frozen_status'] == 'satisfied']
    # Cover each available task x evidence-type cell, then every pair/checkpoint.
    for keys, reason in [(('task_id', 'energy'), 'satisfied_task_energy_stratum'),
                         (('pair_id',), 'satisfied_pair_coverage')]:
        seen = set()
        for row in satisfied:
            cell = tuple(row[k] for k in keys)
            if cell not in seen:
                selected.setdefault((row['pair_id'], row['evidence_id']), reason)
                seen.add(cell)
    return selected


def review_template(rows, selected):
    result = []
    for row in rows:
        row = dict(row)
        for key in ('reference_answer', 'render_answer', 'categories'):
            row[key] = json.dumps(row[key], ensure_ascii=False)
        row.update(priority_reason=selected.get((row['pair_id'], row['evidence_id']), ''),
                   review_status='unreviewed', reviewed='false')
        row.update({key: '' for key in (*HUMAN_FIELDS, *FREE_HUMAN_FIELDS)})
        result.append(row)
    return result


def duplicate_review_candidates(rows):
    """Shared Group/Anchor is a review cue, not a confirmed shared physical error."""
    scopes = defaultdict(list)
    for row in rows:
        if row['frozen_status'] != 'candidate_violated':
            continue
        for field in ('group_id', 'anchor_id'):
            if row.get(field):
                scopes[(row['pair_id'], field, row[field])].append(row['evidence_id'])
    return [dict(pair_id=k[0], scope_type=k[1], scope_id=k[2], evidence_ids=v,
                 status='shared_scope_requires_human_check', reviewed=False,
                 same_underlying_difference=None, energy_contribution=False)
            for k, v in scopes.items() if len(v) > 1]


def summarize_reviews(template, filled):
    """Separate human annotations only. This never edits evidence or produces Energy.

    Rates describe explicitly adjudicated items, not the unreviewed population.
    Reviewer identity is a self-attestation; software cannot prove independence.
    """
    expected = {(r['pair_id'], r['evidence_id']): r for r in template}
    accepted, seen = [], set()
    for row in filled:
        key = row['pair_id'], row['evidence_id']
        if key not in expected or key in seen:
            raise ValueError('Unknown or duplicate review key')
        seen.add(key)
        for field, value in expected[key].items():
            if field not in (*HUMAN_FIELDS, *FREE_HUMAN_FIELDS, 'review_status', 'reviewed'):
                if str(row.get(field, '')) != str(value):
                    raise ValueError('Human file changed a frozen machine field: ' + field)
        if row.get('review_status') == 'unreviewed':
            if row.get('reviewed') != 'false' or any(row.get(k) for k in HUMAN_FIELDS):
                raise ValueError('Unreviewed row cannot carry human judgments')
            continue
        if (row.get('review_status') != 'completed' or row.get('reviewed') != 'true'
                or not row.get('reviewer_id', '').strip() or not row.get('reviewed_at_utc', '').strip()):
            raise ValueError('Completed review requires explicit human attribution')
        for key, allowed in HUMAN_FIELDS.items():
            if row.get(key) and row[key] not in allowed:
                raise ValueError('Invalid human label: ' + key)
        if not any(row.get(k) for k in HUMAN_FIELDS):
            raise ValueError('Completed review needs at least one actual human judgment')
        accepted.append(row)

    def rate(field, positive, negative, subset=None):
        population = [r for r in template if subset is None or subset(r)]
        values = Counter(r[field] for r in accepted if subset is None or subset(r))
        denominator = values[positive] + values[negative]
        return dict(status='pending' if not denominator else 'reviewed_subset_only',
            numerator=values[positive], adjudicated_denominator=denominator,
            population_items=len(population), unreviewed_items=sum(
                (r['pair_id'], r['evidence_id']) not in {(a['pair_id'], a['evidence_id']) for a in accepted}
                for r in population), uncertain_items=values['uncertain'],
            value=values[positive] / denominator if denominator else None)

    def unique_reference_rate(field, positive, negative):
        # Repeated renders share the same frozen Reference claim and answer.
        # Conflicting human annotations are unresolved, never majority-voted.
        grouped = defaultdict(set)
        for row in accepted:
            if row.get(field):
                grouped[(row['task_id'], row['evidence_id'])].add(row[field])
        values = Counter(next(iter(v)) if len(v) == 1 else 'conflict' for v in grouped.values())
        total = len({(r['task_id'], r['evidence_id']) for r in template})
        denominator = values[positive] + values[negative]
        return dict(status='pending' if not denominator else 'reviewed_subset_only',
            unit='unique task_id / evidence_id', numerator=values[positive],
            adjudicated_denominator=denominator, population_items=total,
            unreviewed_items=total-len(grouped), uncertain_items=values['uncertain'],
            conflicting_items=values['conflict'], value=values[positive]/denominator if denominator else None)

    metrics = {
        'reference_evidence_validity': unique_reference_rate('reference_evidence_validity', 'valid', 'invalid'),
        'reference_vqa_correctness': unique_reference_rate('reference_answer_correctness', 'correct', 'incorrect'),
        'render_vqa_correctness': rate('render_answer_correctness', 'correct', 'incorrect'),
        'candidate_confirmation': rate('candidate_difference_confirmation', 'confirmed', 'not_confirmed',
                                      lambda r: r['frozen_status'] == 'candidate_violated'),
        'satisfied_false_negative': rate('satisfied_false_negative', 'yes', 'no',
                                       lambda r: r['frozen_status'] == 'satisfied'),
        'abstention_appropriateness': rate('abstention_appropriateness', 'reasonable', 'unreasonable',
                                        lambda r: r['frozen_status'] == 'unknown' or any(
                                            r[k] in ('"ambiguous"', '"unknown"') for k in
                                            ('reference_answer', 'render_answer'))),
    }
    duplicates = defaultdict(list)
    for row in accepted:
        if row.get('duplicate_issue_id'):
            duplicates[(row['pair_id'], row['duplicate_issue_id'])].append(row['evidence_id'])
    return dict(status='pending' if not accepted else 'partial_human_annotations',
        completed_reviews=len(accepted), metrics=metrics,
        reference_unit='unique task/evidence IDs; Render judgments remain pair-specific and clustered',
        blind_uncovered_differences=dict(status='pending', value=None,
            reason='Requires frozen blind free-text differences and separate human coverage linking; no automatic recall'),
        duplicate_associations=[dict(pair_id=k[0], issue_id=k[1], evidence_ids=v)
                                for k, v in duplicates.items()], energy_contribution=False,
        human_independence='Must be established by coordinator, not inferred by this program')


def lineage_strata(config, batch):
    """Use saved run_config.load_trajectory to link continuations, never filenames alone."""
    roots = {str(Path(p['provenance']['run_config']).parent): p['pair_id'] for p in config['pairs']}
    parents = {}
    for pair in config['pairs']:
        run_config = read_json(pair['provenance']['run_config'])
        load = run_config.get('agent', {}).get('load_trajectory')
        matches = [pid for root, pid in roots.items()
                   if load and Path(root) in Path(load).parents]
        if len(matches) > 1:
            raise ValueError('Ambiguous continuation source')
        parents[pair['pair_id']] = matches[0] if matches else None
        if load and not matches:
            raise ValueError('Continuation exists outside batch; explicit lineage review needed')

    def root(pid):
        seen = set()
        while parents[pid]:
            if pid in seen:
                raise ValueError('Cyclic Agent lineage')
            seen.add(pid)
            pid = parents[pid]
        return pid

    measured = {p['pair_id']: p for p in batch['pairs']}
    strata = []
    for index, pair in enumerate(config['pairs'], 1):
        actual = measured[pair['pair_id']]
        camera = actual['scene_validity']
        generic = pair['input_mode'] in ('rgb_only_with_generic_protocol',
                                        'rgb_with_generic_reconstruction_instructions')
        strata.append(dict(audit_id=f'P{index:03d}', pair_id=pair['pair_id'],
            task_id=pair['task_id'], input_mode=pair['input_mode'],
            input_stratum='rgb_generic_protocol' if generic else 'rgb_scene_specific_text',
            agent=pair['agent'], run_id=pair['run_id'], completion=pair['completion'],
            completion_stratum='completed' if pair['completion'] == 'completed' else 'incomplete_checkpoint',
            lineage_id=root(pair['pair_id']), continuation_of=parents[pair['pair_id']] or '',
            lineage_source='saved run_config.agent.load_trajectory; absent means no recorded continuation',
            task_cluster=pair['task_id'], independent_sample='not_established',
            camera_protocol=camera['camera_protocol'], pose_matches_T0=camera.get('pose_matches_T0'),
            camera_reason=camera['reason'], reference_camera='unknown',
            historical_png_blend_sync='unknown', formal_eligible=False, reviewed=False,
            usage='provisional/debug'))
    return strata


def geometry_inventory(config, source):
    records = []
    for pair in config['pairs']:
        geometry = read_json(source / 'pairs' / pair['pair_id'] / 'geometry.json')
        graph = pair.get('scene_graph_cache') or {}
        visibility = pair.get('group_visibility_cache') or {}
        # Read cache metadata only; no Blender, mesh evaluation, or asset loading.
        if graph.get('source'):
            saved = read_json(graph['source'])
            object_count = len(saved.get('objects', []))
        else:
            object_count = None
        records.append(dict(pair_id=pair['pair_id'], blend_exists=Path(pair['blend']).is_file(),
            blend_opened=False, geometry_status=geometry.get('status'), geometry_reason=geometry.get('reason'),
            collision_records=len(geometry.get('collisions', [])),
            support_object_records=len(geometry.get('objects', [])),
            evaluated_component_records=len(geometry.get('components', [])),
            scene_graph_objects=object_count, graph_matches_blend=graph.get('source_blend_matches'),
            group_id_cache_available=bool(visibility),
            safe_current_collision_contact_rank_extraction=False,
            structural_energy=None, reason='Names, base-mesh bounds and sampled Group-ID support do not establish contact, penetration or complete evaluated affine rank'))
    return records


def font(size):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)


def contact_sheet(a, b, title, lines=(), *, width=768):
    """No generated interpretation; pixels plus verbatim frozen text only."""
    panels = []
    for image in (a, b):
        image = image.copy().convert('RGB')
        image.thumbnail((width, width), Image.Resampling.LANCZOS)
        panels.append(image)
    wrapped = [part for line in lines for part in textwrap.wrap(line, width=137) or ['']]
    height = max(p.height for p in panels) + 88 + 25 * len(wrapped)
    out = Image.new('RGB', (2 * width + 36, height), '#ffffff')
    draw = ImageDraw.Draw(out)
    draw.text((12, 8), title, font=font(21), fill='#111111')
    for i, (label, panel) in enumerate(zip(('Reference', 'Render'), panels)):
        x = 12 + i * (width + 12)
        draw.text((x, 38), label, font=font(18), fill='#222222')
        out.paste(panel, (x, 66))
    y = max(p.height for p in panels) + 76
    for line in wrapped:
        draw.text((12, y), line, font=font(17), fill='#111111')
        y += 25
    return out


def private_images(source, output, config, rows, selected):
    private = output / 'private'
    private.mkdir(mode=0o700)
    blind, stage2 = private / 'stage1_blind', private / 'stage2_evidence'
    blind.mkdir(mode=0o700); stage2.mkdir(mode=0o700)
    key = []
    for index, pair in enumerate(config['pairs'], 1):
        aid = f'P{index:03d}'
        refpath = source / 'references' / pair['task_id'] / 'reference.png'
        renpath = source / 'pairs' / pair['pair_id'] / 'render.png'
        ref, ren = Image.open(refpath).convert('RGB'), Image.open(renpath).convert('RGB')
        evidence = read_json(refpath.parent / 'reference_evidence.json')
        if ref.size != ren.size or list(ref.size) != evidence['image_size']:
            raise ValueError('Prepared coordinate grids disagree')
        contact_sheet(ref, ren, f'{aid} / Full model-input grid').save(blind / f'{aid}_full.png')
        # Higher-resolution full images aid visibility review. No registration or ROI movement.
        with Image.open(pair['reference_rgb']) as native_ref, Image.open(pair['render_rgb']) as native_ren:
            contact_sheet(native_ref, native_ren, f'{aid} / Native full frames; no alignment',
                          width=1500).save(blind / f'{aid}_native.png')
        region_files = {}
        for region in evidence['regions']:
            box = region['bbox']
            if len(box) != 4 or not all(math.isfinite(x) for x in box):
                raise ValueError('Invalid fixed ROI')
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= ref.width and 0 <= y1 < y2 <= ref.height):
                raise ValueError('ROI out of common image bounds')
            pixels = (math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2))
            filename = f'{aid}_{region["id"]}.png'
            contact_sheet(ref.crop(pixels), ren.crop(pixels),
                f'{aid} / Fixed scope {region["id"]}; common-grid crop; no new detail').save(blind / filename)
            region_files[region['id']] = filename
        for row in rows:
            if row['pair_id'] != pair['pair_id']:
                continue
            lines = [f'{row["evidence_id"]} | {row["energy"]} | {row["region_id"]}',
                     'Frozen claim: ' + row['claim'], 'Question: ' + row['question'],
                     'Frozen answer space: ' + row['answer_type'] + ' ' + json.dumps(row['categories']),
                     'Reference answer: ' + json.dumps(row['reference_answer']),
                     'Render answer: ' + json.dumps(row['render_answer']),
                     'Machine comparison: ' + row['frozen_status'] + ' | Human review: unreviewed',
                     'Not GT; camera / occlusion / recognition uncertainty requires human inspection.']
            # Questions get full context here; neutral fixed-region closeups are linked in the key.
            contact_sheet(ref, ren, f'{aid} / Evidence audit / {row["evidence_id"]}', lines).save(
                stage2 / f'{aid}_{row["evidence_id"]}.png')
        key.append(dict(audit_id=aid, pair_id=pair['pair_id'], task_id=pair['task_id'],
            source_reference=str(Path(pair['reference_rgb']).resolve()),
            source_render=str(Path(pair['render_rgb']).resolve()),
            prepared_reference=str(refpath.resolve()), prepared_render=str(renpath.resolve()),
            valid_pixels=str((renpath.parent / 'valid_pixels.png').resolve()),
            regions=region_files,
            priority_evidence_ids=[r['evidence_id'] for r in rows if r['pair_id'] == pair['pair_id']
                                   and (r['pair_id'], r['evidence_id']) in selected]))
    write_json(private / 'coordinator_key.json', key)
    (blind / 'INSTRUCTIONS.md').write_text(
        '# 第一阶段：先记录图像差异\n\n只分发本目录与blind_difference_template.csv的副本。'
        '不要打开第二阶段、问题表、结果、分层信息或历史报告。先看*_full.png及*_native.png，'
        '记录主要可见差异和不确定性；冻结该记录后，才可看同目录中性固定范围近图。'
        '范围来自历史自动规划，可能提示关注位置，因此全图自由记录必须先冻结。'
        'Reference/Render不是质量标签；不要推断相机差异一定是重建错误。'
        '同一人若已知道历史判断，应主动披露，不声称严格盲审。\n')
    return dict(blind_pngs=len(list(blind.glob('*.png'))),
                evidence_pngs=len(list(stage2.glob('*.png'))),
                model_calls=0, blender_executions=0)


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError('Audit must not be written inside frozen source batch')
    config, batch = read_json(source / 'config.frozen.json'), read_json(source / 'report.json')
    rows = collect_rows(source, config)
    selected = prioritize(rows)
    template = review_template(rows, selected)
    strata = lineage_strata(config, batch)
    geometry = geometry_inventory(config, source)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_csv(output / 'human_review_template.csv', template)
    blind_rows = [dict(audit_id=s['audit_id'], difference_id=f'{s["audit_id"]}_D{j:02d}',
        scope='', visible_difference='', uncertainty='', possible_camera_or_occlusion='',
        reviewer_id='', reviewed_at_utc='', prior_exposure='', full_frame_notes_frozen_at_utc='',
        stage1_completed='false', reviewed='false') for s in strata for j in range(1, 4)]
    write_csv(output / 'blind_difference_template.csv', blind_rows)
    write_csv(output / 'protocol_strata.csv', strata)
    images = private_images(source, output, config, rows, selected)
    states = dict(Counter(r['frozen_status'] for r in rows))
    validity = dict(baseline_commit=BASE_COMMIT, frozen_batch='existing_scene_batch_20261025',
        pair_count=len(config['pairs']), unique_references=len({p['task_id'] for p in config['pairs']}),
        paired_comparisons=len(rows), unique_reference_evidence=len({(r['task_id'], r['evidence_id']) for r in rows}),
        frozen_status_counts=states, priority_review_count=len(selected),
        priority_status_counts=dict(Counter(r['frozen_status'] for r in rows
            if (r['pair_id'], r['evidence_id']) in selected)),
        satisfied_sampling='First saved item per task x energy cell, plus each pair; deterministic coverage sample, not random or prevalence representative',
        human_review=summarize_reviews(template, template), reviewed=False, usage='provisional/debug',
        formal_eligible=False, new_model_calls=0, image_preparation=images,
        input_strata=dict(Counter(r['input_stratum'] for r in strata)),
        completion_strata=dict(Counter(r['completion_stratum'] for r in strata)),
        recorded_agent_lineages=len({r['lineage_id'] for r in strata}),
        geometry_inventory=geometry, frozen_metric_coverage=batch['coverage'],
        duplicate_review_candidates=duplicate_review_candidates(rows),
        diagnostic_duplicate_links_status='pending human issue IDs; no claims merged, no penalties added')
    write_json(output / 'evidence_validity.json', validity)
    write_documents(output, validity, strata)
    return validity


def write_documents(output, validity, strata):
    enums = '\n'.join(f'- `{key}`: ' + ' / '.join(values) for key, values in HUMAN_FIELDS.items())
    (output / 'audit_packet.md').write_text(f'''# Evaluation Validity v0.1：人工审核包

状态：pending human review；reviewed=false；provisional/debug。只读取冻结批次，0次新模型、Blender、Agent或指标推理；原问题、回答、Energy及权重不改。

## 分发与冻结顺序

1. 协调者只向独立人类审核者分发服务器私有 `private/stage1_blind/` 和 [空白差异表](blind_difference_template.csv)。此文档、协议分层、问题表及其他历史实验**不要**同时分发。中性编号P001等只用于回填。软件不能保证人类没有先验知识，审核者须填写prior_exposure。
2. 先看每组全图：`*_full.png`是历史模型共同坐标输入；`*_native.png`是两侧原始全图的独立等比展示，非配准。先冻结全图自由记录，再看固定Region近图并追加观察。Region范围来自VLM，可能形成注意偏差，不属于完全无提示盲审；近图不含问题、答案或状态。三个空槽不是差异数，可追加行或填“未发现明确差异”。
3. 第一阶段副本冻结（填写UTC时间，并保留原副本）后，才分发私有 `private/stage2_evidence/`、[107条证据审核表](human_review_template.csv)。每项保留冻结claim、问题、类别空间、双方真实回答和程序状态；对应Region近图在第一阶段目录，映射位于仅协调者可读的 `private/coordinator_key.json`。
4. 优先完成全部13条candidate_violated、3条unknown，以及{validity['priority_status_counts'].get('satisfied', 0)}条分层satisfied，共{validity['priority_review_count']}条。priority_reason为空的其余项可随后扩展至全部107条。样本覆盖任务×证据类别及每组配对，是确定性覆盖抽样，不能外推91条satisfied总体误判率。
5. 保存填写后的**独立文件**，不要编辑冻结输入、原始JSON或空白模板。`review_status=completed`、`reviewed=true`只由真实人类填写；使用匿名审核者ID和UTC时间，实际姓名不公开。机器无法认证审核者身份/独立性。

## 逐条审核

先判断Reference命题本身是否可观察、成立，再独立判断两侧VQA答案是否正确。`satisfied`只表示答案相同，不能代替图像质量判断；`candidate_violated`不是已确认错误。unknown/ambiguous的弃权适当性要结合可见性。原生高分辨率能辨认而模型输入不能辨认时，在image_support中区分，不能忽略分辨率限制。

{enums}

所有人工标签默认为空；review_status初始unreviewed。`candidate_difference_confirmation`只用于候选差异，`satisfied_false_negative`只用于satisfied，其他项可填not_applicable。`satisfied_false_negative=yes`指本条冻结问题对应的事实确有可比较差异，却被相同回答漏报；未被问题覆盖的其他外观或细节差异应进入盲审覆盖表，不能算成本题VQA错误。`image_support`记录图像位置和依据；`notes`记录不确定性。Render物体移出固定ROI但在全图可见时，不能直接确认缺失。所有相机差异仍待确认。

同一配对多条问题若描述同一底层问题，在`duplicate_issue_id`填写相同人类指定ID（作用域为pair_id），不合并或改写原判断；在`blind_difference_ids`关联第一阶段差异。evidence_validity.json列出同一Group/Anchor下多条candidate_violated的共享范围提示，**不等于确认同一物理错误**，不得据此去重打分。第一阶段发现但所有冻结命题均未覆盖的差异，另存人工覆盖关联表；没有此表，不计算漏检率/召回率。

## 已审核标注如何接入现有计算

当前CSV是有效性审查，**不是Energy输入**。`verification_adapter.validate_diagnostics()`即使收到reviewed=true也重建为未审核诊断，不能用改一个布尔字段开启评分。Group/Atomic VQA尚无通用数值映射；人工核准答案不等于核准一个0/1惩罚。

现有Manifest支持独立reference_evidence、render_evidence、geometry、triage、rules。人工审核后应另建显式标注文件，保留原始ID、输入图像与坐标来源、审核依据和限定为[0,1]的reliability；不能将VLM自信度当可靠性。`benchmark_evidence.reliability()`要求reviewed=true且非unknown、无冲突。Region Semantic可比较双方审核过的同ID category，存在性另需同类别审核occupancy。Anchor匹配支持human来源、input_view范围、可靠且已审核的anchor_verdicts；确认缺失须充分证据，不能由检测失败推出。importance仍独立于reliability。

Structural需要真实已评估几何加独立语义/物理规则：穿透状态+reviewed triage；支撑接收者、完整性、Z-up及排除其他附着；退化需完整 evaluated component affine_rank 与体积期望，多个平面部件还需联合空间秩。名称、AABB或Group-ID不得构造这些字段的“真值”。本批均N/A。

## 复现（只准备材料，不调用模型）

```bash
python3 -B -m scripts.evaluation_validity --source results/existing_scene_batch_20261025 --output results/evaluation_validity_v01_new
python3 -B -m unittest discover -s tests -p 'test_evaluation_validity.py'
```

须具备服务器私有原始图像及run_config；公开仓库不含第三方图片，无法单凭clone生成审核PNG。输出必须是新目录。收集真实人类副本后可用脚本的`--reviews`模式写入新的汇总文件；该汇总不修改Energy。图片仅私有，未获再分发许可，不生成HTML。
''')
    coverage_lines = ['# 指标适用范围与人工有效性状态', '',
        '以下数值直接读取冻结报告，不重跑DINO或其他指标。可计算覆盖率不等于正确率。全部历史相机不合规/未验证，正式成绩0。', '',
        '| Energy | 有条件数值配对 | 有效记录/计划记录 | 实际含义与限制 |',
        '| --- | --- | --- | --- |']
    descriptions = dict(semantic='N/A；Group/Atomic未审核且仅诊断，候选数量不是分数',
        spatial='Dense图像边缘代理；无可靠RGB对象定位/对应，连续空间N/A',
        appearance='真实图像颜色/纹理差异，仍受视角、可见性、尺寸适配影响',
        statistical='纹理统计/多尺度边缘分布代理，不是书籍/唱片真实密度或数量',
        perceptual='已运行DINOv2 CPU特征差异；并非语义正确性概率，局部尺寸/上下文仍有限制',
        structural='N/A；13个.blend存在，但无绑定的已评估穿透、支撑、退化检查')
    for name, row in validity['frozen_metric_coverage'].items():
        coverage_lines.append(f'| {name} | {row["measured_pairs"]}/{row["selected_pairs"]} | '
            f'{row.get("valid_metric_records", "N/A")}/{row.get("planned_metric_records", "N/A")} | {descriptions[name]} |')
    coverage_lines += ['', '## Geometry盘点', '',
        '13/13原生.blend路径存在，本轮全部未打开。13/13绑定geometry.json均unavailable，无碰撞记录、支撑记录或evaluated components。仅bw_0074有900对象的已有Scene Graph和低分辨率Group-ID缓存；基础网格边界/变换、名称和像素可见支持不能验证接触/碰撞或结构退化，也不证明与历史PNG逐像素同步。详见evidence_validity.json逐配对库存。未发现足以安全启用Structural评分的现成数据；未执行新提取。', '',
        '## 待人类标注后才可报告的有效性', '',
        'Reference Evidence正确/可观察比例、两侧VQA正确性、候选差异确认、satisfied误判、unknown/ambiguous适当性、盲审未覆盖差异、重复底层问题和相机影响目前均pending。逐配对判断可审查，但Reference相同的task_id/evidence_id只算一个参考命题；不能把107条当107条独立Reference真值或独立物理错误。按任务和运行链聚类，按输入及完成状态分层；本轮不排名、不估计总体准确率。', '',
        '审核后的Group/Structural Layout命题仍可作为Spatial/Statistical诊断；正式接入需明确比较定义、可靠定位或经验证的语义测量及协议合规。图像中的隔板布局属于Observation Spatial，不等于独立3D Structural接触/支撑检查。']
    (output / 'metric_coverage.md').write_text('\n'.join(coverage_lines) + '\n')
    (output / 'summary.md').write_text(f'''# Evaluation Validity Study v0.1

基准：`{BASE_COMMIT}`。冻结输入13组、10个任务/Reference、80条独立参考命题、107条配对比较：91 satisfied、13 candidate_violated、3 unknown。本轮没有新增模型调用、Blender执行或指标推理，没有改问题、回答、Energy、权重或Runtime。

审核包已准备，尚无人类标签；所有有效性指标pending、reviewed=false、provisional/debug，不能发布正式成绩。

- [两阶段审核说明](audit_packet.md)、[107条空白证据审核模板](human_review_template.csv)、[39个可扩展盲审空槽](blind_difference_template.csv)。优先审核{validity['priority_review_count']}条：13候选差异+3 Unknown+{validity['priority_status_counts'].get('satisfied', 0)}条satisfied覆盖抽样，剩余可扩展。
- [协议分层](protocol_strata.csv)：3组RGB+通用协议、10组RGB+场景专属文字；9完整、4不完整检查点；12条已记录Agent运行链（厨房续接与超时检查点同链），10任务；不混合排名、不将检查点当独立样本。没有记录续接也不证明统计独立。
- 私有PNG：`private/stage1_blind/`（全图、原生全图、中性固定Region近图），`private/stage2_evidence/`（逐条冻结问答）。只向盲审者分发第一阶段；冻结后才给第二阶段。公开仓库不含第三方像素或私有路径映射。
- [有效性待审及Geometry库存](evidence_validity.json)、[指标覆盖和限制](metric_coverage.md)。全部历史相机正式资格false；Reference相机未知，PNG/.blend同步未知。相机、遮挡和重建差异不可强行分离。
- 现有reliability、Region/Anchor和Structural triage/rules可读取独立人工审核标注；Group/Atomic VQA仍仅诊断，无通用数值Energy映射，不能按候选数打分。13个.blend存在，只有一个Scene Graph/Group-ID缓存，无可用于实际碰撞/支撑/退化评分的绑定Geometry，Structural继续N/A。

需要人类：先独立盲审13组主要差异并冻结，再逐条确认命题可观察性、双方回答、比较状态、混淆和重复问题；同时披露先验暴露。Codex未填任何人类结论，没有将审核准备冒充独立审核。人类身份与隔离由协调者管理，软件不作认证。

复现命令及字段枚举见审核说明。CPU测试和公开审查完成后另存检查记录；本轮不开展新实验、不扩大数据集。
''')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--template', type=Path)
    args = parser.parse_args()
    if args.reviews:
        if args.output.exists() or not args.template:
            parser.error('Review summary needs a template and a new output file')
        with args.template.open(newline='') as stream:
            template = list(csv.DictReader(stream))
        with args.reviews.open(newline='') as stream:
            filled = list(csv.DictReader(stream))
        write_json(args.output, summarize_reviews(template, filled))
    elif args.source:
        value = prepare(args.source, args.output)
        print(json.dumps({k: value[k] for k in ('pair_count', 'paired_comparisons',
                         'priority_review_count', 'image_preparation')}, indent=2))
    else:
        parser.error('Supply --source or --reviews with --template')


if __name__ == '__main__':
    main()
