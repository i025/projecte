"""Two authorized Region-only calls, then frozen A/B2 cache grounding.

Separate prepare/request/ground stages make offline reproduction non-billable.
No Agent, Blender, DINO, SAM, energy metric or model-verification execution.
"""
import argparse
import base64
from copy import deepcopy
import html
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import time
import unicodedata
from types import SimpleNamespace

import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.region_first_pilot import SYSTEM,USER,MODEL,region_request,location_window
from scripts.coarse_roi_experiment import rectangles,content_hints,coarse_polygons,polygon_loops,raster_polygons
from scripts.region_first_generalization import cached_candidates,panel_grid,write_csv
from scripts.region_grounding_experiment import read,save,method
from e_harness.benchmark_evidence import REGION_FIRST_SCHEMA,validate_region_first_plan,grounding_concepts,load_document
from benchmark.vlm import VLMClient

TASKS=('bw_9064','bw_0073')
FROZEN=ROOT/'results/region_first_generalization_checked/source_snapshot'


def check_frozen():
    paths=['scripts/coarse_roi_experiment.py','e_harness/benchmark_evidence.py']
    for name in paths:
        if (ROOT/name).read_bytes() != (FROZEN/Path(name).name).read_bytes():
            raise ValueError('Frozen source differs: '+name)
    return paths


def configuration():
    """Only literal VLM assignments, in memory; never source shell startup code."""
    result={}
    for line in Path('/home/xymo/.bashrc').read_text().splitlines():
        match=re.match(r'^\s*(?:export\s+)?(VLM_API_KEY|VLM_BASE_URL|VLM_MODEL)=(.*)$',line)
        if not match:continue
        values=shlex.split(match[2],comments=True)
        if len(values)==1 and not any(c in values[0] for c in ('$','`')):
            result[match[1]]=values[0]
    for key in ('VLM_API_KEY','VLM_BASE_URL','VLM_MODEL'):
        result.setdefault(key,os.environ.get(key,''))
    if not result['VLM_API_KEY']:raise ValueError('Configured credential unavailable')
    if result['VLM_BASE_URL'].rstrip('/')!='https://api.ofox.ai/v1':raise ValueError('Unexpected configured provider')
    if result['VLM_MODEL']!=MODEL:raise ValueError('Configured model differs from last successful model')
    return result


def sanitized(value,key):
    if isinstance(value,dict):
        return {k:sanitized(v,key) for k,v in value.items()
                if k.lower() not in {'authorization','proxy-authorization','api_key','access_token','refresh_token','secret'}}
    if isinstance(value,list):return [sanitized(v,key) for v in value]
    if isinstance(value,str):return re.sub(r'(?i)Bearer\s+\S+','[redacted]',value.replace(key,'[redacted]'))
    return value


def prepare(out):
    check_frozen();out.mkdir(parents=True,exist_ok=False);(out/'source_snapshot').mkdir()
    for name in check_frozen():shutil.copyfile(ROOT/name,out/'source_snapshot'/Path(name).name)
    manifest=read(ROOT/'results/multiscene_region_extraction/manifest.json')
    save(out/'protocol.json',dict(tasks=list(TASKS),system=SYSTEM,user=USER,model=MODEL,
        max_tokens=1500,temperature=.2,json_mode=False,maximum_paid_requests=2,
        per_image_limit=1,automatic_retries=False,verification_requests=0,
        grounding_max_side=1536,vlm_image_max_side=1024,reviewed=False,
        frozen_parameters=read(ROOT/'results/coarse_evaluation_roi_bw0074/B2_edge_polygons/diagnostics.json')['parameters']))
    save(out/'schema.json',REGION_FIRST_SCHEMA)
    for task in TASKS:
        folder=out/task;folder.mkdir();source=next(t for t in manifest['tasks'] if t['task_id']==task)
        original=Path(source['original_reference_image']);staged=Path(source['reference_image'])
        for name in ('input_json','task_json'):
            if read(source['provenance'][name])['task_id']!=task:raise ValueError('Reference task mismatch')
        if original.read_bytes()!=staged.read_bytes():raise ValueError('Reference association mismatch')
        with Image.open(original) as image:
            image=image.convert('RGB');native=list(image.size)
            if native!=source['image_size']:raise ValueError('Reference dimensions differ')
            image.thumbnail((1536,1536),Image.Resampling.LANCZOS);image.info.clear();image.save(folder/'reference.png')
        request_image=Image.open(original).convert('RGB');request_image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
        request_image.info.clear();request_image.save(folder/'request_image.png')
        save(folder/'input.json',dict(task_id=task,reference_rgb=str(original),provenance=source['provenance'],
            original_staged_bytes_equal=True,native_image_size=native,image_size=list(image.size),
            request_image_size=list(request_image.size),render_used=False,reviewed=False))
    print('Prepared two reference-only inputs; no network calls',flush=True)


def reserve(out,task):
    if task not in TASKS:raise ValueError('Unexpected task')
    ledger=out/'vlm_requests.json'
    records=read(ledger) if ledger.exists() else []
    if len(records)>=2:raise ValueError('Two-attempt request budget exhausted')
    save(out/task/'attempt_reserved.json',dict(task_id=task,per_image_limit=1,automatic_retry=False,reviewed=False))


def request(out):
    import requests
    from requests.adapters import HTTPAdapter
    check_frozen()
    if read(out/'offline_checks.json').get('passed') is not True:raise ValueError('Offline checks must pass first')
    config=configuration()
    client=VLMClient(out/'vlm_requests.json',api_key=config['VLM_API_KEY'],
        base_url=config['VLM_BASE_URL'],model=config['VLM_MODEL'],request_limit=2)
    sys.path.insert(0,str(ROOT.parent/'BlenderWorld/scripts'))
    from ofox_tunnel import OfoxTunnel
    for task in TASKS:
        folder=out/task
        if (folder/'vlm_plan.json').exists():raise FileExistsError('Plan exists; no additional paid request')
        reserve(out,task)
        try:
            with OfoxTunnel(ip='47.83.144.71') as tunnel:
                with requests.Session() as session:
                    tunnel.configure_session(session)
                    session.mount('https://',HTTPAdapter(max_retries=0))
                    def post(url,*,json,**kwargs):
                        payload=region_request(json);summary=deepcopy(payload)
                        summary['messages'][1]['content'][1]['image_url']['url']='[actual PNG data URL; request_image.png]'
                        save(folder/'request_parameters.json',dict(body=summary,image_file='request_image.png',
                            image_count=1,credentials_recorded=False))
                        response=session.post(url,json=payload,**kwargs)
                        try:body=response.json()
                        except ValueError:body=dict(non_json_response_text=response.text)
                        safe_body=sanitized(body,config['VLM_API_KEY'])
                        save(folder/'provider_response.json',dict(http_status=response.status_code,
                            body=safe_body,reviewed=False))
                        return SimpleNamespace(status_code=response.status_code,json=lambda:safe_body)
                    packet=client.call([folder/'request_image.png'],USER,task+':region_first_e2e',
                        session=SimpleNamespace(post=post),max_tokens=1500,token_parameter='max_tokens',
                        retry_network=False,read_timeout=300)
            result=dict(packet,status='unavailable',reviewed=False)
            if packet.get('evaluation_status')=='answered':
                try:
                    clean=validate_region_first_plan(packet['parsed_answer'])
                    save(folder/'vlm_plan.json',dict(regions=[dict(r,reviewed=False,reliability=0.) for r in clean['regions']],
                        reviewed=False,structure_valid=True,semantic_review='automatic_initial_review_pending',render_used=False))
                    result['status']='structure_valid'
                except (ValueError,KeyError,TypeError) as exc:result['schema_error']=str(exc)
            save(folder/'vlm_response.json',sanitized(result,config['VLM_API_KEY']))
            print(task+': '+result['status'],flush=True)
        except Exception as exc:
            if not (folder/'vlm_response.json').exists():
                save(folder/'vlm_response.json',dict(status='unavailable',error_type=type(exc).__name__,reviewed=False))
            print(task+': unavailable; see sanitized local record',flush=True)


def rectangle_from_plan(region,pool,size):
    """Existing noun matching + pilot context padding + unchanged location prior.

    Uses predicted cached mask bboxes, never their historical prompt_bbox or
    manifest region boxes. No vocabulary additions or scene-specific choices.
    """
    width,height=size;primary_terms=grounding_concepts(region['name'])
    content_terms=grounding_concepts(region['content'])
    primary=[c for c in pool if grounding_concepts(c['category'])&primary_terms]
    seeds=primary or [c for c in pool if grounding_concepts(c['category'])&content_terms]
    window=location_window(region['location'])
    note=dict(id=region['id'],name_concepts=sorted(primary_terms),content_concepts=sorted(content_terms),
        matched_candidate_ids=[c['id'] for c in seeds],positional_prior=window,reviewed=False)
    if not seeds or window is None:
        return None,dict(note,status='Grounding Failure',reason='No matched cached model evidence or no interpretable positional cue')
    boxes=np.asarray([c['bbox'] for c in seeds])
    box=np.r_[boxes[:,:2].min(0),boxes[:,2:].max(0)].astype(float)
    if not primary:box += [-width*.10,-height*.04,width*.10,height*.04]
    elif any('group' in c['category'] for c in primary):box += [-width*.04,-height*.04,width*.04,height*.04]
    if re.search('下方|below|underneath',region['content']):box[3]+=height*.15
    prior=np.asarray(window)*[width,height,width,height]
    box[:2]=np.maximum(box[:2],prior[:2]);box[2:]=np.minimum(box[2:],prior[2:])
    box=np.clip(np.rint(box),[0,0,0,0],[width,height,width,height]).astype(int).tolist()
    if box[0]>=box[2] or box[1]>=box[3]:return None,dict(note,status='Grounding Failure',reason='Cached model evidence conflicts with positional prior')
    return box,dict(note,status='candidate',bbox=box,reason='Approximate group extent; content completeness unverified')


def ground(out):
    check_frozen();summary=[]
    for task in TASKS:
        folder=out/task;image=Image.open(folder/'reference.png').convert('RGB');rgb=np.asarray(image)
        if not (folder/'vlm_plan.json').exists():
            save(folder/'grounding_status.json',dict(status='Planning Failure',reason='No valid actual VLM Plan; no replacement generated',reviewed=False))
            continue
        info=read(folder/'input.json');plan=read(folder/'vlm_plan.json');regions=plan['regions']
        pool=cached_candidates(task,info['native_image_size'],list(image.size))
        # Preserve inference provenance but never use prompt_bbox for geometry.
        save(folder/'cached_model_candidates.json',dict(candidates=[{k:c[k] for k in ('id','category','bbox','source_document','prompt_source')} for c in pool],reviewed=False))
        boxes=[];records=[]
        for region in regions:
            box,note=rectangle_from_plan(region,pool,list(image.size));boxes.append(box);records.append(note)
        indices=[i for i,box in enumerate(boxes) if box is not None]
        masks_a=np.zeros((len(regions),*rgb.shape[:2]),bool);masks_b=masks_a.copy()
        diagnostics=dict(status='No grounded input windows',parameters=read(out/'protocol.json')['frozen_parameters'])
        if indices:
            supported=[regions[i] for i in indices];valid_boxes=[boxes[i] for i in indices]
            masks_a[indices]=rectangles(rgb.shape[:2],valid_boxes)
            hints,hint_notes=content_hints(supported,pool,rgb.shape[:2],valid_boxes)
            t=time.perf_counter();result,diagnostics=coarse_polygons(rgb,valid_boxes,hints,snap=True)
            diagnostics.update(seconds=time.perf_counter()-t,supported_plan_indices=indices)
            if diagnostics['parameters']!=read(out/'protocol.json')['frozen_parameters']:raise ValueError('B2 parameter drift')
            masks_b[indices]=result
            save(folder/'content_hints.json',dict(regions=hint_notes,reviewed=False))
        save(folder/'rectangle_grounding.json',dict(regions=records,reviewed=False,
             source='Actual new VLM Plan + cached model predictions; no manual ROI substitution'))
        for key,masks in [('A_rectangles',masks_a),('B2_frozen',masks_b)]:
            stats=method(folder,key,rgb,regions,masks,source=str(folder/'vlm_plan.json'))
            stats.update(task_id=task,planned_roi_count=len(regions),grounded_roi_count=len(indices))
            summary.append(stats)
            loops=[polygon_loops(mask) for mask in masks]
            for mask,polygons in zip(masks,loops):np.testing.assert_array_equal(mask,raster_polygons(mask.shape,polygons))
            save(folder/key/'polygons.json',dict(image_size=list(image.size),regions=[dict(id=r['id'],polygons=p,reviewed=False) for r,p in zip(regions,loops)]))
            evidence_path=folder/key/'evidence.json';doc=read(evidence_path)
            for i,row in enumerate(doc['regions']):
                row.update(representation='coarse_evaluation_roi',semantic_mask_available=False,
                    localization_status='candidate_content_unverified' if indices and i in indices else 'Grounding Failure',
                    grounding_reason=records[i]['reason'])
            evidence_path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
            loaded=load_document(evidence_path)
            assert all(r['reviewed'] is False and r['reliability']==0 for r in loaded['regions'])
        save(folder/'B2_frozen/diagnostics.json',diagnostics)
        single=folder/'per_region';single.mkdir()
        for i,row in enumerate(regions):
            panel_grid([('Reference RGB',image),('A: '+row['id'],Image.open(folder/'A_rectangles'/(row['id']+'_overlay.png'))),
                ('B2: '+row['id'],Image.open(folder/'B2_frozen'/(row['id']+'_overlay.png'))),
                ('B2 unassigned',Image.open(folder/'B2_frozen/unassigned_overlay.png'))],single/(row['id']+'.png'))
        save(folder/'grounding_status.json',dict(status='candidates_available',planned=len(regions),grounded=len(indices),
            failures=[r for r in records if r['status']=='Grounding Failure'],reviewed=False))
    if summary:write_csv(out/'geometry_summary.csv',summary)
    check_frozen();print('Grounding finished; no model calls or scoring',flush=True)


def wrapped(text,units=52):
    lines=[];line='';used=0
    for char in text:
        n=2 if unicodedata.east_asian_width(char) in ('W','F') else 1
        if used+n>units:lines.append(line);line='';used=0
        line+=char;used+=n
    if line:lines.append(line)
    return lines


def comparison_svg(folder,regions):
    """Original Chinese plan is SVG text, rendered with client-side font fallback.

    Embedded PNGs keep this single figure portable without downloading fonts.
    """
    image=Image.open(folder/'reference.png');width=760;picture_h=round(image.height*width/image.width)
    lines=['实际 VLM Region Plan — 自动候选，reviewed:false','']
    for row in regions:
        lines+=wrapped(row['id']+' '+row['name'])+wrapped('位置：'+row['location'])+wrapped('内容：'+row['content'])+['']
    cell_h=max(picture_h+48,70+len(lines)*27)
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width*2}" height="{cell_h*2}" viewBox="0 0 {width*2} {cell_h*2}">',
            '<rect width="100%" height="100%" fill="#17212f"/>']
    for x,y,title,path in [(0,0,'Reference RGB',folder/'reference.png'),
        (0,cell_h,'A — Coarse Rectangle ROI',folder/'A_rectangles/overlay.png'),
        (width,cell_h,'B2 — Frozen Coarse Polygon ROI',folder/'B2_frozen/overlay.png')]:
        data=base64.b64encode(path.read_bytes()).decode('ascii')
        result.append(f'<text x="{x+14}" y="{y+30}" fill="white" font-family="sans-serif" font-size="23">{html.escape(title)}</text>')
        result.append(f'<image x="{x}" y="{y+48}" width="{width}" height="{cell_h-48}" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{data}"/>')
    for i,line in enumerate(lines):
        result.append(f'<text x="{width+20}" y="{35+i*27}" fill="white" font-family="sans-serif" font-size="21">{html.escape(line)}</text>')
    result.append('</svg>');(folder/'comparison.svg').write_text('\n'.join(result))


def present(out):
    check_frozen();body=['<!doctype html><meta charset="utf-8"><title>Region-first end-to-end generalization</title>',
      '<style>body{font:16px sans-serif;margin:24px;background:#f3f5f8;color:#17212f}img{max-width:100%;height:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{padding:10px;vertical-align:top;border:1px solid #ccd2da}pre{white-space:pre-wrap}.failure{background:#ffe6e4}section{margin-bottom:45px}li{margin-bottom:6px}</style>',
      '<h1>Region-first：真实 VLM Plan → 矩形 / 冻结 B2</h1>',
      '<p>全部候选 reviewed:false。没有运行 SAM/DINO、Agent、Blender、能量评分或局部扰动。N/A 表示定位失败，不能解释为零误差。</p>',
      '<p><a href="report.md">报告</a> · <a href="initial_review.json">自动初审与失败记录</a> · <a href="vlm_requests.json">实际请求和 Token</a> · <a href="geometry_summary.csv">辅助几何统计</a></p>']
    initial=read(out/'initial_review.json')['tasks'] if (out/'initial_review.json').exists() else {}
    for task in TASKS:
        folder=out/task
        body.append('<section><h2>'+task+'</h2>')
        if not (folder/'vlm_plan.json').exists():
            body.append('<p class="failure">Planning Failure：没有合法 Plan，不生成替代区域。</p></section>');continue
        regions=read(folder/'vlm_plan.json')['regions'];records=read(folder/'rectangle_grounding.json')['regions']
        comparison_svg(folder,regions)
        body.append('<p><a href="'+task+'/comparison.svg">独立四面板对照图（原始中文 Plan）</a> · <a href="'+task+'/vlm_plan.json">实际 Plan JSON</a> · <a href="'+task+'/provider_response.json">脱敏原始响应</a></p>')
        plan_html='<ol>'+''.join('<li><b>'+html.escape(r['id']+' '+r['name'])+'</b><br>'+html.escape(r['location'])+'<br>'+html.escape(r['content'])+'</li>' for r in regions)+'</ol>'
        body.append('<table><tr><th>Reference RGB</th><th>实际 VLM Region Plan</th><th>A Rectangle</th><th>Frozen B2</th></tr><tr><td><img src="'+task+'/reference.png"></td><td>'+plan_html+'</td><td><img src="'+task+'/A_rectangles/overlay.png"></td><td><img src="'+task+'/B2_frozen/overlay.png"></td></tr></table>')
        body.append('<h3>逐 Region 内容完整性对照</h3>')
        for row,record in zip(regions,records):
            unavailable=record['status']=='Grounding Failure'
            state='N/A — Grounding Failure' if unavailable else 'Candidate — completeness unverified'
            image=Image.open(folder/'reference.png').convert('RGB')
            # Presentation only: these captions do not change saved geometry.
            panel_grid([('Reference RGB',image),('A '+row['id']+': '+('N/A' if unavailable else 'candidate'),Image.open(folder/'A_rectangles'/(row['id']+'_overlay.png'))),
                ('B2 '+row['id']+': '+('N/A' if unavailable else 'candidate'),Image.open(folder/'B2_frozen'/(row['id']+'_overlay.png'))),
                ('B2 unassigned',Image.open(folder/'B2_frozen/unassigned_overlay.png'))],folder/'per_region'/(row['id']+'.png'))
            body.append('<h4>'+html.escape(row['id']+' '+row['name'])+'</h4><p>'+html.escape(row['content'])+'</p><p class="'+('failure' if unavailable else '')+'">'+state+' · '+html.escape(record['reason'])+'</p>')
            review=next((r for r in initial.get(task,{}).get('regions',[]) if r['id']==row['id']),None)
            if review:
                body.append('<p><b>自动初审：</b>'+html.escape(' / '.join(review['failure_categories']))+'</p><p>A：'+html.escape(review['A_completeness'])+'<br>B2：'+html.escape(review['B2_completeness'])+'<br>'+html.escape(review['comparison'])+'</p>')
            body.append('<p><a href="'+task+'/per_region/'+row['id']+'.png">单区独立对照图</a></p><table><tr><th>Reference</th><th>A</th><th>B2</th></tr><tr><td><img src="'+task+'/reference.png"></td><td><img src="'+task+'/A_rectangles/'+row['id']+'_overlay.png"></td><td><img src="'+task+'/B2_frozen/'+row['id']+'_overlay.png"></td></tr></table>')
        body.append('<p><a href="'+task+'/rectangle_grounding.json">矩形定位关联依据</a> · <a href="'+task+'/B2_frozen/diagnostics.json">冻结 B2 决策</a></p></section>')
    (out/'comparison.html').write_text('\n'.join(body))


def replay(out,source):
    """Offline replay of saved successful/failing responses; no request stage."""
    prepare(out)
    save(out/'replay_info.json',dict(source=str(source),new_api_calls=0,reviewed=False))
    for task in TASKS:
        for name in ('vlm_plan.json','vlm_response.json','provider_response.json'):
            path=source/task/name
            if path.exists():shutil.copyfile(path,out/task/name)
    for name in ('initial_review.json','report.md','vlm_requests.json'):
        if (source/name).exists():shutil.copyfile(source/name,out/name)
    ground(out);present(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','request','ground','present','replay'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.stage=='replay':
        if args.source is None:parser.error('replay requires --source')
        replay(args.output.resolve(),args.source.resolve())
    else:globals()[args.stage](args.output.resolve())
