"""Two independent, recorded Codex observations of a frozen real-image Group."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.group_statistical_controls import read, save, answer_value, compare_values
from scripts.region_real_render import fit_render
from scripts.region_grounding_experiment import edges

QUESTIONS = {
    'present': '标记区域内是否存在可辨认的黑胶唱片封套集合？',
    'multiple_sections': '可辨认的唱片封套是否分布在至少两个清晰可辨的独立柜格中？',
    'upright_display': '可辨认的唱片封套是否主要呈竖直站立陈列（允许倾斜），而非水平平放叠放？',
}
SYSTEM = '''你是图像证据验证器。只根据当前图片及标记区域判断可见内容，不猜测不可见内容。不要把装订书籍、文件夹、柜体隔板或音响设备当作唱片封套，也不要因为问题提到唱片就假定它存在。类别、柜格边界、主要排列方式或可见性不明确时返回unknown。只输出JSON，不解释。
yes：有充分可见证据确认命题成立。
no：相关内容足够清晰，能够确认命题不成立。
unknown：模糊、遮挡、类别歧义或证据不足，无法可靠判断。不要把没看清直接当作不存在。'''
USER = '''图中橙色边界标记目标评价区域；右侧是该区域同坐标的放大图。只评价橙线范围，完整图仅提供上下文。不评价区域外的其他集合。
集合范围：可辨认的黑胶LP唱片封套陈列；不包含装订书籍、音响设备或柜体本身。不要求逐张识别、计数或匹配。

Q1：标记区域内是否存在可辨认的黑胶唱片封套集合？
Q2：可辨认的唱片封套是否分布在至少两个清晰可辨的独立柜格中？
Q3：可辨认的唱片封套是否主要呈竖直站立陈列（允许倾斜），而非水平平放叠放？

柜格必须有可见隔板或柜框分隔；同一柜格内的多个小簇不能算作多个柜格。Q3只判断可辨认封套的主要摆放方向；多方向接近、主次不清时回答unknown。若无法确认唱片封套存在，Q2和Q3回答unknown。不要凭区域内未识别就推断全图完全缺失。
只输出一个JSON对象，严格包含present、multiple_sections、upright_display三个字段。每个字段只能为单个字符串yes、no或unknown。不要输出解释、推理或其他字段。'''
ENERGY = dict(present='semantic', multiple_sections='spatial', upright_display='statistical')
DISPLAY_QUESTIONS = dict(
    present='Q1: Is a recognizable collection of vinyl LP sleeves present inside the marked ROI?',
    multiple_sections='Q2: Do recognizable LP sleeves occupy at least two clearly separated shelf compartments?',
    upright_display='Q3: Are recognizable LP sleeves mainly standing upright (leaning allowed), rather than stacked flat?')


def parse_answer(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('Nonfinite JSON: ' + value)
    try:
        obj = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
        if not isinstance(obj, dict):
            raise ValueError('Expected one JSON object')
    except (ValueError, TypeError) as error:
        return dict(status='unavailable', fields={}, error=str(error))
    fields = {}
    for key in QUESTIONS:
        value = obj.get(key)
        valid = isinstance(value, str) and value in ('yes', 'no', 'unknown')
        fields[key] = dict(value=value if valid else None, raw_value=value,
                           validation_status='valid' if valid else 'unavailable',
                           error=None if valid else 'Missing or invalid field')
    extra = sorted(set(obj) - set(QUESTIONS))
    valid = not extra and all(v['validation_status'] == 'valid' for v in fields.values())
    return dict(status='valid' if valid else 'partial', fields=fields, unexpected_fields=extra)


def compare(reference, rendered):
    rows = []
    presence = [answer_value(p, 'present') for p in (reference, rendered)]
    for key in QUESTIONS:
        values = [answer_value(p, key) for p in (reference, rendered)]
        independent = compare_values(*values)
        status = independent
        reason = 'Answer comparison only; neither answer is GT'
        if key != 'present' and presence != ['yes', 'yes']:
            status = 'unavailable' if None in presence or independent == 'unavailable' else 'unknown'
            reason = 'Group presence/category not confirmed on both sides; dependent evidence withheld'
        rows.append(dict(id=key, group_id='bw_0074_R3_records', region_id='R3',
            question=QUESTIONS[key], energy=ENERGY[key], reference_answer=values[0], render_answer=values[1],
            independent_comparison=independent, status=status, reason=reason,
            reviewed=False, q=0., value=None, score=None, scorable=False, usage='provisional/debug'))
    return rows


def font(size):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    work = ROOT / 'runs' / ('records_group_' + uuid.uuid4().hex)
    work.mkdir()
    plan_path = ROOT / 'results/region_first_pilot_bw0074/vlm_plan.json'
    region = next(r for r in read(plan_path)['regions'] if r['id'] == 'R3')
    reference = ROOT / 'results/vlm_direct_grounding_cross_scene/bw_0074/reference.png'
    roi = ROOT / 'results/coarse_evaluation_roi_bw0074/B2_edge_polygons/R3.png'
    with Image.open(reference) as image, Image.open(roi) as mask:
        if image.size != mask.size or not mask.getbbox():
            raise ValueError('Reference/ROI grid mismatch or empty ROI')
        size, bbox = list(image.size), list(mask.getbbox())
    protocol = dict(scene_id='bw_0074', region_id='R3', region=region,
        reference_rgb=str(reference), roi=str(roi), image_size=size, crop_bbox=bbox,
        plan_source=str(plan_path), work=str(work), backend='Codex Subagent', model='gpt-6-sol',
        system=SYSTEM, user=USER, questions=QUESTIONS,
        schema=dict(type='object', additionalProperties=False, required=list(QUESTIONS),
            properties={k: dict(type='string', enum=['yes','no','unknown']) for k in QUESTIONS}),
        group=dict(group_id='bw_0074_R3_records', region_id='R3', name='唱片封套陈列集合',
            scope='R3内可辨认黑胶LP封套的可见陈列；排除R2装订书籍、音响与隔板。',
            evidence=[dict(id=k, type=ENERGY[k], question=v, expected=None, reviewed=False,
                          source_type='assistant_reference_only_provisional') for k,v in QUESTIONS.items()],
            reference_observation='右侧柜架多层可见密集薄封套侧缘，主要竖立并有倾斜；类别与柜格判断仍需审核。',
            provenance=dict(reference_image=str(reference), region_plan=str(plan_path), render_used=False),
            exact_mask=None, member_instance_ids=None, reliability=0., reviewed=False),
        source_type='assistant_reference_only_provisional', render_viewed_before_freeze_this_run=False,
        prior_render_knowledge_disclosed=True, strict_blind_test=False,
        leakage_note='历史对话已暴露Render概况；清点所读Inventory含旧概括性书架/书本差异描述，非严格盲测。未据Render构造本轮问题。',
        maximum_verifiers=2, serial=True, automatic_retries=False, ofox_calls=0,
        camera_protocol='historical_camera', fixed_t0_compliant=False, reviewed=False, usage='provisional/debug')
    history = {str(p): dict(size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns)
        for directory in ('results/group_vlm_verification_bw0074','results/group_statistical_hard_books',
                          'results/group_abstention_calibration','results/group_level_evidence_pilot')
        for p in (ROOT/directory).rglob('*') if p.is_file()}
    save(work/'historical_state.json', history)
    save(work/'source_state.json', {str(p): dict(size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns)
                                  for p in (reference, roi, plan_path)})
    save(work/'frozen_plan.json', protocol)
    (work/'frozen_plan.json').chmod(0o444)
    save(output/'verification_results.json', dict(status='reference_frozen', protocol=protocol, reviewed=False))
    print(json.dumps(dict(output=str(output), work=str(work), reference_frozen=True)))


def input_image(rgb, mask):
    pixels = np.array(rgb).copy()
    pixels[edges(mask)] = [255, 150, 0]
    marked = Image.fromarray(pixels)
    bbox = Image.fromarray(np.uint8(mask)*255).getbbox()
    crop = marked.crop(bbox).resize(((bbox[2]-bbox[0])*2, (bbox[3]-bbox[1])*2), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (rgb.width+crop.width+72, max(rgb.height,crop.height)+76), '#f4f5f7')
    draw = ImageDraw.Draw(canvas)
    draw.text((24,8), 'Full image: orange outline = target ROI', font=font(23), fill='#202d40')
    draw.text((rgb.width+48,8), 'Same-coordinate zoom (with context)', font=font(23), fill='#202d40')
    canvas.paste(marked,(24,52)); canvas.paste(crop,(rgb.width+48,52))
    return canvas


def pair(output):
    pending = read(output/'verification_results.json'); protocol = pending['protocol']; work=Path(protocol['work'])
    if pending['status'] != 'reference_frozen' or protocol != read(work/'frozen_plan.json'):
        raise ValueError('Reference must be frozen before reading Render')
    if (work/'frozen_agent_inputs.json').exists():
        raise FileExistsError('Verifier inputs already staged; do not repeat')
    audit=read(ROOT/'results/group_level_evidence_pilot/bw_0074/pair_audit.json')
    reference=Image.open(protocol['reference_rgb']).convert('RGB')
    original=Image.open(audit['render_rgb'])
    rendered,valid,transform=fit_render(original,reference.size)
    cached=Image.open(ROOT/'results/group_level_evidence_pilot/bw_0074/render.png').convert('RGB')
    if not np.array_equal(rendered,np.asarray(cached)) or transform != audit['comparison_transform']:
        raise ValueError('Source pair differs from existing audited pair')
    mask=np.asarray(Image.open(protocol['roi']).convert('L'))>0
    (output/'images').mkdir(exist_ok=True)
    staged={}; requests={}
    wrapper='只观察下面指定的一张PNG。仅允许一次view_image读取该图，设置detail="original"，并用image(result.image_url,"original")转交图片；不读取其他文件，不联网，不调用其他模型，不写文件，不请求澄清。最终只输出规定JSON。\n\n图像：{IMAGE}\n\nSystem：\n'+SYSTEM+'\n\nUser：\n'+USER
    for side,rgb in [('reference',reference),('render',Image.fromarray(rendered))]:
        directory=Path('/tmp')/uuid.uuid4().hex; directory.mkdir(mode=0o700)
        name=uuid.uuid4().hex+'.png'; path=directory/name
        image=input_image(rgb,mask); image.save(output/'images'/name); shutil.copyfile(output/'images'/name,path)
        path.chmod(0o444); task='v_'+uuid.uuid4().hex[:12]
        staged[side]=dict(path=str(path),source=str(output/'images'/name),agent_task=task)
        requests[side]=dict(task_name=task,model='gpt-6-sol',fork_turns='none',message=wrapper.replace('{IMAGE}',str(path)))
    save(work/'staged_inputs.json',staged); save(work/'frozen_agent_inputs.json',requests)
    (work/'frozen_agent_inputs.json').chmod(0o444)
    save(work/'pair_audit.json',dict(source_audit=audit,transform=transform,render_rgb=audit['render_rgb'],
        valid_roi_pixels=int((mask&valid).sum()),roi_pixels=int(mask.sum()),
        coordinates='Reference native pixel grid; x right, y down; unchanged ROI on both sides',
        reference_frozen_before_render_read=True,roi_relocated=False,reviewed=False))
    print(json.dumps(requests,ensure_ascii=False))


def collect(output, parse=parse_answer):
    protocol=read(output/'verification_results.json')['protocol'];work=Path(protocol['work'])
    inputs=read(work/'frozen_agent_inputs.json');staged=read(work/'staged_inputs.json');packets={}
    names={'/root/'+request['task_name']:side for side,request in inputs.items()}
    for path in Path('/home/xymo/.codex/sessions').glob('*/*/*/*.jsonl'):
        with path.open() as stream:
            try:meta=json.loads(next(stream))['payload']
            except (ValueError,KeyError,StopIteration):continue
        if meta.get('agent_path') not in names:continue
        side=names[meta['agent_path']];final=[];calls=[];models=set();efforts=set();done=None;usage=None
        for line in path.read_text().splitlines():
            row=json.loads(line);p=row.get('payload',{});kind=row['type']
            if kind=='turn_context':models.add(p['model']);efforts.add(p.get('effort'))
            elif kind=='event_msg' and p.get('type')=='task_complete':done=p
            elif kind=='event_msg' and p.get('type')=='token_count' and p.get('info'):usage=p['info']['total_token_usage']
            elif kind=='response_item' and p.get('type') in ('custom_tool_call','function_call'):
                calls.append(dict(name=p['name'],input=p.get('input',p.get('arguments',''))))
            elif kind=='response_item' and p.get('type')=='message' and p.get('role')=='assistant' and p.get('phase')=='final_answer':
                final.append(''.join(c.get('text','') for c in p.get('content',[]) if isinstance(c,dict)))
        raw=final[0] if len(final)==1 else None
        safe=(len(calls)==1 and calls[0]['name']=='exec' and calls[0]['input'].count('tools.view_image(')==1
              and staged[side]['path'] in calls[0]['input'] and not any(term in calls[0]['input']
                  for term in ('exec_command','read_text','requests','fetch','open(')))
        parsed=parse(raw) if safe and models=={'gpt-6-sol'} else dict(status='unavailable',fields={})
        if side in packets:raise ValueError('Duplicate session; no retry allowed')
        packets[side]=dict(raw_answer=raw,parsed=parsed,actual_input=inputs[side],model_observed=sorted(models),
            effort_observed=sorted(efforts),read_audit_passed=bool(safe),tool_calls=calls,
            session_file=str(path.resolve()),agent_path=meta['agent_path'],usage=usage,
            duration_seconds=done['duration_ms']/1000 if done else None,
            started_at=done['started_at'] if done else None,completed_at=done['completed_at'] if done else None,
            received_task_text_independently_readable=False,context_inheritance='none',reviewed=False)
    if set(packets)!=set(inputs):raise ValueError('Missing session; do not fabricate response')
    if any(packets[a]['completed_at']>packets[b]['started_at']
           for a,b in zip(list(inputs)[:-1],list(inputs)[1:])):raise ValueError('Not serial')
    save(work/'raw_observations.json',packets)
    print(json.dumps({side:p['raw_answer'] for side,p in packets.items()},ensure_ascii=False))


def draw(output,protocol,packets,rows):
    staged=read(Path(protocol['work'])/'staged_inputs.json')
    images=[Image.open(staged[side]['source']).convert('RGB') for side in ('reference','render')]
    width=images[0].width; y=72
    canvas=Image.new('RGB',(width,2*images[0].height+510),'#f4f5f7');d=ImageDraw.Draw(canvas)
    d.text((24,12),'bw_0074 / R3 vinyl LP sleeves - Codex Subagent gpt-6-sol',font=font(29),fill='#172d48')
    for side,im in zip(('Reference','Render'),images):
        d.text((24,y),side+'  | Frozen Reference ROI; human review pending',font=font(25),fill='#172d48')
        canvas.paste(im,(0,y+40));y+=im.height+54
    d.text((24,y),'Actual model answers and deterministic comparisons (no formal Energy)',font=font(26),fill='#172d48');y+=42
    for row in rows:
        d.text((24,y),DISPLAY_QUESTIONS[row['id']],font=font(22),fill='#172d48');y+=34
        d.text((24,y),f"Reference: {row['reference_answer']}    Render: {row['render_answer']}    Result: {row['status']}",font=font(23),fill='#64471b');y+=48
    d.text((24,y),'All reviewed=false; provisional/debug. Agreement is not reconstruction quality or ground truth.',font=font(22),fill='#6d3d2b')
    canvas.save(output/'comparison.png')


def report(output):
    pending=read(output/'verification_results.json');protocol=pending['protocol'];work=Path(protocol['work'])
    if pending['status']!='reference_frozen' or protocol!=read(work/'frozen_plan.json'):
        raise ValueError('Completed results cannot be overwritten; frozen reference changed')
    packets=read(work/'raw_observations.json');rows=compare(packets['reference']['parsed'],packets['render']['parsed'])
    for packet in packets.values():
        if packet['read_audit_passed'] and parse_answer(packet['raw_answer'])!=packet['parsed']:
            raise ValueError('Raw response changed')
    usage={}
    for packet in packets.values():
        for key,value in (packet['usage'] or {}).items():usage[key]=usage.get(key,0)+value
    final=dict(status='completed',protocol=protocol,answers=packets,comparison=rows,pair_audit=read(work/'pair_audit.json'),
        static_review_candidates=read(work/'static_review_candidates.json'),
        offline_checks=read(work/'offline_checks.json'),
        backend='Codex Subagent',model='gpt-6-sol',verification_sessions=2,ofox_calls=0,
        verifier_session_seconds=sum(p['duration_seconds'] or 0 for p in packets.values()),verifier_usage=usage,
        usage_scope='Complete verifier sessions including platform/tool context; parent excluded. Cache is included in input.',
        actual_currency_cost=None,formal_energy=dict(semantic=None,spatial=None,statistical=None),
        reviewed=False,scorable=False,usage='provisional/debug',strict_blind_test_established=False)
    (output/'verification_results.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,allow_nan=False))
    draw(output,protocol,packets,rows)
    table='\n'.join(f"| {QUESTIONS[r['id']]} | {r['reference_answer']} | {r['render_answer']} | {r['status']} |" for r in rows)
    text=f'''# 真实唱片 Group Verification Pilot

仅 bw_0074/R3 唱片与音响区中的唱片封套集合。后端 Codex Subagent/gpt-6-sol，2次独立、串行、单侧验证，无Ofox调用、无重试。所有证据 reviewed=false、provisional/debug，正式Semantic/Spatial/Statistical均N/A。

## 参考侧冻结与图像来源

先读原Reference及历史Region Plan、既有B2 R3 ROI，再冻结Group语义范围、三个问题、Schema；然后才读取本轮Render。只读冻结文件 `{work.relative_to(ROOT)}/frozen_plan.json`。Group是可辨认的黑胶LP封套陈列，排除装订书籍、设备和隔板；没有逐张ID、精确Group Mask、数目或密度GT。候选由协调Agent参考侧静态观察准备，并非自动VLM提取或独立人工标注。问题本轮新增，不追溯声称来自旧冻结书籍证据。

Reference：{protocol['reference_rgb']}。原始JPEG关联见 `results/region_first_pilot_bw0074/input.json`。Region Plan：{protocol['plan_source']}。固定ROI：{protocol['roi']}。同一ROI成员像素用于两侧；放大框仅由其外接矩形导出，未按Render调整。

Render：{final['pair_audit']['render_rgb']}；实际来源Run为 official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8。既有pair_audit记录与重算像素一致。图像统一只作等比例全帧缩放、居中留边：{json.dumps(final['pair_audit']['transform'],ensure_ascii=False)}。这不是相机配准。历史任务包含图片和额外场景文字，不是Strict RGB-only；无证据满足固定T0，Reference真实相机未知，Render独立相机参数未知，不执行Blender求取。历史Render是否与最终blend完全同步也未重新验证。

## 冻结定义与实际结果

yes需要充分可见证据；no需要相关区域足够清晰以确认命题不成立；模糊、遮挡、类别/柜格歧义时unknown。柜格必须有可见隔板/柜框，内部小簇不另算柜格；竖直陈列允许倾斜，不判断逐张角度，主次不清弃权。若唱片存在性未确认，后两个问题不得推定有意义的分布错误。完整相同Prompt和Schema保存在JSON.protocol，两个子Agent只看各自一张匿名PNG，不看另一侧、预期标签或历史答案。

| 问题 | Reference真实回答 | Render真实回答 | 程序比较 |
|---|---|---|---|
{table}

satisfied仅表示两侧回答一致；candidate_violated仅是待审核差异；unknown/unavailable不伪造为零误差。保留独立字段比较与存在性依赖处理，原始答案不改写，不将语义缺失重复计入位置/排列。没有总分，也没有使用模型置信度。

## 能力、失败模式与迁移边界

实际两侧均为yes/yes/yes，三个比较均satisfied，candidate_violated、unknown和unavailable均为0。没有发现本轮三个命题所覆盖的差异；这不是三项独立人工验证成功，也不是三项Energy为零。模型没有弃权，只能记录这一行为，不能据此证明类别无歧义。

协调Agent在参考冻结后进行的静态复核候选（不是独立人工审核）：Reference封套侧缘的颜色、宽窄和倾斜更不规则，Render更浅色和规整；局部分簇、间隙与倾斜的可见差异并未触发这三个粗命题。当前没有可靠Group Mask、密度数值或逐张身份，不把这些观察写成确认的数量/密度错误。两侧仍均满足多层陈列和主要竖直这个粗描述。固定R3在Render顶部包含更多顶棚/墙面，且柜架投影高度不同，不能排除相机影响。完整未审核观察保存在JSON.static_review_candidates；冻结问题及证据未随之修改。

本轮可观察是否对集合存在性、至少两个柜格的粗分布、主要陈列方向给出一致或不同回答；这些能力可以沿用书籍实验的少量Group组织、独立单侧问答、确定性比较和弃权协议。但一对图片没有独立类别GT或唱片/书籍对照，不能证明VLM可靠区分二者。LP封套背脊、书脊、文件夹可能相似；已知区域和问句也会形成类别先验。

柜格判断受透视、遮挡、柜体结构变化影响。“至少两个”只反映粗分散程度，会漏掉同为多个柜格时的数量、占据位置、疏密和覆盖差异。主要竖直的二值问题不覆盖稀疏、小范围横放或倾斜角变化。没有Group定位，不输出连续空间中心、精确面积、密度或实例数；柜体颜色、材质、封套纹理等仍应由Appearance/Perceptual诊断，本轮不重算。

即使两侧均yes，也不能证明Group重建质量良好；即使回答不同，也可能是相机、可见性或识别差异。若目标在固定ROI外而全图可见，应人工检查Misplaced，不能判Confirmed Missing。需要独立人工逐侧确认类别、柜格与排列可见性，扩展独立真实类别混淆/遮挡对照并核验验证器，再讨论Group-level Statistical适用性。未审核候选不能直接转成Statistical Energy。

## 隔离、成本与复现

参考准备存在历史知识泄漏可能；本轮前置清点也读到了Inventory旧概括性书架差异描述，不能称严格盲测。验证子Agent使用fork_turns=none、随机路径/任务名，相同冻结文本，不接收源侧身份、预期、其他答案。单图读取可通过工具日志审计；共享文件系统没有强制单文件权限边界，持久会话中父任务正文不可独立明文逐字核实，因此不宣称严格隔离或等价固定API。实际工具调用、原始回答、模型标识和用量保存在JSON.answers。

两个完整验证会话累计 {final['verifier_session_seconds']:.3f} 秒；Token统计 {json.dumps(usage,ensure_ascii=False)}，包含平台上下文、图像工具阶段及最终答案，排除主Agent；缓存输入、推理输出分别包含在输入/输出，不重复加总。Codex货币费用未知，Ofox调用0，不声称免费。

8项CPU单元测试通过，覆盖独立字段可用性、非法/重复JSON、unknown、语义依赖和避免重复处罚。实际输入离线检查保存在JSON.offline_checks。准备时遇到系统无中文字体，改用已有DejaVu绘制英文显示标签；未下载字体或依赖，冻结的中文问句不变，发生在任何验证子Agent启动之前。原始RGB在完整图中保留原始像素，仅在ROI边界画细线；右侧统一2倍放大，不涂黑区域外内容。核实原图来源、ROI/源文件未改、模型/单图读取、冻结时序和离线重放的最终检查在同一work目录final_checks.json。

只重放已保存回答到全新目录，不调用模型、不读取凭证：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/records_group_verification.py --stage replay --output results/records_group_verification_bw0074 --destination results/records_group_verification_bw0074_replay
```

离线Schema/依赖比较及最终检查在 `{work.relative_to(ROOT)}` 中。没有HTML，未运行SAM/SLIC/DINO/GPU/Blender或Agent代码，未修改Grounding、五类能量、权重或历史书籍实验，未提交Git。完成本轮两侧验证后停止。
'''
    (output/'report.md').write_text(text)
    print(json.dumps(dict(output=str(output),comparison=rows,seconds=final['verifier_session_seconds'],usage=usage),ensure_ascii=False))


def replay(source,destination):
    shutil.copytree(source,destination)
    final=read(destination/'verification_results.json')
    if final['status']!='completed':raise ValueError('Completed observations required')
    (destination/'verification_results.json').write_text(json.dumps(dict(status='reference_frozen',protocol=final['protocol'])))
    report(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('freeze','pair','collect','report','replay'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--destination',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='replay':
        if args.destination is None:parser.error('Fresh --destination required')
        replay(output,args.destination.resolve())
    else:globals()[args.stage](output)
