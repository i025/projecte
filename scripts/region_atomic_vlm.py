"""Two authorized single-side VQA requests; deterministic provisional comparison."""
import argparse
import base64
from copy import deepcopy
import html
import io
import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.region_first_e2e import configuration,sanitized
from scripts.region_grounding_experiment import read,save,edges,box
from scripts.region_first_generalization import panel_grid
from scripts.region_real_render import fit_render
from benchmark.vlm import VLMClient

SOURCE=ROOT/'results/region_first_real_render_bw0073'
MODEL='openai/gpt-6-sol'
MAX_TOKENS=800
SYSTEM='你是视觉证据验证器。只根据当前图像回答给定问题。不要猜测不可见内容。无法可靠判断时回答 unknown。不要比较其他图像，不要评价整体重建质量。只输出 JSON。'
USER='''请根据图像回答以下三个问题：

Q1：画面中是否存在中央厨房岛台？

Q2：岛台靠近相机的一侧，可见几把高脚椅？

Q3：如果岛台和吊灯都可见，从当前图像视角看，吊灯是否位于岛台上方？

仅返回一个 JSON 对象，包含 q1、q2、q3 三个字段。

- q1：yes、no 或 unknown
- q2：非负整数或 unknown
- q3：yes、no 或 unknown

不要输出其他字段、解释或推理过程。'''
QUESTIONS=[('q1','semantic','画面中是否存在中央厨房岛台？'),
    ('q2','statistical','岛台靠近相机的一侧，可见几把高脚椅？'),
    ('q3','spatial','如果岛台和吊灯都可见，从当前图像视角看，吊灯是否位于岛台上方？')]
SCHEMA=dict(type='object',additionalProperties=False,required=['q1','q2','q3'],properties=dict(
    q1=dict(enum=['yes','no','unknown']),q2=dict(anyOf=[dict(type='integer',minimum=0),dict(const='unknown')]),
    q3=dict(enum=['yes','no','unknown'])))


def parse_answers(raw):
    if not isinstance(raw,str):raise ValueError('Expected text JSON response')
    text=raw.strip()
    if text.startswith('```') and text.endswith('```'):
        text=re.sub(r'^```(?:json)?\s*','',text,flags=re.I)[:-3].strip()
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    def nonfinite(_):raise ValueError('Nonfinite JSON value')
    answer=json.loads(text,object_pairs_hook=unique,parse_constant=nonfinite)
    if not isinstance(answer,dict) or set(answer)!={'q1','q2','q3'}:raise ValueError('Expected only q1, q2 and q3')
    for key in ('q1','q3'):
        if not isinstance(answer[key],str) or answer[key] not in {'yes','no','unknown'}:raise ValueError('Invalid '+key+' answer')
    if not (type(answer['q2']) is int and answer['q2']>=0) and answer['q2']!='unknown':
        raise ValueError('q2 requires a nonnegative integer or unknown')
    return answer


def compare_answer_packets(reference,rendered):
    rows=[];available=all(p.get('status')=='valid' for p in (reference,rendered))
    a=reference.get('answers') or {};b=rendered.get('answers') or {}
    if available:
        # Validate offline replay as strictly as the original response.
        a=parse_answers(json.dumps(a));b=parse_answers(json.dumps(b))
    for key,energy,question in QUESTIONS:
        first,second=a.get(key),b.get(key)
        if not available:status,reason='unavailable','A request or response validation failed / was not attempted'
        elif key!='q1' and (a['q1']!='yes' or b['q1']!='yes'):
            status,reason='unknown','Island presence prerequisite not established on both sides; no dependent penalty'
        elif 'unknown' in (first,second):status,reason='unknown','At least one side answered unknown'
        elif first==second:status,reason='satisfied','Known answers agree; agreement does not establish correctness or GT'
        else:status,reason='candidate_violated','Known answers differ; visual/camera/model errors require human review'
        rows.append(dict(id=key,region_id='R2',energy=energy,question=question,reference_answer=first,
            render_answer=second,status=status,reason=reason,raw_answer_changed=(first!=second) if available else None,
            level='region',value=None,aggregation_weight=1.,score=None,q=0.,reviewed=False,scorable=False,usage='provisional/debug'))
    return rows


def request_payload(payload):
    body=deepcopy(payload)
    if len(body.get('messages',[]))!=2:raise ValueError('Expected system/user messages only')
    content=body['messages'][1].get('content')
    if not isinstance(content,list) or len(content)!=3 or content[0]!={'type':'text','text':USER}:
        raise ValueError('Expected neutral questions and two images of one side')
    sizes=[]
    for item in content[1:]:
        if item.get('type')!='image_url':raise ValueError('Expected PNG image data')
        url=item.get('image_url',{}).get('url','');prefix='data:image/png;base64,'
        if not url.startswith(prefix):raise ValueError('Expected actual PNG data URL')
        try:
            decoded=base64.b64decode(url[len(prefix):],validate=True)
            with Image.open(io.BytesIO(decoded)) as image:
                if image.format!='PNG':raise ValueError('PNG required')
                sizes.append(image.size);image.verify()
        except Exception as exc:raise ValueError('Invalid PNG image payload') from exc
    if sizes[0]!=sizes[1] or max(sizes[0])>1024:raise ValueError('Full/outlined image dimensions must match, at most 1024')
    if body.get('model')!=MODEL:raise ValueError('Unexpected model')
    body['messages'][0]={'role':'system','content':SYSTEM}
    body.pop('response_format',None);body['temperature']=.1
    body['max_tokens']=MAX_TOKENS
    return body


def reserve(out,side):
    if side not in {'reference','render'}:raise ValueError('Unknown image side')
    target=out/(side+'_attempt.json')
    if target.exists():raise FileExistsError('This side already reserved; no retry')
    ledger=read(out/'vlm_requests.json') if (out/'vlm_requests.json').exists() else []
    if len(ledger)>=2 or len(list(out.glob('*_attempt.json')))>=2:raise ValueError('Two-request budget exhausted')
    save(target,dict(side=side,maximum_side_requests=1,automatic_retry=False,reviewed=False))


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);(out/'request_images').mkdir();(out/'source_snapshot').mkdir()
    audit=read(SOURCE/'pair_audit.json')
    reference=Image.open(audit['reference_rgb']).convert('RGB');reference.thumbnail((1536,1536),Image.Resampling.LANCZOS)
    expected=np.asarray(Image.open(SOURCE/'reference.png').convert('RGB'))
    if not np.array_equal(np.asarray(reference),expected):raise ValueError('Reference provenance mismatch')
    fitted,valid,transform=fit_render(Image.open(audit['render_rgb']),reference.size)
    if not np.array_equal(fitted,np.asarray(Image.open(SOURCE/'render.png'))):raise ValueError('Real Render provenance mismatch')
    if transform!=audit['comparison_transform']:raise ValueError('Historical full-frame transform changed')
    for name in ('reference.png','render.png','pair_audit.json'):shutil.copyfile(SOURCE/name,out/name)
    shutil.copyfile(SOURCE/'measurement_rois/polygon_R2.png',out/'R2_polygon.png')
    shutil.copyfile(SOURCE/'measurement_rois/box_R2.png',out/'R2_box.png')
    mask=np.asarray(Image.open(out/'R2_polygon.png'),bool);inputs={}
    request_size=(1024,558)
    request_mask=np.asarray(Image.fromarray(mask).resize(request_size,Image.Resampling.NEAREST),bool)
    Image.fromarray(request_mask).save(out/'request_R2_polygon.png')
    for side in ('reference','render'):
        image=Image.open(out/(side+'.png')).convert('RGB').resize(request_size,Image.Resampling.LANCZOS)
        image.info.clear();full='request_images/'+side+'_full.png';image.save(out/full)
        marked=np.asarray(image).copy();marked[edges(request_mask)]=[255,170,0]
        outline=Image.fromarray(marked);draw=ImageDraw.Draw(outline);x0,y0,_,_=box(request_mask)
        draw.text((x0+4,y0+4),'R2',fill='black',stroke_width=2,stroke_fill='white')
        marked_path='request_images/'+side+'_r2.png';outline.save(out/marked_path)
        inputs[side]=dict(images=[full,marked_path],image_size=list(request_size),same_side_only=True)
    save(out/'inputs.json',dict(sides=inputs,source=str(SOURCE),common_grid=list(reference.size),
        roi_polygon='R2_polygon.png',roi_box='R2_box.png',request_roi='request_R2_polygon.png',
        roi_changed=False,full_context_preserved=True,images_black_masked=False,reviewed=False))
    save(out/'protocol.json',dict(system=SYSTEM,user=USER,model=MODEL,max_tokens=MAX_TOKENS,temperature=.1,
        output_schema='schema.json',maximum_paid_requests=2,per_side_limit=1,automatic_retries=False,
        reference_expected_answers_in_prompt=False,json_mode=False,usage='provisional/debug',reviewed=False))
    save(out/'schema.json',SCHEMA)
    for name in ('benchmark_evidence.py','benchmark_metrics.py','benchmark_config.py'):
        shutil.copyfile(ROOT/'e_harness'/name,out/'source_snapshot'/name)
    shutil.copyfile(Path(__file__),out/'source_snapshot'/Path(__file__).name)
    print('Prepared the two independent sides; no API requests',flush=True)


def clean_response(value,key):
    value=sanitized(value,key)
    if isinstance(value,dict):return {k:clean_response(v,key) for k,v in value.items()}
    if isinstance(value,list):return [clean_response(v,key) for v in value]
    if isinstance(value,str):return re.sub(r'data:image/[^;,\s]+;base64,[A-Za-z0-9+/=\r\n]+','[image payload redacted]',value)
    return value


def request(out):
    import requests
    from requests.adapters import HTTPAdapter
    if read(out/'offline_checks.json').get('passed') is not True:raise ValueError('Offline checks must pass before paid requests')
    if (out/'vlm_requests.json').exists() or list(out.glob('*_attempt.json')) or (out/'stopped.json').exists():
        raise FileExistsError('Paid stage already started; no rerun or retry')
    config=configuration()  # In-memory literal assignments only; never saved or printed.
    client=VLMClient(out/'vlm_requests.json',api_key=config['VLM_API_KEY'],base_url=config['VLM_BASE_URL'],
        model=config['VLM_MODEL'],request_limit=2)
    manifest=read(out/'inputs.json')['sides']
    sys.path.insert(0,str(ROOT.parent/'BlenderWorld/scripts'))
    from ofox_tunnel import OfoxTunnel
    for side in ('reference','render'):
        reserve(out,side)
        result=dict(side=side,status='unavailable',answers=None,source='real_vlm',reviewed=False,usage='provisional/debug')
        try:
            with OfoxTunnel(ip='47.83.144.71') as tunnel:
                with requests.Session() as session:
                    tunnel.configure_session(session)
                    session.mount('https://',HTTPAdapter(max_retries=0));session.mount('http://',HTTPAdapter(max_retries=0))
                    calls=0
                    def post(url,*,json,**kwargs):
                        nonlocal calls
                        calls+=1
                        if calls!=1:raise ValueError('No second HTTP attempt allowed')
                        body=request_payload(json)
                        response=session.post(url,json=body,**kwargs)
                        save(out/(side+'_provider_response.json'),dict(http_status=response.status_code,
                            raw_response_text=clean_response(response.text,client.key),reviewed=False))
                        return response
                    packet=client.call([out/p for p in manifest[side]['images']],USER,'bw_0073:R2:'+side+'_atomic_answers',
                        session=SimpleNamespace(post=post),max_tokens=MAX_TOKENS,token_parameter='max_tokens',
                        retry_network=False,read_timeout=300)
            result['response']=clean_response(packet,client.key)
            if packet.get('evaluation_status')=='answered':
                result.update(status='valid',answers=parse_answers(packet['raw_answer']))
            else:result['error']=clean_response(packet.get('error','Request unavailable'),client.key)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            result['error']=clean_response(str(exc),client.key)
        except Exception as exc:
            result['error_type']=type(exc).__name__  # Never serialize request/credential-bearing exception repr.
        save(out/(side+'_answers.json'),clean_response(result,client.key))
        print(side+': '+result['status'],flush=True)
        if result['status']!='valid':
            save(out/'stopped.json',dict(side=side,reason='Request/parse failed; no retry or further request',reviewed=False))
            break


def report(out):
    packets={}
    for side in ('reference','render'):
        path=out/(side+'_answers.json')
        if not path.exists():save(path,dict(side=side,status='unavailable',answers=None,
            error='Not attempted after earlier failure / paid stage not run',source='real_vlm',reviewed=False))
        packets[side]=read(path)
    rows=compare_answer_packets(packets['reference'],packets['render'])
    verification=dict(results=rows,source='independent real VLM answers + deterministic comparison',
        reference_answers_are_gt=False,mock_results_used=False,formal_energy=dict(semantic=None,spatial=None,statistical=None),
        observation_energy=None,reviewed=False,usage='provisional/debug')
    if (out/'verification_results.json').exists():assert read(out/'verification_results.json')==verification
    else:save(out/'verification_results.json',verification)
    ledger=read(out/'vlm_requests.json') if (out/'vlm_requests.json').exists() else []
    cost=dict(actual_requests=len(ledger),maximum_authorized=2,
        usage=[dict(side=r['purpose'],model=r.get('returned_model') or r['model'],tokens=r.get('usage'),
            latency_seconds=r.get('latency_seconds'),actual_cost=r.get('actual_cost')) for r in ledger],
        total_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in ledger) if ledger and all(r.get('usage') for r in ledger) else None,
        total_latency_seconds=sum(r.get('latency_seconds',0) for r in ledger),
        total_actual_cost=sum(r['actual_cost'] for r in ledger) if ledger and all(type(r.get('actual_cost')) in (int,float) for r in ledger) else None,
        actual_cost_unknown_reason=None if ledger and all(type(r.get('actual_cost')) in (int,float) for r in ledger) else
            'Provider did not supply a numeric cost; no estimate/balance request',reviewed=False)
    if (out/'request_summary.json').exists():assert read(out/'request_summary.json')==cost
    else:save(out/'request_summary.json',cost)
    panels=[]
    for side in ('reference','render'):
        for variant in ('full','r2'):panels.append((side+' / '+variant,Image.open(out/'request_images'/(side+'_'+variant+'.png'))))
    panel_grid(panels,out/'comparison.png',width=750)
    table=['| 问题 | Reference真实回答 | Render真实回答 | 程序结果 |','| --- | --- | --- | --- |']
    body=['<!doctype html><meta charset="utf-8"><title>R2 Real VLM Atomic Verification</title>',
        '<style>body{font:16px sans-serif;line-height:1.7;margin:24px;background:#f6f7f9}img{max-width:100%}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #bbb;text-align:left}pre{white-space:pre-wrap}</style>',
        '<h1>bw_0073 R2：首次真实 VLM 原子验证</h1>',
        '<p>provisional/debug；全部reviewed=false。两侧独立回答相同中立问题，Reference回答不是GT，一致也不是正确性证明。</p>',
        '<p><a href="report.md">报告与离线复现</a> · <a href="reference_answers.json">真实Reference回答</a> · <a href="render_answers.json">真实Render回答</a> · <a href="verification_results.json">确定性比较</a> · <a href="request_summary.json">实际Token/延迟/费用</a></p>',
        '<img src="comparison.png"><h2>真实回答与程序比较</h2><table><tr><th>问题</th><th>Reference</th><th>Render</th><th>程序结果及原因</th></tr>']
    for row in rows:
        values=[row['question'],str(row['reference_answer']),str(row['render_answer']),row['status']+' / '+row['reason']]
        body+=['<tr>'+''.join('<td>'+html.escape(value)+'</td>' for value in values)+'</tr>']
        table.append('| '+row['id']+' | '+str(row['reference_answer'])+' | '+str(row['render_answer'])+' | '+row['status']+' |')
    body+=['</table>']
    review_text='尚未保存静态图像初审意见，全部判断待人工核对。'
    if (out/'initial_visual_review.json').exists():
        review=read(out/'initial_visual_review.json')
        body+=['<h2>助手静态图像初审；不是人工审核或第三次VLM请求</h2><table><tr><th>问题</th><th>Reference初审</th><th>Render初审</th><th>依据与限制</th></tr>']
        review_lines=[]
        for row in review['judgments']:
            body+=['<tr>'+''.join('<td>'+html.escape(row[k])+'</td>' for k in ('id','reference','render','reason'))+'</tr>']
            review_lines.append('- '+row['id']+'：Reference '+row['reference']+'；Render '+row['render']+'。'+row['reason'])
        body+=['</table><p>所有初审reviewed=false；模型答案与可见内容相符仍不能证明可靠准确率。</p>']
        review_text='\n'.join(review_lines)
    body+=['<h2>需要人工核对</h2><ul><li>分别检查岛台、椅子数量及吊灯投影关系；模型答案不是人工GT。</li><li>固定R2 Polygon未跟随Render中下移的吊灯；完整图片保留了ROI外内容，不将移出ROI当作缺失。</li><li>Q3没有独立吊灯可见性字段，不能自动证明模型正确执行了前提。</li><li>相机高度1.5m与正式T0的2m不同，Reference相机未知，可能影响可见数量和关系。</li><li>每侧一次请求，无法检验重测稳定性或统计准确率。</li></ul><h2>实际调用记录</h2><pre>'+html.escape(json.dumps(cost,ensure_ascii=False,indent=2))+'</pre>',
        '<p>Semantic / Spatial / Statistical正式Energy均N/A；candidate_violated不触发惩罚。没有新Grounding、SAM/SLIC/DINO/Blender或Agent执行。</p>']
    (out/'comparison.html').write_text('\n'.join(body))
    text='''# R2 首次真实VLM Atomic Verification

只验证bw_0073 R2的三个问题；既有Reference、真实Render与同坐标ROI来源见pair_audit.json和inputs.json。沿用1536×837共同网格及历史全图适配，输入均缩放到1024×558。每次请求只含同一侧的完整RGB与R2轮廓图；无黑色Mask、无期望答案、无跨侧比较。

[人工审核页面](comparison.html) · [真实Reference回答](reference_answers.json) · [真实Render回答](render_answers.json) · [比较结果](verification_results.json) · [实际成本](request_summary.json)

TABLE

## 静态图像初审及本轮结论

VISUAL_REVIEW

上述如有静态初审，均是助手查看已保存RGB后的可见性意见，reviewed=false，并非第三次模型API验证或真实人工GT。ACTUAL_RESULT 一次回答不能检验稳定性。

本例最重要的限制是问题覆盖范围：岛台存在、椅子数量和吊灯上方关系这三项即使同时一致，形状、纹理、材质、灯具高度和具体位置仍可能明显不同。因此未发现原子违反不等于重建无错；这里是命题覆盖局限，不是已经证明模型答错。完整上下文保留了固定Polygon外的吊灯，避免直接把移出ROI当成缺失；没有额外跑黑色Mask对照，不能宣称量化改善。

有效格式的Semantic存在性和Statistical可见计数回答可供进一步人工审核；Spatial仅支持图像投影上方这一粗命题，尚不支持精确位移或3D关系。三者都缺少审核后的Reference GT、验证器校准和正式相机条件，当前均不能作为正式Energy。无效或Unknown回答不能补造为评分输入。

## 结果的含义

本目录分别保存实际模型响应、请求/解析失败时的不可用记录和程序比较，未人工审核；实际调用数与有效回答数见下方。known相同记satisfied，明确不同记candidate_violated，任一unknown记unknown，请求/解析失败记unavailable。Q1两侧任一不是yes时，Q2/Q3保留原答但比较记unknown，不重复处罚。没有确认缺失判定，也不把物体移出ROI当成不存在。Q3没有独立吊灯可见性字段，必须人工核对模型是否遵守条件。

Reference答案不是GT，相同回答可能共同错误；不同回答也可能来自视觉识别、遮挡、视角或真实重建差异。每侧只有一次，不能声称稳定性或可靠准确率已验证。Semantic/Spatial/Statistical各只有一个具体命题；计数不等于密度/分布评测，投影上方不等于世界坐标或完整3D结构。全部正式Energy和总分保持N/A。

## 实际请求、费用和边界

模型openai/gpt-6-sol，temperature=0.1，最多800输出Token；使用既有OfoxTunnel、HTTPS原域名与证书校验。关闭网络和HTTP自动重试，每侧独占预算记录，最多2次；首次请求/解析失败即停止后续请求。不额外检查余额、模型目录或验证模型。

SUMMARY

费用字段缺失时unknown，不估价、不推断免费。保存脱敏原始provider响应和原始回答；没有保存API Key、认证Header或Base64请求正文。原图/Render和Mask仅复制到新目录，核心公式、权重、Grounding参数及历史产物不改动。历史相机不符合T0，全部provisional/debug、reviewed=false。

173项离线CPU测试通过后才发送付费请求，详情见tests_offline.log与offline_checks.json。正式评分、SAM、SLIC、DINO、Blender和Agent执行均为0。复用现有VLMClient及Energy记录字段，保留level=region、energy、q=0、value/score=null，不将candidate_violated改成正式惩罚。离线重放和最终检查见validation.json。

## 免费离线复现

以下仅重放已保存真实回答、重建页面，不会请求API。目标目录必须不存在：

```bash
cd /home/xymo/projects/e-harness
/home/xymo/environments/relateanything-inference/bin/python scripts/region_atomic_vlm.py replay --source results/region_atomic_vlm_r2_bw0073 --output results/region_atomic_vlm_r2_bw0073_replay
```

本轮请求结束后停止，等待人工审核，不计算正式Benchmark总分。
'''
    actual_text='两侧真实解析答案：'+json.dumps({side:p.get('answers') for side,p in packets.items()},ensure_ascii=False)+'。程序状态数量：'+json.dumps({s:sum(r['status']==s for r in rows) for s in ('satisfied','candidate_violated','unknown','unavailable')},ensure_ascii=False)+'。'
    (out/'report.md').write_text(text.replace('TABLE','\n'.join(table)).replace('VISUAL_REVIEW',review_text).replace('ACTUAL_RESULT',actual_text).replace('SUMMARY','```json\n'+json.dumps(cost,ensure_ascii=False,indent=2)+'\n```'))
    print('Saved deterministic comparison and review page; no API request',flush=True)


def replay(source,out):
    prepare(out)
    for name in ('reference_answers.json','render_answers.json','vlm_requests.json','reference_provider_response.json','render_provider_response.json','initial_visual_review.json'):
        if (source/name).exists():shutil.copyfile(source/name,out/name)
    report(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','request','report','replay'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--source',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if args.stage=='prepare':prepare(out)
    elif args.stage=='request':request(out)
    elif args.stage=='report':report(out)
    else:
        if args.source is None:parser.error('replay requires --source')
        replay(args.source.resolve(),out)
