"""Post-hoc four-input Group identity/context pilot; no API or model launcher."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read, save, font, collect as collect_sessions
from scripts.region_real_render import fit_render

CATEGORIES=['vinyl_sleeves','books','other','ambiguous','absent']
SYSTEM='''你是图像内容分类器。只依据当前图片中目标柜格陈列内容本身的可见视觉证据分类，不猜测不可见内容。不能仅凭附近音响、唱机或其他设备推断唱片存在。证据不足时允许ambiguous，不强行判为不存在或类别错误。只输出JSON，不解释。'''
USER='''目标柜格内主要可辨认的陈列内容是什么？

仅输出一个JSON对象，只有category字段，其值只能是以下一个字符串：
vinyl_sleeves：陈列内容本身有足够视觉证据辨认为黑胶唱片封套。
books：陈列内容本身有足够视觉证据辨认为装订书籍。
other：有明确可辨认的陈列内容，但主要属于其他类别。
ambiguous：能看到内容，但类别、主要类别或可见性不足以可靠判断；柜格被裁掉或遮挡而无法判断时也使用此值。
absent：目标柜格清晰可见，能够确认没有上述待识别的陈列集合；不能把没看清或裁掉当作不存在。

不根据附近设备作类别推断，不输出其他字段、解释或推理。'''


def parse_identity(raw):
    def unique(pairs):
        data={}
        for key,value in pairs:
            if key in data:raise ValueError('Duplicate JSON key: '+key)
            data[key]=value
        return data
    try:
        data=json.loads(raw,object_pairs_hook=unique)
        if not isinstance(data,dict) or set(data)!={'category'}:raise ValueError('Expected only category')
        if not isinstance(data['category'],str) or data['category'] not in CATEGORIES:
            raise ValueError('Invalid category enum/type')
        return dict(status='valid',category=data['category'])
    except (ValueError,TypeError) as error:
        return dict(status='unavailable',category=None,error=str(error))


def compare_categories(first,second,comparable=True):
    a=first.get('category') if first.get('status')=='valid' else None
    b=second.get('category') if second.get('status')=='valid' else None
    status=('unavailable' if not comparable or a is None or b is None else
            'unknown' if 'ambiguous' in (a,b) else 'satisfied' if a==b else 'candidate_violated')
    return dict(first_answer=a,second_answer=b,status=status,
        raw_label_changed=a!=b if a is not None and b is not None else None,
        reason='Context/input comparison only; not a reconstruction error or correctness label',
        reviewed=False,scorable=False,value=None)


def freeze(output):
    output.mkdir(parents=True,exist_ok=False)
    work=ROOT/'runs'/('group_identity_'+uuid.uuid4().hex);work.mkdir()
    source=ROOT/'results/records_group_verification_bw0074/verification_results.json';old=read(source)
    roi=Path(old['protocol']['roi']);reference=Path(old['protocol']['reference_rgb'])
    with Image.open(roi) as im:full=list(im.getbbox())
    # Coordinator's Reference-only crop: first two shelf bands, above the receiver band.
    content=[full[0],full[1],full[2],322]
    with Image.open(reference) as im:
        if list(im.size)!=old['protocol']['image_size'] or not (0<=full[1]<content[3]<full[3]<=im.height):
            raise ValueError('Reference/crop grid mismatch')
    protocol=dict(scene_id='bw_0074',region_id='R3',experiment='post-hoc exploratory',
        reference_rgb=str(reference),roi=str(roi),source_result=str(source),work=str(work),
        image_size=old['protocol']['image_size'],crops=dict(context=full,display=content),
        crop_provenance='Coordinator Reference-only visual draft: upper two cabinet bands; exclude lower receiver/turntables. Not automatic grounding or independently reviewed GT.',
        crop_scope_note='Display crop retains a subset of visible cabinet contents; not every member of the full Group.',
        system=SYSTEM,user=USER,categories=CATEGORIES,
        schema=dict(type='object',required=['category'],additionalProperties=False,
                    properties=dict(category=dict(type='string',enum=CATEGORIES))),
        input_processing='Identical crop coordinates on Reference-native grid; 2x LANCZOS for all four. No labels, outlines, masking, generated pixels or expected answers.',
        backend='Codex Subagent',model='gpt-6-sol',maximum_verifiers=4,serial=True,automatic_retries=False,
        no_expected_labels=True,prior_render_knowledge_disclosed=True,strict_blind_test=False,
        reference_crop_frozen_before_new_render_read=True,reviewed=False,usage='provisional/debug')
    state={str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)
        for directory in ('results/records_group_verification_bw0074','results/group_vlm_verification_bw0074')
        for p in (ROOT/directory).rglob('*') if p.is_file()}
    for path in (roi,reference):state[str(path)]=dict(size=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns)
    save(work/'historical_state.json',state);save(work/'frozen_plan.json',protocol)
    (work/'frozen_plan.json').chmod(0o444)
    save(output/'verification_results.json',dict(status='prepared_not_verified',protocol=protocol,reviewed=False))
    print(json.dumps(dict(output=str(output),work=str(work),frozen_crops=protocol['crops'])))


def stage(output):
    protocol=read(output/'verification_results.json')['protocol'];work=Path(protocol['work'])
    if protocol!=read(work/'frozen_plan.json') or (work/'frozen_agent_inputs.json').exists():
        raise ValueError('Frozen protocol changed or already staged')
    old=read(protocol['source_result']);reference=Image.open(protocol['reference_rgb']).convert('RGB')
    rendered,valid,transform=fit_render(Image.open(old['pair_audit']['render_rgb']),reference.size)
    if transform!=old['pair_audit']['transform']:raise ValueError('Historical fit changed')
    (output/'images').mkdir();staged={};requests={}
    wrapper='只观察下面指定的一张PNG。仅允许一次view_image读取该图，设置detail="original"，并用image(result.image_url,"original")转交图片；不读取其他文件，不联网，不调用其他模型，不写文件，不请求澄清。最终只输出规定JSON。\n\n图像：{IMAGE}\n\nSystem：\n'+SYSTEM+'\n\nUser：\n'+USER
    for side,rgb in [('reference',reference),('render',Image.fromarray(rendered))]:
        for mode,bbox in protocol['crops'].items():
            key=side+'_'+mode;directory=Path('/tmp')/uuid.uuid4().hex;directory.mkdir(mode=0o700)
            path=directory/(uuid.uuid4().hex+'.png');local=output/'images'/path.name
            crop=rgb.crop(bbox);crop.resize((crop.width*2,crop.height*2),Image.Resampling.LANCZOS).save(local)
            shutil.copyfile(local,path);path.chmod(0o444);task='v_'+uuid.uuid4().hex[:12]
            staged[key]=dict(path=str(path),source=str(local),agent_task=task,side=side,mode=mode)
            requests[key]=dict(task_name=task,model='gpt-6-sol',fork_turns='none',message=wrapper.replace('{IMAGE}',str(path)))
    save(work/'staged_inputs.json',staged);save(work/'frozen_agent_inputs.json',requests)
    (work/'frozen_agent_inputs.json').chmod(0o444)
    save(work/'pair_transform.json',dict(transform=transform,render_rgb=old['pair_audit']['render_rgb'],
        reference_camera='unknown',camera_protocol='historical_camera',roi_moved=False,reviewed=False))
    print(json.dumps(requests,ensure_ascii=False))


def draw(output,result):
    protocol=result['protocol'];staged=read(Path(protocol['work'])/'staged_inputs.json')
    canvas=Image.new('RGB',(1580,1700),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((24,12),'Group identity and visual context | bw_0074/R3 | post-hoc exploratory',font=font(28),fill='#14273e')
    for mode,y in [('context',70),('display',1032)]:
        for side,x in [('reference',24),('render',806)]:
            key=side+'_'+mode;source=staged[key]['source']
            with Image.open(source) as im:canvas.paste(im,(x,y+40))
            name='Full R3 context' if mode=='context' else 'Upper display compartments only'
            d.text((x,y),side.title()+' | '+name,font=font(22),fill='#14273e')
            answer=result['answers'][key]['parsed'].get('category')
            status=result['crop_comparability'][key]['status']
            label_y=y+40+(844 if mode=='context' else 406)+8
            d.text((x,label_y),'Actual category: '+str(answer),font=font(23),fill='#75500b')
            d.text((x,label_y+32),'Visibility: '+status+' (unreviewed)',font=font(17),fill='#42536a')
    d.text((24,1576),'Question: What is the main recognizable display content in the target shelf compartments?',font=font(23),fill='#14273e')
    line=' | '.join(side+': '+str(result['context_effect'][side]['first_answer'])+' -> '+str(result['context_effect'][side]['second_answer']) for side in ('reference','render'))
    d.text((24,1615),line,font=font(22),fill='#75500b')
    d.text((24,1650),'All reviewed=false; provisional/debug. No GT, formal Energy, or revision of earlier satisfied results.',font=font(21),fill='#6b3f29')
    canvas.save(output/'comparison.png')


def report(output):
    pending=read(output/'verification_results.json');protocol=pending['protocol'];work=Path(protocol['work'])
    if pending['status']!='prepared_not_verified' or protocol!=read(work/'frozen_plan.json'):
        raise ValueError('Completed run cannot be overwritten; frozen protocol changed')
    packets=read(work/'raw_observations.json');visibility=read(work/'crop_comparability.json')
    for packet in packets.values():
        if packet['read_audit_passed'] and packet['parsed']!=parse_identity(packet['raw_answer']):raise ValueError('Raw response changed')
    effects={side:compare_categories(packets[side+'_context']['parsed'],packets[side+'_display']['parsed'],
        all(visibility[side+'_'+mode]['comparable'] for mode in ('context','display'))) for side in ('reference','render')}
    usage={}
    for packet in packets.values():
        for key,value in (packet['usage'] or {}).items():usage[key]=usage.get(key,0)+value
    final=dict(status='completed',protocol=protocol,answers=packets,crop_comparability=visibility,context_effect=effects,
        experiment='post-hoc exploratory',reviewed=False,scorable=False,usage='provisional/debug',
        verifier_sessions=4,ofox_calls=0,total_verifier_seconds=sum(p['duration_seconds'] or 0 for p in packets.values()),
        verifier_usage=usage,actual_currency_cost=None,formal_energy=None,old_results_revised=False,
        strict_blind_test_established=False,api_equivalence_established=False)
    (output/'verification_results.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,allow_nan=False))
    draw(output,final)
    rows='\n'.join(f"| {key} | {packets[key]['raw_answer']} | {visibility[key]['status']} |"
                   for key in ('reference_context','reference_display','render_context','render_display'))
    effect_text='；'.join(side+'：'+str(effects[side]['first_answer'])+' → '+str(effects[side]['second_answer'])+
                          '（'+effects[side]['status']+'）' for side in ('reference','render'))
    findings=[]
    for side,effect in effects.items():
        a,b=effect['first_answer'],effect['second_answer']
        if a==b=='ambiguous':finding='完整和局部都无法可靠确定类别，未观察到去除上下文后的明确类别改变。'
        elif a==b and a is not None:finding='两种输入保持同一类别；这只是本次观测稳定，不证明正确或不依赖任何上下文。'
        else:finding='输入下原始标签变化或不可用；需区分识别证据、裁剪可见成员和模型随机性，不能据此确认类别错误。'
        findings.append(side+'：'+finding)
    text=f'''# Group Semantic Identity 与上下文依赖

**post-hoc exploratory / Codex Subagent gpt-6-sol / reviewed=false / provisional/debug**。最多4个验证子Agent，实际每图一次、串行、无重试、无Ofox。不修改此前R3三个satisfied，也不生成正式Energy。

## 先冻结Reference裁剪与问题

沿用参考图 `{protocol['reference_rgb']}`、已有固定R3 ROI `{protocol['roi']}`。完整R3输入取其外接矩形 {protocol['crops']['context']}；仅陈列输入为 {protocol['crops']['display']}，保留Reference上方两层柜格，排除下方收录机和唱机。坐标均为Reference原始1258×855网格的xyxy、右/下界不含；由协调Agent只看Reference作粗裁剪，不是自动Grounding或独立人工GT。裁剪、Prompt及Schema先保存在只读 `{work.relative_to(ROOT)}/frozen_plan.json`，本轮再次读取Render前冻结。

Render按此前已保存的等比例全帧缩放/居中留边规则映射到参考网格，之后使用完全相同裁剪坐标；不移动ROI或重对齐。所有输入都用统一2倍LANCZOS放大、无文字/类别提示/覆盖涂黑，匿名PNG目录每个只有一图。图片大小不同是裁剪范围不同的直接结果，显示目标的像素放大倍数一致；并非只删设备且其余像素集合完全相同的因果消融，因为局部输入同时删去较低柜格。模型只接收一张图及同一冻结问题/分类规则，没有Reference/Render身份、条件名称、预期类别或其他答案。

唯一问题：**目标柜格内主要可辨认的陈列内容是什么？** 输出单个category，严格枚举vinyl_sleeves/books/other/ambiguous/absent。需要陈列内容本身的可见证据，不得只从附近设备猜测。ambiguous是证据不足；absent要求柜格清晰且确实没有集合，不能用裁掉/没看清替代。完整原文在JSON.protocol。

## 原始回答与裁剪可比性

| 输入 | 原始回答（未改写） | 协调Agent可见性初审，未人工审核 |
|---|---|---|
{rows}

完整→局部确定性比较：{effect_text}。
两枚举都明确且相同记satisfied，不同记candidate_violated；任一ambiguous记unknown；解析/调用失败或目标裁掉不可比较记unavailable。raw_label_changed另外保留是否变化，不把ambiguous当作一个已确认错误类别。这里的candidate_violated指输入上下文下分类变化候选，不是Agent重建错误。全部原始回答完整保留，不改写为GT。

## 解读与限制

{' '.join(findings)} 本轮不能将此前三个satisfied追溯改为错误；新分类问题的任务、选项与输入均不同于此前是否存在/多个柜格/竖直陈列的二值问题。它揭示本次类别证据的可用性，不直接证明此前回答来自设备推断。

裁剪初审在验证前完成，均未获独立人工确认：Reference局部仍保留右缘一小块扬声器和左缘植物，因此不是彻底去除全部背景的输入；Render局部含更多顶棚/墙面，保留一整排及部分下一排陈列，目标没有完全被裁掉，但可见成员范围与Reference不完全相同。分类行为可作有限诊断，不可用于完整Group数量/密度比较，也不是严格的成对因果对照。若目标完全被裁掉，程序比较会记unavailable，不移动裁剪框。

应分别读取Reference和Render的完整/局部回答：出现明确类别→ambiguous，只能说明这一观测的局部证据不足；明确类别改变是输入敏感性候选；保持相同类别也不能证明模型独立于上下文或分类正确。单侧每条件仅一个观测，模型随机性和裁剪改变可见集合成员都可能影响结果，不能把变化完全归因于音响设备。没有独立类别GT或书籍/唱片混淆负对照，也没有独立人工可比性审核。

历史相机并未配准，Reference真实相机未知，Render不满足正式固定T0证据要求。相同参考坐标可能在Render中含更多背景或截去部分柜格；详细可见性在JSON.crop_comparability。若裁掉目标，不迁移裁剪框去寻找它，更不能将其认定为Confirmed Missing。

协调Agent已知此前Render与三个satisfied，不能称参考准备严格盲测；本轮裁剪选择本身是事后探索。验证Agent通过fork_turns=none和匿名路径减少泄漏，实际模型、输入模板、单图工具读取、原始回复及用量保存在JSON.answers。共享文件系统没有强制单文件访问边界，持久日志无法独立明文重读父任务正文，因此不宣称严格隔离或与固定API等价。未要求模型解释/反思，不能从最终一字段回答还原其实际视觉依据。

4个完整验证会话共 {final['total_verifier_seconds']:.3f} 秒；Token {json.dumps(usage,ensure_ascii=False)}，包括子会话平台上下文和图像工具阶段，不含主Agent。缓存包含在输入、推理包含在输出，不重复加总；Codex实际货币成本未知。Ofox调用0，不读取凭证。14项CPU单元测试通过（本轮6项、沿用三字段协议的回归测试8项）；输入检查和最终完整性检查存于 `{work.relative_to(ROOT)}`。未运行SAM/SLIC/DINO/Blender或历史Agent代码，未修改正式Energy/权重，未提交Git，没有HTML。

## 离线复现

在项目目录，仅重放既有真实回答并重画到新的目录，不调用模型：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_identity_context.py --stage replay --output results/group_identity_context_bw0074 --destination results/group_identity_context_bw0074_replay
```

完成本轮四图后停止。
'''
    (output/'report.md').write_text(text)
    print(json.dumps(dict(output=str(output),effects=effects,seconds=final['total_verifier_seconds'],usage=usage),ensure_ascii=False))


def replay(source,destination):
    shutil.copytree(source,destination);final=read(destination/'verification_results.json')
    if final['status']!='completed':raise ValueError('Need completed observations')
    (destination/'verification_results.json').write_text(json.dumps(dict(status='prepared_not_verified',protocol=final['protocol'])))
    report(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('freeze','stage','collect','report','replay'),required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='collect':collect_sessions(output,parse=parse_identity)
    elif args.stage=='replay':
        if args.destination is None:parser.error('Fresh --destination required')
        replay(output,args.destination.resolve())
    else:globals()[args.stage](output)
