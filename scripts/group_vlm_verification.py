"""Two single-side book-Group VQA calls; offline preparation/replay are free."""
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
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.region_atomic_vlm import clean_response, reserve
from scripts.region_first_e2e import configuration
from scripts.region_grounding_experiment import edges, box
from scripts.region_real_render import fit_render
from scripts.group_evidence_pilot import table, panel_row
from benchmark.vlm import VLMClient

SOURCE=ROOT/'results/group_level_evidence_pilot'
MODEL='openai/gpt-6-sol'
MAX_TOKENS=600
SYSTEM='你是图像证据验证器。只根据当前图片判断指定区域中可见的书籍集合。不要将唱片误认为书籍，不推测不可见内容。无法可靠判断时返回 unknown。只输出 JSON，不解释。'
USER='''请观察标记的书架区域，回答：

1. 该区域内是否有可辨认的书籍？
2. 书籍占据多少个不同的书架分区？
3. 书籍的主要摆放方向是什么？

输出：
{
  "present": "yes",
  "shelf_sections": "3+",
  "arrangement": "upright"
}

以上仅为格式示例，不是预期答案。

取值严格限定：
- present：yes、no、unknown
- shelf_sections：0、1、2、3+、unknown
- arrangement：upright、horizontal、mixed、unknown

只有清晰可辨的独立柜格才计入数量。无法区分书籍与唱片、柜格边界不明确或遮挡严重时，选择 unknown。'''
ENUMS=dict(present=['yes','no','unknown'],shelf_sections=['0','1','2','3+','unknown'],
           arrangement=['upright','horizontal','mixed','unknown'])
SCHEMA=dict(type='object',additionalProperties=False,required=list(ENUMS),
            properties={k:dict(type='string',enum=v) for k,v in ENUMS.items()})
ENERGY=dict(present='semantic',shelf_sections='spatial',arrangement='statistical')
QUESTIONS=dict(present='该区域内是否有可辨认的书籍？',shelf_sections='书籍占据多少个不同的书架分区？',
               arrangement='书籍的主要摆放方向是什么？')


def read(path):return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def parse_fields(raw):
    """Strict JSON envelope, independent enum validation, no invented defaults."""
    if not isinstance(raw,str):raise ValueError('Expected text JSON response')
    text=raw.strip()
    if text.startswith('```') and text.endswith('```'):
        text=re.sub(r'^```(?:json)?\s*','',text,flags=re.I)[:-3].strip()
    def unique(pairs):
        output={}
        for key,value in pairs:
            if key in output:raise ValueError('Duplicate JSON key: '+key)
            output[key]=value
        return output
    def nonfinite(_):raise ValueError('Nonfinite JSON value')
    data=json.loads(text,object_pairs_hook=unique,parse_constant=nonfinite)
    if not isinstance(data,dict):raise ValueError('Expected one JSON object')
    fields={};answers={}
    for key,allowed in ENUMS.items():
        value=data.get(key)
        valid=key in data and isinstance(value,str) and value in allowed
        fields[key]=dict(validation_status='valid' if valid else 'unavailable',
                         value=value if valid else None,
                         error=None if valid else 'Missing field' if key not in data else 'Invalid enum/type',
                         raw_value=value,field_present=key in data)
        if valid:answers[key]=value
    errors=[]
    if set(data)-set(ENUMS):errors.append('Unexpected fields: '+', '.join(sorted(set(data)-set(ENUMS))))
    valid=all(f['validation_status']=='valid' for f in fields.values()) and not errors
    return dict(status='valid' if valid else 'partial',answers=answers,fields=fields,
                schema_valid=valid,schema_errors=errors)


def compare_fields(reference,rendered):
    rows=[]
    for key in ENUMS:
        a=reference.get('fields',{}).get(key,{})
        b=rendered.get('fields',{}).get(key,{})
        available=(reference.get('status') in {'valid','partial'} and rendered.get('status') in {'valid','partial'}
                   and a.get('validation_status')=='valid' and b.get('validation_status')=='valid')
        first,second=a.get('value'),b.get('value')
        if not available:status,reason='unavailable','Request/JSON/this field unavailable; other fields remain independent'
        elif 'unknown' in (first,second):status,reason='unknown','At least one side abstained'
        elif first==second:status,reason='satisfied','Comparable answers agree; correctness/GT is not established'
        else:status,reason='candidate_violated','Answers differ; require semantic/visibility/camera review'
        rows.append(dict(id=key,region_id='R2',group_id='bw_0074_R2_books',energy=ENERGY[key],
            reference_answer=first,render_answer=second,status=status,reason=reason,
            reference_field_error=a.get('error'),render_field_error=b.get('error'),
            reviewed=False,q=0.,score=None,value=None,scorable=False,usage='provisional/debug'))
    return rows


def request_payload(payload):
    body=deepcopy(payload)
    messages=body.get('messages',[])
    if len(messages)!=2 or messages[1].get('role')!='user':raise ValueError('Expected system/user messages')
    content=messages[1].get('content')
    if not isinstance(content,list) or len(content)!=3 or content[0]!={'type':'text','text':USER}:
        raise ValueError('Expected identical neutral prompt and two same-side images')
    sizes=[]
    for item in content[1:]:
        url=item.get('image_url',{}).get('url','');prefix='data:image/png;base64,'
        if item.get('type')!='image_url' or not url.startswith(prefix):raise ValueError('Actual PNG data required')
        try:
            raw=base64.b64decode(url[len(prefix):],validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format!='PNG':raise ValueError('PNG required')
                sizes.append(image.size);image.verify()
        except Exception as exc:raise ValueError('Invalid PNG payload') from exc
    if sizes[0]!=sizes[1] or max(sizes[0])>1024:raise ValueError('Full/marked grids must agree, max side 1024')
    if body.get('model')!=MODEL:raise ValueError('Unexpected model')
    body['messages'][0]=dict(role='system',content=SYSTEM)
    body.pop('response_format',None)
    body.update(temperature=.1,max_tokens=MAX_TOKENS)
    return body


def redact(value,key,image_tokens=()):
    """Reuse credential sanitization; also remove exact in-memory image echoes."""
    value=clean_response(value,key)
    if isinstance(value,dict):
        return {k:redact(v,key,image_tokens) for k,v in value.items()
                if k.lower().replace('-','_') not in {'headers','request_headers','authorization','proxy_authorization',
                                                     'api_key','x_api_key','access_token','refresh_token','secret'}}
    if isinstance(value,list):return [redact(v,key,image_tokens) for v in value]
    if isinstance(value,str):
        for token in image_tokens:
            value=value.replace(token,'[image payload redacted]').replace(token.replace('/','\\/'),'[image payload redacted]')
        value=re.sub(r'data:image/[^;,\s]+;base64,[A-Za-z0-9+/=\\\r\n]+','[image payload redacted]',value)
    return value


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);(output/'request_images').mkdir()
    frozen=read(SOURCE/'reference_groups_frozen.json')
    case=next(c for c in frozen['cases'] if c['scene_id']=='bw_0074')
    group=next(g for g in case['semantic_groups'] if g['group_id']=='bw_0074_R2_books')
    if case['region_id']!='R2' or group['region_id']!='R2':raise ValueError('Unexpected parent Region')
    audit=read(SOURCE/'bw_0074/pair_audit.json')
    a=Image.open(audit['reference_rgb']).convert('RGB')
    b,valid,transform=fit_render(Image.open(audit['render_rgb']),a.size)
    if (not np.array_equal(np.asarray(a),np.asarray(Image.open(SOURCE/'bw_0074/reference.png').convert('RGB')))
            or not np.array_equal(b,np.asarray(Image.open(SOURCE/'bw_0074/render.png').convert('RGB')))
            or transform!=audit['comparison_transform']):raise ValueError('Historical RGB pair/fit differs')
    mask=np.asarray(Image.open(case['roi_source']).convert('L'))>0
    cached_mask=np.asarray(Image.open(SOURCE/'bw_0074/fixed_roi.png').convert('L'))>0
    if not np.array_equal(mask,cached_mask) or list(mask.shape[::-1])!=case['image_size']:
        raise ValueError('Frozen R2 membership changed')
    for side in ('reference','render'):
        shutil.copyfile(SOURCE/'bw_0074'/(side+'.png'),output/(side+'.png'))
    shutil.copyfile(audit['render_rgb'],output/'render_native.png')
    shutil.copyfile(case['roi_source'],output/'R2.png')
    save(output/'pair_audit.json',audit)
    shutil.copyfile(SOURCE/'bw_0074/region_only.json',output/'region_only.json')
    save(output/'reference_contract.json',dict(scene_id='bw_0074',region_id='R2',group=group,
        frozen_source=str(SOURCE/'reference_groups_frozen.json'),roi_source=case['roi_source'],
        original_group_evidence=[e for e in case['atomic_evidence'] if e['group_id']==group['group_id']],
        questions=dict(
            present=dict(provenance='frozen_candidate',source_evidence='bw_0074_R2_books_presence'),
            shelf_sections=dict(provenance='exploratory',reason='Frozen evidence has no occupied shelf-compartment count'),
            arrangement=dict(provenance='exploratory_categorical_extension',source_evidence='bw_0074_R2_books_orientations',
                             reason='Frozen bool only says both orientations occur; no dominant-orientation/mixed threshold')),
        frozen_expected_answers_sent_to_model=False,reviewed=False,reliability=0.,
        root_prior_render_knowledge_disclosed=True,strict_blind_test=False))
    size=(1024,round(a.height*1024/a.width))
    request_mask=np.asarray(Image.fromarray(mask).resize(size,Image.Resampling.NEAREST))>0
    Image.fromarray(np.uint8(request_mask)*255).save(output/'request_R2.png')
    manifest={}
    for side in ('reference','render'):
        image=Image.open(output/(side+'.png')).convert('RGB').resize(size,Image.Resampling.LANCZOS)
        image.info.clear();full='request_images/'+side+'_full.png';image.save(output/full)
        pixels=np.asarray(image).copy();pixels[edges(request_mask)]=[255,170,0]
        outlined=Image.fromarray(pixels);draw=ImageDraw.Draw(outlined);x,y,_,_=box(request_mask)
        draw.text((x+4,y+4),'R2',fill='black',stroke_width=2,stroke_fill='white')
        marked='request_images/'+side+'_r2.png';outlined.save(output/marked)
        manifest[side]=dict(images=[full,marked],image_size=list(size),same_side_only=True)
    save(output/'inputs.json',dict(sides=manifest,common_grid=list(a.size),request_grid=list(size),
        roi_source=case['roi_source'],reference_roi_unchanged=True,full_context_preserved=True,
        no_black_mask=True,render_fit=transform,render_roi_not_relocated=True,reviewed=False))
    save(output/'protocol.json',dict(system=SYSTEM,user=USER,model=MODEL,temperature=.1,max_tokens=MAX_TOKENS,
        maximum_paid_requests=2,per_side_limit=1,automatic_retries=False,json_mode=False,
        region_definition='R2展示书架中的可辨认装订书籍；排除独立框画、柜体隔板及R3唱片。',
        region_definition_note='Exact frozen membership details stay local; only neutral supplied prompt plus R2 outline sent.',
        candidate_expected_answers_in_prompt=False,usage='provisional/debug',reviewed=False))
    save(output/'schema.json',SCHEMA)
    print('Prepared Reference/Render independently; no API request or credential read',flush=True)


def offline_checks(output):
    protocol=read(output/'protocol.json');inputs=read(output/'inputs.json')
    assert protocol['system']==SYSTEM and protocol['user']==USER
    mask=np.asarray(Image.open(output/'request_R2.png').convert('L'))>0
    from benchmark.vlm import VLMClient
    calls=[]
    class OfflineResponse:
        status_code=200
        def json(self):return dict(choices=[dict(message=dict(content='{"present":"unknown","shelf_sections":"unknown","arrangement":"unknown"}'),finish_reason='stop')])
    def post(url,*,json,**kwargs):
        body=request_payload(json);calls.append(body)
        assert kwargs['allow_redirects'] is False
        return OfflineResponse()
    # Fake key/transport only in memory. No client metadata writes into real ledger.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='book_group_offline_') as td:
        for side in ('reference','render'):
            client=VLMClient(Path(td)/(side+'.json'),api_key='synthetic-offline-only',base_url='https://offline.invalid/v1',model=MODEL,request_limit=1)
            result=client.call([output/p for p in inputs['sides'][side]['images']],USER,'offline_fixture',
                session=SimpleNamespace(post=post),max_tokens=MAX_TOKENS,token_parameter='max_tokens',retry_network=False)
            assert result['evaluation_status']=='answered'
            files=inputs['sides'][side]['images']
            full=np.asarray(Image.open(output/files[0]));marked=np.asarray(Image.open(output/files[1]))
            assert full.shape==marked.shape and list(full.shape[1::-1])==inputs['request_grid']
            # Label stays near the reference boundary; the object pixels are not masked black.
            assert np.mean(np.any(full!=marked,axis=2))<.03
    assert len(calls)==2 and all(c['messages'][0]['content']==SYSTEM for c in calls)
    assert all(c['messages'][1]['content'][0]['text']==USER for c in calls)
    import subprocess
    tests=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_group_vlm.py','-v'],
                         cwd=ROOT,capture_output=True,text=True,timeout=60)
    (output/'tests_offline.txt').write_text(tests.stdout+tests.stderr)
    if tests.returncode:raise RuntimeError('Offline parser/payload tests failed; no paid request authorized by this runner')
    save(output/'offline_checks.json',dict(passed=True,synthetic_transport_only=True,real_requests=0,
        no_credential_read=True,same_prompt_and_preprocessing=True,request_image_size=inputs['request_grid'],
        original_roi_unchanged=True,field_parser_tests='tests/test_group_vlm.py',unit_tests_exit_code=0,reviewed=False))


def request(output):
    import requests
    from requests.adapters import HTTPAdapter
    if read(output/'offline_checks.json').get('passed') is not True:
        raise ValueError('Offline checks must pass first')
    if (output/'vlm_requests.json').exists() or list(output.glob('*_attempt.json')) or (output/'stopped.json').exists():
        raise FileExistsError('Paid stage already started; no retry or rerun')
    config=configuration()  # Literal approved configuration, kept in memory.
    client=VLMClient(output/'vlm_requests.json',api_key=config['VLM_API_KEY'],base_url=config['VLM_BASE_URL'],
                     model=config['VLM_MODEL'],request_limit=2)
    manifest=read(output/'inputs.json')['sides']
    sys.path.insert(0,str(ROOT.parent/'BlenderWorld/scripts'))
    from ofox_tunnel import OfoxTunnel
    for side in ('reference','render'):
        reserve(output,side)
        result=dict(side=side,status='unavailable',answers=None,fields={},source='real_vlm',reviewed=False,usage='provisional/debug')
        image_tokens=[]
        try:
            with OfoxTunnel(ip='47.83.144.71') as tunnel:
                with requests.Session() as session:
                    tunnel.configure_session(session)
                    session.mount('https://',HTTPAdapter(max_retries=0));session.mount('http://',HTTPAdapter(max_retries=0))
                    calls=0
                    def post(url,*,json,**kwargs):
                        nonlocal calls
                        calls+=1
                        if calls!=1:raise ValueError('Only one HTTP attempt per side')
                        body=request_payload(json)
                        image_tokens.extend(item['image_url']['url'].split(',',1)[1] for item in body['messages'][1]['content'][1:])
                        try:
                            response=session.post(url,json=body,**kwargs)
                        except Exception as exc:
                            save(output/(side+'_provider_response.json'),dict(http_status=None,
                                network_error_type=type(exc).__name__,
                                network_error=redact(str(exc),client.key,image_tokens),reviewed=False))
                            raise
                        # Provider envelope is sanitized BEFORE the shared client's
                        # ledger sees model/usage/cost/content, not just afterward.
                        try:
                            clean_body=redact(response.json(),client.key,image_tokens)
                            raw_safe=__import__('json').dumps(clean_body,ensure_ascii=False)
                        except ValueError:
                            clean_body=None;raw_safe=redact(response.text,client.key,image_tokens)
                        save(output/(side+'_provider_response.json'),dict(http_status=response.status_code,
                            raw_response_text=raw_safe,redaction='Credentials and exact image echoes removed',reviewed=False))
                        def response_json():
                            if not isinstance(clean_body,dict):raise ValueError('Provider returned invalid/non-object JSON envelope')
                            return clean_body
                        return SimpleNamespace(status_code=response.status_code,json=response_json)
                    packet=client.call([output/p for p in manifest[side]['images']],USER,'bw_0074:R2:books:'+side,
                        session=SimpleNamespace(post=post),max_tokens=MAX_TOKENS,token_parameter='max_tokens',
                        retry_network=False,read_timeout=300)
            result['response']=redact(packet,client.key,image_tokens)
            if packet.get('evaluation_status')=='answered':
                result.update(parse_fields(packet['raw_answer']))
                if not result['answers']:
                    result.update(status='unavailable',error='No valid fields in parsed response; stop without another request')
            else:result['error']=redact(packet.get('error','Request unavailable'),client.key,image_tokens)
        except Exception as exc:
            result.update(error_type=type(exc).__name__,error=redact(str(exc),client.key,image_tokens))
        result=redact(result,client.key,image_tokens)
        save(output/(side+'_answers.json'),result)
        # Defense-in-depth check before ending the credential-bearing stage.
        for path in output.glob('*.json'):
            content=path.read_text()
            if client.key in content or any(token in content for token in image_tokens):
                raise RuntimeError('Sensitive-data output check failed')
        print(side+': '+result['status'],flush=True)
        if result['status'] not in {'valid','partial'}:
            save(output/'stopped.json',dict(side=side,reason='HTTP/whole-JSON failure; no retry or further request',reviewed=False))
            break


def report(output):
    packets={}
    for side in ('reference','render'):
        path=output/(side+'_answers.json')
        if path.exists():packets[side]=read(path)
        else:packets[side]=dict(side=side,status='unavailable',answers=None,fields={},reviewed=False,
                               error='Not attempted / stopped after an earlier failure',source='real_vlm')
    rows=compare_fields(packets['reference'],packets['render'])
    save(output/'verification_results.json',dict(scene_id='bw_0074',region_id='R2',group_id='bw_0074_R2_books',
        results=rows,formal_energy=None,reference_is_gt=False,reviewed=False,
        correspondence_state='Unknown; no per-member matching or confirmed absence',
        missing_policy='Non-detection inside fixed R2 does not establish global absence; Misplaced/Unknown remains possible'))
    ledger=read(output/'vlm_requests.json') if (output/'vlm_requests.json').exists() else []
    costs=[]
    for row in ledger:
        costs.append(dict(request_number=row['request_number'],purpose=row['purpose'],model=row['model'],
            returned_model=row.get('returned_model'),http_status=row.get('http_status'),
            usage=row.get('usage'),latency_seconds=row.get('latency_seconds'),actual_cost=row.get('actual_cost'),
            outcome=row['outcome'],automatic_network_retry_enabled=row['automatic_network_retry_enabled']))
    def token_total(key):
        values=[r.get('usage',{}).get(key) if isinstance(r.get('usage'),dict) else None for r in costs]
        return sum(values) if values and all(type(v) is int and v>=0 for v in values) else None
    summary=dict(actual_request_attempts=len(ledger),request_budget=2,
        prompt_tokens=token_total('prompt_tokens'),completion_tokens=token_total('completion_tokens'),total_tokens=token_total('total_tokens'),
        total_latency_seconds=sum(r.get('latency_seconds') or 0 for r in costs) if costs else None,
        actual_cost='unknown unless explicitly supplied per request',requests=costs,reviewed=False)
    save(output/'request_summary.json',summary)
    a=Image.open(output/'request_images/reference_r2.png').convert('RGB')
    b=Image.open(output/'request_images/render_r2.png').convert('RGB')
    panel_row([('Reference: fixed R2, books Group',a),('Historical Render: identical R2',b)],output/'comparison.png',680)
    contract=read(output/'reference_contract.json');visual=read(output/'region_only.json')
    display=[{k:r[k] for k in ('id','energy','reference_answer','render_answer','status','reference_field_error','render_field_error')} for r in rows]
    failure_rows=[dict(side=s,status=p['status'],error=p.get('error'),schema_errors=p.get('schema_errors')) for s,p in packets.items()]
    page='''<!doctype html><meta charset="utf-8"><title>Book Group VLM Verification / bw_0074 R2</title>
<style>body{font:16px system-ui;max-width:1450px;margin:24px auto;padding:0 18px;line-height:1.65}img{max-width:100%}.pair{display:flex;gap:12px}.pair>div{width:50%}table{width:100%;border-collapse:collapse;margin:16px 0}td,th{padding:8px;border:1px solid #bbb;text-align:left;vertical-align:top}.note{background:#fff0ce;padding:15px}pre{white-space:pre-wrap}a{color:#1759a0}</style>
<h1>bw_0074 / R2：首次真实书籍Group验证</h1>
<p class="note">真实VLM回答、程序比较、人工审核候选必须区分。Reference回答不是GT，回答一致不代表重建质量良好。所有候选reviewed=false，q=0，无正式Energy。历史相机未配准，仅provisional/debug。</p>
<p><a href="report.md">报告/复现</a> · <a href="reference_contract.json">Reference溯源</a> · <a href="reference_answers.json">Reference真实回答</a> · <a href="render_answers.json">Render真实回答（若已请求）</a> · <a href="verification_results.json">比较</a> · <a href="request_summary.json">Token/时间</a> · <a href="tests_offline.txt">离线测试</a></p>
<h2>无标记工作RGB与原生Render</h2><div class="pair"><div>Reference RGB<img src="reference.png"></div><div>Render：历史全图等比适配<img src="render.png"></div></div><p><a href="render_native.png">未经适配的原生Agent Render</a></p>
<h2>完全相同的Reference R2标记</h2><img src="comparison.png"><p>每次请求只发送一侧全图和标记图；未黑底遮罩。黄色边界由冻结Reference ROI缩放而来，没有移动Render ROI。右侧R3唱片排除。</p>
<h2>Group定义与问题来源</h2><p>'''+html.escape(contract['group']['scope'])+'</p>'+table([
        dict(field=k,provenance=v['provenance'],source=v.get('source_evidence'),note=v.get('reason')) for k,v in contract['questions'].items()])+'''
<h2>真实回答及确定性逐字段比较</h2>'''+table(display)+table(failure_rows)+'''
<p>原始message.content保存在两侧answers.response.raw_answer。Provider响应经脱敏重新序列化归档；不保存Key、认证Header或Base64请求正文。单个非法字段保留错误，其余合法字段独立比较。</p>
<h2>调用与资源</h2>'''+table(costs)+table([{k:summary[k] for k in ('actual_request_attempts','prompt_tokens','completion_tokens','total_tokens','total_latency_seconds')}])+'''
<h2>Region-only对照</h2>'''+table([dict(appearance=visual['appearance'],perceptual=visual['perceptual'],
        source='Cached same historical pair / frozen R2; no recomputation',group_score=None)])+'''
<p>Region Appearance反映整体像素差异；集合回答能指出类别、柜格覆盖类别或摆放方向，但三问不测书脊文字、封面内容、颜色/纹理、精确数量、间距或连续密度。“3+”存在饱和，不能判断具体位置或分散程度是否相同。</p>
<h2>人工审核清单</h2><ul><li>两侧是否将右侧R3唱片、独立框画封面误认为R2书籍？</li><li>柜格以清晰独立分区为单位，开放长搁板、隔板遮挡和视角差是否造成计数歧义？</li><li>upright/horizontal/mixed的“主要”口径未校准；两种方向存在不等于主导比例。</li><li>固定ROI外仍可能有移动后的书籍，区域内no不等于全场景Confirmed Missing。</li><li>Reference/Render相机未知或不同，不能认定是正式三维重建错误。</li><li>每个字段：□ Correct □ Needs Correction □ Uncertain。candidate_violated只作待审候选。</li></ul>'''
    review_path=output/'visual_review_candidates.json'
    question_table='<h2>两侧完全相同的三个问题</h2>'+table([
        dict(field=k,question=QUESTIONS[k],allowed_values=' / '.join(v)) for k,v in ENUMS.items()])
    page=page.replace('<h2>真实回答及确定性逐字段比较</h2>',question_table+'<h2>真实回答及确定性逐字段比较</h2>')
    raw_links=[s+'_provider_response.json' for s in ('reference','render') if (output/(s+'_provider_response.json')).exists()]
    page+='<p>'+ ' · '.join('<a href="'+p+'">'+p+'</a>' for p in raw_links)+'</p>'
    if review_path.exists():
        review=read(review_path)
        page+='<h2>真实回复之后的静态审核候选（非VLM新回复、非人工GT）</h2>'+table(review['items'])
        page+='<p>'+html.escape(review['scope_warning'])+'</p>'
    # A skipped side gets an explicit unavailable packet, never invented answers.
    for side in ('reference','render'):
        if not (output/(side+'_answers.json')).exists():save(output/(side+'_answers.json'),packets[side])
    (output/'comparison.html').write_text(page)
    changes=[r['id'] for r in rows if r['status']=='candidate_violated']
    narrative=f'''# 首次真实Group-level VLM Verification：bw_0074 / R2

仅书籍陈列集合bw_0074_R2_books。复用group_level_evidence_pilot中已冻结Reference合同、B2 R2 ROI和同Run真实Agent Render；未使用不存在的vlm_direct_grounding_bw0074目录，也没有修补无效历史Polygon。唱片属于R3，排除。

## Reference与问题来源

present复用冻结books_presence候选；shelf_sections是新增exploratory柜格覆盖问题；arrangement四分类是exploratory延伸。冻结books_orientations只说两方向均存在，不给“主要方向”比例或mixed阈值，不能把mixed当预期GT。采用用户给定中立System/User、两侧同一Prompt和枚举Schema；本地Reference期望没有进入请求。主代理已有历史Render知识，非严格盲测；没有按Render修改冻结证据或问题。

输入固定1258×855公共网格，同一ROI缩放至1024×696；每侧发送全图和R2轮廓标记图各一张、保留上下文。Render全图等比适配沿用历史参数，不按对象重对齐。原生Render另存render_native.png，最终blend同步及Reference相机未知，只能provisional/debug。

## 实际回答与比较

| 字段 | Reference | Render | 比较 |
| --- | --- | --- | --- |
'''+''.join(f'| {r["id"]} | {r["reference_answer"]} | {r["render_answer"]} | {r["status"]} |\n' for r in rows)+f'''
发生明确答案变化的字段：{changes or '无'}。保存的是模型实际回答，不是Reference GT。逐字段严格枚举校验：某字段非法/缺失即unavailable，不删除其他合法字段；unknown是明确弃权。整包语法、HTTP失败停止，不重试、不补答。未将任何候选变化转为正式Energy，score/value均null，q=0，reviewed=false。

调用记录：{summary['actual_request_attempts']}/2次；prompt tokens={summary['prompt_tokens']}，completion tokens={summary['completion_tokens']}，总tokens={summary['total_tokens']}；累计请求延迟={summary['total_latency_seconds']}秒。模型{MODEL}。费用只看供应商实际返回值，未返回则unknown，不估算。详细HTTP、Token、延迟和错误见request_summary.json及两侧provider_response.json（已脱敏）。不因HTTP 200判定Schema或语义可靠。

## 解释与人工待审

- 一次Reference/Render请求只能检查这对图的可用性，不能证明模型稳定或可靠；需要人工核对是否确实识别书籍、没有混入R3唱片。
- 柜格数是离散覆盖类别，不是连续Spatial位置。3+饱和，既不区分3和更多，也不说明书籍是否集中到同一侧。开放书架分区、遮挡、视角会影响判断。
- 排列是粗粒度Statistical/VQA分类，不是密度/面积。upright/horizontal/mixed未规定占比，少量横放书是否应判mixed存在语义歧义，必须审核。
- 两侧相同只代表这些问题未发现差异，不覆盖书封/书脊、逐本身份、精细分布和颜色纹理；两侧不同也可能来自可见性、相机或识别误差。
- 若区域内present=no，最多是可见区域的候选缺失；保留书籍移出固定R2的Misplaced/Unknown可能。没有建立新Object Matching系统或Confirmed Missing证据。

## Region-only对照与Energy条件

原有R2 Appearance={visual['appearance']:.6f}，直接复用、不重新计算；Perceptual仍N/A。本轮没有运行DINO/SAM/SLIC/GPU/Blender。

Group回答提供“是否书籍”“占用柜格类别”“方向类别”三个可审语义诊断入口，是Region像素差异没有直接给出的内容。新增问题数量不代表准确率提升。Semantic存在性可在人工核实两侧回答与可见范围后进一步研究映射；柜格Spatial和方向Statistical均需先审核操作定义、模型判读及离散分类到既有指标的适用性。当前没有校准误差映射，三项正式Energy全部N/A，无综合分数。

## 测试、边界与复现

付费前完成tests_offline.txt与offline_checks.json：严格JSON、逐字段保留、未知/错误、固定同侧图片、预处理及无重试。实际预算通过持久预留和VLMClient账本限制，每侧只发一次session.post，经OfoxTunnel；没有余额/模型列表/额外自检请求。凭证只在请求阶段内存读取，Provider元数据先脱敏再交给客户端写账本；不保存认证Header或请求图像Base64。

离线重放（只读已保存实际答案，不发请求）：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_vlm_verification.py replay --source {output} --output results/group_vlm_verification_bw0074_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p test_group_vlm.py -v
```

正式五能量、权重、Region Plan与ROI未改，未提交Git。所有候选仍reviewed:false。是否语义判读正确，仍需comparison.html逐字段人工审核；后续不自动扩展。
'''
    if review_path.exists():
        narrative+='\n## 静态审核候选（不是新增VLM回答或人工GT）\n\n'
        narrative+='\n'.join('- '+r['field']+'：'+r['assessment']+' '+r['uncertainty'] for r in review['items'])
        narrative+='\n\n'+review['scope_warning']+'\n'
    (output/'report.md').write_text(narrative)
    links=re.findall(r'(?:src|href)="([^"]+)"',page)
    assert all((output/link).is_file() for link in links)
    save(output/'validation.json',dict(passed=True,local_html_links=len(links),request_attempts=len(ledger),
        request_budget_respected=len(ledger)<=2,all_unreviewed=True,formal_scores_available=0,
        same_reference_roi=True,reviewed=False))


def replay(source,output):
    output.mkdir(parents=True,exist_ok=False);(output/'request_images').mkdir()
    for name in ('reference.png','render.png','render_native.png','R2.png','request_R2.png','pair_audit.json',
                 'region_only.json','reference_contract.json','inputs.json','protocol.json','schema.json','offline_checks.json','tests_offline.txt',
                 'reference_answers.json','render_answers.json','vlm_requests.json',
                 'reference_provider_response.json','render_provider_response.json','visual_review_candidates.json'):
        path=source/name
        if path.exists():shutil.copyfile(path,output/name)
    for path in (source/'request_images').glob('*.png'):shutil.copyfile(path,output/'request_images'/path.name)
    save(output/'offline_replay.json',dict(source=str(source),new_paid_requests=0,new_model_runs=0,
        note='Request ledger/Token/latency refer to original historical calls, not this offline replay',reviewed=False))
    report(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('prepare','check','request','report','replay'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='prepare':prepare(output)
    elif args.stage=='check':offline_checks(output)
    elif args.stage=='request':request(output)
    elif args.stage=='report':report(output)
    else:
        if args.source is None:parser.error('replay requires --source')
        replay(args.source.resolve(),output)
