"""Fixed four-image observability pilot; no model/API invocation in this script."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import uuid

from PIL import Image,ImageDraw,ImageFilter,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.group_statistical_controls import read,save,parse_prediction,answer_value,SCHEMA
from scripts.group_statistical_hard_controls import assess,collect


def frozen_protocol():
    definitions=dict(
        yes='有充分可见证据确认该排列存在。',
        no='相关书架区域足够清晰，能够确认该排列不存在。',
        unknown='由于模糊、遮挡或类别歧义，无法可靠判断。')
    system='''你是视觉证据验证器。只根据当前图像判断书籍的可见摆放方式。不要把唱片或文件夹当作书籍，不猜测不可见内容。
严格使用以下操作定义：
yes：有充分可见证据确认该排列存在。
no：相关书架区域足够清晰，能够确认该排列不存在。
unknown：由于模糊、遮挡或类别歧义，无法可靠判断。
不要把“没有清楚看到”直接等同于“不存在”。只输出 JSON。'''
    user='''请根据当前图像回答：

Q1：图中是否存在至少两本水平叠放的书籍？
Q2：图中是否存在竖直站立摆放的书籍？

只输出：
{
  "horizontal_stack": "yes",
  "upright_books": "yes"
}

两个字段均只能为单个 yes、no 或 unknown。
以上 JSON 只是格式示例，不是预期答案。不要输出额外字段、解释或推理过程。'''
    return dict(system=system,user=user,schema=deepcopy(SCHEMA),definitions=definitions)


def draw_comparison(output,plan,cases=None):
    width=896;gap=24;top=140;panel_h=900
    canvas=Image.new('RGB',(2*width+3*gap,1960),'#f2f5f8');draw=ImageDraw.Draw(canvas)
    font=lambda size,b=False:ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf',size)
    draw.text((gap,18),'Book Groups - Absence versus Insufficient Evidence',font=font(32,True),fill='#142235')
    draw.text((gap,65),'NEW frozen definitions | Codex Subagent / gpt-6-sol | all human labels unreviewed',font=font(22),fill='#324459')
    draw.text((gap,103),'Blurred visibility labels are unset. Source construction is not a visibility judgement.',font=font(21),fill='#7c4c0a')
    for n,(key,item) in enumerate(plan['samples'].items()):
        x=gap+(n%2)*(width+gap);y=top+(n//2)*panel_h
        draw.text((x,y),item['display_name'],font=font(26,True),fill='#142235')
        with Image.open(output/'images'/Path(item['image']).name) as im:canvas.paste(im.convert('RGB'),(x,y+44))
        construction=item['source_construction'];visible=item['visible_expected']
        pred=cases[key]['prediction'] if cases else dict(horizontal_stack='pending',upright_books='pending')
        texts=[f"Source construction H/U: {construction['horizontal_stack']} / {construction['upright_books']}",
               'Visible labels H/U: '+('unreviewed / unset' if item['blurred'] else f"{visible['horizontal_stack']} / {visible['upright_books']} (construction-only)"),
               f"Actual H/U: {pred['horizontal_stack']} / {pred['upright_books']}",
               'Human visibility / category review: UNREVIEWED']
        for i,text in enumerate(texts):draw.text((x,y+760+i*30),text,font=font(21,i==2),fill='#142235' if i==2 else '#324459')
    canvas.save(output/'comparison.png')


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);(output/'images').mkdir()
    work=ROOT/'runs'/('group_observability_'+uuid.uuid4().hex);work.mkdir()
    source=ROOT/'results/group_statistical_hard_books';prior=read(source/'verification_results.json')
    plan=dict(frozen_protocol(),work=str(work),backend='Codex Subagent',model='gpt-6-sol',
        maximum_verifiers=4,serial=True,blur=dict(operation='whole-image GaussianBlur',radius_pixels=14),
        previous_experiment=str(source),historical_results_modified=False,reviewed=False,samples={})
    sources={k:source/prior['cases'][k]['original_image'] for k in ('T1','T2')}
    for key,origin,blurred in [('clear_T1','T1',False),('clear_T2','T2',False),('blur_T1','T1',True),('blur_T2','T2',True)]:
        construction=deepcopy(prior['cases'][origin]['expected'])
        plan['samples'][key]=dict(image=str(output/'images'/(uuid.uuid4().hex+'.png')),source_image=str(sources[origin]),
            source_image_mtime_ns=sources[origin].stat().st_mtime_ns,
            source_construction=construction,visible_expected={f:None for f in construction} if blurred else deepcopy(construction),
            visible_label_source='unreviewed' if blurred else 'construction_expected_clear_control',
            display_name=('Blurred ' if blurred else 'Clear ')+origin,blurred=blurred,
            human_visibility_review='unreviewed',human_book_category_review='unreviewed',reviewed=False)
    save(work/'frozen_plan.json',plan);(work/'frozen_plan.json').chmod(0o444)
    for item in plan['samples'].values():
        if item['blurred']:
            with Image.open(item['source_image']) as im:
                im.convert('RGB').filter(ImageFilter.GaussianBlur(plan['blur']['radius_pixels'])).save(item['image'])
        else:shutil.copyfile(item['source_image'],item['image'])
    save(output/'verification_results.json',dict(status='prepared_not_verified',protocol=plan,reviewed=False,
        formal_statistical_energy=None,usage='provisional/debug'))
    draw_comparison(output,plan)
    print(json.dumps(dict(output=str(output),work=str(work),status='PNG preview ready; no verifier launched'),ensure_ascii=False))


def stage(output):
    plan=read(output/'verification_results.json')['protocol'];work=Path(plan['work']);staged={};requests={}
    wrapper='只观察下面指定的一张图像。仅使用 view_image 读取此 PNG，不读取其他文件，不联网，不调用其他模型，不写文件，不请求澄清。最终只输出下面规定的 JSON。\n\n图像：{IMAGE}\n\nSystem：\n'+plan['system']+'\n\nUser：\n'+plan['user']
    for key,item in plan['samples'].items():
        directory=Path('/tmp')/uuid.uuid4().hex;directory.mkdir(mode=0o700)
        path=directory/(uuid.uuid4().hex+'.png');shutil.copyfile(item['image'],path);path.chmod(0o444)
        task='v_'+uuid.uuid4().hex[:12]
        staged[key]=dict(path=str(path),source=item['image'],agent_task=task)
        requests[key]=dict(task_name=task,model='gpt-6-sol',fork_turns='none',message=wrapper.replace('{IMAGE}',str(path)))
    save(work/'staged_inputs.json',staged);save(work/'frozen_agent_inputs.json',requests)
    (work/'frozen_agent_inputs.json').chmod(0o444)
    print(json.dumps(requests,ensure_ascii=False))


def report(output):
    pending=read(output/'verification_results.json');plan=pending['protocol'];work=Path(plan['work'])
    if pending['status']!='prepared_not_verified':raise FileExistsError('Completed run cannot be overwritten')
    if plan!=read(work/'frozen_plan.json'):raise ValueError('Frozen protocol/labels changed')
    raw=read(work/'raw_observations.json');inputs=read(work/'frozen_agent_inputs.json')
    cases={};usage={};seconds=0.;counts={k:0 for k in ('correct','false_positive','false_negative','unknown','unavailable')}
    blur_behavior=dict(unknown=0,definite_yes=0,definite_no=0,unavailable=0)
    for key,item in plan['samples'].items():
        packet=raw[key]
        if packet['actual_input']!=inputs[key]:raise ValueError('Input record changed')
        if packet['parsed']['status'] in ('valid','partial') and parse_prediction(packet['raw_answer'])!=packet['parsed']:
            raise ValueError('Raw answer differs from stored parse')
        if Path(item['source_image']).stat().st_mtime_ns!=item['source_image_mtime_ns']:
            raise ValueError('Historical source image changed')
        rows=[];prediction={}
        for field,expected in item['visible_expected'].items():
            value=answer_value(packet['parsed'],field);prediction[field]=value;assessment=assess(expected,value)
            rows.append(dict(field=field,source_construction=item['source_construction'][field],
                visible_expected=expected,model_answer=value,assessment=assessment,
                verification_status='unavailable' if value is None else 'unknown' if value=='unknown' or expected is None else
                    'satisfied' if value==expected else 'candidate_violated',
                human_visibility_review='unreviewed',human_book_category_review='unreviewed',
                correctness_scored=False,energy_value=None,scorable=False,reviewed=False))
            if item['blurred']:
                blur_behavior['unavailable' if value is None else value if value=='unknown' else 'definite_'+value]+=1
            else:counts[assessment]+=1
        cases[key]=dict(prediction=prediction,fields=rows,raw_response=packet,source_construction=item['source_construction'],
            visible_expected=item['visible_expected'],blurred=item['blurred'],reviewed=False)
        seconds+=packet['duration_seconds'] or 0.
        for field,value in (packet['usage'] or {}).items():usage[field]=usage.get(field,0)+value
    comparisons={key:dict(clear_answer=cases[clear]['prediction'],blur_answer=cases[blur]['prediction'],
        abstained_fields=[f for f,v in cases[blur]['prediction'].items() if v=='unknown'],
        correctness='not_scored; blurred visibility/category labels unreviewed',reviewed=False)
        for key,clear,blur in [('T1','clear_T1','blur_T1'),('T2','clear_T2','blur_T2')]}
    final=dict(status='completed',backend='Codex Subagent',model='gpt-6-sol',protocol=plan,cases=cases,
        clear_construction_comparison_counts=counts,blur_response_behavior=blur_behavior,paired_behavior=comparisons,
        independent_human_visibility_review=False,blurred_correctness='not_scored',
        observability_review=read(work/'observability_review.json'),
        verification_sessions=4,ofox_calls=0,total_verifier_session_seconds=seconds,verifier_usage=usage,
        usage_scope='Four complete verifier sessions, platform/tool context included; parent/preparation excluded',
        actual_currency_cost=None,ofox_cost_usd=0,formal_statistical_energy=None,reviewed=False,scorable=False,
        strict_blind_test_established=False,single_image_filesystem_access_enforced=False,
        received_task_text_independently_readable=False,api_equivalence_established=False,usage='provisional/debug')
    (output/'verification_results.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,allow_nan=False))
    draw_comparison(output,plan,cases)
    table='\n'.join(f"| {plan['samples'][k]['display_name']} | {c['source_construction']['horizontal_stack']}/{c['source_construction']['upright_books']} | {'未审核，不评分' if c['blurred'] else 'construction_expected，未人工审核'} | {c['prediction']['horizontal_stack']}/{c['prediction']['upright_books']} |" for k,c in cases.items())
    tests=read(work/'tests_result.json')
    report_text=f'''# Group Verification：不存在与证据不足

本轮采用新的独立实验协议，旧 T1–T5 原图、Prompt、标签和原始结果均未修改。后端为 **Codex Subagent / gpt-6-sol**，4 个验证子 Agent，每图一次、严格串行、无自动重试。结果全部 reviewed=false、provisional/debug；没有正式 Statistical Energy。

## 验证前冻结的操作定义

- yes：有充分可见证据确认该排列存在。
- no：相关书架区域足够清晰，能够确认该排列不存在。
- unknown：由于模糊、遮挡或类别歧义，无法可靠判断。

Q1：图中是否存在至少两本水平叠放的书籍？
Q2：图中是否存在竖直站立摆放的书籍？

冻结 System 明确要求不要将“没有清楚看到”当作“不存在”，两个字段各只允许单个 yes/no/unknown。完整原文和Schema在 JSON.protocol，验证前只读副本为 {work.relative_to(ROOT)}/frozen_plan.json。没有根据任何回答修改定义。

## 数据、预览和可观察性审核

直接复用上轮清晰 T1/T2，分别生成相同 whole-image GaussianBlur(radius=14) 的新 PNG；分辨率896×704、相机、构图和场景内容完全保持，没有 Blender/GPU/新场景变量。清晰图逐像素与来源一致，两张模糊图均由明确的同一处理生成。新模糊T1与上轮T5视觉像素相同，这是固定视觉输入下对新协议的行为观察；旧结果未替换。

先生成 comparison.png 的 Pending 预览，协调 Agent 做静态观察：清晰图有书脊/页块和排列线索，模糊图仍有整体形状但细节消失。**没有独立人工审核**，静态观察不是人工可见性GT。JSON将source_construction、visible_expected、human_visibility_review和human_book_category_review分开记录。清晰控制仅与未审核的构造预期比较；模糊两图的4个可见标签均为None，不用源场景真值代替，不预设unknown正确。

## 实际原始回答

H/U = horizontal_stack / upright_books。

| 图像 | 源构造 H/U | 当前可见标签来源 | 模型实际 H/U |
|---|---|---|---|
{table}

清晰控制分字段候选比较：{json.dumps(counts,ensure_ascii=False)}。Unknown/Unavailable独立保留，不折算为对错。模糊样本行为：{json.dumps(blur_behavior,ensure_ascii=False)}。这只是回答类型计数，不是弃权准确率。

T1 clear→blur：{cases['clear_T1']['prediction']} → {cases['blur_T1']['prediction']}。
T2 clear→blur：{cases['clear_T2']['prediction']} → {cases['blur_T2']['prediction']}。

## 结论及不能证明的部分

本次清晰T1得到yes/yes，清晰T2得到no/yes：模型在清晰对照中保留了横放存在与不存在的区别。模糊T1得到unknown/yes，模糊T2得到unknown/unknown；4个模糊判断中3个弃权、1个肯定、0个否定。这说明本次运行确实出现了按字段弃权，而不是将未看清一律回答no。模糊T1的竖放yes仍需人工判断其可见依据是否充分；不能由源场景中存在竖放书籍反推它一定正确。

清晰正/负控制是否保留判断，应逐字段读上表；与construction_expected一致只能作为初步对照证据。对模糊图，unknown表示模型选择弃权，并不自动证明弃权合理；yes/no表示给出确定回答，也不自动证明无依据或错误，仍需人工判断其所依据的可见形状是否足够、书籍类别是否可辨。因缺少这组人工可观察性标签，本轮不能计算模糊误报/漏检率或宣称校准完成。

新定义明确收紧no的证据要求，减少“未看清＝不存在”的文字歧义。但只看最终二字段JSON，不能区分剩余问题来自视觉识别、书籍类别歧义、模型对no/unknown边界的执行、或对模糊整体形状的推断；本轮没有要求解释或追加自检，不能编造原因。与旧T5回答的变化只作描述，单次独立调用和不同任务上下文不能建立Prompt修正的因果效果。

当前最多支持有限的合成可观察性行为对照，**不足以把确定回答直接作为真实 Render 的重建错误，也不足以认证真实Render的弃权可靠性**。接入真实图之前，需要独立审核这些可见标签，并在有GT的清晰不存在、局部模糊、遮挡和类别混淆案例上检查选择性误报、漏检与弃权；本轮不自动扩展。所有 Energy 值保持None，不把unknown/unavailable伪造为零误差。

## 输入隔离与实际开销

每图采用独立 /tmp/随机目录/随机文件名.png，验证者只收到这一图路径和相同冻结任务文本，未得到源构造、清晰/模糊条件、其他图答案或历史结论。fork_turns=none；会话日志核实gpt-6-sol，实际工具读取记录及原始回复完整保存在JSON.cases.*.raw_response。共享文件系统不提供强制单图访问边界，父任务正文持久日志为加密形式，无法独立逐字核实交付内容；System/User作为任务文本转交，平台系统上下文、温度及输出上限不同于API。所以不宣称已实现严格盲测或固定API等价复现。

四个PNG的预处理按冻结协议执行，但子Agent自主使用view_image时，clear_T2和blur_T1显式指定original，clear_T1和blur_T2使用工具默认值，图片转交模型时的detail提示也不完全相同。原始调用已保留，未补跑或重试；因此不能保证底层视觉编码完全一致。这是本轮子Agent后端的额外控制限制，不能把所有回答差异仅归因于图像模糊或新Prompt。

4 个验证会话合计 {seconds:.3f} 秒，Token口径：{json.dumps(usage,ensure_ascii=False)}。包含子会话平台指令、取得图像的工具阶段和最终回答；不含主协调/准备。缓存输入、推理输出分别已包含在输入、输出，不重复加总。Ofox调用0；Codex实际货币费用未知，不称免费。

{tests['tests_run']} 项针对新定义/比较逻辑的CPU测试通过。输入像素、冻结时序、单图工具读取、原始JSON重解析、串行和离线重画检查另保存在 {work.relative_to(ROOT)}/final_checks.json；实际测试结果见tests.txt。没有新增HTML，没有调用OfoxTunnel、SAM/SLIC/DINO/Blender，未自动提交Git。

## 离线复现

只根据已保存回复重画，无模型/API请求，目标目录须不存在：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_abstention_calibration.py --stage replay --output results/group_abstention_calibration --destination results/group_abstention_calibration_replay
```

重新准备输入和Pending预览（不启动验证、不重新渲染）：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_abstention_calibration.py --stage prepare --output results/group_abstention_calibration_inputs_repro
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p test_group_abstention_calibration.py -v
```

主实验的只读冻结文件、实际发送模板、可观察性待审记录、原始回复与测试日志位于 {work.relative_to(ROOT)}。完成四次验证后停止。
'''
    (output/'report.md').write_text(report_text)
    print(json.dumps(dict(output=str(output),clear_counts=counts,blur_behavior=blur_behavior,seconds=seconds,tokens=usage),ensure_ascii=False))


def replay(source,destination):
    shutil.copytree(source,destination)
    final=read(destination/'verification_results.json')
    if final['status']!='completed':raise ValueError('Need completed observations')
    (destination/'verification_results.json').write_text(json.dumps(dict(status='prepared_not_verified',protocol=final['protocol'])))
    report(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('prepare','stage','collect','report','replay'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--destination',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='prepare':prepare(output)
    elif args.stage=='stage':stage(output)
    elif args.stage=='collect':collect(output)
    elif args.stage=='report':report(output)
    else:
        if args.destination is None:parser.error('replay requires a fresh --destination')
        replay(output,args.destination.resolve())
