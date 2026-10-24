"""Offline synthetic book controls. This pilot has NO authorized API entry."""
import argparse
from copy import deepcopy
import fcntl
import html
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from scripts.group_evidence_pilot import (panel_row,table,group_questions,group_energy_rows)
from scripts.region_atomic_pilot import replay_atomic_answers

SYSTEM='你是视觉证据验证器。只根据当前图像判断书籍的可见摆放方式。不要把唱片或文件夹当作书籍，不猜测不可见内容。无法判断时回答 unknown。只输出 JSON。'
USER='''请回答：

1. 是否能清楚看到至少两本水平叠放的书籍？
2. 是否能清楚看到竖直站立摆放的书籍？

只输出：
{
  "horizontal_stack": "yes",
  "upright_books": "yes"
}

字段取值均为 yes、no 或 unknown。

以上 JSON 只是格式示例，不是预期答案。'''
FIELDS=('horizontal_stack','upright_books')
SCHEMA=dict(type='object',additionalProperties=False,required=list(FIELDS),
            properties={k:dict(type='string',enum=['yes','no','unknown']) for k in FIELDS})
DEFINITIONS=dict(horizontal_stack='至少两本可辨认的书水平叠放，存在明显上下堆叠关系。',
    upright_books='存在可辨认的书籍，其书脊或书体主要呈竖直站立状态。',
    exclusions='唱片、文件夹、单本平放且无法确认的物体不强行当作横向书堆。',
    abstention='遮挡严重、分辨率不足或类别不明确时回答unknown。')


def save(path,data):
    with Path(path).open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)


def read(path):return json.loads(Path(path).read_text())


def scene_configs():
    """One fixed layout, same nine book components in every condition."""
    common=dict(camera=dict(location=[3.25,-6.5,2.9],target=[0,0,1.24],lens_mm=60.,sensor_width_mm=36.),
        rendering=dict(resolution=[768,640],samples=8,seed=27,engine='CYCLES',device='CPU',threads=2,
                       denoising=False,max_bounces=4,view_transform='AgX',exposure=0.,gamma=1.),
        lighting=dict(world_strength=.65,key_location=[-3,-4,5],key_energy=650.,key_size=4.,
                      fill_location=[4,-1,4],fill_energy=350.,fill_size=3.),
        shelf=dict(width=3.3,depth=.7,levels=[.16,1.14,2.22],board_thickness=.09,
                   divider_x=0.,back_y=.37,wood_color=[.16,.085,.035,1.],back_color=[.48,.44,.38,1.]),
        background_color=[.65,.69,.72,1.],books=[])
    colors=[[.16,.31,.47,1.],[.58,.15,.10,1.],[.72,.46,.12,1.],
            [.22,.44,.28,1.],[.48,.19,.29,1.],[.23,.27,.38,1.],
            [.62,.32,.12,1.],[.14,.38,.42,1.],[.45,.29,.48,1.]]
    for i in range(3):
        h=[.63,.70,.66][i];t=[.09,.10,.085][i]
        common['books'].append(dict(id=f'book_{i+1:02d}',dimensions=[t,.44,h],
            location=[-1.13+i*.17,-.035,.205+h/2],rotation_y=0.,cover_color=colors[i],
            support_z=.205,source_group='standing'))
    for g,(center,support) in enumerate(((.78,.205),(-.78,1.185))):
        accumulated=0.
        for i in range(3):
            n=3+g*3+i;t=[.085,.095,.08][i];h=[.66,.62,.69][i]
            common['books'].append(dict(id=f'book_{n+1:02d}',dimensions=[t,.43+.015*i,h],
                location=[center+.018*i,-.035,support+accumulated+t/2],rotation_y=math.pi/2,
                cover_color=colors[n],support_z=support,source_group=f'stack_{g+1}'))
            accumulated+=t
    a=deepcopy(common);b=deepcopy(common);c=deepcopy(common)
    for book in b['books']:
        if book['source_group'].startswith('stack_'):
            i=(int(book['id'].split('_')[1])-4)%3
            center=.78 if book['source_group']=='stack_1' else -.78
            book['rotation_y']=0.
            book['location']=[center+(i-1)*.16,-.035,book['support_z']+book['dimensions'][2]/2]
    palette=[[.10,.48,.57,1.],[.72,.37,.15,1.],[.40,.29,.64,1.],
             [.66,.21,.36,1.],[.32,.48,.13,1.],[.15,.45,.40,1.],
             [.48,.30,.18,1.],[.63,.42,.12,1.],[.24,.34,.62,1.]]
    for book,color in zip(c['books'],palette):book['cover_color']=color
    return dict(A=a,B=b,C=c)


def validate_config_controls(configs):
    a,b,c=(configs[k] for k in ('A','B','C'))
    nonbook=lambda cfg:{k:v for k,v in cfg.items() if k!='books'}
    if nonbook(a)!=nonbook(b) or nonbook(a)!=nonbook(c):raise ValueError('Non-book scene changed')
    ids=[[r['id'] for r in cfg['books']] for cfg in (a,b,c)]
    if ids[0]!=ids[1] or ids[0]!=ids[2] or any(len(row)!=9 or len(set(row))!=9 for row in ids):
        raise ValueError('Book identities/count changed')
    deltas=[]
    for first,second,third in zip(a['books'],b['books'],c['books']):
        allowed={k for k in set(first)|set(second) if first.get(k)!=second.get(k)}
        if allowed-set(('rotation_y','location')):raise ValueError('B changed more than book transform')
        if first['source_group']=='standing' and allowed:raise ValueError('B moved original upright books')
        baseline_angle=0. if first['source_group']=='standing' else math.pi/2
        if not math.isclose(first['rotation_y'],baseline_angle,abs_tol=1e-12) or not math.isclose(second['rotation_y'],0.,abs_tol=1e-12):
            raise ValueError('A must contain horizontal stacks; B must turn their books upright')
        if {k:v for k,v in first.items() if k!='cover_color'}!={k:v for k,v in third.items() if k!='cover_color'}:
            raise ValueError('C changed geometry/other metadata')
        deltas.append(dict(book_id=first['id'],B_changed_fields=sorted(allowed),
            A_location=first['location'],B_location=second['location'],
            A_rotation_y=first['rotation_y'],B_rotation_y=second['rotation_y'],
            C_changed_fields=['cover_color'] if first['cover_color']!=third['cover_color'] else []))
    if sum(bool(r['B_changed_fields']) for r in deltas)!=6:raise ValueError('Expected six converted horizontal books')
    return dict(passed=True,book_count=9,converted_books=6,nonbook_settings_identical=True,
        C_only_cover_colors_changed=True,per_book_deltas=deltas,
        limitation='B necessarily changes height/spacing, projected extent, occlusion and shadows; not a pixel-isolated factor')


def parse_prediction(raw):
    if not isinstance(raw,str):raise ValueError('Expected text JSON')
    text=raw.strip()
    if text.startswith('```') and text.endswith('```'):
        text=re.sub(r'^```(?:json)?\s*','',text,flags=re.I)[:-3].strip()
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('Duplicate JSON key')
            obj[key]=value
        return obj
    def invalid(_):raise ValueError('Nonfinite JSON')
    obj=json.loads(text,object_pairs_hook=unique,parse_constant=invalid)
    if not isinstance(obj,dict):raise ValueError('Expected object')
    fields={}
    for key in FIELDS:
        value=obj.get(key);valid=isinstance(value,str) and value in ('yes','no','unknown')
        fields[key]=dict(value=value if valid else None,raw_value=value,
            validation_status='valid' if valid else 'unavailable',
            error=None if valid else 'Missing/invalid field')
    extras=set(obj)-set(FIELDS)
    return dict(status='valid' if not extras and all(f['validation_status']=='valid' for f in fields.values()) else 'partial',
                fields=fields,schema_errors=['Unexpected fields'] if extras else [])


def answer_value(packet,key):
    field=packet.get('fields',{}).get(key,{})
    return field.get('value') if packet.get('status') in ('valid','partial') and field.get('validation_status')=='valid' else None


def compare_values(first,second):
    if first is None or second is None:return 'unavailable'
    if 'unknown' in (first,second):return 'unknown'
    return 'satisfied' if first==second else 'candidate_violated'


def compare_expected(expected,packet):
    return [dict(field=key,construction_expected=expected[key],prediction=answer_value(packet,key),
                 status=compare_values(expected[key],answer_value(packet,key)),
                 expected_source='construction_expected',reviewed=False,value=None,score=None,scorable=False)
            for key in FIELDS]


def compare_pair(first,second):
    return [dict(field=key,first_answer=answer_value(first,key),second_answer=answer_value(second,key),
                 status=compare_values(answer_value(first,key),answer_value(second,key)),
                 reviewed=False,value=None,score=None,scorable=False) for key in FIELDS]


def request(*args,**kwargs):
    raise PermissionError('No paid API requests authorized for this controls pilot; preparation only')


def group_contracts(labels):
    """Use the existing Group/Atomic adapters, without observations or scoring."""
    cases={};questions={};applicability={}
    for key,expected in labels['samples'].items():
        provenance=dict(source='new trusted procedural books fixture',render_used=False,
                        expected_source='construction_expected',reviewed=False)
        atoms=[]
        for field,question in zip(FIELDS,(
                '是否能清楚看到至少两本水平叠放的书籍？','是否能清楚看到竖直站立摆放的书籍？')):
            atoms.append(dict(id='books_'+field,group_id='G_books',region_id='R_shelf',type='statistical',
                claim='当前图像中存在'+('至少两本清晰水平叠放书籍' if field=='horizontal_stack' else '清晰竖直站立书籍'),
                definition=DEFINITIONS[field],question=question,answer_field=field,
                expected=expected[field]=='yes',answer_type='boolean',requires=[],status='candidate',
                canonical_fact_id='books_'+field,owner_id='G_books',scope='visible books in the whole image',
                source='construction config, not a VLM answer or reviewed GT',source_type='construction_expected',
                provenance=provenance,anchor_refs=[],reviewed=False,reliability=0.))
        case=dict(scene_id='independent_books_controls_'+key,reviewed=False,
            regions=[dict(id='R_shelf',description='independent synthetic book display',reviewed=False)],
            semantic_groups=[dict(group_id='G_books',region_id='R_shelf',name='visible book display',
                scope='all visible books in the independently constructed shelf',evidence=[a['id'] for a in atoms],
                member_instance_ids=None,provenance=provenance,reviewed=False,reliability=0.)],
            optional_anchors=[],atomic_evidence=atoms)
        questions[key],aliases=group_questions(case)
        if aliases:raise ValueError('No duplicate facts/aliases needed for the two controls')
        results=replay_atomic_answers(questions[key],source_kind='unavailable')
        applicability[key]=dict(verification_results=results,energy_records=group_energy_rows(questions[key],results),
            statistical_energy=None,scorable=False,reason='Verification Pending; no calibrated binary-to-energy mapping')
        cases[key]=case
    return dict(expected_source='construction_expected',reviewed=False,samples=cases),questions,applicability


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);(output/'images').mkdir();(output/'construction').mkdir()
    protocol=dict(system=SYSTEM,user=USER,definitions=DEFINITIONS,schema=SCHEMA,reviewed=False,
        frozen_before_images=True,maximum_actual_requests_authorized=0,proposed_future_budget=3,
        prompt_tuning_allowed=False,model='openai/gpt-6-sol',temperature=.1,max_tokens=400,json_mode=False,
        note='Definitions/Prompt are fixed before rendering and cannot be revised after model results')
    save(output/'frozen_protocol.json',protocol);(output/'frozen_protocol.json').chmod(0o444)
    configs=scene_configs();checks=validate_config_controls(configs)
    labels={key:dict(horizontal_stack='no' if key=='B' else 'yes',upright_books='yes') for key in configs}
    save(output/'expected_labels.json',dict(expected_source='construction_expected',reviewed=False,
        review_status='unreviewed',samples=labels,not_pixel_gt=True))
    (output/'expected_labels.json').chmod(0o444)
    for key,cfg in configs.items():
        cfg=dict(cfg,output=str(output/'images'/f'sample_{ord(key)-64:02d}.png'),metadata=str(output/'construction'/(key+'_render.json')))
        save(output/'construction'/(key+'.json'),cfg)
        (output/'construction'/(key+'.json')).chmod(0o444)
    save(output/'construction_checks.json',checks)
    save(output/'resource_preflight.json',dict(logical_cpus=os.cpu_count(),load_average=list(os.getloadavg()),
        selected_profile='existing serial supervised CPU launcher',threads=2,cpu_seconds_limit=60,
        timeout_seconds=120,rss_limit_bytes=1024**3,gpu_used=False,formal_runtime_status_changed=False))
    (output/'construction/books_control_scene.py').write_bytes((ROOT/'scripts/books_control_scene.py').read_bytes())
    (output/'construction/books_control_scene.py').chmod(0o444)
    save(output/'construction/source_review.json',dict(status='static_code_checked',human_label_review='unreviewed',
        source='newly authored primitive-only fixture; reviewed before execution',
        external_assets=False,historical_agent_code=False,loads_blend=False,network=False,
        checks=['nine closed books with cream page blocks and two covers',
                'horizontal books touch their supporting shelf/book',
                'fixed camera/lights/seed; no text objects or image stamps',
                'CPU only; existing serial resource-limited launcher']))
    print('Frozen definitions, prompt, labels and three construction configs; no API',flush=True)


def check_frozen(output):
    protocol=read(output/'frozen_protocol.json')
    for key,value in dict(system=SYSTEM,user=USER,definitions=DEFINITIONS,schema=SCHEMA).items():
        if protocol[key]!=value:raise ValueError('Frozen protocol differs: '+key)
    if protocol['maximum_actual_requests_authorized']!=0:raise ValueError('Offline preparation only')
    configs={k:read(output/'construction'/(k+'.json')) for k in ('A','B','C')}
    validate_config_controls({k:{f:v for f,v in cfg.items() if f not in ('output','metadata')}
                              for k,cfg in configs.items()})
    if (output/'construction/books_control_scene.py').read_bytes()!=(ROOT/'scripts/books_control_scene.py').read_bytes():
        raise ValueError('Fixture changed after preparation; do not overwrite or silently update it')
    return configs


def render(output):
    """Only our reviewed primitive fixture, never historical Agent source/blends."""
    from manual_cpu_render import launch,statistics
    configs=check_frozen(output)
    summary=dict(success=False,cases=[],api_requests=0,gpu_used=False,strictly_serial=True,
                 formal_runtime_status_changed=False)
    with (ROOT/'runs/.manual_reviewed_replay.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for key,cfg in configs.items():
            if Path(cfg['output']).exists() or Path(cfg['metadata']).exists():raise FileExistsError('No rerender/overwrite')
            folder=output/('launch_'+key);folder.mkdir(exist_ok=False)
            result=launch(folder,output,output/'construction/books_control_scene.py',
                          output/'construction'/(key+'.json'),label='trusted_books')
            result.update(statistics(folder))
            result['condition']=key
            result['success']=bool(result['success'] and result['cleanup_complete'] and
                result['all_sampled_threads_within_affinity'] and Path(cfg['output']).is_file() and Path(cfg['metadata']).is_file())
            if result['success']:
                result['render_seconds']=read(Path(cfg['metadata']))['render_seconds']
            summary['cases'].append(result)
            print(f"{key}: success={result['success']}, wall={result['seconds']}s, peak RSS={result['peak_rss_bytes']} bytes",flush=True)
            if not result['success']:break
    summary['success']=len(summary['cases'])==3 and all(r['success'] for r in summary['cases'])
    save(output/'render_summary.json',summary)
    return summary['success']


def finalize(output):
    configs=check_frozen(output)
    protocol=read(output/'frozen_protocol.json');labels=read(output/'expected_labels.json')
    summary=read(output/'render_summary.json')
    packets={k:dict(status='unavailable',fields={},request_status='not_requested',
        reason='Verification Pending: no paid requests authorized',source='not_requested',reviewed=False) for k in configs}
    save(output/'verification_results.json',dict(status='Verification Pending',actual_requests=0,
        raw_predictions=packets,per_sample={k:compare_expected(labels['samples'][k],packets[k]) for k in configs},
        pairs=dict(A_B=compare_pair(packets['A'],packets['B']),A_C=compare_pair(packets['A'],packets['C'])),
        detection_rate=None,accuracy=None,statistical_energy=None,scorable=False,reviewed=False))
    evidence,questions,applicability=group_contracts(labels)
    save(output/'group_evidence.json',evidence)
    save(output/'verification_questions.json',questions)
    save(output/'benchmark_applicability.json',applicability)
    requests=[];panels=[];checks=[];review_rows=[]
    metadata={}
    for index,(key,cfg) in enumerate(configs.items(),1):
        path=Path(cfg['output'])
        if not path.is_file():
            checks.append(dict(check=key+' rendered image',passed=False,detail='Unavailable; inspect launch logs'))
            continue
        with Image.open(path) as raw:
            image=raw.convert('RGB');image.load()
            checks.append(dict(check=key+' clean PNG',passed=raw.format=='PNG' and raw.mode=='RGB' and
                list(raw.size)==cfg['rendering']['resolution'],detail=f'{raw.format} {raw.mode} {raw.size}; no text overlay'))
        metadata[key]=read(Path(cfg['metadata']))
        m=metadata[key]
        checks.append(dict(check=key+' construction metadata',passed=m['book_count']==9 and m['text_objects']==0 and
            m['device']=='CPU' and m['threads']==2 and not m['historical_agent_code'] and not m['external_assets'],
            detail='nine books; no FONT/external assets; CPU 2 threads'))
        panels.append((key+' - '+('orientation change' if key=='B' else 'cover colors' if key=='C' else 'baseline'),image))
        # Local image_ref is a preparation descriptor, not a wire-ready request.
        # No expected labels/condition names are included in model-visible messages.
        requests.append(dict(sample_id=f'sample_{index:02d}',image_file=str(path),model=protocol['model'],
            temperature=protocol['temperature'],max_tokens=protocol['max_tokens'],automatic_retries=0,
            messages=[dict(role='system',content=SYSTEM),dict(role='user',content=[dict(type='text',text=USER),
                dict(type='image_ref',path=str(path),detail='high')])],
            response_schema=SCHEMA,send_json_mode=False,status='prepared_not_sent'))
        expected=labels['samples'][key]
        review_rows.append(dict(condition=key,construction_horizontal=expected['horizontal_stack'],
            construction_upright=expected['upright_books'],human_review='unreviewed',vlm='Verification Pending'))
    if len(metadata)==3:
        checks.extend([
            dict(check='all camera matrices identical',passed=metadata['A']['camera_matrix']==metadata['B']['camera_matrix']==metadata['C']['camera_matrix'],detail='exported Blender matrices'),
            dict(check='A/C book transforms identical',passed=metadata['A']['book_world_matrices']==metadata['C']['book_world_matrices'],detail='exported matrices; C changes cover colors only'),
            dict(check='B original three standing books unchanged',passed=all(metadata['A']['book_world_matrices'][f'book_{i:02d}']==metadata['B']['book_world_matrices'][f'book_{i:02d}'] for i in (1,2,3)),detail='six other books are rotated/repositioned'),
            dict(check='actual API requests',passed=True,detail='0; request() always refuses before loading credentials')])
        a=np.asarray(panels[0][1]);c=np.asarray(panels[2][1])
        checks.append(dict(check='C appearance actually differs from A',passed=not np.array_equal(a,c),
            detail='pixel differences confirm a nonidentical image; not a semantic measurement'))
    save(output/'pending_requests.json',dict(status='Verification Pending',authorized_now=0,
        proposed_future_requests=len(requests),images_per_request=1,requests=requests,
        transport='existing OfoxTunnel + VLMClient after explicit future authorization only',
        image_encoding='materialize image_ref as image_url in memory only after authorization; never persist Base64',
        credentials_included=False,expected_labels_sent=False,automatic_retries=False))
    save(output/'offline_checks.json',dict(passed=summary['success'] and all(r['passed'] for r in checks),checks=checks,
        model_executed=False,human_label_review='unreviewed'))
    save(output/'human_review.json',dict(status='unreviewed',reviewed=False,rows=[dict(condition=k,
        horizontal_stack_visible='unreviewed',upright_books_visible='unreviewed',
        B_nonbook_horizontal_confounds='unreviewed',occlusion_resolution_or_category_ambiguity='unreviewed',
        text_or_condition_cues_in_image='unreviewed') for k in configs]))
    if panels:panel_row(panels,output/'comparison.png',512)
    rows=table(review_rows)
    gallery=''.join(f'<figure><a href="{html.escape(Path(cfg["output"]).relative_to(output).as_posix())}"><img src="{html.escape(Path(cfg["output"]).relative_to(output).as_posix())}" alt="{key}"></a><figcaption>{key}: construction_expected only; human review unreviewed</figcaption></figure>' for key,cfg in configs.items() if Path(cfg['output']).is_file())
    checklist=''.join(f'<tr><td>{k}</td><td>□ yes □ no □ unknown</td><td>□ yes □ no □ unknown</td><td>□ 检查书架横板/纹饰误判、遮挡与页块</td><td>unreviewed</td></tr>' for k in configs)
    page=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>Independent books controls — Verification Pending</title>
<style>body{{font:16px sans-serif;max-width:1500px;margin:24px auto;padding:0 16px;line-height:1.55}}.gallery{{display:flex;gap:12px}}figure{{margin:0;flex:1;min-width:0}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;margin:16px 0}}td,th{{border:1px solid #bbb;padding:8px;text-align:left}}pre{{white-space:pre-wrap;background:#f2f4f6;padding:16px}}</style>
<h1>Group-level Statistical 控制实验</h1><p><b>Verification Pending；真实 API 请求 0 次。</b>下方 A/B/C 标签只在审核页出现，不写入发送给模型的 PNG。所有标签为 construction_expected，人工状态均为 unreviewed。</p>
<div class="gallery">{gallery}</div><h2>预注册预期（不是模型预测）</h2>{rows}
<h2>冻结的两个事实</h2><ul>{''.join('<li>'+html.escape(k+': '+v)+'</li>' for k,v in DEFINITIONS.items())}</ul>
<h2>人工审核表</h2><p>需人工逐项观察后另存结论。本页未替人工确认。</p><table><tr><th>样本</th><th>清晰横向书堆</th><th>清晰竖放书籍</th><th>歧义检查</th><th>状态</th></tr>{checklist}</table>
<h2>控制变量与已知限制</h2><p>9 本书、书架、相机、光照、渲染种子固定。B 将 6 本横放书转竖，需要改变中心高度与间距；因此投影范围、遮挡、阴影随之改变。C 仅改封面颜色，几何、光照不变；物理反射/间接光颜色可跟随变化。书架横板、细金色书脊纹饰不能被当成横向书堆。</p>
<h2>静态可视性候选观察（不是人工确认）</h2><p>A/C 左上与右下有可区分的三层薄体，左下有竖体；B 三组均呈竖体，未发现整本被裁切。但 8 samples 噪点明显、页块细节偏弱，仍需人工确认能否排除文件夹/唱片套。横板、书脊饰带与隔板交接黑条是潜在误判线索；C 浅色封面也可能降低边界对比。本轮保留这些问题，不重绘或事后修改 Prompt。reviewed=false。</p>
<h2>冻结 Prompt</h2><pre>{html.escape(SYSTEM+'\n\n'+USER)}</pre><h2>离线检查</h2>{table(checks)}
<p>A/B 应只在 horizontal_stack 上产生排列变化；A/C 两项都应不变。这是预期，不是已得到的 VLM 结果。所有实际验证状态仍为 unavailable，不计算检出率或 Statistical Energy。</p>
<p><a href="report.md">报告</a> · <a href="frozen_protocol.json">冻结协议</a> · <a href="expected_labels.json">预期标签</a> · <a href="pending_requests.json">待运行请求</a> · <a href="verification_results.json">实际验证状态</a></p></html>'''
    (output/'comparison.html').write_text(page)
    wall=sum(r['seconds'] for r in summary['cases']);peak=max((r['peak_rss_bytes'] for r in summary['cases']),default=0)
    test_result=read(output/'tests_result.json') if (output/'tests_result.json').exists() else None
    test_note=(f"{test_result['tests_run']} 项纯 CPU 单元测试，失败 {test_result['failures']}、错误 {test_result['errors']}、跳过 {test_result['skipped']}。" if test_result else '单元测试未运行；请执行下方命令。')
    render_rows='\n'.join(f'| {r["condition"]} | {r["success"]} | {r["seconds"]:.3f} | {r["peak_rss_bytes"]/1024**2:.1f} |' for r in summary['cases'])
    report=f'''# 独立书籍排列控制实验 — Verification Pending

完成 1 组 A/B/C 独立合成样本的离线准备；真实 VLM 请求 **0 次**，没有模型预测、检出率或正式 Statistical Energy。预期标签仅为 `construction_expected`，全部 `reviewed:false` / `unreviewed`。

## 冻结协议与数据来源

在生成图片前保存只读 `frozen_protocol.json` 与 `expected_labels.json`。两个问题分别判断“至少两本清楚可辨的横向堆叠书籍”和“清楚可辨的竖放书籍”，都只接受 yes/no/unknown。严格采用用户给定 Prompt，不根据图片或后续结果修改定义。旧 mixed→upright 实验只作为研究背景，本组未读取或使用 bw_0074 Reference/Render，也不声称进行全新研究者盲测。

场景由本轮新写并静态检查的 `construction/books_control_scene.py` 构建，只用基础几何、材质和固定相机；没有打开历史 .blend、执行 Agent 代码或调用 GPU/大型模型。每本书含封面、书脊和米色页块，避免使用单块彩色矩形代替所有书籍线索。没有文字、实验条件或预期标签写进原始 PNG。供模型观察的仅为 `images/sample_01.png` 至 `sample_03.png`；comparison.png/HTML 的标题仅供审核，不作为模型输入。

## 构造条件

| 条件 | Horizontal | Upright | 控制方式 |
|---|---|---|---|
| A | yes | yes | 3 本竖放 + 两组各 3 本横向书堆 |
| B | no | yes | 将同 6 本横放书转竖；原 3 本竖放不变 |
| C | yes | yes | A 的几何完全不变，仅改 9 本封面颜色 |

三侧均为同 9 本书，书本尺寸、书架、相机、分辨率、光照、曝光、随机种子相同。B 的旋转必然要求中心高度及间距变化；投影轮廓、可见页块、遮挡和阴影也会变，**并非只改变一个像素级因素**。C 的灯光不变，但封面色影响物理反射与间接光，不能保证非书籍像素完全相同。逐本差异在 construction_checks.json，实际相机/物体矩阵在 construction/*_render.json。

## 实际运行

复用现有受控 CPU 启动器，严格串行、两核亲和性、nice=10、每图 120 秒墙钟/60 秒 CPU、1 GiB RSS 停止阈值；CPU Cycles 768×640、8 samples、固定 seed、无去噪。保持正式 Runtime blocked 未改。总启动墙钟约 {wall:.3f} 秒，采样峰值 RSS 最大 {peak/1024**2:.1f} MiB。

| 条件 | 成功 | 启动墙钟 s | 采样峰值 RSS MiB |
|---|---|---|---|
{render_rows}

资源记录和日志位于 launch_A/、launch_B/、launch_C/。本轮不生成第二组布局，避免扩大实验。

{test_note} 数据检查 {len(checks)} 项，全部通过：{all(r['passed'] for r in checks)}。这些检查覆盖构造约束、解析/四状态/非评分适配与文件可读性，不代表真实 VLM 检测通过。

## 验证准备与 Benchmark 连接

pending_requests.json 保存完全相同的 System/User、预定模型 openai/gpt-6-sol、低 temperature、400 输出 Token 上限、每次一个完整 RGB、零重试；只有本地 image_ref，未保存 Base64、认证信息或预期标签到模型消息中。它是待授权请求描述，不是已发送的 HTTP 请求。现有 OfoxTunnel/VLMClient 可在下一轮获准后把 image_ref 在内存转为 image_url；当前 request() 在读取凭证/创建客户端之前直接拒绝。

复用现有 group_questions → replay_atomic_answers → group_energy_rows 适配链，生成兼容的 Group/Region/Atomic evidence 与 N/A 记录（benchmark_applicability.json）。每图与预期比较，以及 A/B、A/C 成对比较，都保持 unavailable（Verification Pending）。解析器保留另一有效字段，区分 unknown 与 unavailable；明确相同→satisfied、明确不同→candidate_violated，均不直接生成 Energy。group_evidence.json 提供 Group-level Statistical 候选输入，可靠性为 0，scorable=false，不新增第六类 Energy，也不改变正式公式/权重。两个事实分别有唯一 Group 所有者，无需逐实例成员匹配或额外 Anchor 罚项。

## 审核重点与限制

人工需确认两处横向书堆是否清晰、B 是否确实没有横向书堆、竖放书是否可辨，是否将书架横板/金色纹饰/页块误认成横向书。请在 human_review.json 另存人工结论；本轮不自动确认。没有逐本人工 GT、真实 VLM 结果或独立准确率，合成域结果即使成功也不能直接证明真实图像有效。此组没有唱片/文件夹干扰项，也没有严重遮挡、模糊、未知样本，无法测量这些失败模式或 unknown 校准。

静态可视性候选观察（reviewed=false）：A/C 左上与右下各有三层薄体、左下有竖体；B 三组均呈竖体，未发现整本裁切。但 8 samples 噪点明显，页块细节较弱，类别可能与文件夹/唱片套混淆；书架横板、书脊饰带、隔板交接黑条与顶部暗缝可成为杂线索；C 浅色书脊可能降低分层边界对比。此处不构成人工审核通过，本轮保留原图，不事后改场景或 Prompt。

最小真实验证需要 **3 次请求**（A/B/C 各 1 次，独立观察；不额外调用成对比较）。当前授权 **0 次**，等待用户批准后才能执行。后续需要不含历史 bw_0074 调参泄漏的独立真实图、人工按冻结定义审核的正/负/unknown 标签，以及唱片/文件夹、单本平放、遮挡、分辨率和多视角困难对照；报告误报、漏报、弃权及外观不变性，才能判断该候选是否适合接入正式 Statistical Energy。一次二值成功不构成分数校准。

## 离线复现

在仓库根目录使用现有 Python 环境，无需安装依赖。使用新的空输出目录，不能覆盖本轮结果：

```sh
/home/xymo/environments/relateanything-inference/bin/python scripts/group_statistical_controls.py --stage prepare --output results/group_statistical_controls_books_repro
/home/xymo/environments/relateanything-inference/bin/python -m unittest discover -s tests -p test_group_statistical_controls.py -v
/home/xymo/environments/relateanything-inference/bin/python scripts/group_statistical_controls.py --stage render --output results/group_statistical_controls_books_repro
/home/xymo/environments/relateanything-inference/bin/python scripts/group_statistical_controls.py --stage finalize --output results/group_statistical_controls_books_repro
```

render 仅运行本轮可信合成 fixture，使用原有命名空间及资源限制；若资源/隔离不可用即停止，不降低隔离标准。离线测试使用明确的构造答案测试解析比较逻辑，不将其写成真实 VLM 输出。测试结果见 tests.txt / tests_result.json；数据检查见 offline_checks.json。初次使用点号模块路径的测试启动因 tests 非包而失败，已改为 discover；原错误保存在 initial_tests.txt / initial_tests_result.json，不是测试断言失败。未修改正式评分、历史结果或 Git 提交。
'''
    (output/'report.md').write_text(report)
    print('Created review page and pending requests; VLM verification NOT executed',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('prepare','render','finalize','request'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='request':request()
    if args.stage=='prepare':prepare(output)
    elif args.stage=='render':return 0 if render(output) else 1
    elif args.stage=='finalize':finalize(output)
    return 0


if __name__=='__main__':raise SystemExit(main())
