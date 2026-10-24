"""One offline R2/R3 atomic-evidence pilot; no network, Agent or segmentation."""
import argparse
import html
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_evidence import (load_document,build_reference,local_dino_extractor,vlm_verify)
from e_harness.benchmark_metrics import compare,aggregate,perceptual_error
from scripts.region_grounding_experiment import read,save,box
from scripts.region_first_generalization import panel_grid,write_csv
from scripts.region_real_render import masked_view,heatmap

SOURCE=ROOT/'results/region_first_real_render_bw0073'
SEED_SOURCE='Assistant manual inspection of Reference RGB; human-seeded workflow draft, not actual human review or VLM extraction'



def atomic_questions(document):
    """Adapt provisional propositions to the existing concrete-question format."""
    regions={r['id'] for r in document.get('regions',[])}
    atoms=document.get('atomic_evidence',[]);ids=[a['id'] for a in atoms]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate atomic evidence ID')
    output=[]
    for atom in atoms:
        if atom['region_id'] not in regions or atom['type'] not in {'semantic','spatial','statistical'}:
            raise ValueError('Unknown atomic Region or energy')
        expected=atom['expected'];kind=atom['answer_type']
        valid=(type(expected) is bool if kind=='boolean' else
               type(expected) is int and expected>=0 if kind=='count' else False)
        if (expected is not None and not valid) or (expected is None and atom.get('status')!='unknown'):
            raise ValueError('Invalid atomic expected answer/type')
        if kind not in {'boolean','count'}:raise ValueError('Unsupported atomic answer type')
        if not all(isinstance(atom[k],str) and atom[k].strip() for k in ('claim','question','source')):
            raise ValueError('Atomic evidence needs text and traceable source')
        dependencies=atom.get('requires',[])
        if (len(dependencies)!=len(set(dependencies)) or any(x not in ids or x==atom['id'] for x in dependencies)):
            raise ValueError('Invalid atomic prerequisite')
        output.append(dict(id=atom['id'],region_id=atom['region_id'],energy=atom['type'],level='region',
            question=atom['question'],expected=expected,answer_type=kind,requires=dependencies,
            criteria=dict(expected=expected,answer_type=kind,coordinate_frame='input image: x right, y down; not world coordinates',
                          binary_proposition_only=True,not_element_density_or_distribution=True),
            status=atom.get('status','candidate'),reviewed=atom.get('reviewed',False),reliability=atom.get('reliability',0.),
            source=atom['source'],source_type=atom.get('source_type','unknown')))
    # Dependencies are presence prerequisites, never implicit coordinate estimates.
    by_id={a['id']:a for a in atoms}
    for atom in atoms:
        for dependency in atom.get('requires',[]):
            target=by_id[dependency]
            if target['type']!='semantic' or target['answer_type']!='boolean' or target['expected'] is not True:
                raise ValueError('Prerequisite must be a positive semantic-presence proposition')
            if target.get('requires'):raise ValueError('Nested atomic prerequisites are unsupported')
    return output


def validate_atomic_answer(answer, question):
    """Typed short answers, without interpreting model confidence as reliability."""
    fields={'id','status','observed','finding','reason'}
    if not isinstance(answer,dict) or set(answer)!=fields or answer['id']!=question['id']:
        raise ValueError('Expected exact atomic answer fields and matching ID')
    if answer['status'] not in {'satisfied','violated','unknown','unavailable'}:
        raise ValueError('Invalid atomic verification status')
    if answer['finding'] not in {'none','matched','misplaced','semantic_mismatch','confirmed_missing','not_detected','count_mismatch'}:
        raise ValueError('Invalid atomic finding')
    if not isinstance(answer['reason'],str) or not answer['reason'].strip():raise ValueError('Atomic reason required')
    value=answer['observed']
    typed=type(value) is bool if question['answer_type']=='boolean' else type(value) is int and value>=0
    if value is not None and not typed:raise ValueError('Wrong atomic observed answer type')
    if answer['status'] in {'satisfied','violated'}:
        if value is None or question['expected'] is None:raise ValueError('Decisive answer needs known expected and observed values')
        if (value==question['expected'])!=(answer['status']=='satisfied'):raise ValueError('Answer contradicts verification status')
    elif value is not None:raise ValueError('Unknown/unavailable must not assert an observed value')
    if answer['finding']=='confirmed_missing' and not (question['energy']=='semantic' and value is False and answer['status']=='violated'):
        raise ValueError('Confirmed missing needs a negative semantic-presence observation')
    if answer['finding']=='misplaced' and not (question['energy']=='semantic' and value is True and answer['status']=='satisfied'):
        raise ValueError('A misplaced object is still present')
    return dict(answer)


def replay_atomic_answers(questions, answers=(), *, source_kind='unavailable'):
    """Offline states only. No API, scoring, review upgrades or inferred absence.

    Mock answers demonstrate control flow but never become real observations.
    Duplicate contradictory answers abstain; unavailable dependencies propagate.
    """
    if source_kind not in {'unavailable','mock','historical_replay'}:raise ValueError('Unknown offline answer source')
    if source_kind=='unavailable' and answers:raise ValueError('Unavailable verifier cannot supply observations')
    ids={q['id'] for q in questions};grouped={key:[] for key in ids}
    for answer in answers:
        if not isinstance(answer,dict) or answer.get('id') not in ids:raise ValueError('Unknown atomic answer ID')
        grouped[answer['id']].append(answer)
    results={}
    for q in questions:
        result=dict(id=q['id'],region_id=q['region_id'],status='unavailable',observed=None,finding='none',
            reason='No reusable real atomic verification response; no authorized verifier configured')
        if q['expected'] is None:
            result.update(status='unknown',reason='Reference proposition is unknown; cannot define a violation')
        elif grouped[q['id']]:
            try:
                checked=[validate_atomic_answer(a,q) for a in grouped[q['id']]]
                outcomes={(a['status'],a['observed'],a['finding']) for a in checked}
                if len(outcomes)!=1:result.update(status='unknown',reason='Conflicting verification answers; human resolution required')
                else:result.update(checked[0])
            except (ValueError,KeyError,TypeError) as exc:
                result['reason']='Malformed offline response: '+str(exc)
        if result['finding'] in {'not_detected','confirmed_missing'}:
            # Confirmed absence requires the existing independently reviewed
            # input-view Anchor verdict path, not a short-answer self assertion.
            result.update(status='unknown',observed=None,finding='not_detected',
                          reason='Non-detection/self-asserted absence is not a reviewed confirmed-missing verdict')
        result.update(source_kind=source_kind,reviewed=False,scorable=False,score=None)
        results[q['id']]=result
    for q in questions:
        dependencies=[results[key] for key in q['requires']]
        if dependencies and any(d['status']!='satisfied' for d in dependencies):
            results[q['id']].update(status='unknown' if any(d['status']!='unavailable' for d in dependencies) else 'unavailable',
                observed=None,finding='none',reason='Presence prerequisite not established; do not charge dependent count/relation again')
    return [results[q['id']] for q in questions]


def reference_seeds():
    """Explicit permitted provisional seeds, recorded from Reference only.

    This is NOT an extraction model. No Render is accepted as an argument.
    """
    data=[
      ('R2_island','R2','semantic','可见一个中央岛台','画面中央是否可见岛台？',True,[]),
      ('R2_stools','R2','semantic','岛台前侧可见一组高脚椅','岛台前侧是否可见高脚椅？',True,[]),
      ('R2_lamp','R2','semantic','可见一盏悬挂式吊灯','中央区域是否可见悬挂式吊灯？',True,[]),
      ('R2_above','R2','spatial','吊灯在图像投影中位于岛台上方','按图像上下方向，吊灯是否在岛台上方？',True,['R2_island','R2_lamp']),
      ('R2_count','R2','statistical','岛台前侧可辨认四把高脚椅','岛台前侧可见几把高脚椅？看不清请答 unknown。',4,['R2_stools']),
      ('R3_cabinets','R3','semantic','后方可见一组壁挂橱柜','后方区域是否可见壁挂橱柜？',True,[]),
      ('R3_counter','R3','semantic','后方可见一段台面','后方区域是否可见台面？',True,[]),
      ('R3_above','R3','spatial','后方壁挂橱柜在图像投影中位于后方台面上方','按图像上下方向，后方壁挂橱柜是否在后方台面上方？',True,['R3_cabinets','R3_counter']),
      ('R3_hob_count','R3','statistical','可辨认的后方炉灶单元数量尚不能确定','后方台面可清楚辨认几组炉灶？看不清请答 unknown。',None,[]),
    ]
    result=[]
    for identifier,region,energy,claim,question,expected,requires in data:
        result.append(dict(id=identifier,region_id=region,type=energy,claim=claim,question=question,
            expected=expected,answer_type='count' if energy=='statistical' else 'boolean',requires=requires,
            status='unknown' if expected is None else 'candidate',source_type='human_seeded_provisional',
            source=SEED_SOURCE,source_rgb='reference.png',source_roi='rois/polygon_'+region+'.png',
            scope='visible input image only; full Reference context allowed',reviewed=False,reliability=0.,
            uncertainty='Reference cooking surface obscured / not confidently identifiable' if expected is None else
                        'Provisional visual seed; existence/count/relation and ROI applicability require human review'))
    return result


def mock_examples(questions):
    """Transport/state fixtures only; deliberately independent of actual Render."""
    def answer(key,status,value,finding='matched'):
        return dict(id=key,status=status,observed=value,finding=finding,reason='MOCK fixture; not an observation of bw_0073')
    selected=[q for q in questions if q['id'] in {'R2_island','R2_stools','R2_count','R2_lamp','R2_above'}]
    responses=[answer('R2_island','satisfied',True),answer('R2_stools','satisfied',True),
        answer('R2_count','violated',3,'count_mismatch'),answer('R2_lamp','violated',False,'confirmed_missing'),
        answer('R2_above','violated',False,'none')]
    conflict=[answer('R2_island','satisfied',True),answer('R2_island','violated',False,'semantic_mismatch')]
    gateway=vlm_verify('Synthetic binary proposition?',None,None,dict(synthetic_fixture=True),
        lambda *args:dict(status='valid',score=1.,reason='MOCK binary violation; not a real Energy'))
    return dict(source_kind='mock',render_inspected=False,reviewed=False,formal_eligible=False,
        raw_answers=responses,state_demo=replay_atomic_answers(selected,responses,source_kind='mock'),
        conflict_demo=replay_atomic_answers(selected,conflict,source_kind='mock'),
        existing_vlm_gateway_demo=gateway,mock_gateway_score_is_not_used_in_real_records=True)


def dino_variants(a,b,mask):
    """Input-only ablations; geometry and official Perceptual stay unchanged."""
    x0,y0,x1,y1=box(mask);sl=np.s_[y0:y1,x0:x1];m=mask[sl]
    output={'official_black_crop':(a,b,mask)}
    for name,fill in [('common_gray_crop',127),('bbox_context',None)]:
        pair=[]
        for im in (a,b):
            crop=im[sl].copy()
            if fill is not None:crop[~m]=fill
            pair.append(crop)
        output[name]=(*pair,np.ones(m.shape,bool))
    pair=[np.where(mask[...,None],im,0).astype(np.uint8) for im in (a,b)]
    output['full_frame_black']=(*pair,np.ones(mask.shape,bool))
    return output


def dino_diagnostics(out,a,b,units,cached,enabled):
    start=time.monotonic();extract=None;reason='Explicitly skipped CPU DINO input diagnostics'
    if enabled:
        try:
            import torch
            torch.set_num_threads(2);torch.set_num_interop_threads(1)
            extract=local_dino_extractor(Path('/home/xymo/models/dinov2'),'cpu',preserve_frame=True);reason=None
        except Exception as exc:reason=type(exc).__name__+': '+str(exc)
    rows=[];self_checks=[]
    for unit in units:
        mask=np.asarray(Image.open(out/unit['mask']),bool)&np.asarray(Image.open(out/'render_valid.png'),bool)
        variants=dino_variants(a,b,mask)
        for name,(x,y,m) in variants.items():
            score,why=perceptual_error(x,y,m.astype(float),extract)
            baseline=cached[unit['id']]['perceptual']
            rows.append(dict(id=unit['id'],input_variant=name,perceptual=score,reason=why or reason,
                original_cached_perceptual=baseline,delta_from_official=None if score is None else score-baseline,
                diagnostic_only=True,reviewed=False))
            if name=='official_black_crop' and score is not None and abs(score-baseline)>1e-6:
                raise ValueError('Official DINO replay differs from existing measurement')
            if unit['id']=='polygon_R2':
                identical=dino_variants(a,a,mask)[name]
                value,why=perceptual_error(identical[0],identical[1],identical[2].astype(float),extract)
                self_checks.append(dict(input_variant=name,value=value,reason=why,reviewed=False))
        panels=[]
        for name,(x,y,m) in variants.items():
            crop=lambda image:np.uint8(image*m[...,None])
            if name=='official_black_crop':
                x0,y0,x1,y1=box(m);panels.extend([(name+' / Reference',Image.fromarray(crop(x)[y0:y1,x0:x1])),(name+' / Render',Image.fromarray(crop(y)[y0:y1,x0:x1]))])
            else:panels.extend([(name+' / Reference',Image.fromarray(x)),(name+' / Render',Image.fromarray(y))])
        panel_grid(panels,out/'dino_inputs'/(unit['id']+'.png'),width=600)
    save(out/'dino_diagnostics.json',dict(rows=rows,self_checks=self_checks,device='cpu',
        model_loaded=extract is not None,unavailable_reason=reason,seconds=time.monotonic()-start,
        official_formula_changed=False,roi_geometry_changed=False,diagnostic_only=True,reviewed=False))
    write_csv(out/'dino_diagnostics.csv',rows)
    return rows


def run(out,diagnose_dino=True):
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False)
    for folder in ('rois','inputs','dino_inputs','source_snapshot'):(out/folder).mkdir()
    # Freeze/reference seeds are written before any Render pixels are opened.
    shutil.copyfile(SOURCE/'reference.png',out/'reference.png')
    a=np.asarray(Image.open(out/'reference.png').convert('RGB'))
    units=[];regions=[]
    plan=read(SOURCE/'region_plan.json')
    for row in plan['regions']:
        if row['id'] not in {'R2','R3'}:continue
        for group in ('box','polygon'):
            name=group+'_'+row['id'];path='rois/'+name+'.png'
            shutil.copyfile(SOURCE/'measurement_rois'/(name+'.png'),out/path)
            units.append(dict(id=name,region_id=row['id'],mask=path,reviewed=False))
        mask=np.asarray(Image.open(out/'rois'/('polygon_'+row['id']+'.png')),bool)
        regions.append(dict(row,mask='rois/polygon_'+row['id']+'.png',bbox=box(mask),metrics=[],reviewed=False,reliability=0.))
    document=dict(image_size=list(a.shape[1::-1]),regions=regions,anchors=[],relations=[],
        atomic_evidence=reference_seeds(),reviewed=False,inventory_complete=False,
        source_type='human_seeded_provisional',source=SEED_SOURCE,render_used_for_seeds=False,
        coordinate_frame='input image; projected above/below, not world coordinates')
    questions=atomic_questions(document);document['verification_questions']=questions
    save(out/'reference_evidence.json',document)
    # Inspect only plausible existing artifacts, not credentials or transport logs.
    history_paths=[ROOT/'results/region_first_e2e_generalization/bw_0073/vlm_plan.json',
        ROOT/'results/vlm_direct_grounding_bw0073/region_plan.json',
        ROOT/'results/vlm_direct_grounding_bw0073/direct_regions.json',SOURCE/'metrics.json']
    save(out/'history_audit.json',dict(files=[dict(path=str(p),top_fields=list(read(p))) for p in history_paths],
        reusable_atomic_verification_responses_found=False,
        reason='Inspected planning, coordinate and image-metric artifacts; none supplies typed atomic Render observations',reviewed=False))
    loaded=load_document(out/'reference_evidence.json')
    for r in loaded['regions']:assert r['mask'].shape==a.shape[:2]
    for name in ('render.png','render_valid.png','pair_audit.json','overlaps.json'):shutil.copyfile(SOURCE/name,out/name)
    b=np.asarray(Image.open(out/'render.png').convert('RGB'));valid=np.asarray(Image.open(out/'render_valid.png'),bool)
    if a.shape!=b.shape:raise ValueError('Paired image grids differ')
    cached={r['id']:r for r in read(SOURCE/'metrics.json')['rows']}
    measurements=[dict(cached[u['id']],source_file=str(SOURCE/'metrics.json'),recomputed=False) for u in units]
    save(out/'image_measurements.json',dict(rows=measurements,reviewed=False,formal_eligible=False))
    for unit in units:
        mask=np.asarray(Image.open(out/unit['mask']),bool);x0,y0,x1,y1=box(mask);sl=np.s_[y0:y1,x0:x1]
        for name,image in [('reference',a),('render',b)]:Image.fromarray(image[sl]).save(out/'inputs'/(unit['id']+'_'+name+'.png'))
        err=np.abs(a.astype(float)-b.astype(float)).mean(2)/255;heat=heatmap(err,mask&valid)
        panel_grid([('Reference / frozen '+unit['id'],Image.fromarray(masked_view(a,mask)[sl])),
            ('Actual Render / SAME coordinates',Image.fromarray(masked_view(b,mask)[sl])),
            ('RGB L1 / fixed [0,1]',Image.fromarray(heat[sl]))],out/'inputs'/(unit['id']+'_comparison.png'),width=650)
    for q in questions:
        q['inputs']=dict(render_full='render.png',render_context_crop='inputs/polygon_'+q['region_id']+'_render.png',
            reference_full='reference.png',reference_context_crop='inputs/polygon_'+q['region_id']+'_reference.png',
            roi_mask='rois/polygon_'+q['region_id']+'.png',crop_box=next(r['bbox'] for r in regions if r['id']==q['region_id']),
            rendered_crop_is_bbox_context_not_new_semantic_mask=True)
    save(out/'verification_questions.json',dict(questions=questions,expected_answers_not_model_predictions=True,reviewed=False))
    schema=dict(type='object',additionalProperties=False,required=['id','status','observed','finding','reason'],
        properties=dict(id=dict(type='string'),status=dict(enum=['satisfied','violated','unknown','unavailable']),
            observed=dict(type=['boolean','integer','null'],minimum=0),
            finding=dict(enum=['none','matched','misplaced','semantic_mismatch','confirmed_missing','not_detected','count_mismatch']),reason=dict(type='string',minLength=1)),
        additional_checks='validate_atomic_answer enforces per-question type, outcome consistency and presence-vs-position distinction')
    save(out/'verification_schema.json',schema)
    results=replay_atomic_answers(questions)
    save(out/'verification_results.json',dict(results=results,mode='real_verifier_unavailable',
        paid_requests=0,mock_results_included=False,reviewed=False))
    save(out/'mock_verification.json',mock_examples(questions))
    # Existing compare gate handles actual unreviewed questions; no callback invoked.
    rows,_=compare(a,b,build_reference(a,loaded))
    atom_ids={q['id'] for q in questions};atomic_rows=[r for r in rows if r['id'] in atom_ids]
    assert len(atomic_rows)==len(questions) and all(r['q']==0 and r['value'] is None for r in atomic_rows)
    energies=[]
    for region in ('R2','R3'):
        ids={q['id'] for q in questions if q['region_id']==region}
        selected=[r for r in atomic_rows if r['id'] in ids];grouped,_=aggregate(selected)
        energies.append(dict(region_id=region,energies={k:grouped[k] for k in ('semantic','spatial','statistical')},
            formal_score=None,reviewed=False))
    save(out/'energy_adapter.json',dict(records=atomic_rows,regions=energies,observation_energy=None,
        mapping='Existing verification_questions.energy + compare + aggregate; no changes to formulas/weights',
        mock_answers_used=False,reviewed=False))
    diag=dino_diagnostics(out,a,b,units,cached,diagnose_dino)
    write_page(out,document,questions,results,measurements,diag)
    for path in [Path(__file__),ROOT/'e_harness/benchmark_evidence.py',ROOT/'e_harness/benchmark_metrics.py',ROOT/'e_harness/benchmark_config.py']:
        shutil.copyfile(path,out/'source_snapshot'/path.name)
    save(out/'execution.json',dict(seconds=time.monotonic()-started,device='cpu',paid_api_requests=0,
        sam_runs=0,slic_runs=0,agent_runs=0,blender_runs=0,official_scoring=False,reviewed=False))
    write_report(out)
    validate_outputs(out)
    print('R2/R3 pilot saved:',out,flush=True)


def write_page(out,document,questions,results,measurements,diag):
    esc=html.escape;statuses={r['id']:r for r in results}
    parts=['<!doctype html><meta charset="utf-8"><title>R2/R3 Atomic Evidence Pilot</title>',
        '<style>body{font:16px sans-serif;margin:24px;line-height:1.65;background:#f6f7f9}img{max-width:100%}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;text-align:left}pre{white-space:pre-wrap}</style>',
        '<h1>bw_0073 R2/R3：Atomic Evidence → Verification → Energy</h1>',
        '<p>historical_camera / provisional-debug；全部 reviewed=false。Reference 种子由助手观察原图后手工拟定，未获人工审核，不是模型自动提取。真实原子验证不可用；Mock 只测试流程，没有真实语义分数。</p>',
        '<p><a href="report.md">报告与复现</a> · <a href="reference_evidence.json">Reference 证据</a> · <a href="verification_questions.json">问题/图像清单</a> · <a href="verification_results.json">真实可用状态</a> · <a href="energy_adapter.json">已有 Energy 接口</a> · <a href="mock_verification.json">单列 Mock</a></p>',
        '<div class="pair"><div>Reference RGB<img src="reference.png"></div><div>实际历史 Agent Render<img src="render.png"></div></div>']
    for region in document['regions']:
        identifier=region['id'];parts+=['<h2>'+esc(identifier+' '+region['name'])+'</h2>']
        for group in ('box','polygon'):parts+=['<h3>固定 '+group+'</h3><img src="inputs/'+group+'_'+identifier+'_comparison.png">']
        parts+=['<h3>Reference 原子候选与验证</h3><table><tr><th>ID / 类型</th><th>候选命题 / 期望</th><th>Verification Question</th><th>真实状态 / 原因</th><th>来源 / 审核</th></tr>']
        for atom in document['atomic_evidence']:
            if atom['region_id']!=identifier:continue
            r=statuses[atom['id']]
            parts+=['<tr><td>'+esc(atom['id']+' / '+atom['type'])+'</td><td>'+esc(atom['claim']+' / '+json.dumps(atom['expected'],ensure_ascii=False))+'</td><td>'+esc(atom['question'])+'</td><td>'+esc(r['status']+' / '+r['reason'])+'</td><td>human_seeded_provisional；助手手工草稿 / reviewed=false / q=0</td></tr>']
        parts+=['</table><h3>真实图像测量（从上一轮原样复用）</h3><table><tr><th>ROI</th><th>Appearance</th><th>Perceptual</th><th>Semantic / Spatial / Statistical</th></tr>']
        for row in measurements:
            if row['id'].endswith(identifier):parts+=['<tr><td>'+row['id']+'</td><td>'+f'{row["appearance"]:.5f}'+'</td><td>'+f'{row["perceptual"]:.5f}'+'</td><td>N/A / N/A / N/A</td></tr>']
        parts+=['</table><p>R2：固定 Polygon 的吊灯部分不会追随 Render 中下移的灯；R3：炉灶数量在 Reference 中不够清楚。物体未检测到不等于确认缺失。没有把这些不确定性转换为最大惩罚。</p>']
    parts+=['<h2>DINO 输入处理诊断；不替换正式测量</h2><p>相同 ROI 内像素不变；比较官方黑色裁剪、共同灰色填充、外接框上下文和全图黑色输入。后两者改变上下文/相对尺度，不能当作同一个新评分。</p><table><tr><th>ROI / 输入</th><th>实际 DINO 距离</th><th>相对原始值变化</th></tr>']
    for row in diag:
        fmt=lambda v:'N/A' if v is None else f'{v:.6f}'
        parts+=['<tr><td>'+esc(row['id']+' / '+row['input_variant'])+'</td><td>'+fmt(row['perceptual'])+'</td><td>'+fmt(row['delta_from_official'])+'</td></tr>']
    parts+=['</table>']
    for group in ('box','polygon'):
        for region in ('R2','R3'):parts+=['<img src="dino_inputs/'+group+'_'+region+'.png">']
    parts+=['<h2>失败案例及限制</h2><p>Reference 相机未知，历史导出相机高度1.5m与正式T0的2m不同。图像差异不能单独归因为材质、语义或空间错误。R2/R3仍重叠，不能直接相加。计数候选不是密度/尺度/分布评测。没有真实VQA与审核，不能确认类别、缺失、关系或数量错误。</p>',
        '<h2>Mock 与真实验证严格分开</h2><p>Mock 中的三把椅子、缺失吊灯等仅为虚构控制流输入，绝不描述实际 Agent Render。自称缺失被降为Unknown，关联关系不再额外处罚；冲突答案保持Unknown。参见 mock_verification.json 和单元测试。</p>']
    (out/'comparison.html').write_text('\n'.join(parts))


def write_report(out):
    measurements=read(out/'image_measurements.json')['rows'];diag=read(out/'dino_diagnostics.json')
    actual=read(out/'verification_results.json')['results'];runtime=read(out/'execution.json')
    image_table=['| ROI | Appearance | Perceptual |','| --- | ---: | ---: |']
    for r in measurements:image_table.append(f"| {r['id']} | {r['appearance']:.6f} | {r['perceptual']:.6f} |")
    dino_table=['| ROI | 输入处理 | DINO距离 | 相对原公式变化 |','| --- | --- | ---: | ---: |']
    fmt=lambda v:'N/A' if v is None else f'{v:.6f}'
    for r in diag['rows']:dino_table.append(f"| {r['id']} | {r['input_variant']} | {fmt(r['perceptual'])} | {fmt(r['delta_from_official'])} |")
    text='''# R2/R3 Region-level Atomic Evidence & Verification Pilot

本轮打通了可审计的数据和程序流程，但**尚未完成真实语义验证**。已有系统未配置可靠原子验证器，也没有可重放的同题真实验证响应。没有以 Mock 或 RGB/DINO 距离替代 Semantic / Spatial / Statistical。

[完整图像/命题/状态对照](comparison.html) · [Reference证据](reference_evidence.json) · [问题与输入](verification_questions.json) · [真实验证状态](verification_results.json) · [Energy适配](energy_adapter.json) · [单列Mock](mock_verification.json) · [DINO诊断](dino_diagnostics.csv) · [一致性检查](validation.json)

## 数据、来源和冻结边界

- 只使用 bw_0073 的 R2/R3；继承 `results/region_first_real_render_bw0073/pair_audit.json` 的真实 Reference/Render 对应依据。完整路径与相机导出保存于本目录 `pair_audit.json`。Reference为7952×4333，Render为1672×941，工作网格1536×837。
- Reference原始路径：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/data/hf-snapshot/bw_0073/tests/dataset/tasks/bw_0073/references/image_01.jpg`。
- 实际Render：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.png`。
- 复用上一轮等比全图适配后的Render和有效像素图，不重新配准。四张 Box/Polygon Mask 原样复制，Reference和Render共用同坐标；R2/R3均位于有效画面内。未修改顶点、Box、边界、Grounding词表或参数。
- 相机为 historical_camera：保存的相机高度1.5m，正式T0高度2m，Reference相机未知。图像差异混合了相机、布局、几何、光照与材质，不能转为正式Benchmark成绩。
- 原子候选在脚本打开Render像素之前写出。`reference_seeds()`不接收Render，明确是依据Reference观察拟定的手工流程种子：`human_seeded_provisional`。种子由助手拟定，**并非真实人工审核，也不是VLM自动提取**。不能把历史Region Plan的描述或命名当作已验证GT。
- 所有Region、原子证据及问题均 `reviewed:false`、可靠性0；没有发现或读取Key，不使用认证Header。

## Reference原子候选

R2共5条：中央岛台存在；高脚椅组存在；吊灯存在；吊灯在图像投影中位于岛台上方；前侧可辨认4把高脚椅。

R3共4条：后方壁挂橱柜存在；后方台面存在；壁挂橱柜在图像投影中位于台面上方；可辨认炉灶数量未知。炉灶部分不够明确，期望值为null，不能从Render推回或强行填0。

每条只表达一个候选命题，来源、Region ID、简短问题、期望值及依赖均保留在JSON。只观察输入视角可见内容，不推断世界坐标、物体背面或完整隐藏数量。统计候选只检查一个可见数量命题，**不代表已实现密度、尺度、占据或空间分布评测**。

## Verification与实际可用性

四态Schema支持 `satisfied / violated / unknown / unavailable`，校验ID、布尔/非负整数类型、期望值与状态一致性。额外confidence字段被拒绝，不转为可靠性。完整Render和同坐标BBox上下文Crop都已准备；Crop附带原始Mask与裁剪坐标，不能把Crop内所有内容当作该Region的语义成员。未来计数问题不应向验证模型泄露期望数量。

本轮真实状态：**UNAVAILABLE_COUNT条Unavailable，UNKNOWN_COUNT条Unknown，0条Satisfied，0条Violated**。Unavailable表示缺少真实验证器或可重放响应；Unknown表示Reference炉灶数量本身不确定。没有真实响应，不能由RGB差异确认任何类别错误、缺失、数量或空间关系违反。

程序可自动完成加载、Schema校验、问题/图像清单、依赖检查、冲突保留、状态映射和已有RGB/DINO测量；不能凭这些步骤自动确认物体语义。对象存在性、可见数量和关系需要可靠的真实VLM/VQA或人工观察；精确空间/分布验证还需要经审核的实例对应、位置或占据证据，当前没有运行检测器来补造它们。

## 接入已有Energy，保持N/A

原子问题使用既有 `verification_questions` 格式：`energy=semantic/spatial/statistical`、`level=region`、独立ID。实际适配调用原有 `load_document → build_reference → compare → aggregate`，只保存9条原子问题的记录和每个Region的三类能量；不使用内部Global/Dense代理结果生成语义结论。

全部问题可靠性为0，原有compare拒绝它们，故9条记录value=null，R2/R3三类能量均N/A，覆盖率0（0个可计分判断/9个计划问题）。没有总分，没有把N/A当作0误差，也没有改变五类公式与权重。

未来经审核且有真实、有效验证器时，可以通过既有具体指标VLM接口表达单项命题违反；本次Mock只演示既有合法0–1误差返回契约，不制定新的连续计数误差或评分权重。布尔计数命题的违反也不能冒充完整Statistical分布能量。现有空间中心位移/占据接口仍需要独立证据，而不能从ROI名字或固定Mask推导Render对象位置。

## 归因、冲突与重复处罚

- 物体存在但移位：存在性仍可Satisfied；已有 `match_anchors` 将其区分为misplaced，不按missing处理。这里只用可信合成fixture检查逻辑，没有给真实Render赋该状态。
- 同位置类别替换与未检测到：沿用已有semantic_mismatch / unknown区分；未检测到、自称confirmed_missing均不自动建立缺失。
- 确认缺失：必须走现有独立审核的input-view缺失判定路径；合成oracle测试证实其缺失由Semantic承担，Anchor Spatial/Appearance/Perceptual不再附加最大惩罚。
- 计数/关系具有显式存在性前提。前提不可用或冲突时，相关命题Unknown/Unavailable，不把缺失原因再变成关系或计数违反。矛盾回答保留Unknown，相同重复回答不重复计条。
- Mock中的“3把椅子”“缺失吊灯”只是虚构流程输入，**完全不是对实际Agent的判断**。Mock单列，不进入实际结果或Energy适配。没有真实VQA结果时，不能宣称已验证Agent缺失某对象。
- 像素Appearance/Perceptual仍可能对同一图像原因自然响应；这种相关性没有被宣称完全消除。本轮没有把它们与原子违反加权相加，也没有对原子Unknown附加惩罚。
- R2/R3仍有重叠：Box共享82800像素（R3全部），Polygon共享16792像素。原记录见overlaps.json，不直接相加为Region总分。

## 实际Appearance / Perceptual

下列四项逐字段复用上一轮真实测量，不重算或替换为Mock。数值较小表示输入表示下的图像距离较小，不是语义正确概率。

IMAGE_TABLE

R2仍有岛台/椅子/吊灯图像差异，固定Polygon的吊灯部分不能跟随Render中下移的灯，因而不能完整评价移出范围的物体。R3的台面、墙面和柜体图像差异可定位，但不能从RGB差异区分材质、相机或语义错误。Reference炉灶数量的不确定性来自证据提取，不应归咎Agent。

## DINO输入处理受控诊断

仅用已有本地DINOv2在CPU做小范围实际推理；没有改正式Perceptual。每个ROI比较：原公式黑色裁剪；相同ROI外共同填127灰色；外接框原图上下文；全图保留ROI且其余黑色。后两项改变上下文/相对输入尺度，只用于分析，不是候选新公式。ROI内的Reference和Render像素始终不变。

DINO_TABLE

若实际模型可用，原公式四次重放应与缓存一致。共同填充、框内上下文或全图输入导致的距离变化，说明不同面积/长宽比/裁剪方式的ROI不能直接据数值高低比较质量。灰色不是经验证更正确的方案，全图黑色更低也可能来自共同背景与目标缩小。

SELF_DIAGNOSTICS 尚无像素GT、真实语义标签或质量标定，不能把输入敏感性等同于已测出的语义伪差异率。

## Region-first的实际增益和未完成部分

理论上，Region把少量局部评价范围与可审核命题、独立验证问题和失败原因关联，避免只有Global均值而无法追溯局部内容；存在性、关系、数量能分开讨论。相比无语义网格，更适合人工按功能组审核。

本轮实际增加了9条可追踪命题、同坐标验证输入、明确的Unknown/Unavailable原因，以及逐Region图像距离和DINO输入敏感性。**没有实际证明新的语义检出能力或优于Dense的准确率**，没有确认任何真实原子违反，完整的真实语义闭环仍缺验证器和人工审核。Global/Dense仍覆盖Region外内容，不替代或删除困难区域。

## 执行、限制与复现

- 只新增 `scripts/region_atomic_pilot.py` 和 `tests/test_atomic_evidence.py`。核心evidence/metrics/config保持原样，历史Grounding冻结检查不受影响。新辅助函数放在实验脚本，避免修改B2冻结的整份源码。
- 新增14项CPU测试，结合原有145项回归共159项通过；当前日志在tests.log。测试覆盖四态/类型、Unknown、冲突、未检测到、存在性前提、缺失单次处罚、q=0不调用验证器和输入变体像素保持。Mock通过不代表真实语义验证成功。
- 本轮运行耗时约RUNTIME秒，其中DINO诊断DINO_SECONDS秒，CPU单模型、2线程。未运行GPU、SAM、SLIC、Agent或Blender，没有付费请求、下载、正式评分或Git提交。
- 所有结果provisional/debug；不满足固定外参，没有人工GT或真实VQA。失败案例保留，不自动扩展样本。

只浏览现有页面无需运行任何命令。免费离线复现如下，目标目录必须不存在；重复运行请另选目录：

```bash
cd /home/xymo/projects/e-harness
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python -m unittest discover -s tests -p test_atomic_evidence.py -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python scripts/region_atomic_pilot.py --output results/region_atomic_verification_bw0073_replay
```

若只重放已有测量和程序流程，可加 `--skip-dino-diagnostics`，新增输入变体Perceptual应报告N/A，不能声称执行了实际推理。本轮完成后停止，等待人工审核。
'''
    text=text.replace('UNAVAILABLE_COUNT',str(sum(r['status']=='unavailable' for r in actual))).replace('UNKNOWN_COUNT',str(sum(r['status']=='unknown' for r in actual)))
    text=text.replace('IMAGE_TABLE','\n'.join(image_table)).replace('DINO_TABLE','\n'.join(dino_table))
    self_text=('同一Reference输入的四种处理自比较均接近0（容差1e-12）。共同黑色填充并未在完全相同输入上凭空产生明显正误差，但会改变不同图像的特征距离及解释。'
        if diag['model_loaded'] else '本次未加载DINO，输入变体距离和自比较均未实际推理，保持N/A；不能把离线流程测试描述为DINO实测。')
    text=text.replace('SELF_DIAGNOSTICS',self_text)
    text=text.replace('RUNTIME',f'{runtime["seconds"]:.3f}').replace('DINO_SECONDS',f'{diag["seconds"]:.3f}')
    (out/'report.md').write_text(text)


def validate_outputs(out):
    from html.parser import HTMLParser
    from urllib.parse import urlsplit
    doc=load_document(out/'reference_evidence.json');questions=read(out/'verification_questions.json')['questions']
    results=read(out/'verification_results.json')['results'];adapter=read(out/'energy_adapter.json')
    assert len(questions)==len(results)==9
    assert all(a['reviewed'] is False and a['reliability']==0 for a in doc['atomic_evidence'])
    assert all(q['reviewed'] is False and q['reliability']==0 for q in questions)
    assert all(r['score'] is None and r['reviewed'] is False and r['source_kind']=='unavailable' for r in results)
    assert all(r['value'] is None and r['q']==0 for r in adapter['records'])
    assert all(e['value'] is None and e['coverage']==0 for region in adapter['regions'] for e in region['energies'].values())
    assert adapter['observation_energy'] is None and adapter['mock_answers_used'] is False
    a=np.asarray(Image.open(out/'reference.png').convert('RGB'));b=np.asarray(Image.open(out/'render.png').convert('RGB'))
    valid=np.asarray(Image.open(out/'render_valid.png'),bool);err=np.abs(a.astype(float)-b.astype(float)).mean(2)/255
    for row in read(out/'image_measurements.json')['rows']:
        path='rois/'+row['id']+'.png';mask=np.asarray(Image.open(out/path),bool)
        assert (out/path).read_bytes()==(SOURCE/'measurement_rois'/(row['id']+'.png')).read_bytes()
        assert abs(row['appearance']-err[mask&valid].mean())<1e-12
    for name in ('benchmark_evidence.py','benchmark_metrics.py','benchmark_config.py'):
        assert (ROOT/'e_harness'/name).read_bytes()==(SOURCE/'source_snapshot'/name).read_bytes()
    for name in ('reference.png','render.png','render_valid.png','pair_audit.json'):
        assert (out/name).read_bytes()==(SOURCE/name).read_bytes()
    for row in read(out/'dino_diagnostics.json')['self_checks']:
        assert row['value'] is None or abs(row['value'])<1e-12
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key in ('href','src') and value and not urlsplit(value).scheme:assert (out/value).is_file(),value
    Links().feed((out/'comparison.html').read_text())
    for q in questions:
        for field in ('render_full','render_context_crop','reference_full','reference_context_crop','roi_mask'):
            assert (out/q['inputs'][field]).is_file()
    save(out/'validation.json',dict(passed=True,atomic_candidates=9,reference_unknown=1,real_verified=0,
        core_modules_byte_identical=True,frozen_masks_and_pair_identical=True,real_metrics_reused=True,
        all_real_atomic_scores_unavailable=True,all_review_flags_false=True,mocks_separated=True,
        html_and_question_inputs_exist=True,formal_score=None,reviewed=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--skip-dino-diagnostics',action='store_true')
    args=parser.parse_args();run(args.output.resolve(),not args.skip_dino_diagnostics)
