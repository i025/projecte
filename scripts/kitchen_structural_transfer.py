"""Frozen Reference claims, two independent real-image observations, no scoring."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read,save,font,collect
from scripts.region_real_render import fit_render

IDS=('K1','K2','K3','K4')
SYSTEM='你是图像空间结构验证器。只根据当前单侧图片逐条判断可见柜体外部结构。present 表示充分可见证据支持；absent 表示相关局部足够清晰可见且可确认不满足；unknown 表示该局部被遮挡、裁切、类别歧义或对应无法确认。不要因其他局部不可见而弃权整个区域。区分前面板接合边界、柜体外框、装饰缝、拉手和内容边缘；不推测面板后方的内部隔板。只输出简洁 JSON。'
FORMAT='''左侧为完整图，橙框为目标区域；右侧为相同固定坐标的放大图。完整图仅提供上下文；不把标记线、裁切或留边当作柜体结构。颜色仅用于定位，不能仅凭颜色不同推断结构。逐条回答，不要求完整物体列表。
输出一个 JSON 对象，唯一字段 evidence，为四项数组。每项仅含 id、answer（present/absent/unknown）、visibility（clear/partial/unobservable/ambiguous）、visual_basis（不超过80字的直接可见依据或不确定原因）、boundary_type（facade_joint/group_transition/uncertain）、segments（0–4条粗边界线段）。
坐标相对于右侧目标裁剪图归一化到0–1000，左上为原点；线段为[x1,y1,x2,y2]。只画当前图中独立观察到的可见边界，不补画未见结构；没有可靠线段可用空数组。partial 不自动否定可见的正证据；不能确认不存在时应回答 unknown。仅输出 JSON，不输出推理过程。'''


def parse_answers(raw):
    def unique(pairs):
        x={}
        for k,v in pairs:
            if k in x:raise ValueError('Duplicate key: '+k)
            x[k]=v
        return x
    try:
        x=json.loads(raw,object_pairs_hook=unique)
        if not isinstance(x,dict) or set(x)!={'evidence'} or not isinstance(x['evidence'],list):raise ValueError('Expected evidence array')
        fields={}
        for item in x['evidence']:
            if not isinstance(item,dict) or item.get('id') not in IDS or item['id'] in fields:raise ValueError('Invalid or duplicate evidence ID')
            error=None
            try:
                if set(item)!={'id','answer','visibility','visual_basis','boundary_type','segments'}:raise ValueError('Unexpected/missing fields')
                if item['answer'] not in ('present','absent','unknown') or item['visibility'] not in ('clear','partial','unobservable','ambiguous'):raise ValueError('Invalid enum')
                if item['boundary_type'] not in ('facade_joint','group_transition','uncertain'):raise ValueError('Invalid boundary type')
                if not isinstance(item['visual_basis'],str) or not item['visual_basis'].strip():raise ValueError('Missing visible basis')
                segs=item['segments']
                if not isinstance(segs,list) or len(segs)>4:raise ValueError('Invalid segment count')
                for s in segs:
                    if not isinstance(s,list) or len(s)!=4 or not all(type(v) in (int,float) and np.isfinite(v) and 0<=v<=1000 for v in s) or s[:2]==s[2:]:raise ValueError('Invalid segment coordinates')
            except (ValueError,TypeError) as e:error=str(e)
            fields[item['id']]=dict(status='valid' if error is None else 'unavailable',data=item,error=error)
        for key in IDS:
            if key not in fields:fields[key]=dict(status='unavailable',data=None,error='Missing item')
        return dict(status='valid' if all(f['status']=='valid' for f in fields.values()) else 'partial',fields=fields)
    except (ValueError,TypeError) as e:return dict(status='unavailable',fields={},error=str(e))


def comparable_answer(field):
    if field.get('status')!='valid':return None,'Invalid/missing item'
    x=field['data']
    if x['answer']=='unknown' or x['visibility'] in ('unobservable','ambiguous'):return 'unknown','Local evidence insufficient'
    if x['answer']=='absent' and x['visibility']!='clear':return 'unknown','Absence needs clear local visibility'
    return x['answer'],'Positive partial evidence is usable' if x['visibility']=='partial' else 'Clear local evidence'


def compare(reference,render,claims):
    rows=[]
    for claim in claims:
        key=claim['id'];a=reference.get('fields',{}).get(key,{});b=render.get('fields',{}).get(key,{})
        va,ra=comparable_answer(a);vb,rb=comparable_answer(b)
        status='unavailable' if va is None or vb is None else 'unknown' if 'unknown' in (va,vb) else 'structure_consistent' if va==vb else 'candidate_structural_layout_mismatch'
        rows.append(dict(id=key,reference=a,render=b,effective_reference_answer=va,effective_render_answer=vb,status=status,
            reference_comparability_reason=ra,render_comparability_reason=rb,
            reference_seed_support='supported_candidate' if va=='present' else 'not_confirmed',
            geometry_support='N/A: no object-level Scene Graph for this Run',reviewed=False,scorable=False,formal_energy=None))
    return rows


def prepare(frozen_path,output):
    frozen=read(frozen_path);assert not frozen_path.stat().st_mode & 0o222
    assert [c['id'] for c in frozen['claims']]==list(IDS)
    work=frozen_path.parent;output.mkdir(parents=True,exist_ok=False);(work/'images').mkdir();(work/'collector').mkdir()
    pair=read(ROOT/'results/region_first_real_render_bw0073/pair_audit.json');plan=read(frozen['region_plan'])
    region=next(r for r in plan['regions'] if r['id']==frozen['region_id'])
    assert region['name']=='右侧高柜区'
    ref=Image.open(frozen['reference']).convert('RGB');roi=Image.open(frozen['roi']).convert('L')
    assert list(roi.getbbox())==frozen['bbox'] and ref.size==roi.size
    rgb,valid,transform=fit_render(Image.open(pair['render_rgb']),ref.size);assert transform==pair['comparison_transform']
    protocol=dict(work=str(work),output=str(output),reference_frozen=str(frozen_path),frozen_before_current_render_read=True,
        reference_rgb=frozen['reference'],render_rgb=pair['render_rgb'],roi=frozen['roi'],bbox=frozen['bbox'],image_size=frozen['image_size'],
        region=region,pair_audit=pair,transform=transform,system=SYSTEM,format=FORMAT,
        questions=[dict(id=c['id'],question=c['question']) for c in frozen['claims']],
        model='gpt-6-sol',backend='Codex Subagent',maximum_verifiers=2,serial=True,automatic_retries=False,reviewed=False)
    question_text='\n'.join(c['id']+'：'+c['question'] for c in frozen['claims'])
    requests={};staged={};bbox=frozen['bbox']
    for side,image in [('reference',ref),('render',Image.fromarray(rgb))]:
        mark=image.copy();ImageDraw.Draw(mark).rectangle((bbox[0],bbox[1],bbox[2]-1,bbox[3]-1),outline='#ff931e',width=3)
        context=mark.resize((1024,558),Image.Resampling.LANCZOS)
        crop=image.crop(tuple(bbox));crop=crop.resize((crop.width*2,crop.height*2),Image.Resampling.LANCZOS)
        sheet=Image.new('RGB',(1044+crop.width,max(558,crop.height)),'#e1e4e8');sheet.paste(context,(0,0));sheet.paste(crop,(1044,0))
        folder=Path('/tmp')/uuid.uuid4().hex;folder.mkdir(mode=0o700);path=folder/(uuid.uuid4().hex+'.png');local=work/'images'/path.name
        sheet.save(local);shutil.copyfile(local,path);path.chmod(0o444);local.chmod(0o444);task='v_'+uuid.uuid4().hex[:12]
        message='只观察下面指定的一张PNG。仅允许一次view_image读取该图，设置detail="original"，并用image(result.image_url,"original")转交图片；不读取其他文件，不联网，不调用其他模型，不写文件，不请求澄清。最终只输出规定JSON。\n\n图像：'+str(path)+'\n\nSystem：\n'+SYSTEM+'\n\nUser：\n'+question_text+'\n\n'+FORMAT
        requests[side]=dict(task_name=task,model='gpt-6-sol',fork_turns='none',message=message);staged[side]=dict(path=str(path),source=str(local),agent_task=task)
    metadata_scan=dict(status='unavailable',object_level_scene_graph=None,reason='No existing object-level export for the paired bw_0073 Run; no new Blender extraction authorized or executed',
        searched=['Project e results/runs scene_graph/scene_summary/scene_metadata/object_metadata JSON paths','Paired Run artifacts/workspace/exports JSON files'],
        available_export_files=['camera_parameters.json','final.png','preview.png'],
        excluded_wrong_scene_graph='blender_scene_graph_audit_bw0074/scene_graph.json belongs to a different scene and Run',
        excluded_non_graph='vlm_direct_grounding_bw0073/geometry_audit.json is ROI overlap, not object geometry',
        camera_metadata_only=pair['camera_export'],supports_door_drawer_geometry=False,reviewed=False)
    tracked={frozen_path,Path(frozen['reference']),Path(frozen['roi']),Path(pair['render_rgb']),Path(pair['camera_export_source']),Path(frozen['region_plan'])}
    for directory in ('vlm_direct_grounding_bw0073','region_first_real_render_bw0073'):
        tracked.update(p for p in (ROOT/'results'/directory).rglob('*') if p.is_file())
    save(work/'source_state.json',{str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in tracked})
    save(work/'frozen_plan.json',protocol);(work/'frozen_plan.json').chmod(0o444)
    save(work/'frozen_agent_inputs.json',requests);(work/'frozen_agent_inputs.json').chmod(0o444)
    save(work/'staged_inputs.json',staged);save(work/'metadata_availability.json',metadata_scan)
    save(work/'collector/verification_results.json',dict(status='prepared',protocol=protocol,reviewed=False))
    print(json.dumps(dict(work=str(work),requests=requests),ensure_ascii=False))


def figure(output,p,observations,rows):
    ref=Image.open(p['reference_rgb']).convert('RGB');rgb,_,_=fit_render(Image.open(p['render_rgb']),ref.size)
    canvas=Image.new('RGB',(2460,1860),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((24,15),'bw_0073 / R4 | Kitchen facade structure | independent single-image observations',font=font(31),fill='#19354d')
    d.text((24,62),'Boundary lines are raw independent predictions, not corrected masks or hidden internal partitions.',font=font(26),fill='#33495d')
    colors=['#f5bc35','#37cce4','#e38de0','#86d26f'];width=710;height=1225
    for side,x,image in [('reference',24,ref),('render',780,Image.fromarray(rgb))]:
        crop=image.crop(tuple(p['bbox'])).resize((width,height),Image.Resampling.LANCZOS);cd=ImageDraw.Draw(crop)
        for i,key in enumerate(IDS):
            field=observations[side]['parsed'].get('fields',{}).get(key,{})
            if field.get('status')!='valid':continue
            for segment in field['data']['segments']:
                pts=(segment[0]*width/1000,segment[1]*height/1000,segment[2]*width/1000,segment[3]*height/1000)
                cd.line(pts,fill=colors[i],width=4)
                cd.text((pts[0]+4,pts[1]+4),key,font=font(21),fill=colors[i],stroke_width=1,stroke_fill='#142a3b')
        d.text((x,112),side.title()+' / fixed Reference R4',font=font(26),fill='#19354d');canvas.paste(crop,(x,160))
    x=1540
    labels=['K1: side-by-side tall facade panels','K2: short upper tier over tall fronts','K3: vertically stacked drawer-like fronts','K4: tall cabinet beside lower worktop']
    for i,(label,row) in enumerate(zip(labels,rows)):
        y=160+i*222
        d.text((x,y),label,font=font(23),fill=colors[i])
        d.text((x,y+44),'Reference: '+str(row['effective_reference_answer']),font=font(26),fill='#19354d')
        d.text((x,y+86),'Render: '+str(row['effective_render_answer']),font=font(26),fill='#19354d')
        d.text((x,y+132),row['status'],font=font(23),fill='#6b4d2e')
    notes=['No paired object-level Scene Graph found.', 'Door/drawer geometry corroboration: N/A.',
           'Camera export only: z=1.5m, lens=22.5mm.', 'Reference camera unknown; no alignment.',
           'Facade seams != confirmed hidden dividers.', 'Color or handles alone do not prove structure.',
           'All reviewed=false / provisional/debug.']
    for i,line in enumerate(notes):d.text((x,1090+i*42),line,font=font(23),fill='#33495d')
    lines=['Transfer concerns exterior facade divisions and coarse layout; no shelf-specific divider rule or per-object instance matching.',
        'Per-proposition partial positive evidence can survive; uncertain local visibility is withheld independently.',
        'Different camera/projection and ROI truncation can change visible modules. Candidate differences are not confirmed 3D errors.',
        'The Reference seed, real VLM responses, deterministic comparison and unavailable geometry are stored separately.',
        'Exactly two gpt-6-sol subagent sessions; no Ofox / Blender / GPU / SAM / SLIC; no formal Spatial score.']
    for i,line in enumerate(lines):d.text((24,1455+i*57),line,font=font(26),fill='#33495d')
    canvas.save(output/'comparison.png')


def report(work,destination):
    p=read(work/'frozen_plan.json');frozen_bytes=Path(p['reference_frozen']).read_bytes();frozen=json.loads(frozen_bytes)
    packets=read(work/'raw_observations.json');requests=read(work/'frozen_agent_inputs.json');staged=read(work/'staged_inputs.json')
    assert frozen['freeze']['unix']<min(a['started_at'] for a in packets.values())
    assert requests['reference']['message'].replace(staged['reference']['path'],'{IMAGE}')==requests['render']['message'].replace(staged['render']['path'],'{IMAGE}')
    for side,a in packets.items():
        if a['read_audit_passed']:assert a['parsed']==parse_answers(a['raw_answer'])
        assert Path(staged[side]['path']).read_bytes()==Path(staged[side]['source']).read_bytes()
    rows=compare(packets['reference']['parsed'],packets['render']['parsed'],frozen['claims'])
    source_state=read(work/'source_state.json');assert all(Path(path).stat().st_size==s['size'] and Path(path).stat().st_mtime_ns==s['mtime_ns'] for path,s in source_state.items())
    usage={}
    for a in packets.values():
        for key,value in (a['usage'] or {}).items():usage[key]=usage.get(key,0)+value
    metadata=read(work/'metadata_availability.json')
    result=dict(scene='bw_0073',region_id='R4',reviewed=False,usage='provisional/debug',scorable=False,formal_energy=None,
        reference_seed=frozen,protocol=p,observations=packets,comparison=rows,metadata_assistance=metadata,
        execution=dict(backend='Codex Subagent',model='gpt-6-sol',sessions=2,serial=True,automatic_retries=False,
            total_session_seconds=sum(a['duration_seconds'] or 0 for a in packets.values()),token_usage=usage,actual_currency_cost=None,
            token_scope='Whole verifier sessions incl platform/image/tool context; parent excluded; cached input and reasoning are already included',
            ofox=0,blender=0,gpu=0,sam=0,slic=0),
        isolation=dict(fork_turns='none',single_image_tool_audit=all(a['read_audit_passed'] for a in packets.values()),
            no_expected_values_or_other_side_supplied=True,strict_blind_test=False,shared_filesystem_not_hard_isolated=True,
            received_task_text_independently_readable=False),
        checks=dict(frozen_reference_unchanged=True,source_files_unchanged=True,anonymous_inputs_equal_staged_images=True,prompt_symmetric=True))
    source_output=Path(p['output'])
    if destination!=source_output:destination.mkdir(parents=True,exist_ok=False)
    for name in ('comparison.png','structural_evidence.json','report.md'):
        if (destination/name).exists():raise ValueError('Completed artifacts cannot be overwritten')
    figure(destination,p,packets,rows)
    assert Path(p['reference_frozen']).read_bytes()==frozen_bytes
    save(destination/'structural_evidence.json',result);write_report(destination,result)
    print(json.dumps(dict(output=str(destination),comparison=rows,execution=result['execution']),ensure_ascii=False))


def write_report(output,result):
    rows=result['comparison'];p=result['protocol'];table='\n'.join(f"| {r['id']} | {r['effective_reference_answer']} | {r['effective_render_answer']} | {r['status']} |" for r in rows)
    def data(r,side):return r[side].get('data') or {}
    bases='\n'.join(f"| {r['id']} | {data(r,'reference').get('visibility','unavailable')} / {data(r,'reference').get('visual_basis','')} | {data(r,'render').get('visibility','unavailable')} / {data(r,'render').get('visual_basis','')} |" for r in rows)
    questions='\n'.join(c['id']+'：'+c['claim'] for c in result['reference_seed']['claims'])
    statuses={status:sum(r['status']==status for r in rows) for status in ('structure_consistent','candidate_structural_layout_mismatch','unknown','unavailable')}
    k3=next(r for r in rows if r['id']=='K3')
    finding=('K3 实际获得 present → absent：Reference 的低柜被识别为上下叠置抽屉样前面板，Render 被识别为并排竖向门板。Reference 虽右端裁切，但两条水平接合线和上下排列仍可观察；Render 对该局部给出 clear，故保留外立面布局差异候选。这是实际单图回答产生的结果，不只是接口的潜在检出能力。'
             if k3['status']=='candidate_structural_layout_mismatch' else 'K3 本轮未得到通过局部可比较性条件的明确差异，按实际状态保留，不据预期补造。')
    text=f'''# Structural Spatial Evidence 跨场景：bw_0073/R4

全部 reviewed=false、provisional/debug。本轮真实执行 2 个独立 gpt-6-sol 单侧图像会话，没有新 Ofox/Blender/GPU/SAM/SLIC 调用或正式 Spatial 分数。

实际状态计数：{json.dumps(statuses,ensure_ascii=False)}。

{finding}

K1/K2/K4 的一致只说明粗门板分界、上下层和高低柜关系在本次回答中均可见，不代表面板数量、比例或完整 R4 重建质量一致。当前未出现模型 unknown 或解析 unavailable；仍然保留该处理机制，不人为制造弃权案例。

## Reference-only 冻结与正确配对

实际 Region Plan 确认为 R4「右侧高柜区」，内容为浅木色柜体、深色高柜及下方抽屉柜。复用 `vlm_direct_grounding_bw0073/region_plan.json` 与已存 Direct Box 测量 ROI，范围 {p['bbox']}、图像 1536×837。未修改 Region/ROI，也未以 Render 重定位。

先仅查看 Reference，冻结四条外立面结构候选到只读 `{p['reference_frozen']}`，之后才在本轮查看 Render。候选由主 Agent 静态观察准备，不是 GT 或自动提取成果：

{questions}

它们只描述可见门板/抽屉样前面板接合及高低柜组织，不推断隐藏隔板、实际开合机构或完整柜体实例图。原对话已包含历史 Render 相关知识，因此参考准备也不能称为严格盲测。冻结后未依据 Render 改写命题。

配对 Run：{p['pair_audit']['run_id']}。Reference 原始来源及 Render 导出对应由既有 pair_audit 支持；完整路径、相机文件和映射依据写入 structural_evidence.json.protocol。历史相机 z=1.5m、lens=22.5mm，正式协议要求 z=2m；Reference 相机未知，PNG/最终 blend 精确同步也未重新证明。全部仅用于离线诊断。

## 实际独立验证结果

使用相同简短三态协议与四个中立问题，模型只接收自己一侧的完整图（框示固定区域）及相同坐标放大图；不提供种子“应为 present”、另一侧答案或差异假设。输出逐项状态、局部可见性、短可见依据与粗线段，不输出长篇推理。

| 命题 | Reference | Render | 确定性比较 |
| --- | --- | --- | --- |
{table}

| 命题 | Reference 原始可见性 / 依据 | Render 原始可见性 / 依据 |
| --- | --- | --- |
{bases}

present/partial 的局部正证据可以比较；absent 需要相关局部 clear，否则降为比较 Unknown（原始回答不改写）。任一条 unknown/unavailable 不阻塞其他条目。两侧明确相同为 structure_consistent，不同为 candidate_structural_layout_mismatch。比较只是结构命题是否一致的未审核诊断，不等于正确性或 3D 错误 GT。若 Reference 验证未支持种子，则单独保留 not_confirmed，不让人工式候选自动变成真值。

PNG 中的边界来自两侧独立响应的原始坐标，未修补、配准或从参考复制；它们是外立面接合/组间交接线，不是精确 Mask。回答 absent 时没有可靠边界允许空线段，不能虚构缺失位置。

## Scene Graph 辅助证据的实际可用性

在 Project e results/runs 的已有 Scene Graph/scene summary/object metadata JSON，以及这个正确 Run 的 artifacts/workspace/exports 中检查后，没有找到 bw_0073 对象级图结构或柜门/抽屉几何导出。可用的是 camera_parameters.json；`vlm_direct_grounding_bw0073/geometry_audit.json` 只是 ROI 重叠审计。bw_0074 的 Scene Graph 属于另一场景，未借用。没有打开 blend 或从历史 Agent Python 推导“实际几何”。

因此门板/抽屉几何佐证 **N/A**，不是查询发现几何缺失。相机元数据仅支持坐标和协议限制说明。即使未来有对象名称，也必须区分 Agent 名称声明、实际板件几何、可见门缝和语义柜体；外观接缝不能直接升级为门后内部隔板 GT。

## 迁移性、失败与限制

这轮从书架“内部隔板”迁移到厨房“外立面接合与高低柜关系”，复用的是 Reference 先冻结、独立单图回答、局部可观察性和三态比较原则，没有使用书架厚度、世界 Z 层数或 AABB 隔板阈值，也没有逐柜体实例匹配。

structure_consistent 表示对应粗属性的回答一致，可能遗漏面板比例、数量及细节；candidate_structural_layout_mismatch 表示已得到真实回答差异，仍可能受柜体对应、视角、遮挡或对装饰缝/拉手的识别错误影响。unknown/unavailable 是本轮没有充分证据的条目，不伪造成一致或缺失。

单场景/单次每侧不能证明跨场景稳定检出率；没有独立人工结构 GT，没有新正负对照，也没有对象几何佐证。Reference 右边界有截断，Render 与 Reference 视角不同，固定 ROI 含背景/留边的比例不同；因此不比较线坐标的直接距离，不将门板数量差直接解释为三维拓扑错误。要进入正式 Spatial，需独立审核结构身份、局部对应和可见性，并在同相机受控柜体扰动中校验检出与弃权行为。

保留的失败/未验证项是：对象级几何缓存缺失；“至少两块门板”的粗命题对门板数和比例变化不敏感；抽屉样外观不证明真实抽屉机构；当前没有同相机因果对照来排除历史视角影响。没有把这些限制隐藏在三个一致结果之后。

## 审计与复现

匿名路径、fork_turns=none 和工具轨迹限制了额外信息读取；共享文件系统不是硬隔离，持久日志不能独立重读实际父任务正文，故不宣称严格盲测或固定 API 等价。原始回答、完整实际输入、模型标识和子会话用量都保留。冻结时间早于验证；两份提示除匿名路径外一致，输入图片逐字节相同于准备图；源文件大小/mtime 未变。

实际会话数 2，合计 {result['execution']['total_session_seconds']:.3f} 秒；Token {json.dumps(result['execution']['token_usage'],ensure_ascii=False)}。统计包含验证子会话平台/图像工具上下文，排除主 Agent；缓存和推理分别已包含于输入/输出，货币成本未知。没有付费 Ofox 请求。

4 项纯 CPU 单元测试在验证前通过：局部 partial 正证据保留而 partial 缺失弃权、单条 Unknown 不阻塞其他差异、缺失字段不补造、非法坐标仅使受影响项不可用。它们验证程序行为，不等于真实视觉准确率。

只重放已有回答并画到新目录，不调用模型：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/kitchen_structural_transfer.py --stage report --work {p['work']} --output results/kitchen_structural_transfer_bw0073_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_kitchen_structural_transfer.py'
```

输出只包含 comparison.png、structural_evidence.json、report.md；模型输入、冻结候选与会话记录在 runs 目录，无 HTML。完成后停止，不调整提示或扩展图片。
'''
    (output/'report.md').write_text(text)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','collect','report'],required=True)
    parser.add_argument('--reference-frozen',type=Path);parser.add_argument('--work',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.stage=='prepare':prepare(args.reference_frozen.resolve(),args.output.resolve())
    elif args.stage=='collect':collect(args.work.resolve()/'collector',parse=parse_answers)
    else:report(args.work.resolve(),args.output.resolve())
