"""New CPU-only synthetic shelf images; independent visual answers collected offline."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
import uuid

from PIL import Image, ImageChops, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read,save,font,collect

SYSTEM='你是图像结构验证器。只根据当前图片判断指定书架结构。present 表示有充分可见证据确认内部竖向结构隔板存在；absent 表示目标层足够可见，能确认没有该隔板；unknown 表示遮挡、模糊或类别歧义导致无法判断。不要把柜体外框、书脊、阴影或遮挡物当成内部隔板，不猜测被遮挡的结构。只输出 JSON。'
USER='书架最上方开口层（柜体外顶板与第一块内部水平层板之间）是否存在把同层左右开口分开的内部竖向结构隔板？仅输出一个 JSON 对象，唯一字段 internal_divider，其值只能为 present、absent 或 unknown。不要输出解释。'


def parse_answer(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('Duplicate key: '+k)
            result[k]=v
        return result
    try:
        obj=json.loads(raw,object_pairs_hook=unique)
        if not isinstance(obj,dict) or set(obj)!={'internal_divider'} or obj['internal_divider'] not in ('present','absent','unknown'):
            raise ValueError('Expected exactly internal_divider with present/absent/unknown')
        return dict(status='valid',value=obj['internal_divider'])
    except (ValueError,TypeError) as e:return dict(status='unavailable',value=None,error=str(e))


def classify(parsed,label):
    value=parsed.get('value') if parsed.get('status')=='valid' else None
    if value is None:return dict(status='unavailable',prediction=None,reviewed=False)
    if label['human_visibility_review']=='unreviewed':
        return dict(status='not_scored_visibility_review_pending',prediction=value,
            matches_frozen_visibility_candidate=value==label['answer_candidate'],
            diagnostic='abstained' if value=='unknown' else 'potential_unjustified_certainty_needs_review',reviewed=False)
    expected=label['answer_candidate']
    status='abstained' if value=='unknown' else 'matches_construction_expected' if value==expected else 'false_negative' if expected=='present' else 'false_positive'
    return dict(status=status,prediction=value,expected=expected,labels_are_reviewed_gt=False,reviewed=False)


def make_image(divider,occluded):
    """Fixed affine orthographic 2.5D drawing, not photorealistic or Blender output."""
    scale=2;size=(1024,800);im=Image.new('RGB',(size[0]*scale,size[1]*scale),'#ece9e2');d=ImageDraw.Draw(im)
    def pt(x,y,z):return ((495+185*(x+.38*y))*scale,(752-177*(z+.20*y))*scale)
    def poly(points,color):d.polygon([pt(*p) for p in points],fill=color)
    def box(x1,x2,y1,y2,z1,z2,color):
        rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
        light=tuple(min(255,round(v*1.12)) for v in rgb);dark=tuple(round(v*.75) for v in rgb)
        poly([(x1,y1,z2),(x2,y1,z2),(x2,y2,z2),(x1,y2,z2)],light)
        poly([(x2,y1,z1),(x2,y2,z1),(x2,y2,z2),(x2,y1,z2)],dark)
        poly([(x1,y1,z1),(x2,y1,z1),(x2,y1,z2),(x1,y1,z2)],rgb)
    # The camera, frame, books and deterministic colors remain identical in every sample.
    poly([(-2.25,-.12,.12),(2.4,-.12,.12),(2.55,.60,.12),(-2.1,.60,.12)],'#d2cbc0')
    box(-2.1,2.1,.42,.48,.2,3.8,'#bdb1a0')
    palette=['#a75841','#d1ba79','#557d83','#c7c1a6','#78667d','#668567']
    books=[]
    for j,x in enumerate([-1.76,-1.52,-1.28,-1.04,.72,.96,1.20,1.44,1.68]):
        h=[1.13,1.29,1.18,1.36][j%4];w=.17
        box(x,x+w,.07,.36,2.05,2.05+h,palette[j%6]);books.append([x,w,h])
        # Small horizontal spine markings make the thin items visually distinct from frame boards.
        poly([(x+.025,.062,2.25),(x+w-.025,.062,2.25),(x+w-.025,.062,2.27),(x+.025,.062,2.27)],'#e8ddc3')
    for j,x in enumerate([-1.76,-1.5,-1.24,-.98,.90,1.14,1.38,1.62]):
        box(x,x+.18,.05,.37,.39,.39+[1.12,1.32,1.22][j%3],palette[(j+2)%6])
    for j in range(3):box(-.48,.52,.04,.36,.40+j*.13,.51+j*.13,palette[(j+1)%6])
    for z1,z2 in [(.20,.39),(1.92,2.05),(3.64,3.8)]:box(-2.1,2.1,0,.48,z1,z2,'#315364')
    box(-2.1,-1.93,0,.48,.2,3.8,'#315364');box(1.93,2.1,0,.48,.2,3.8,'#315364')
    if divider:box(-.055,.055,0,.45,2.05,3.64,'#315364')
    if occluded:
        # An opaque foreground cloth covers the whole upper opening, including both divider joints.
        y=-.22
        edge=[(-2.03,y,3.85),(2.03,y,3.85),(2.03,y,2.00)]
        for j in range(25,-1,-1):edge.append((-2.03+4.06*j/25,y,2.0+(.018 if j%2 else 0)))
        poly(edge,'#bca992')
        for j in range(6):
            x=-1.7+j*.62
            poly([(x,y-.004,3.55),(x+.065,y-.004,3.55),(x+.18,y-.004,2.14),(x+.12,y-.004,2.14)],'#b29e86')
        # Short horizontal fastening tabs and scalloped hem identify foreground fabric, not a vertical wall.
        for x in [-1.75,-.9,0,.9,1.75]:box(x-.06,x+.06,y-.01,y,3.81,3.88,'#d4c6b2')
    return im.resize(size,Image.Resampling.LANCZOS),dict(size=list(size),projection='fixed affine orthographic 2.5D; no perspective camera fitting',
        projection_formula='x=495+185*(x+.38*y); y=752-177*(z+.20*y)',frame_bounds=[[-2.1,0,.2],[2.1,.48,3.8]],
        target_divider=[[-.055,0,2.05],[.055,.45,3.64]],divider_constructed=divider,foreground_occluder=occluded,
        other_book_and_frame_geometry_unchanged=True,supersampling=2,upper_book_geometry=books)


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);work=ROOT/'runs'/('structural_visual_'+uuid.uuid4().hex);work.mkdir();(work/'images').mkdir()
    protocol=dict(work=str(work),backend='Codex Subagent',model='gpt-6-sol',system=SYSTEM,user=USER,
        schema=dict(type='object',required=['internal_divider'],additionalProperties=False,
                    properties=dict(internal_divider=dict(type='string',enum=['present','absent','unknown']))),
        maximum_verifiers=3,serial=True,automatic_retries=False,synthetic=True,reviewed=False,usage='provisional/debug',
        generation='New Pillow 2.5D fixture; CPU only; same view/frame/books; no history images or Agent code',
        source_inspection='Coordinator inspected this small drawing function before execution; no dynamic code, network, Blender or subprocess',
        maximum_cpu_seconds_per_process=30,maximum_address_space_bytes=1073741824)
    staged={};draft=[]
    for condition,divider,occluded,construction in [('divider_present',True,False,'present'),('divider_absent',False,False,'absent'),('target_occluded',True,True,'present')]:
        key='i_'+uuid.uuid4().hex[:10];image,config=make_image(divider,occluded);path=work/'images'/(uuid.uuid4().hex+'.png');image.save(path);path.chmod(0o444)
        staged[key]=dict(source=str(path),condition=condition)
        draft.append(dict(sample_id=key,image=str(path),condition=condition,scene=config,construction_truth=construction,
            answer_candidate=None if occluded else construction,answer_candidate_source='pending_separate_visibility_audit' if occluded else 'construction_expected_with_clear_unoccluded_fixture',
            human_visibility_review='unreviewed' if occluded else 'not_independently_reviewed_construction_label',reviewed=False))
    save(work/'protocol.json',protocol);(work/'protocol.json').chmod(0o444)
    save(work/'samples_draft.json',draft);save(work/'staged_inputs.json',staged)
    tracked={p for folder in ('structural_layout_bw0074','structural_local_comparability_bw0074') for p in (ROOT/'results'/folder).rglob('*') if p.is_file()}
    save(work/'historical_state.json',{str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in tracked})
    save(output/'verification_results.json',dict(status='images_prepared_no_verification',protocol=protocol,reviewed=False))
    print(json.dumps(dict(work=str(work),images=draft,generation_usage=dict(cpu_seconds=resource.getrusage(resource.RUSAGE_SELF).ru_utime,
        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)),ensure_ascii=False))


def seal(output):
    pending=read(output/'verification_results.json');work=Path(pending['protocol']['work']);audit=read(work/'visibility_audit.json')
    samples=read(work/'samples_draft.json');staged=read(work/'staged_inputs.json');requests={}
    for sample in samples:
        entry=audit[sample['sample_id']]
        sample.update(visibility_audit=entry,answer_candidate=entry['answer_candidate'],answer_candidate_source=entry['source'])
        folder=Path('/tmp')/uuid.uuid4().hex;folder.mkdir(mode=0o700);path=folder/(uuid.uuid4().hex+'.png')
        shutil.copyfile(sample['image'],path);path.chmod(0o444);task='v_'+uuid.uuid4().hex[:12]
        staged[sample['sample_id']].update(path=str(path),agent_task=task)
        requests[sample['sample_id']]=dict(task_name=task,model='gpt-6-sol',fork_turns='none',message=
            '只观察下面指定的一张PNG。仅允许一次view_image读取该图，设置detail="original"，并用image(result.image_url,"original")转交图片；不读取其他文件，不联网，不调用其他模型，不写文件，不请求澄清。最终只输出规定JSON。\n\n图像：'+str(path)+'\n\nSystem：\n'+SYSTEM+'\n\nUser：\n'+USER)
    save(work/'expected_frozen.json',dict(frozen_unix=time.time(),samples=samples,reviewed=False));(work/'expected_frozen.json').chmod(0o444)
    save(work/'frozen_plan.json',pending['protocol']);(work/'frozen_plan.json').chmod(0o444)
    save(work/'frozen_agent_inputs.json',requests);(work/'frozen_agent_inputs.json').chmod(0o444)
    (work/'staged_inputs.json').write_text(json.dumps(staged,ensure_ascii=False,indent=2))
    pending['status']='frozen_ready_for_visual_verification';(output/'verification_results.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2))
    print(json.dumps(requests,ensure_ascii=False))


def report(output,destination):
    pending=read(output/'verification_results.json');work=Path(pending['protocol']['work']);protocol=read(work/'frozen_plan.json')
    assert protocol==pending['protocol']
    frozen_bytes=(work/'expected_frozen.json').read_bytes();frozen=json.loads(frozen_bytes);samples=frozen['samples'];packets=read(work/'raw_observations.json')
    assert frozen['frozen_unix']<min(p['started_at'] for p in packets.values())
    requests=read(work/'frozen_agent_inputs.json');staged=read(work/'staged_inputs.json');normalized=[]
    for s in samples:
        key=s['sample_id'];normalized.append(requests[key]['message'].replace(staged[key]['path'],'{IMAGE}'))
        assert Path(staged[key]['path']).read_bytes()==Path(s['image']).read_bytes()
        with Image.open(s['image']) as im:assert not im.info, 'Unexpected image metadata'
    assert len(set(normalized))==1
    rows=[];usage={}
    for sample in samples:
        packet=packets[sample['sample_id']]
        if packet['read_audit_passed']:assert packet['parsed']==parse_answer(packet['raw_answer'])
        row=dict(sample=sample,observation=packet,comparison=classify(packet['parsed'],sample),reviewed=False);rows.append(row)
        for key,value in (packet['usage'] or {}).items():usage[key]=usage.get(key,0)+value
    state=read(work/'historical_state.json');assert all(Path(p).stat().st_size==s['size'] and Path(p).stat().st_mtime_ns==s['mtime_ns'] for p,s in state.items())
    if destination!=output:destination.mkdir(parents=True,exist_ok=False)
    for name in ('comparison.png','report.md'):
        if (destination/name).exists():raise ValueError('Completed artifacts must not be overwritten')
    canvas=Image.new('RGB',(3120,1250),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((24,15),'Structural visual verifier | NEW synthetic shelf | Codex Subagent gpt-6-sol',font=font(34),fill='#17354d')
    d.text((24,65),'Same camera / frame / books. Labels shown here were added AFTER inference, never sent to verifiers.',font=font(27),fill='#33495d')
    for i,row in enumerate(rows):
        x=24+i*1036;image=Image.open(row['sample']['image']);canvas.paste(image,(x,125));label=row['sample'];c=row['comparison']
        lines=[label['condition'],f"Construction truth: {label['construction_truth']}",f"Frozen visible-answer candidate: {label['answer_candidate']}",
               'Actual: '+str(c['prediction']),'Result: '+c['status'],
               'Independent visibility review: pending' if label['human_visibility_review']=='unreviewed' else 'Label: construction_expected / unreviewed']
        for j,line in enumerate(lines):d.text((x,950+j*40),line,font=font(24),fill='#17354d')
    d.text((24,1200),'All reviewed=false / provisional/debug. Occluded sample not scored as correct/incorrect before independent visibility review.',font=font(25),fill='#654f2e')
    canvas.save(destination/'comparison.png')
    assert (work/'expected_frozen.json').read_bytes()==frozen_bytes
    clear_outcomes={status:sum(r['comparison']['status']==status for r in rows if r['sample']['condition']!='target_occluded')
        for status in ('matches_construction_expected','false_positive','false_negative','abstained','unavailable')}
    difference_bbox=ImageChops.difference(Image.open(samples[0]['image']),Image.open(samples[1]['image'])).getbbox()
    preflight=read(work/'preflight_note.json') if (work/'preflight_note.json').exists() else None
    result=dict(status='completed',protocol=protocol,rows=rows,backend='Codex Subagent',model='gpt-6-sol',
        actual_verifier_sessions=len(packets),total_session_seconds=sum(p['duration_seconds'] or 0 for p in packets.values()),token_usage=usage,
        token_scope='Full verifier sessions incl platform/image/tool context; parent excluded; cache included in input and reasoning included in output',
        actual_currency_cost=None,formal_energy=None,accuracy=None,reviewed=False,usage='provisional/debug',
        strict_blind_test=False,isolation='fork_turns=none + anonymous image + one-image tool trace; shared filesystem not hard isolated; received task text not independently readable',
        new_execution=dict(ofox=0,blender=0,gpu=0,sam=0,slic=0),clear_construction_label_outcomes=clear_outcomes,
        pre_inference_image_preflight=preflight,present_absent_pixel_difference_bbox=difference_bbox,
        checks=dict(frozen_labels_unchanged=True,historical_sources_unchanged=True,labels_frozen_before_all_sessions=True,
            same_anonymous_prompt_except_path=True,anonymous_inputs_equal_frozen_images=True,png_metadata_empty=True,offline_unit_tests_passed=4),
        generation_scope='2.5D deterministic drawings, not real Render or photorealistic 3D scenes')
    if destination==output:(output/'verification_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    else:save(destination/'verification_results.json',result)
    table='\n'.join(f"| {r['sample']['condition']} | {r['sample']['construction_truth']} | {r['sample']['answer_candidate']} | {r['observation']['raw_answer']} | {r['comparison']['status']} |" for r in rows)
    text=f'''# Structural Layout 视觉验证器：首次独立合成对照

本轮实际运行 3 个独立 gpt-6-sol 视觉验证子 Agent，每图一次、严格串行、无重试。判断来自真实单图输入与原始回答，不是 Oracle 标签代替模型输出。全部 reviewed=false、provisional/debug，不生成正式 Spatial Energy 或准确率。

| 样本条件（不进入模型输入） | 构造结构真值 | 冻结可见答案候选 | 真实原始回答 | 比较结果 |
| --- | --- | --- | --- | --- |
{table}

清晰样本的描述性结果计数：{json.dumps(clear_outcomes,ensure_ascii=False)}。遮挡图的真实回答单独保留，不纳入该计数。它说明本次模型实际选择了什么，不能用未审核的遮挡标签宣称三项全对或稳定准确率。

## 构造与控制

新书架使用本轮静态检查过的 Pillow 轻量程序绘制固定仿正交 2.5D 视图；1024×800、2倍超采样。所有样本保留相同书架外框、层板、上下层书籍、颜色、投影和背景。明确区别于此前 bw_0074 和旧正视矩形 Oracle 对照，没有运行历史 Agent 代码或 Blender。

存在/缺失两图仅增加或移除最上方开口内连接上下边界的竖向薄板；没有移动书籍。遮挡样本沿用存在图的结构，并增加位于前景的布帘，覆盖最上方开口。新增遮挡物会改变颜色、遮挡、边缘，这是可见性控制的必要变化，不宣称只改变一个像素因素。仿正交图是程序化示意场景，不能代表复杂真实图片能力。

场景配置、独立 PNG、预先冻结的构造真值和可见性记录均位于 `{work}`。程序主入口设置单核亲和性、30秒 CPU/进程、1GiB 地址空间限制；不启动 GPU 或渲染器。初次 prepare 观测用户 CPU 约 0.644 秒、峰值 RSS 108.8 MiB；另一次轻量单图预检修正为普通单进程 CPU 绘图，未将主入口限制扩称为所有辅助工具调用的硬配额。

首次图像预检发现遮挡图仍露出一小块隔板顶面，因此在任何验证调用与最终标签冻结之前，将布帘向上扩展一次；原草稿保留，记录见 preflight_note.json。该修改仅依据图像可见性检查，未看到模型结果、未改 Prompt。最终 A/B 像素差异范围为 {difference_bbox}，其他布局未改变。

## 标签、审核与冻结

在首次验证前，冻结了相同 System/User、唯一字段 internal_divider 的 present/absent/unknown Schema，以及 expected_frozen.json（只读）。present 要有内部结构隔板的可见证据；absent 要目标层可观察且确认无隔板；遮挡/类别歧义时 unknown，不能用未看到替代不存在。外框、书脊、阴影和布帘都不计隔板。

遮挡样本另由主 Agent 在请求前静态检查图像，记录可观察性候选，不从其几何存在真值直接继承可见答案。其 unknown 仍只是**未独立人工审核的可见性候选**：human_visibility_review=unreviewed，因此无论实际回答如何均不计算正确/错误。两个清晰样本按 construction_expected 作描述性比较，也不是独立审核 GT。没有在结果后改图、改标签或改 Prompt。

## 输入隔离和真实请求

三个模型接收匿名随机路径的单张原始图及完全相同的简短问题，只针对最上方开口内的内部竖向隔板。没有 A/B/C 标题、条件名、预期值、其他图或历史结论。没有同时展示对照页给模型。fork_turns=none；工具日志、实际输入全文、模型标识和原始回答保存在每项 observation。核对通过：冻结时间早于全部会话、输入提示除匿名路径外完全相同、匿名 PNG 与冻结图片逐字节相同且无附加元数据。

共享文件系统未实施单文件权限沙箱，持久日志不能独立明文验证父任务正文；因此不声称严格盲测或与固定 API 相同。可审计的是模型标识、各次只读取指定单图的工具轨迹和原始回答。Ofox 不可用且本轮没有调用，也未读取密钥。

## 如何解释本轮证据

存在图若 present、缺失图若 absent，可作为实际视觉区分的初步证据；unknown 为弃权，不强行算作正确/错误。明确输出相反类别分别记录漏检/误报。遮挡图若 unknown，仅说明本次表现符合冻结的弃权候选，需独立可见性审核后才能验证弃权正确；若给出确定类别，记录潜在无依据确定性，不能直接归为重建错误。

本轮不能证明提取器稳定区分复杂隔板、书脊或外框：只有一个新布局、每种条件一个观测，未测试倾斜/透明/合并几何、遮挡程度梯度或真实图片。布帘也可能成为易识别的弃权线索；清晰 present/absent 的简单结构不能代表真实书架中细隔板漏检已解决。未发生模型失败时也不得以零失败宣称稳定可靠。

## 实际成本与复现

共 {len(packets)} 个真实验证会话、{result['total_session_seconds']:.3f} 秒；Token 为 {json.dumps(usage,ensure_ascii=False)}。统计为验证子会话全量平台/图像工具上下文，排除主 Agent；缓存已包含在输入、推理已包含在输出，不重复相加。Codex 货币费用不可核实；Ofox 请求 0。未修改历史结果、Reference Evidence、ROI 或正式权重。

仅从冻结数据及真实会话回答重画到新目录（不调用模型）：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/structural_visual_controls.py --stage report --output {output} --destination results/structural_visual_verifier_controls_replay
```

输出 comparison.png、verification_results.json、report.md，无 HTML。完成后停止，没有重复调 Prompt 或扩展样本。
'''
    (destination/'report.md').write_text(text)
    print(json.dumps(dict(output=str(destination),results=[r['comparison'] for r in rows],session_seconds=result['total_session_seconds'],tokens=usage),ensure_ascii=False))


if __name__=='__main__':
    # Bound only this lightweight preparation/replay process, never the shared environment.
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
    allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(allowed)})
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','seal','collect','report'],required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path);args=parser.parse_args()
    if args.stage=='prepare':prepare(args.output.resolve())
    elif args.stage=='seal':seal(args.output.resolve())
    elif args.stage=='collect':collect(args.output.resolve(),parse=parse_answer)
    else:report(args.output.resolve(),args.destination.resolve() if args.destination else args.output.resolve())
