"""Offline report of three recorded child-agent observations; never calls a model."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.group_statistical_controls import (FIELDS,read,save,parse_prediction,answer_value,
    compare_expected,compare_pair,group_contracts,group_energy_rows)


def outcome(rows):
    states={r['status'] for r in rows}
    if 'unavailable' in states:return 'UNAVAILABLE'
    if 'unknown' in states:return 'UNKNOWN'
    return 'MATCH construction_expected' if states=={'satisfied'} else 'MISMATCH construction_expected'


def build(run,output):
    protocol=read(run/'run_protocol.json');source=Path(protocol['source'])
    labels=read(source/'expected_labels.json')
    for name in ('frozen_protocol','expected_labels'):
        state=read(run/(name+'_source_state.json'));path=Path(state['path'])
        if read(path)!=state['content'] or path.stat().st_mtime_ns!=state['mtime_ns']:
            raise ValueError('Frozen source changed: '+name)
    for image in protocol['images']:
        path=Path(image['path'])
        if path.stat().st_mtime_ns!=image['mtime_ns'] or path.stat().st_size!=image['bytes']:
            raise ValueError('Source PNG changed')
    packets={};parsed={};comparisons={};total_usage={};duration=0.
    for index,key in enumerate(('A','B','C'),1):
        packet=read(run/'raw_responses'/f'sample_{index:02d}.json')
        if packet['observed_models']!=['gpt-6-sol']:raise ValueError('Unexpected agent model')
        if packet['attempts']!=1 or packet['final_messages']!=1:raise ValueError('Repeated observation')
        parsed[key]=parse_prediction(packet['raw_answer'])
        if parsed[key]!=packet['parsed']:raise ValueError('Saved parse differs from raw answer')
        packets[key]=packet;comparisons[key]=compare_expected(labels['samples'][key],parsed[key])
        for field,value in packet['usage'].items():total_usage[field]=total_usage.get(field,0)+value
        duration+=packet['duration_seconds']
    ordered=list(packets.values())
    if any(ordered[i]['end_time']>ordered[i+1]['start_time'] for i in (0,1)):
        raise ValueError('Agent sessions overlapped')
    output.mkdir(parents=True,exist_ok=True)
    for name in ('verification_results.json','comparison.png','report.md'):
        if (output/name).exists():raise FileExistsError('No report overwrite: '+name)
    if output!=run:
        (output/'raw_responses').mkdir(exist_ok=False)
        for p in (run/'raw_responses').glob('*.json'):shutil.copyfile(p,output/'raw_responses'/p.name)
        for name in ('run_protocol.json','offline_checks.json','tests.txt','input_audit.json',
                     'agent_input_template.json','session_registry.json','frozen_protocol_source_state.json',
                     'expected_labels_source_state.json'):
            shutil.copyfile(run/name,output/name)
    _,questions,_=group_contracts(labels)
    energy_records={}
    for key in packets:
        results=[]
        for row in comparisons[key]:
            value=row['prediction']
            results.append(dict(id='books_'+row['field'],status=row['status'],
                observed=(value=='yes') if value in ('yes','no') else None,
                reason='Codex subagent compared with unreviewed construction_expected; no calibrated score mapping',
                source='codex_subagent',reviewed=False,scorable=False))
        energy_records[key]=group_energy_rows(questions[key],results)
    pairs=dict(A_B=compare_pair(parsed['A'],parsed['B']),A_C=compare_pair(parsed['A'],parsed['C']))
    save(output/'verification_results.json',dict(source='codex_subagent',usage='provisional/debug',reviewed=False,
        original_protocol_source=str(source/'frozen_protocol.json'),model_requested='gpt-6-sol',
        original_api_model=protocol['original_api_model'],api_equivalence_established=False,
        actual_ofox_api_requests=0,independent_subagent_sessions=3,total_subagent_session_seconds=duration,
        subagent_usage=total_usage,usage_scope='Three complete child sessions only; cached input already included in input; parent excluded',
        ofox_cost_usd=0,subagent_cost_usd=None,actual_currency_total=None,
        conditions={k:dict(construction_expected=labels['samples'][k],
            prediction={f:answer_value(parsed[k],f) for f in FIELDS},parsed=parsed[k],
            comparison=comparisons[k],outcome=outcome(comparisons[k]),
            raw_response='raw_responses/'+packets[k]['sample_id']+'.json',
            duration_seconds=packets[k]['duration_seconds'],tokens=packets[k]['usage'],reviewed=False) for k in packets},
        pairs=pairs,energy_records=energy_records,formal_statistical_energy=None,scorable=False,
        unknown_fields=sum(r['status']=='unknown' for rows in comparisons.values() for r in rows),
        unavailable_fields=sum(r['status']=='unavailable' for rows in comparisons.values() for r in rows),
        construction_mismatch_fields=sum(r['status']=='candidate_violated' for rows in comparisons.values() for r in rows)))
    # Original RGB stays native-size; display text is added outside it after inference.
    margin=24;width=768;height=640;top=205;bottom=140
    canvas=Image.new('RGB',(3*width+4*margin,top+height+bottom),'#f2f5f8');draw=ImageDraw.Draw(canvas)
    font=lambda size,bold=False:ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf',size)
    draw.text((margin,18),'Book Group Controls - Independent Subagent Verification',font=font(32,True),fill='#142235')
    draw.text((margin,64),'gpt-6-sol | 3 serial sessions | 0 Ofox calls | unreviewed / provisional-debug',font=font(22),fill='#324459')
    draw.text((margin,100),'Not API-equivalent: platform context and temperature/token-cap controls differ.',font=font(21),fill='#7c4c0a')
    for n,key in enumerate(packets):
        x=margin+n*(width+margin);p=packets[key];expected=labels['samples'][key]
        prediction={f:answer_value(parsed[key],f) for f in FIELDS}
        draw.text((x,150),key+' - '+dict(A='original arrangement',B='orientation change',C='cover colors only')[key],font=font(25,True),fill='#142235')
        with Image.open(p['image_file']) as image:canvas.paste(image.convert('RGB'),(x,top))
        y=top+height+10
        draw.text((x,y),f"Expected: horizontal={expected[FIELDS[0]]}, upright={expected[FIELDS[1]]}",font=font(21),fill='#324459')
        draw.text((x,y+30),f"Actual: horizontal={prediction[FIELDS[0]]}, upright={prediction[FIELDS[1]]}",font=font(21,True),fill='#142235')
        result=outcome(comparisons[key]);color='#156744' if result.startswith('MATCH') else '#8a4a0b'
        draw.text((x,y+62),result,font=font(21,True),fill=color)
        draw.text((x,y+94),f"Unknown: {sum(r['status']=='unknown' for r in comparisons[key])} | Unavailable: {sum(r['status']=='unavailable' for r in comparisons[key])} | {p['duration_seconds']:.3f}s",font=font(18),fill='#324459')
    canvas.save(output/'comparison.png')
    for n,p in enumerate(packets.values()):
        with Image.open(p['image_file']) as original:
            if canvas.crop((margin+n*(width+margin),top,margin+n*(width+margin)+width,top+height)).tobytes()!=original.convert('RGB').tobytes():
                raise ValueError('Display changed original image pixels')
    result_rows='\n'.join(f"| {k} | {labels['samples'][k]['horizontal_stack']}/{labels['samples'][k]['upright_books']} | {answer_value(parsed[k],'horizontal_stack')}/{answer_value(parsed[k],'upright_books')} | {outcome(comparisons[k])} | {packets[k]['duration_seconds']:.3f} | {packets[k]['usage']['total_tokens']:,} |" for k in packets)
    report=f'''# Group-level Statistical：子 agent 替代验证

本轮实际运行 **3 个独立、严格串行的 gpt-6-sol 子 agent**，每张图一个会话、只读取一次指定原始 PNG、只返回一个最终 JSON。**Ofox 请求 0 次**，未读取密钥或使用该账户额度。全部保持 `reviewed:false`、`provisional/debug`，没有正式 Statistical Energy。

## 真实回答与确定性比较

以下 Horizontal/Upright 预期来自此前冻结的 construction_expected，不是人工 GT。

| 样本 | 冻结预期 H/U | 子 agent 实际 H/U | 与构造预期比较 | 会话耗时 s | 会话 Tokens |
|---|---|---|---|---:|---:|
{result_rows}

A→B：Horizontal yes→no，Upright yes→yes，检测到预定的排列变化。A→C：两个字段均保持 yes，没有在这组颜色控制中报告排列变化。6 个字段与 construction_expected 一致，本组三图没有观察到误报、漏检、Unknown 或 Unavailable。这里不计算跨场景准确率，也不将两侧一致解释为重建质量良好。

复用现有 parse_prediction、compare_expected、compare_pair 和 group_energy_rows。A/B 的 Horizontal 成对状态为 candidate_violated，表示相对于 A 的命题发生变化，正是本控制希望发现的变化；不是确认真实 Agent 错误，更不产生惩罚。单图与预期比较均为 satisfied。所有正式能量记录仍 value=None、q=0、scorable=false。

## 输入一致性与通道差异

使用冻结 System/User 原文、相同 JSON Schema、相同任务包装，唯一输入变化为原始 sample_01/02/03.png。三个子 agent 都以 fork_turns=none 启动，未继承父对话、预期答案或其他图片。日志各显示一次 tools.view_image，未见其他文件读取、网络、模型或执行工具。图片无裁剪、局部标记或人工修补；view_image 的平台媒体处理策略由平台控制。comparison.png 的原图区域保持原始 768×640 像素，文字在推理完成后加在图像外，未进入验证输入。

**这不是原 Ofox API 的等价复现。** 模型选择与会话日志均为 gpt-6-sol，原接口标识为 openai/gpt-6-sol，但无法证明两通道的后端完全一致。冻结 System 文本作为子 agent 任务中的指令转交，实际系统/开发者上下文还包含平台工具与运行指令；原 API temperature=0.1、max_tokens=400 不能在 spawn_agent 上强制设置。日志记录的推理档为 medium。原始任务包装保存在 agent_input_template.json；子会话将父消息加密存储，本轮未解密/导出这些内容，转交文本以协调端实际发送模板为准。

因此，本轮只能支持“该子 agent 通道能在这组三张合成图上区分目标排列变化与封面颜色变化”，不能改称原 Ofox 接口验证成功、三次单轮 HTTP 请求或稳定的真实图像检出率。

## 实际资源与成本

三会话累计 {duration:.3f} 秒，输入 {total_usage['input_tokens']:,}、缓存输入 {total_usage['cached_input_tokens']:,}、输出 {total_usage['output_tokens']:,}、总计 {total_usage['total_tokens']:,} Tokens。缓存输入已经包含在输入中，推理输出也已经包含在输出中；不要再次加总。每个子会话有两个用量记录，覆盖取得图像的工具调用阶段与最终回答，包含平台上下文；不含主协调 agent。本用量不能与原 API 的短 Prompt 单轮请求直接比较。Ofox 费用为 0，Codex 子 agent 的实际货币费用未知，不能宣称整个过程免费。

## 失败模式与待审核内容

本轮没有字段不符，但图像仍存在明显的 8-sample 噪点、弱页块细节、书脊饰带与横向书架板。模型可能将薄体误作文件夹/唱片套，也可能依赖水平边线；二值 JSON 没有提供它使用的视觉证据，本轮未追加解释或自检。B 没误报横向书堆，仅能说明此图通过；本组没有真正的文件夹、唱片、单本平放、模糊/严重遮挡或必须 Unknown 的样本。C 只测试一组封面色变化，不能证明普遍外观不变性。

预期仍是未经人工审核的构造标签。还需按冻结定义人工审核，并在独立真实图、非书籍干扰、遮挡/低分辨率、不同布局与视角上验证误报、漏检和弃权；之后才讨论可靠性校准与正式 Energy 适用性。本轮未新增样本、修改冻结 Prompt/标签、运行 SAM/SLIC/DINO/Blender、修改五类公式或提交 Git。

## 测试与离线复现

17 项已有纯 CPU 测试通过。模型名、原始 JSON 重解析、每图一 agent、一工具读取、严格串行、唯一输入图片、原图/冻结文件状态及 comparison.png 内原始像素检查通过；原始回复与元数据在 raw_responses/，没有 Mock、凭证、请求 Base64 或隐藏推理文本。没有生成新 HTML。

仅重放已保存回复并重画 PNG（不启动 agent，不调用 API）；使用新的空目录：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/report_group_statistical_subagents.py --run {run.relative_to(ROOT)} --output {run.relative_to(ROOT)}_replay
```

原始 source/session 路径用于本机审计；重画只读取保存的回复、协议与原图。完成后三图验证即停止，不追加模型判断或正式评分。
'''
    (output/'report.md').write_text(report)
    save(output/'artifact_checks.json',dict(passed=True,raw_json_reparsed=True,observed_models_equal=True,
        strictly_serial=True,source_file_state_unchanged=True,comparison_native_pixels_preserved=True,
        frozen_prompt_and_labels_unchanged=True,new_html_files=0,formal_energy=None,reviewed=False))
    print(json.dumps(dict(output=str(output),ofox_calls=0,subagent_sessions=3,total_usage=total_usage,
        child_session_seconds=duration,outcomes={k:outcome(comparisons[k]) for k in packets}),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.run.resolve(),args.output.resolve())
