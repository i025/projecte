"""Five bounded book-group controls. Preparation/rendering/reporting only."""
import argparse
from copy import deepcopy
import datetime
import fcntl
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import uuid

from PIL import Image,ImageDraw,ImageFilter,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from scripts.group_statistical_controls import (SYSTEM,USER,SCHEMA,DEFINITIONS,read,save,
    scene_configs,parse_prediction,answer_value,compare_pair)


def configs():
    base=scene_configs()['A'];base['books']=[]
    base['camera'].update(location=[3.5,-7.3,3.2],target=[0,0,1.26],lens_mm=58.)
    base['rendering'].update(resolution=[896,704],samples=24,seed=83)
    base['shelf'].update(width=3.6,levels=[.16,.89,1.62,2.35],divider_positions=[-.48,.65],
                         wood_color=[.42,.34,.24,1.],back_color=[.64,.65,.62,1.])
    colors=[[.17,.32,.47,1.],[.62,.24,.17,1.],[.61,.48,.21,1.],
            [.25,.43,.31,1.],[.46,.27,.39,1.],[.30,.36,.45,1.]]
    for x,support,h in [(-1.46,.205,.54),(-1.28,.205,.58),(-1.10,.205,.50),
                        (-.27,.935,.49),(-.08,.935,.54),(.11,.935,.51),
                        (-.20,1.665,.50),(.03,1.665,.55)]:
        n=len(base['books'])
        base['books'].append(dict(id=f'book_{n:02d}',dimensions=[.10,.38,h],
            location=[x,-.04,support+h/2],rotation_y=0.,support_z=support,
            source_group='standing',cover_color=colors[n%len(colors)]))
    accumulated=0.
    for i,(t,h) in enumerate(((.09,.56),(.105,.53),(.085,.59))):
        base['books'].append(dict(id=f'book_{8+i:02d}',dimensions=[t,.39,h],
            location=[1.14+.012*i,-.04,.935+accumulated+t/2],rotation_y=math.pi/2,
            support_z=.935,source_group='stack',cover_color=colors[(i+2)%len(colors)]))
        accumulated+=t
    result={key:deepcopy(base) for key in ('T1','T2','T3','T4')}
    for i,book in enumerate(b for b in result['T2']['books'] if b['source_group']=='stack'):
        book['rotation_y']=0.;book['location']=[.94+i*.19,-.04,.935+book['dimensions'][2]/2]
    result['T3']['books']=[b for b in result['T3']['books'] if b['source_group']=='standing' or b['id']=='book_08']
    result['T4']['books']=[b for b in result['T4']['books'] if b['source_group']=='standing']
    result['T4']['vinyl_records']=[dict(location=[1.14,-.04,.941+.015*i],radius=.27,
        upright=False,label_color=colors[i]) for i in range(3)]
    result['T4']['vinyl_records']+= [dict(location=[1.14,-.04,support+.29],radius=.29,
        upright=True,label_color=colors[i+3]) for i,support in enumerate((.205,1.665))]
    return result


def expected_labels():
    return dict(T1=dict(horizontal_stack='yes',upright_books='yes'),
                T2=dict(horizontal_stack='no',upright_books='yes'),
                T3=dict(horizontal_stack='no',upright_books='yes'),
                T4=dict(horizontal_stack='no',upright_books='yes'),
                T5=dict(horizontal_stack=None,upright_books=None))


def assess(expected,prediction):
    if prediction is None:return 'unavailable'
    if prediction=='unknown':return 'unknown'
    if expected is None:return 'expected_unreviewed'
    if prediction==expected:return 'correct'
    return 'false_positive' if prediction=='yes' else 'false_negative'


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    work=ROOT/'runs'/('books_controls_'+uuid.uuid4().hex);work.mkdir()
    (output/'images').mkdir()
    frozen=read(ROOT/'results/group_statistical_controls_books/frozen_protocol.json')
    if (frozen['system'],frozen['user'],frozen['schema'])!=(SYSTEM,USER,SCHEMA):raise ValueError('Frozen prompt changed')
    plan=dict(work=str(work),system=SYSTEM,user=USER,schema=SCHEMA,definitions=DEFINITIONS,
        expected=expected_labels(),expected_source='construction_expected',reviewed=False,
        T5_label_status='human_review_pending; visible labels unset, no correctness scoring',
        T5_underlying_construction=dict(horizontal_stack='yes',upright_books='yes'),
        T5_transform=dict(source='T1',operation='whole-image Gaussian blur',radius_pixels=14),
        model='gpt-6-sol',backend='Codex Subagent',maximum_new_verifiers=5,serial=True,
        no_api_equivalence=True,strict_blind_test=False,
        samples={key:dict(image=str(output/'images'/(uuid.uuid4().hex+'.png'))) for key in expected_labels()},
        authoring_resources=dict(logical_cpus=os.cpu_count(),load_average=list(os.getloadavg()),
                                 blender_device='CPU',threads=2,gpu_used=False))
    for key,cfg in configs().items():
        cfg.update(output=plan['samples'][key]['image'],metadata=str(work/(key+'_render.json')))
        save(work/(key+'.json'),cfg)
    (work/'fixture.py').write_bytes((ROOT/'scripts/books_control_scene.py').read_bytes())
    save(work/'frozen_plan.json',plan);(work/'frozen_plan.json').chmod(0o444)
    save(output/'verification_results.json',dict(status='prepared_not_verified',protocol=plan,
        raw_responses={},formal_statistical_energy=None,reviewed=False,usage='provisional/debug'))
    print(json.dumps(dict(output=str(output),work=str(work),frozen_before_model=True),ensure_ascii=False))


def render(output):
    from manual_cpu_render import launch,statistics
    pending=read(output/'verification_results.json');plan=pending['protocol'];work=Path(plan['work'])
    results=[]
    with (ROOT/'runs/.manual_reviewed_replay.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for key in ('T1','T2','T3','T4'):
            folder=work/('launch_'+key);folder.mkdir(exist_ok=False)
            result=launch(folder,work,work/'fixture.py',work/(key+'.json'),label='trusted_books')
            result.update(statistics(folder));result['case']=key
            result['success']=bool(result['success'] and result['cleanup_complete'] and
                result['all_sampled_threads_within_affinity'] and Path(plan['samples'][key]['image']).is_file())
            results.append(result);print(f"{key}: success={result['success']}, wall={result['seconds']}s",flush=True)
            if not result['success']:
                save(work/'render_summary.json',dict(success=False,cases=results));return False
    with Image.open(plan['samples']['T1']['image']) as original:
        original.convert('RGB').filter(ImageFilter.GaussianBlur(plan['T5_transform']['radius_pixels'])).save(plan['samples']['T5']['image'])
    save(work/'render_summary.json',dict(success=True,cases=results,T5='fixed blur of new T1, not another render'))
    save(work/'visible_quality_review.json',dict(status='pending_static_check',human_review='unreviewed',reviewed=False))
    print('Five new PNGs ready; no verifier launched',flush=True)
    return True


def stage(output):
    plan=read(output/'verification_results.json')['protocol'];work=Path(plan['work']);staged={}
    for key,case in plan['samples'].items():
        path=Path(case['image']);directory=Path('/tmp')/uuid.uuid4().hex;directory.mkdir(mode=0o700)
        target=directory/(uuid.uuid4().hex+'.png');shutil.copyfile(path,target);target.chmod(0o444)
        with Image.open(path) as a,Image.open(target) as b:
            if a.size!=(896,704) or a.tobytes()!=b.tobytes():raise ValueError('PNG staging changed image')
        staged[key]=dict(path=str(target),source=str(path),agent_task='v_'+uuid.uuid4().hex[:12])
    save(work/'staged_inputs.json',staged)
    print(json.dumps(staged,ensure_ascii=False))


def collect(output):
    """Read completed sessions, never launch/retry a verifier."""
    plan=read(output/'verification_results.json')['protocol'];work=Path(plan['work'])
    requests=read(work/'frozen_agent_inputs.json');staged=read(work/'staged_inputs.json')
    names={'/root/'+v['task_name']:k for k,v in requests.items()};packets={}
    for path in Path('/home/xymo/.codex/sessions').glob('*/*/*/*.jsonl'):
        with path.open() as stream:
            try:meta=json.loads(next(stream))['payload']
            except (ValueError,KeyError,StopIteration):continue
        if meta.get('agent_path') not in names:continue
        key=names[meta['agent_path']];final=[];models=set();efforts=set();calls=[];done=None;usage=None;usage_events=0
        for line in path.read_text().splitlines():
            row=json.loads(line);p=row.get('payload',{});kind=row['type']
            if kind=='turn_context':models.add(p['model']);efforts.add(p.get('effort'))
            elif kind=='event_msg' and p.get('type')=='task_complete':done=p
            elif kind=='event_msg' and p.get('type')=='token_count' and p.get('info'):
                usage=p['info']['total_token_usage'];usage_events+=1
            elif kind=='response_item' and p.get('type') in ('custom_tool_call','function_call'):
                calls.append(dict(name=p['name'],input=p.get('input',p.get('arguments',''))))
            elif kind=='response_item' and p.get('type')=='message' and p.get('role')=='assistant' and p.get('phase')=='final_answer':
                final.append(''.join(c.get('text','') for c in p.get('content',[]) if isinstance(c,dict)))
        raw=final[0] if len(final)==1 else None
        safe=bool(len(calls)==1 and calls[0]['name']=='exec' and calls[0]['input'].count('tools.view_image(')==1
            and staged[key]['path'] in calls[0]['input'] and not any(x in calls[0]['input']
                for x in ('exec_command','read_text','requests','fetch','open(')))
        try:parsed=parse_prediction(raw) if safe and models=={'gpt-6-sol'} else dict(status='unavailable',fields={})
        except (ValueError,TypeError):parsed=dict(status='unavailable',fields={})
        packet=dict(raw_answer=raw,parsed=parsed,actual_input=requests[key],model_observed=sorted(models),
            effort_observed=sorted(efforts),source='Codex Subagent',session_file=str(path.resolve()),
            agent_path=meta['agent_path'],tool_calls=calls,read_audit_passed=safe,
            received_task_text_independently_readable=False,context_inheritance='none',
            final_messages=len(final),usage=usage,usage_events=usage_events,
            duration_seconds=done['duration_ms']/1000 if done else None,
            started_at=done['started_at'] if done else None,completed_at=done['completed_at'] if done else None,
            reviewed=False,scorable=False)
        if key in packets:raise ValueError('Duplicate verifier session')
        packets[key]=packet
    if set(packets)!=set(requests):raise ValueError('Missing session; do not generate observations')
    if any(packets[a]['completed_at']>packets[b]['started_at'] for a,b in zip(list(requests)[:-1],list(requests)[1:])):
        raise ValueError('Verifier sessions were not serial')
    save(work/'raw_observations.json',packets)
    print(json.dumps({k:p['raw_answer'] for k,p in packets.items()},ensure_ascii=False))


def report(output):
    pending=read(output/'verification_results.json');plan=pending['protocol'];work=Path(plan['work'])
    if pending['status']!='prepared_not_verified':raise FileExistsError('Final results already exist; no overwrite')
    if plan!=read(work/'frozen_plan.json'):raise ValueError('Frozen labels/protocol changed')
    packets=read(work/'raw_observations.json');requests=read(work/'frozen_agent_inputs.json')
    counts={k:0 for k in ('correct','false_positive','false_negative','unknown','unavailable')}
    cases={};usage={};duration=0.
    for key in plan['samples']:
        p=packets[key]
        if p['actual_input']!=requests[key]:raise ValueError('Input record changed')
        if p['raw_answer'] is not None and p['parsed']['status'] in ('valid','partial'):
            if parse_prediction(p['raw_answer'])!=p['parsed']:raise ValueError('Parsed answer changed')
        fields=[]
        for field,expected in plan['expected'][key].items():
            predicted=answer_value(p['parsed'],field);assessment=assess(expected,predicted)
            state=('unavailable' if predicted is None else 'unknown' if predicted=='unknown' or expected is None else
                   'satisfied' if predicted==expected else 'candidate_violated')
            fields.append(dict(field=field,expected=expected,prediction=predicted,assessment=assessment,
                verification_status=state,reference_label_review='unreviewed',reviewed=False,
                correctness_scored=False,construction_comparison_available=expected is not None and predicted not in (None,'unknown'),
                energy_value=None,scorable=False))
            if key!='T5':counts[assessment]+=1
        cases[key]=dict(expected=plan['expected'][key],expected_source='construction_expected' if key!='T5' else 'human_review_pending',
            prediction={f:answer_value(p['parsed'],f) for f in plan['expected'][key]},fields=fields,
            original_image='images/'+Path(plan['samples'][key]['image']).name,
            raw_response=p,reviewed=False,usage='provisional/debug')
        duration+=p['duration_seconds'] or 0.
        for field,value in (p['usage'] or {}).items():usage[field]=usage.get(field,0)+value
    pairs=dict(T1_T2=compare_pair(packets['T1']['parsed'],packets['T2']['parsed']))
    final=dict(status='completed',backend='Codex Subagent',protocol=plan,cases=cases,comparison=pairs,
        candidate_counts_T1_T4=counts,T5_correctness='not_scored_pending_human_labels',
        previous_input_audit=read(work/'prior_input_audit.json'),
        verification_sessions=5,ofox_api_calls=0,total_verifier_session_seconds=duration,
        verifier_usage=usage,usage_scope='Whole five child sessions, tools/platform context included; parent/preparation excluded',
        actual_currency_cost=None,ofox_cost_usd=0,strict_blind_test_established=False,
        single_image_filesystem_access_enforced=False,received_task_text_independently_readable=False,
        formal_statistical_energy=None,reviewed=False,scorable=False,usage='provisional/debug')
    # This replaces only this new run's preparation placeholder, preserving its
    # frozen protocol; no pre-existing experiment or reference label is edited.
    (output/'verification_results.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,allow_nan=False))
    width=896;margin=24;panel_h=880;top=135
    canvas=Image.new('RGB',(3*width+4*margin,1920),'#f2f5f8');draw=ImageDraw.Draw(canvas)
    font=lambda s,b=False:ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf',s)
    draw.text((margin,18),'Book Group Controls - New Layout and Difficult Inputs',font=font(34,True),fill='#142235')
    draw.text((margin,66),'Codex Subagent / gpt-6-sol | 5 serial observations | construction_expected / unreviewed',font=font(24),fill='#324459')
    draw.text((margin,102),'T5 has no adjudicated visibility label; its answer is shown without correctness scoring.',font=font(22),fill='#7c4c0a')
    names=dict(T1='new layout: both orientations',T2='same layout: upright only',T3='single flat book',T4='vinyl distractors',T5='blurred: labels pending')
    for n,(key,case) in enumerate(cases.items()):
        x=margin+(n%3)*(width+margin);y=top+(n//3)*panel_h
        draw.text((x,y),key+' - '+names[key],font=font(27,True),fill='#142235')
        with Image.open(output/case['original_image']) as im:canvas.paste(im.convert('RGB'),(x,y+46))
        expected=case['expected'];pred=case['prediction'];label=lambda v:'unset' if v is None else v
        draw.text((x,y+760),f"Expected H/U: {label(expected['horizontal_stack'])} / {label(expected['upright_books'])}",font=font(23),fill='#324459')
        draw.text((x,y+792),f"Actual H/U: {label(pred['horizontal_stack'])} / {label(pred['upright_books'])}",font=font(24,True),fill='#142235')
        assessments=[r['assessment'] for r in case['fields']]
        text=' / '.join(assessments) if key!='T5' else 'UNSCORED: human label review pending'
        draw.text((x,y+828),text,font=font(21,True),fill='#156744' if assessments==['correct','correct'] else '#8a4a0b')
    x=margin+2*(width+margin);y=top+panel_h
    for i,text in enumerate(['What this run establishes:',f'T1-T4 correct fields: {counts["correct"]}',
        f'Candidate false positives: {counts["false_positive"]}',f'Candidate false negatives: {counts["false_negative"]}',
        f'Unknown / Unavailable (T1-T4): {counts["unknown"]} / {counts["unavailable"]}',
        'T5: no correctness/accuracy claim','All labels remain unreviewed.','No formal Statistical Energy.','No Ofox calls; no automatic retries.',
        'Shared-filesystem and platform-context limits remain.']):
        draw.text((x,y+25+i*44),text,font=font(25,i==0),fill='#324459')
    canvas.save(output/'comparison.png')
    # No failure panel is emitted when there is no construction-label mismatch.
    failures=[k for k,c in cases.items() if any(r['assessment'] in ('false_positive','false_negative') for r in c['fields'])]
    if failures:
        panel=Image.new('RGB',(2*width+3*margin,len(failures)*820),'#f2f5f8');pd=ImageDraw.Draw(panel)
        for n,key in enumerate(failures):
            with Image.open(output/cases[key]['original_image']) as im:
                panel.paste(im,(margin,n*820+60))
                # The right-middle compartment is the controlled changed group
                # in these generated scenes; this post-hoc display is not input.
                crop=im.crop((int(.52*im.width),int(.35*im.height),int(.86*im.width),int(.66*im.height)))
                crop.thumbnail((width,704));crop=crop.resize((width,round(crop.height*width/crop.width)))
                panel.paste(crop,(width+2*margin,n*820+60))
            pd.text((margin,n*820+12),key+' candidate mismatch; unreviewed',font=font(28,True),fill='#8a4a0b')
        panel.save(output/'failure_cases.png')
    rows='\n'.join(f"| {k} | {c['expected']['horizontal_stack']}/{c['expected']['upright_books']} | {c['prediction']['horizontal_stack']}/{c['prediction']['upright_books']} | {' / '.join(r['assessment'] for r in c['fields'])} |" for k,c in cases.items())
    render_summary=read(work/'render_summary.json');tests=read(work/'tests_result.json')
    report_text=f'''# 书籍 Group：跨布局与困难样本验证

后端 **Codex Subagent**，模型请求与会话记录均为 **gpt-6-sol**。5 个独立上下文验证子 Agent 严格串行，每图一个、无重试；没有重新运行旧 A/B/C，没有 Ofox 请求、正式 Energy 或综合准确率。全部 reviewed=false、provisional/debug。T1–T4 的“正确/误报/漏检”仅表示相对 construction_expected 的候选诊断，不是人工 GT 结论。

## 先审计旧实验

旧三子会话各只有一次指定图像读取，未观察到标签/其他图读取；模型 gpt-6-sol、fork_turns=none。但旧路径暴露实验主题且用顺序文件名，父任务正文在持久日志中加密，无法独立逐字核实；共享文件系统仍可读，“禁止读取”只是任务约束。旧实验不能追溯认定为强制隔离的严格盲测。审计证据在 verification_results.json.previous_input_audit；原实验保持只读。

## 新数据与冻结

新建三列三层书架，层板、分隔位置、相机与上一轮不同，并非只换颜色。复用本轮可信的基础几何生成器；只扩展可配置隔板和可见唱片圆盘/中心标签/沟槽。T1/T2 同 11 本书、相机、光照、尺寸、材质、seed；3 本横放书转竖必然改变中心高度与横向间距，并改变遮挡/阴影，不能声称像素级单因素。T3 留一册平放书及原竖放书，数量减少是明确记录的负对照。T4 将横放书替为唱片，并增加两个直立展示圆盘；类别依据可见圆盘、沟槽、标签，不依赖 Blender 名称。未测试文件夹或带书籍式封套的唱片。T5 是新 T1 固定 GaussianBlur(radius=14) 的完整图像，没有再生成场景；两项可见预期均为 None，必须人工审核，不能预设 unknown 正确。

预期、问题、Schema 和生成配置均在验证前冻结于 {work.relative_to(ROOT)}/frozen_plan.json；验证输入在 frozen_agent_inputs.json 中先保存再逐个发送。本轮没有根据回答调整场景、标签、问题或模糊程度。4 次受限 CPU 渲染全部成功，累计启动墙钟 {sum(r['seconds'] for r in render_summary['cases']):.3f} 秒；896×704、24 samples、两核、低优先级、每图120秒墙钟/60秒CPU/1GiB RSS阈值、网络命名空间，无 GPU。

## 原始结果

| 样本 | 冻结预期 H/U | 实际 H/U | 分字段候选诊断 |
|---|---|---|---|
{rows}

T1→T2：Horizontal {cases['T1']['prediction']['horizontal_stack']}→{cases['T2']['prediction']['horizontal_stack']}，Upright {cases['T1']['prediction']['upright_books']}→{cases['T2']['prediction']['upright_books']}。成对 candidate_violated 表示目标变化被发现，不是额外 Energy 惩罚；完整分字段状态保留在 JSON。

T1–T4 各字段计数：{json.dumps(counts,ensure_ascii=False)}。Unknown 与 Unavailable 不折算为对或错。T5 两项不计正确、误报、漏检或准确率；实际给出 {cases['T5']['prediction']}，只记录其弃权/确定回答行为，待人工判断证据是否足够。没有已确定的误报/漏检时不生成 failure_cases.png，避免将 T5 未决状态伪称已确认错误。

## 能力证据与失败模式

相较旧 A/B/C 只有方向与颜色控制，本轮添加真实新布局、单册平放与可见唱片干扰。T1/T2 能支持该新布局中的方向变化检测；T3 检查“至少两本”的排除能力；T4 仅检查裸唱片圆盘这个相对明显的非书籍类别，不代表复杂文件夹/封套混淆已解决。原图仍有采样噪点、重复书脊与隔板暗线，整体形状和水平线捷径仍不能排除。没有定位/注意力证据，不能仅凭两个回答证明模型理解每本书或真实实例数量。

T5 未知标签尚未经人工确认，不能说模型弃权正确、漏检或过度自信。如果模型回答 no，它可能将“看不清”解释为“没有清楚看到”，也可能未识别；回答 yes 也可能依赖模糊形状。这个 **no 与 unknown 的可观察性边界**既涉及原子命题定义，也涉及视觉识别，现有 JSON 无法辨别原因。讨论仅作后续协议诊断，本轮问题完全未改。

结论：仍值得作为 Group-level Statistical 的候选验证器继续有限研究；本轮不是可靠性认证。需要人工逐项审核，之后在独立真实图、书籍式唱片封套、文件夹、部分遮挡和分辨率变化上检验类别误报、计数阈值与弃权校准。当前只有一个新合成布局和每条件一个观测，不能以总体准确率声称跨场景稳定。

## 输入隔离与资源口径

每张图使用独立随机 /tmp/UUID/UUID.png 路径，目录仅包含该图；验证者未收到 T编号、实验条件、expected、其他答案或历史结论。模型任务名也随机。实际发送的协调端任务字符串、原始回答、模型、用量、只读工具记录和session路径保存在 verification_results.json；所有源图保存在 images/。与源图字节/像素一致，展示文字在收齐回答后添加，没有进入输入。每个子会话工具记录只应出现一次指定 PNG 的 view_image；shared filesystem 仍没有强制单图读取权限，父消息正文在日志中加密，因此 **不能声称严格盲测隔离已被证明**。冻结 System/User 以任务文本传递，平台系统上下文、温度及输出上限不等价固定 API。

5 个验证会话合计 {duration:.3f} 秒；用量 {json.dumps(usage,ensure_ascii=False)}。这是五个完整子会话（平台指令、取得图像的工具阶段和最终回答），不含主 Agent/代码审计/准备。缓存输入已包含在输入、推理输出已包含在输出。Ofox调用与该Key消费为0；Codex实际货币费用未知，不称免费。本轮 {tests['tests_run']} 项CPU测试通过，另做原始JSON重解析、匿名副本一致性、序列和PNG检查。没有新的 HTML。

## 复现

离线重放现有回答不调用模型。报告生成器拒绝覆盖已完成结果，使用临时副本测试或新目录；现有JSON包含全部固定参数和实际输入，原始会话用于只读核查。受控数据可用以下命令写入新目录，仍使用受限串行CPU启动器：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_group_statistical*controls.py' -v
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_statistical_hard_controls.py --stage prepare --output results/group_statistical_hard_books_repro
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_statistical_hard_controls.py --stage render --output results/group_statistical_hard_books_repro
```

只重画已有结果、不生成新样本或调用模型，使用新的空目标目录：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_statistical_hard_controls.py --stage replay --output results/group_statistical_hard_books --destination results/group_statistical_hard_books_replay
```

collect 阶段只读已存在子会话；report/replay 阶段只读 frozen_plan/raw_observations，不启动验证。主实验的构造、测试与资源日志位于 {work.relative_to(ROOT)}。源码只改可信图片生成器、添加本轮辅助函数及必要测试，没有修改五类 Energy、Region/Group 正式结构、历史产物或提交 Git。完成五图后停止。
'''
    (output/'report.md').write_text(report_text)
    print(json.dumps(dict(output=str(output),counts=counts,T5=cases['T5']['prediction'],sessions=5,tokens=usage,seconds=duration),ensure_ascii=False))


def replay(source,destination):
    """Rebuild presentation from recorded answers, with no model execution."""
    shutil.copytree(source,destination)  # Fails if the destination already exists.
    final=read(destination/'verification_results.json')
    if final['status']!='completed':raise ValueError('Replay needs completed observations')
    (destination/'verification_results.json').write_text(json.dumps(dict(status='prepared_not_verified',protocol=final['protocol'])))
    report(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('prepare','render','stage','collect','report','replay'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--destination',type=Path)
    args=parser.parse_args();destination=args.output.resolve()
    if args.stage=='prepare':prepare(destination)
    elif args.stage=='render':raise SystemExit(0 if render(destination) else 1)
    elif args.stage=='stage':stage(destination)
    elif args.stage=='collect':collect(destination)
    elif args.stage=='report':report(destination)
    else:
        if args.destination is None:parser.error('replay requires a fresh --destination')
        replay(destination,args.destination.resolve())
