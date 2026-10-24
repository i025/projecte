"""Small reference-only experiment. No Agent, Blender, SAM inference or scoring.

Phases write new files only. VLM requests use the established gateway with a
persistent four-attempt budget; credentials stay in inherited environment.
"""
import argparse
import csv
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_evidence import (merge_slic_regions,validate_vlm_region_response,
    validate_region_hierarchy,load_document,local_dino_extractor,coverage_audit,reliability)
from benchmark.vlm import VLMClient
from compare_region_segmentation import boundary,colors,bbox

SOURCE=ROOT/'results/multiscene_region_extraction'
TASKS=('bw_9064','bw_0074')
PLAN_SYSTEM='你是图像评测证据规划器。只根据提供的 RGB 图像提取可观察内容。区分连续区域、重复元素集合和重要独立物体。不要猜测不可见内容。不要进行像素分割。存在歧义时标记 unknown。只输出 JSON。'
PLAN_USER='''分析图片，输出：
1. 最多12个重要 Regions，包括连续区域或重复元素集合；
2. 最多12个 Salient Anchors，仅选择明确且重要的物体；
3. 明确的区域包含关系及重要空间关系；
4. 哪些 Anchor 需要精细 Mask。
每项给出简短名称、位置描述及选择原因。只输出 JSON，不要解释。
不要重复列举大量相似小物体；重复元素优先用集合。不要输出置信概率、bbox 或 Mask。
不要因分割模型未检测到而断言不存在。不要输出推理过程。
严格使用结构 {"regions":[{"id":"r1","name":"short English name","kind":"continuous|collection|unknown","location":"short English location","reason":"简短原因"}],"anchors":[{"id":"a1","name":"short English name","location":"short English location","reason":"简短原因","need_mask":true}],"relations":[{"subject":"已有ID","predicate":"关系","object":"已有ID"}],"uncertain":["简短歧义"]}。
关系仅限 left_of,right_of,above,below,in_front_of,behind,on,inside,contains,beside,attached_to,overlap。
示例中的名字不是图片内容，必须观察图片。'''
GROUP_SYSTEM='你是视觉区域分组助手。根据原始 RGB 和编号区域图，识别属于同一语义结构的区域集合。只引用已有区域 ID，不创造不存在的区域。允许不连续的区域属于同一集合。无法确认时保留 unknown。只输出 JSON。'
GROUP_USER='''根据原图和候选区域编号，建议：
1. 哪些 Region IDs 应组成同一个语义集合；
2. 集合的简短名称；
3. 哪些候选区域存在明显混合内容，不宜合并。
只输出 JSON，不要解释。最多12个集合。
结构：{"groups":[{"name":"short English name","region_ids":["已有ID"]}],"uncertain_region_ids":["已有ID"]}。
未编号的灰色部分不参与本次分组。不要把混合内容的区域加入语义集合。
允许弃权，不要求覆盖全图。不要输出 bbox、Mask、置信概率或推理过程。'''


def read(path): return json.loads(Path(path).read_text())


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f: json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def font(size=19):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',size)


def overlay(image,labels,path,numbered=None):
    array=np.asarray(image)
    tinted=np.uint8(.72*array+.28*colors(labels))
    tinted[boundary(labels)]=[255,190,20]
    if numbered is not None:
        hidden=~np.isin(labels,list(numbered))
        tinted[hidden]=np.uint8(.35*array[hidden]+.65*np.array([110,110,110]))
    result=Image.fromarray(tinted); draw=ImageDraw.Draw(result)
    for key,name in (numbered or {}).items():
        distance=ndimage.distance_transform_edt(labels==key)
        y,x=np.unravel_index(np.argmax(distance),labels.shape)
        x=np.clip(x,38,result.width-38);y=np.clip(y,16,result.height-16)
        draw.text((int(x),int(y)),name,font=font(21),anchor='mm',fill='white',stroke_width=3,stroke_fill='black')
    result.save(path)


def native_labels(labels,size):
    return np.asarray(Image.fromarray(labels.astype(np.int32)).resize(size,Image.Resampling.NEAREST),np.int32)


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    manifest=read(SOURCE/'manifest.json')
    tasks=[]
    for row in manifest['tasks']:
        if row['task_id'] not in TASKS: continue
        folder=out/row['task_id'];folder.mkdir()
        original,staged=Path(row['original_reference_image']),Path(row['reference_image'])
        task=read(row['provenance']['task_json']); inp=read(row['provenance']['input_json'])
        if task['task_id']!=row['task_id'] or inp['task_id']!=row['task_id']: raise ValueError('Task provenance mismatch')
        if original.read_bytes()!=staged.read_bytes(): raise ValueError('Original RGB differs from staged reference')
        image=Image.open(original).convert('RGB')
        if list(image.size)!=row['image_size']: raise ValueError('RGB dimensions changed')
        shutil.copyfile(original,folder/('reference'+original.suffix))
        input_rgb=image.copy();input_rgb.thumbnail((1280,1280),Image.Resampling.LANCZOS)
        input_rgb.save(folder/'vlm_reference.png')
        tasks.append(dict(row,local_reference=str(Path(row['task_id'])/('reference'+original.suffix)),
                          vlm_reference=str(Path(row['task_id'])/'vlm_reference.png'),
                          vlm_image_size=list(input_rgb.size),original_staged_bytes_equal=True))
    save(out/'manifest.json',dict(tasks=tasks,source=str(SOURCE),render_used=False,
         reviewed=False,request_limit=4,per_image_request_limit=2))


def anchor_guards(task,working_size):
    doc=SOURCE/'anchor_candidates'/task/'sam3_visual/candidates.json'
    rows=read(doc)['anchors']
    return [np.asarray(Image.open(doc.parent/r['mask']).resize(working_size,Image.Resampling.NEAREST))>0 for r in rows]


def merge(out,feature_aware=False):
    manifest=read(out/'manifest.json')
    # One extractor load for both images, local weights only, small CPU batches.
    if feature_aware:
        import torch
        torch.set_num_threads(2); torch.set_num_interop_threads(1)
        start=time.monotonic()
        extract=local_dino_extractor('/home/xymo/models/dinov2',device='cpu')
        load_seconds=time.monotonic()-start
    for row in manifest['tasks']:
        task=row['task_id'];folder=out/task/('feature' if feature_aware else 'light')
        folder.mkdir(exist_ok=False)
        with np.load(SOURCE/'methods'/task/'slic_200/dense_labels.npz',allow_pickle=False) as archive:
            labels=archive[archive.files[0]].copy()
        image=Image.open(SOURCE/row['working_image']).convert('RGB')
        if labels.shape!=np.asarray(image).shape[:2]: raise ValueError('SLIC working-grid mismatch')
        features=None; feature_seconds=0.
        if feature_aware:
            start=time.monotonic(); crops=[]
            array=np.asarray(image)
            for key in np.unique(labels):
                mask=labels==key; x0,y0,x1,y1=bbox(mask)
                crop=array[y0:y1,x0:x1].copy(); crop[~mask[y0:y1,x0:x1]]=127
                crops.append(Image.fromarray(crop))
            features=np.concatenate([extract(crops[i:i+8]) for i in range(0,len(crops),8)])
            np.savez_compressed(folder/'dino_region_features.npz',features=features)
            feature_seconds=time.monotonic()-start
        start=time.monotonic()
        guards=anchor_guards(task,image.size)
        result=merge_slic_regions(np.asarray(image),labels,features=features,anchor_masks=guards)
        seconds=time.monotonic()-start
        # Re-run only deterministic lightweight graph operations, never DINO.
        repeat=merge_slic_regions(np.asarray(image),labels,features=features,anchor_masks=guards)
        if not all(np.array_equal(v,repeat['levels'][k]) for k,v in result['levels'].items()):
            raise ValueError('Non-deterministic merging')
        np.savez_compressed(folder/'working_labels.npz',**result['levels'])
        stats=[]
        original_size=tuple(row['image_size'])
        for level,grid in result.pop('levels').items():
            native=native_labels(grid,original_size)
            Image.fromarray(native.astype(np.uint16)).save(folder/(level+'_labels.png'))
            overlay(image,grid,folder/(level+'_overlay.png'))
            leak=0;split=0
            for guard in guards:
                counts=np.bincount(grid.ravel(),weights=guard.ravel())
                areas=np.bincount(grid.ravel())
                leak+=int(np.minimum(counts,areas-counts).sum())
                split+=int((counts>0).sum())
            stats.append(dict(level=level,region_count=len(np.unique(grid)),coverage=float((native>=0).mean()),
                              mixed_anchor_pixels_proxy=leak,anchor_intersecting_regions=split,
                              coverage_grid=list(original_size)))
            if level=='coarse' and not feature_aware:
                areas=np.bincount(grid.ravel());selected=sorted(np.argsort(-areas)[:32].tolist())
                mapping={int(k):f'c{k+1:03d}' for k in selected}
                overlay(image,grid,folder/'numbered_coarse.png',mapping)
                numbered=Image.open(folder/'numbered_coarse.png')
                numbered.thumbnail((1280,1280),Image.Resampling.LANCZOS)
                numbered.save(folder/'vlm_numbered.png')
                save(folder/'group_candidates.json',dict(ids=list(mapping.values()),
                     labels={value:key for key,value in mapping.items()},max_candidates=32,
                     visible_fraction=float(np.isin(grid,selected).mean()),
                     selection='32 largest Coarse regions if needed; unshown cells remain Unknown',reviewed=False))
        save(folder/'merge.json',dict(result,statistics=stats,algorithm_seconds=seconds,
             feature_seconds=feature_seconds,dino_load_seconds=load_seconds if feature_aware else 0.,
             dino_source='local DINOv2 masked bounding-crop CLS; area-weighted after merging' if feature_aware else None,
             repeatable=True,original_unchanged=True,device='cpu',cpu_threads=2,
             gpu_used=False,source_labels=str(SOURCE/'methods'/task/'slic_200/dense_labels.npz'),
             reviewed=False,render_used=False))
        print(task,folder.name,[(s['level'],s['region_count']) for s in stats],flush=True)


def balance(out,label):
    import requests
    if (out/'vlm_final_requests.json').exists(): raise ValueError('Final budget closed: no further network calls')
    filename=out/('balance_'+label+'.json')
    if filename.exists(): raise FileExistsError(filename)
    record=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),label=label,
                documentation='https://ofox.ai/zh/docs/api/openapi/balance',
                scope='account-wide; other concurrent API usage may contribute to differences')
    if urlsplit(os.environ.get('VLM_BASE_URL','')).hostname!='api.ofox.ai':
        record.update(status='unavailable',reason='Configured gateway is not the documented Ofox host')
    elif not os.environ.get('VLM_API_KEY'):
        record.update(status='unavailable',reason='VLM_API_KEY unavailable')
    else:
        start=time.monotonic()
        try:
            with requests.Session() as session:
                response=session.get('https://api.ofox.ai/v1/user/balance',
                    headers={'Authorization':'Bearer '+os.environ['VLM_API_KEY']},timeout=(10,30),allow_redirects=False)
            record['http_status']=response.status_code
            if response.status_code!=200: raise ValueError('HTTP_'+str(response.status_code))
            data=response.json()
            # Only the documented account counters, never response headers or identity.
            for k in ('balance','total','used'):
                if isinstance(data.get(k),bool) or not isinstance(data.get(k),(int,float)) or not np.isfinite(data[k]):
                    raise ValueError('Invalid balance response')
            record.update(status='available',**{k:data[k] for k in ('is_active','balance','total','used','currency')})
        except requests.RequestException as exc: record.update(status='unavailable',reason=type(exc).__name__)
        except (ValueError,KeyError) as exc: record.update(status='unavailable',reason=str(exc)[:100])
        record['seconds']=time.monotonic()-start
    save(filename,record)
    print('balance',label,record['status'],flush=True)


def vlm(out,task,stage):
    import requests
    if (out/'vlm_final_requests.json').exists(): raise ValueError('Final budget closed: no further VLM calls')
    folder=out/task;destination=folder/('vlm_'+stage+'.json')
    if destination.exists(): raise FileExistsError(destination)
    if task not in TASKS: raise ValueError('Task is not authorized')
    ledger=out/'vlm_requests.json'
    records=read(ledger) if ledger.exists() else []
    if sum(r['purpose'].startswith(task+':') for r in records)>=2:
        raise ValueError('Per-image request budget exhausted')
    system,prompt=(PLAN_SYSTEM,PLAN_USER) if stage=='plan' else (GROUP_SYSTEM,GROUP_USER)
    images=[folder/'vlm_reference.png']; ids=[]
    if stage=='group':
        plan=read(folder/'vlm_plan.json')
        if plan['status']!='available':
            save(destination,dict(status='unavailable',reason='Planning request unavailable; no automatic retry',reviewed=False))
            return
        candidate=read(folder/'light/group_candidates.json');ids=candidate['ids']
        prompt+='\n可用 ID（只能引用这些）：'+', '.join(ids)
        images.append(folder/'light/vlm_numbered.png')
    save(folder/('prompt_'+stage+'.json'),dict(system=system,user=prompt,
         image_files=[str(x.relative_to(out)) for x in images],image_sizes=[list(Image.open(x).size) for x in images],
         image_payload='actual PNG data URL, not a filesystem path',render_used=False))

    class ReferenceSession(requests.Session):
        def post(self,url,*,json,**kwargs):
            # The gateway already implements credentials, JSON mode, safe errors,
            # limits and accounting. Its supported Session hook customizes prompts.
            json['messages'][0]['content']=system
            json['temperature']=.2
            return super().post(url,json=json,**kwargs)

    try:
        client=VLMClient(ledger,request_limit=4)
        with ReferenceSession() as session:
            packet=client.call(images,prompt,task+':'+stage,max_tokens=3000 if stage=='plan' else 1800,
                               session=session,retry_network=False,read_timeout=120)
        result=dict(packet,status='unavailable',reviewed=False,render_used=False)
        if packet['evaluation_status']=='answered':
            try:
                result['evidence']=validate_vlm_region_response(packet['parsed_answer'],stage,ids)
                result['status']='available'
            except (ValueError,TypeError,KeyError) as exc:
                result['validation_error']=str(exc)[:200]
    except ValueError:
        result=dict(status='unavailable',reason='VLM configuration unavailable or invalid',reviewed=False)
    save(destination,result)
    print(task,stage,result['status'],result.get('validation_error',result.get('error','')),flush=True)


def final_vlm(out):
    """One explicitly authorized final attempt, combining both scenes to save calls."""
    import requests
    from contextlib import ExitStack
    sys.path.insert(0,str(ROOT.parent/'BlenderWorld/scripts'))
    from ofox_tunnel import OfoxTunnel
    destination=out/'vlm_final.json'
    if destination.exists() or (out/'vlm_final_requests.json').exists():
        raise FileExistsError('The final-attempt budget has already been reserved')
    cached=read(ROOT.parent/'BlenderWorld/logs/evaluation/provider-models.json')
    def find_model(value):
        if isinstance(value,dict):
            if value.get('id')=='openai/gpt-5.1': return value
            for child in value.values():
                found=find_model(child)
                if found:return found
        elif isinstance(value,list):
            for child in value:
                found=find_model(child)
                if found:return found
    model=find_model(cached)
    if not model or 'image' not in model.get('architecture',{}).get('input_modalities',[]):
        raise ValueError('Cached full provider model ID with image capability not found')
    images=[];allowed={}
    for task in TASKS:
        folder=out/task
        row=next(r for r in read(out/'manifest.json')['tasks'] if r['task_id']==task)
        raw=Image.open(out/row['local_reference']).convert('RGB')
        selected=read(folder/'light/group_candidates.json')
        with np.load(folder/'light/working_labels.npz',allow_pickle=False) as archive:
            grid=archive['coarse']
        overlay(Image.open(SOURCE/row['working_image']).convert('RGB'),grid,
                folder/'numbered_for_final.png',{v:k for k,v in selected['labels'].items()})
        numbered=Image.open(folder/'numbered_for_final.png').convert('RGB')
        raw.thumbnail((1024,760),Image.Resampling.LANCZOS)
        numbered=numbered.resize(raw.size,Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',(raw.width*2,raw.height+42),'white')
        canvas.paste(raw,(0,42));canvas.paste(numbered,(raw.width,42))
        draw=ImageDraw.Draw(canvas)
        draw.text((12,7),task+' | Reference RGB',font=font(23),fill='black')
        draw.text((raw.width+12,7),task+' | Coarse IDs (algorithm only)',font=font(23),fill='black')
        canvas.save(folder/'vlm_final_input.png');images.append(folder/'vlm_final_input.png')
        allowed[task]=read(folder/'light/group_candidates.json')['ids']
    prompt=('由于只剩一次请求，同时完成两张图片的规划与区域分组。每张图左侧为原始 Reference RGB 缩小副本，'
            '右侧为同一张图的算法编号候选；灰色未编号部分不参与分组。两个任务的 ID 各自独立，不得跨图片引用。\n'
            +PLAN_SYSTEM+'\n'+PLAN_USER+'\n'+GROUP_SYSTEM+'\n'+GROUP_USER+
            '\n为控制输出，每张图 Regions 和 Anchors 各最多8个，groups 最多8个，reason 不超过15字。'
            'name/location 用简短英文。只输出 {"scenes":{"bw_9064":{"plan":{规划结构},"group":{分组结构}},'
            '"bw_0074":{"plan":{规划结构},"group":{分组结构}}}}。\n可用编号：'+json.dumps(allowed))
    system='你是参考 RGB 证据规划与区域分组助手。只分析提供的图片，不推测不可见内容，不生成像素边界，不输出推理过程，只输出 JSON。'
    save(out/'vlm_final_prompt.json',dict(system=system,user=prompt,
         image_files=[str(p.relative_to(out)) for p in images],image_sizes=[list(Image.open(p).size) for p in images],
         reference_only=True,agent_render_used=False,temperature=.2,max_tokens=6000,
         deviation='Planning and grouping combined in one request because the user authorized one remaining attempt.'))
    save(out/'vlm_budget.json',dict(original_experiment_limit=4,local_prior_attempts=len(read(out/'vlm_requests.json')),
         user_reported_cross_conversation_prior_attempts=5,user_latest_total_limit=6,
         remaining_authorized_attempts=1,final_ledger='vlm_final_requests.json',retries=0,
         note='External five-attempt count is user-reported, not fabricated local request records.'))
    class FinalSession(requests.Session):
        def post(self,url,*,json,**kwargs):
            json['messages'][0]['content']=system;json['temperature']=.2
            return super().post(url,json=json,**kwargs)
    client=VLMClient(out/'vlm_final_requests.json',model=model['id'],request_limit=1)
    with OfoxTunnel(ip='47.83.144.71') as tunnel:
        with FinalSession() as session:
            tunnel.configure_session(session)
            packet=client.call(images,prompt,'two_reference_scenes:final_plan_and_group',max_tokens=6000,
                 session=session,retry_network=False,read_timeout=300,token_parameter='max_tokens')
    result=dict(packet,status='unavailable',reviewed=False,scenes={},transport='provided OfoxTunnel; end-to-end verified TLS')
    if packet['evaluation_status']=='answered':
        scenes=packet['parsed_answer'].get('scenes',{})
        for task in TASKS:
            evidence={}
            for stage in ('plan','group'):
                try:
                    clean=validate_vlm_region_response(scenes[task][stage],stage,allowed[task])
                    evidence[stage]=dict(status='available',evidence=clean,reviewed=False)
                except (ValueError,KeyError,TypeError) as exc:
                    evidence[stage]=dict(status='unavailable',validation_error=str(exc)[:180],reviewed=False)
            result['scenes'][task]=evidence
        result['status']='available' if all(v['status']=='available' for s in result['scenes'].values() for v in s.values()) else 'partial'
    save(destination,result)
    print('final_request',result['status'],result.get('error',''),flush=True)


def api_evidence(out,task,stage):
    if (out/'vlm_final.json').exists():
        return read(out/'vlm_final.json').get('scenes',{}).get(task,{}).get(stage,
                    dict(status='unavailable',reason='Final response lacks this scene/stage'))
    path=out/task/('vlm_'+stage+'.json')
    return read(path) if path.exists() else dict(status='unavailable',reason='Not requested')


def normalize_name(value):
    words=re.sub('[^a-z0-9 ]',' ',value.lower()).split()
    ignored={'a','the','left','right','round','small','large','wooden','transparent','dining','computer'}
    name=' '.join(w for w in words if w not in ignored)
    return {'potted plant':'plant','fridge':'refrigerator','couch':'sofa','television':'monitor'}.get(name,name)


def build(out):
    manifest=read(out/'manifest.json');hierarchy=dict(tasks=[],reviewed=False,formal_score=False)
    vlm_data=dict(tasks={},all_automatic_candidates_unreviewed=True)
    for row in manifest['tasks']:
        task=row['task_id'];folder=out/task
        nodes=[];relations=[];masks=folder/'masks';masks.mkdir(exist_ok=False)
        shape=(row['image_size'][1],row['image_size'][0])
        maps={}; fine_ids={}; source_masks={}
        def add(key,name,level,**extra):
            node=dict(id=task+'_'+key,name=name,description=name,level=level,parent_ids=[],child_ids=[],
                      reviewed=False,mask_reviewed=False,reliability=0.,uncertain=True,status='candidate',
                      provenance=dict(reference_rgb=row['original_reference_image'],render_used=False),**extra)
            nodes.append(node);return node
        def link(parent,child):
            if child['id'] not in parent['child_ids']: parent['child_ids'].append(child['id'])
            if parent['id'] not in child['parent_ids']: child['parent_ids'].append(parent['id'])
        for method in ('light','feature'):
            if not (folder/method/'merge.json').exists():continue
            for level in ('fine','medium','coarse'):
                labels=np.asarray(Image.open(folder/method/(level+'_labels.png')))
                maps[method,level]=labels
                if level=='fine' and fine_ids: continue
                current={}
                for value in np.unique(labels):
                    key=('fine' if level=='fine' else method+'_'+level)+f'_{value+1:03d}'
                    mask=labels==value
                    node=add(key,'Visual region '+key,level,method='slic' if level=='fine' else method,
                             label_map=f'{method}/{level}_labels.png',label_value=int(value),
                             bbox=bbox(mask),metrics=['spatial','appearance','statistical','perceptual'],
                             pixel_count=int(mask.sum()),semantic_status='unknown')
                    node['provenance']['algorithm']='Original SLIC' if level=='fine' else 'adjacent visual merge'
                    current[int(value)]=node
                if level=='fine':fine_ids=current
                source_masks[method,level]=current
            previous=fine_ids
            for level,child_level in [('medium','fine'),('coarse','medium')]:
                for child_value,child in previous.items():
                    parents=np.unique(maps[method,level][maps[method,child_level]==child_value])
                    if len(parents)!=1: raise ValueError('Visual merge is not a nested partition')
                    link(source_masks[method,level][int(parents[0])],child)
                previous=source_masks[method,level]
        plan,group=api_evidence(out,task,'plan'),api_evidence(out,task,'group')
        vlm_data['tasks'][task]=dict(plan=plan,group=group)
        group_nodes=[];semantic_union=np.zeros(shape,bool);plan_nodes={}
        if plan['status']=='available':
            for item in plan['evidence']['regions']:
                node=add('vlm_plan_'+item['id'],item['name'],'semantic_plan',kind=item['kind'],
                         location=item['location'],reason=item['reason'],mask_unavailable=True,metrics=['semantic'])
                node['provenance']['algorithm']='validated VLM planning candidate'
                plan_nodes[item['id']]=node
        if group['status']=='available':
            selected=read(folder/'light/group_candidates.json')['labels']
            for index,item in enumerate(group['evidence']['groups']):
                values=[selected[key] for key in item['region_ids']]
                mask=np.isin(maps['light','coarse'],values)
                path=masks/f'group_{index+1:03d}.png';Image.fromarray(mask.astype(np.uint8)*255).save(path)
                node=add(f'group_{index+1:03d}',item['name'],'semantic',mask=str(path.relative_to(folder)),
                         bbox=bbox(mask),category=item['name'],metrics=['semantic','spatial','appearance','statistical','perceptual'],
                         region_ids=[source_masks['light','coarse'][v]['id'] for v in values])
                node['provenance']['algorithm']='validated VLM grouping suggestion; union of existing visual masks'
                for value in values:link(node,source_masks['light','coarse'][value])
                group_nodes.append(node);semantic_union|=mask
        pool=[]
        for method in ('sam3_visual','sam2_prompted'):
            path=SOURCE/'anchor_candidates'/task/method/'candidates.json'
            for candidate in read(path)['anchors']:
                pool.append(dict(candidate,method=method,source_file=str(path),source_mask=str(path.parent/candidate['mask'])))
        used=set();anchors=[]
        if plan['status']=='available':
            anchor_items=plan['evidence']['anchors']
        else:
            anchor_items=[dict(id=f'saved_{i+1:03d}',name=p['category'],location='Existing fixed RGB bbox prompt',
                               reason='VLM plan unavailable; keep saved candidate independently',need_mask=True,
                               existing_id=p['id']) for i,p in enumerate(pool) if p['method']=='sam3_visual']
        for item in anchor_items:
            matches=[p for p in pool if p['method']=='sam3_visual' and p['id'] not in used and
                     normalize_name(p['category'])==normalize_name(item['name'])]
            if item.get('existing_id'):matches=[p for p in matches if p['id']==item['existing_id']]
            # Multiple same-class instances require a reference-side location cue.
            if len(matches)>1:
                location=(item['name']+' '+item['location']).lower()
                if 'left' in location:matches=[min(matches,key=lambda p:p['bbox'][0])]
                elif 'right' in location:matches=[max(matches,key=lambda p:p['bbox'][0])]
                else: matches=[]
            node=add('anchor_'+item['id'],item['name'],'anchor',category=item['name'],location=item['location'],
                     reason=item['reason'],need_mask=item['need_mask'],importance=1.,metrics=['semantic','spatial','appearance','perceptual'])
            node['provenance']['proposal']='VLM plan' if plan['status']=='available' else 'saved SAM3 candidate, not VLM'
            if len(matches)==1:
                candidate=matches[0];used.add(candidate['id'])
                path=masks/(node['id']+'.png');shutil.copyfile(candidate['source_mask'],path)
                node.update(mask=str(path.relative_to(folder)),bbox=candidate['bbox'],mask_unavailable=False,
                            association_status='candidate_requires_review',source_mask_id=candidate['id'])
                node['provenance'].update(mask_source=candidate['source_mask'],prompt_bbox=candidate['prompt_bbox'])
                node['alternative_masks']=[dict(source_mask=p['source_mask'],method=p['method'],reviewed=False)
                     for p in pool if p['method']=='sam2_prompted' and p.get('prompt_bbox')==candidate.get('prompt_bbox')]
            else:node.update(mask_unavailable=True,association_status='unknown_no_unambiguous_saved_mask')
            anchors.append(node);plan_nodes[item['id']]=node
        if plan['status']=='available':
            for index,relation in enumerate(plan['evidence']['relations']):
                rel=dict(relation,id=task+f'_relation_{index+1:03d}',
                         subject=plan_nodes[relation['subject']]['id'],object=plan_nodes[relation['object']]['id'],
                         uncertain=True,source='VLM planning candidate')
                relations.append(rel)
                if rel['predicate'] in {'contains','inside'}:
                    parent,child=(rel['subject'],rel['object']) if rel['predicate']=='contains' else (rel['object'],rel['subject'])
                    lookup={n['id']:n for n in nodes};link(lookup[parent],lookup[child])
        unknown=~semantic_union
        Image.fromarray(unknown.astype(np.uint8)*255).save(masks/'semantic_unknown.png')
        unknown_node=add('unknown','Semantic Unknown','unknown',mask='masks/semantic_unknown.png',
                         bbox=bbox(unknown) if unknown.any() else [0,0,shape[1],shape[0]],metrics=[],
                         semantic_status='unknown',pixel_count=int(unknown.sum()))
        validate_region_hierarchy(nodes)
        geometric=[n for n in nodes if n['level']!='anchor' and ('mask' in n or 'label_map' in n)]
        document=dict(image_size=row['image_size'],reference_image=row['original_reference_image'],
                      reviewed=False,inventory_complete=False,regions=geometric,anchors=anchors,relations=relations,
                      hierarchy_nodes=nodes,semantic_plan=plan,semantic_grouping=group,
                      note='Candidate construction only. Load a level subset for review. Never sum overlapping levels.')
        save(folder/'evidence.json',document)
        coverage={}
        for key,labels in maps.items():
            coverage['_'.join(key)]=dict(pixel_union_coverage=float((labels>=0).mean()),
                                       region_count=int(len(np.unique(labels))),overlap_fraction=0.)
        coverage.update(candidate_semantic_union=float(semantic_union.mean()),semantic_unknown=float(unknown.mean()),
                        reviewed_semantic_coverage=0.,all_layers_union=1.,
                        definition='Original-grid pixel unions; reviewed semantic coverage remains zero')
        save(folder/'coverage.json',coverage)
        # Semantic unavailable remains visible as Unknown, not an empty perfect result.
        base=np.asarray(Image.open(out/row['local_reference']).convert('RGB'))
        gray=np.uint8(.35*base+.65*np.array([110,110,110]))
        sem=Image.fromarray(gray);d=ImageDraw.Draw(sem)
        if not group_nodes:
            d.rectangle((8,8,min(970,sem.width-8),54),fill='white')
            d.text((18,15),'VLM semantic groups: UNAVAILABLE; all semantic Unknown',font=font(20),fill='black')
        else:
            for index,node in enumerate(group_nodes):
                mask=np.asarray(Image.open(folder/node['mask']))>0
                gray[mask]=np.uint8(.6*base[mask]+.4*np.array([40+index*17%190,220,80]))
            sem=Image.fromarray(gray)
        sem.save(folder/'semantic_overlay.png')
        anchor_image=base.copy()
        for index,node in enumerate(anchors):
            if node.get('mask_unavailable'):continue
            mask=np.asarray(Image.open(folder/node['mask']))>0
            color=np.array([[255,80,90],[40,220,90],[80,150,255],[255,210,40],[210,70,255]][index%5])
            anchor_image[mask]=np.uint8(.6*base[mask]+.4*color)
            anchor_image[boundary(mask.astype(int))]=color
        im=Image.fromarray(anchor_image);d=ImageDraw.Draw(im)
        for i,node in enumerate(anchors):
            if 'bbox' in node:
                x,y=node['bbox'][:2];d.text((x,max(5,y-22)),f'A{i+1}: '+node['name'],font=font(18),fill='white',stroke_width=2,stroke_fill='black')
        im.save(folder/'anchor_overlay.png')
        # Final view shows a visual Coarse partition plus independently saved anchors.
        final=np.asarray(Image.open(folder/'light/coarse_overlay.png').resize(tuple(row['image_size']),Image.Resampling.NEAREST)).copy()
        for node in anchors:
            if node.get('mask_unavailable'):continue
            mask=np.asarray(Image.open(folder/node['mask']))>0
            final[boundary(mask.astype(int))]=[20,255,100]
        Image.fromarray(final).save(folder/'hierarchy_overlay.png')
        hierarchy['tasks'].append(dict(task_id=task,image_size=row['image_size'],evidence_file=task+'/evidence.json',
                 reference_image=row['original_reference_image'],nodes=nodes,relations=relations,coverage=coverage))
    save(out/'hierarchy.json',hierarchy)
    vlm_data['raw_response_files']=['vlm_final.json','bw_9064/vlm_plan.json']
    vlm_data['status']='available' if all(s['status']=='available' for t in vlm_data['tasks'].values() for s in t.values()) else 'unavailable'
    save(out/'vlm_evidence.json',vlm_data)


def report(out):
    if (out/'merge_summary.csv').exists() or (out/'report.md').exists():
        raise FileExistsError('Preserve completed report outputs')
    rows=[];diagnostics={}; manifest=read(out/'manifest.json')
    for item in manifest['tasks']:
        task=item['task_id']; diagnostics[task]={}
        for method in ('light','feature'):
            path=out/task/method/'merge.json'
            if not path.exists():continue
            result=read(path);fine_mix=result['statistics'][0]['mixed_anchor_pixels_proxy']
            for stat in result['statistics']:
                rows.append(dict(task_id=task,method=method,**stat,
                     extra_mixed_anchor_pixels_proxy=stat['mixed_anchor_pixels_proxy']-fine_mix,
                     merge_seconds=result['algorithm_seconds'],dino_feature_seconds=result['feature_seconds'],
                     dino_shared_load_seconds=result['dino_load_seconds'],device=result['device'],
                     threshold=0. if stat['level']=='fine' else result['parameters']['thresholds'][0 if stat['level']=='medium' else 1],
                     reviewed=False))
            # Flag actual clusters whose aggregate Anchor/background mixture grew.
            labels=np.asarray(Image.open(out/task/method/'coarse_labels.png'))
            fine=np.asarray(Image.open(out/task/method/'fine_labels.png'))
            flagged=[]; size=(labels.shape[1],labels.shape[0])
            for guard_index,guard in enumerate(anchor_guards(task,size)):
                counts=np.bincount(fine.ravel(),weights=guard.ravel());areas=np.bincount(fine.ravel())
                for value in np.unique(labels):
                    mask=labels==value; parts=np.unique(fine[mask])
                    old=float(np.minimum(counts[parts],areas[parts]-counts[parts]).sum())
                    new=float(min(guard[mask].sum(),mask.sum()-guard[mask].sum()))
                    if new>old:
                        flagged.append(dict(label_value=int(value),anchor_guard_index=guard_index,
                                            extra_mixed_pixels=int(new-old),bbox=bbox(mask)))
            diagnostics[task][method]=dict(suspect_anchor_mixing=flagged,
                interpretation='Unreviewed SAM-mask consistency proxy, not independent accuracy or GT',
                most_expensive_merges=sorted(result['events'],key=lambda e:e['cost'],reverse=True)[:6])
            # Display suspect cells on top of existing output, with numeric labels.
            img=Image.open(out/task/method/'coarse_overlay.png').convert('RGB')
            d=ImageDraw.Draw(img)
            if flagged:
                sx,sy=img.width/size[0],img.height/size[1]
                for flag in flagged:
                    box=[flag['bbox'][0]*sx,flag['bbox'][1]*sy,flag['bbox'][2]*sx,flag['bbox'][3]*sy]
                    d.rectangle(box,outline='red',width=4)
                    d.text((box[0]+3,box[1]+3),'CHECK c'+str(flag['label_value']+1),font=font(18),fill='red',stroke_width=1,stroke_fill='white')
            img.save(out/task/method/'suspect_overlay.png')
    with (out/'merge_summary.csv').open('x',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    save(out/'merge_diagnostics.json',diagnostics)
    inspection={
      'bw_9064':dict(continuous='墙面与地板上的碎片明显减少；视觉覆盖保持完整。',
          overmerge='Feature Coarse 把相近颜色的顶棚及墙面连到一个大区域，建筑表面边界丢失；Light 也有跨表面合并。',
          undermerge='椅子投影、冰箱阴影与冰箱明暗两面仍形成多个视觉块。',
          anchor='5 个原有 SAM3 Anchor 候选均保留。其轮廓依赖历史分割，仍需审核；SLIC 不是实例分割。'),
      'bw_0074':dict(continuous='相近书脊与沙发布面得到部分合并，但书架与沙发仍有许多小块。',
          overmerge='Light Coarse 在已保存 Anchor 边缘增加混合像素；编号图有书脊、背景与装饰物同块的混合内容。',
          undermerge='沙发褶皱、深色书架和书籍/唱片集合仍碎裂；DINO Coarse 85 块，多于 Light 的 70 块。',
          anchor='5 个原有 SAM3 Anchor 候选均保留；透明椅、植物/鱼缸边缘等仍需人工核查。')}
    save(out/'inspection_notes.json',dict(source='Assistant static visual inspection of reference and algorithm overlays',
         human_review_performed=False,reviewed=False,notes=inspection))
    html_head='<!doctype html><html lang="zh"><meta charset="utf-8"><title>Reference Region Hierarchy</title><style>body{font:16px system-ui;max-width:1600px;margin:24px auto;padding:0 18px} .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}img{width:100%;height:auto}figure{margin:0;border:1px solid #bbb;padding:8px}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.na{color:#a12121}a{color:#145c9d}</style><body>'
    links=[]
    for item in manifest['tasks']:
        task=item['task_id'];folder=out/task
        hierarchy=read(folder/'evidence.json'); coverage=read(folder/'coverage.json')
        panels=[('Reference RGB',Path(item['local_reference']).name),('Original SLIC Fine','light/fine_overlay.png'),
                ('Color + Boundary Medium','light/medium_overlay.png'),('Color + Boundary Coarse','light/suspect_overlay.png'),
                ('Color + Boundary + DINO Medium','feature/medium_overlay.png'),('Color + Boundary + DINO Coarse','feature/suspect_overlay.png'),
                ('VLM Semantic Groups — N/A; Unknown','semantic_overlay.png'),
                ('Hierarchy view: Coarse + saved SAM Anchor boundaries','hierarchy_overlay.png'),
                ('Existing SAM3 Anchors — unreviewed','anchor_overlay.png'),
                ('Numbered Coarse input supplied to VLM','numbered_for_final.png')]
        page=html_head+f'<h1>{task}</h1><p>所有候选 reviewed=false、reliability=0。算法合并、VLM 建议、已有 SAM Mask 与人工审核分开记录；本轮没有人工审核或正式评分。</p>'
        page+='<p class="na">VLM HTTP 200，但结构校验失败。没有有效 Semantic Groups；语义 Unknown 100%。不将不可用当作零误差。</p><div class="grid">'
        for title,path in panels:
            if (folder/path).exists():page+=f'<figure><figcaption>{html.escape(title)}</figcaption><a href="{path}"><img loading="lazy" src="{path}"></a></figure>'
            else:page+=f'<figure>{html.escape(title)}: N/A</figure>'
        page+='</div><h2>静态检查与疑似误合并</h2><ul>'+''.join('<li>'+html.escape(v)+'</li>' for v in inspection[task].values())+'</ul>'
        page+='<h2>Coverage（原图网格的并集）</h2><pre>'+html.escape(json.dumps(coverage,ensure_ascii=False,indent=2))+'</pre>'
        page+='<h2>Semantic Group 组成</h2><p class="na">N/A：没有通过严格 ID 与结构验证的分组；没有人工补全。</p>'
        page+='<h2>层级成员与审核清单</h2><p>逐项选择 Correct / Needs Correction / Remove / Uncertain；此页为静态材料，不写回审核状态。</p>'
        for level in ('fine','medium','coarse','semantic','anchor','unknown'):
            selected=[n for n in hierarchy['hierarchy_nodes'] if n['level']==level]
            page+=f'<details><summary>{level}: {len(selected)}</summary><table><tr><th>ID / name</th><th>Parent IDs</th><th>Children / member IDs</th><th>Review</th></tr>'
            for node in selected:
                page+='<tr><td>'+html.escape(node['id']+' | '+node['name'])+'</td><td>'+html.escape(', '.join(node['parent_ids']))+'</td><td>'+html.escape(', '.join(node['child_ids']))+'</td><td>□ Correct □ Needs Correction □ Remove □ Uncertain</td></tr>'
            page+='</table></details>'
        page+='<p><a href="evidence.json">Evidence JSON</a> · <a href="../vlm_final.json">原始 VLM 回复与校验失败</a> · <a href="../report.md">完整报告</a></p></body></html>'
        (folder/'comparison.html').write_text(page)
        links.append(f'<h2><a href="{task}/comparison.html">{task}：打开独立对照页</a></h2><a href="{task}/comparison.html"><img src="{task}/hierarchy_overlay.png" style="max-width:900px"></a>')
    (out/'comparison.html').write_text(html_head+'<h1>SLIC merging / DINO / VLM hierarchy</h1><p class="na">视觉层级完成。真实 VLM 返回未通过结构校验，语义分组不可用；全部候选未经人工审核。</p>'+''.join(links)+'<p><a href="report.md">Report</a> · <a href="merge_summary.csv">Merge summary</a> · <a href="hierarchy.json">Hierarchy JSON</a> · <a href="vlm_evidence.json">VLM evidence</a></p></body></html>')
    requests=read(out/'vlm_final_requests.json');last=requests[0]
    lines=['# SLIC Region Merging + VLM Semantic Grouping 实验',
      '', '视觉合并、两分支多粒度层级、已有 SAM Anchor 保留与可视化已完成。真实 VLM 连接成功，但返回结构不符合契约，规划与语义分组均不可用；本轮不能认定端到端语义构建成功。',
      '', '## 输入与方法', '',
      '仅使用 bw_9064、bw_0074 的已核实原始 Reference RGB。manifest.json 记录任务元数据和路径对应；重新直接比较原始与 staged 文件字节相同，不计算哈希。没有读取 Agent Render，没有运行 Blender、Agent 或 SAM2/SAM3。',
      '', 'Fine 复用已有 SLIC-200：工作网格分别为 1536×864、1258×855；所有交付 Label/Mask 以最近邻映射至原始 1672×941、1258×855 网格。底层历史 Label Map 未修改。',
      '', 'RAG 仅连接共享水平/垂直边界的块。Lab 均色距离除以100；灰度 Sobel /4 梯度描述边界；DINO 使用现有 local_dino_extractor 从遮掉块外内容的 bbox crop 提取 CLS（批8），不是重新训练的分割器。',
      '', 'Light 成本=0.65 Color + 0.35 Boundary；Feature 成本=0.45 Color + 0.25 Feature + 0.30 Boundary，Feature 为 cosine distance/2。Medium/Coarse 阈值固定0.075/0.14；合并后按面积重算颜色与特征。保留原始共享边界均值的最大值（上限0.22），并限制原始块均色到新簇均色的最大半径 min(0.34,2.5×threshold)，避免简单传递合并。没有固定目标块数或后验阈值调优。',
      '', '已有未审核 SAM3 Visual Anchor Mask 仅作为候选边界保护：原始块占据率≥0.65 与≤0.35 的两类不允许进入同一簇。模糊块仍可合并，该保护不能证明真实物体边界正确。未使用模型分数作为可靠性。',
      '', '## 实测合并结果', '', '|图片|方法|Fine|Medium|Coarse|Coarse 相对 Fine 新增混合像素代理|', '|---|---|---:|---:|---:|---:|']
    for task in TASKS:
        for method in ('light','feature'):
            chosen=[r for r in rows if r['task_id']==task and r['method']==method]
            if chosen:lines.append('|'+task+'|'+method+'|'+str(chosen[0]['region_count'])+'|'+str(chosen[1]['region_count'])+'|'+str(chosen[2]['region_count'])+'|'+str(chosen[2]['extra_mixed_anchor_pixels_proxy'])+'|')
    lines += ['', '所有 Fine/Medium/Coarse 分区覆盖率100%，层内不重叠；跨层有意重叠，使用像素并集统计，不能把覆盖率相加。语义候选并集0%、语义 Unknown 100%、已审核语义覆盖0%。CSV 混合像素在工作网格计算（9064:1536×864，0074:1258×855），coverage_grid 仅说明覆盖率网格；merge_diagnostics 则在原图网格定位疑似块。混合像素是与同一批候选 SAM Mask 的一致性代理，且这些 Mask 也参与保护，不能作为独立准确率。',
      '', '## VLM 实际调用与失败', '',
      '环境已继承 VLM_API_KEY / VLM_BASE_URL / VLM_MODEL，没有读取或输出 .bashrc 内容、没有写入密钥。复用 scene-benchmark/benchmark/vlm.py 的 VLMClient、持久请求账本、PNG data URL、JSON mode 与安全错误处理；Session hook 使用固定 system prompt 和 temperature=0.2。',
      '', '本结果目录有2次实际 VLM 尝试：首次 gpt-5.1 因原代理 TLS 失败，没有 HTTP/Token 回报；随后按用户指定最后一次额度，仅使用本地缓存确认的完整 ID openai/gpt-5.1，以及现有 BlenderWorld/scripts/ofox_tunnel.py。该临时回环 CONNECT 通道连接用户给定供应商 IP 47.83.144.71，URL/SNI/证书校验仍为 api.ofox.ai，未使用127.0.0.1:7897，未关闭 TLS 校验。',
      '', '用户另述跨对话计数5/6；这不是本地生成的五条记录，单独记在 vlm_budget.json。本次只消耗最后1次，独立最终账本限额1，自动重试关闭。没有 DNS、模型目录或额外余额探测。',
      '', '为了仅用最后一次请求覆盖两图，规划和分组合并为一次双图请求；每个 PNG 都由原图缩小副本与对应编号图组成。这偏离原先每图两阶段的计划，已记录实际 Prompt 和输入。Light Coarse 最多取32个最大区域供分组，未展示小块保持 Unknown，没有强制全图语义化。',
      '', f'最后请求 HTTP {last.get("http_status")}，耗时 {last["latency_seconds"]:.3f}s，服务端 reported usage：{json.dumps(last.get("usage"),ensure_ascii=False)}；finish_reason={last.get("finish_reason")}，actual_cost={last.get("actual_cost")}（未返回）。输出上限6000 Token，无自动重试。',
      '', '返回能解析为 JSON，但层级错误：bw_9064 的 anchors/relations 被放进 regions 数组，后面混入损坏的分组字符串；bw_0074 与 group 字段缺失。严格契约校验将四个 scene/stage 全部标为 unavailable。保留 raw_answer / parsed_answer，但不挪动字段、不修复 ID、不把局部看似合理的内容升级为 Evidence，也没有据此生成书籍或唱片集合。',
      '', '余额记录按用户给定的 [Ofox 余额接口文档](https://ofox.ai/zh/docs/api/openapi/balance) 实现白名单字段；首次查询因 SSLError 不可用。最新指示不再消耗连接检查，未做后置查询。因此没有可信的本轮余额差值，也没有猜测费用。账户余额差值即使可得也属于账户级，可能包含其他并发调用。',
      '', '## 静态检查与结论', '',
      '1. 连续区域：bw_9064 的地板和大片墙面明显少碎片；但近色墙面与顶棚会误合并，不能据块数下降认定语义质量提高。',
      '2. DINO：尚无明显整体优势。它减少了复杂图相对候选 Anchor 的新增混合，但保留更多碎片，且 bw_9064 Feature Coarse 丢失部分建筑表面边界。两分支权重不同，未做独立 DINO 消融或人工 GT，不宣称因果改进。',
      '3. VLM Anchor：原始回复提及桌、椅、盆栽和冰箱，可作为连通性观察，但结构失败，不能作为有效 Anchor 规划。正式候选列表仅保留原有 SAM3 Visual 每图5项，与 VLM 输出来源明确分开。',
      '4. 书籍/唱片集合：未验证成功。复杂图 Coarse 仍有混合内容和碎片，VLM 没有有效回复；不能复制原任务示例冒充模型分组。',
      '5. 幻觉：原始坏回复将 wall corner 列为 Anchor，粒度有疑问；无有效分组可判断误组率。需要人工看图核对，不能报告语义准确率。',
      '6. 仅 SLIC+VLM：当前可构建可追溯视觉层级，但本次没有证明语义层有效。VLM 也不能从混合块中恢复精确边界。',
      '7. SAM2/SAM3：在精细椅腿、透明椅、小盆栽、冰箱与背景分离等实例轮廓仍有价值。需要人工确认；没有可靠匹配时保留 mask_unavailable，不将零检测等同缺失。',
      '8. 读取：Evidence JSON 沿用 regions/anchors/relations，并新增可选 label_map+label_value；load_document 支持 levels 子集读取，Fine 无需成百上千份重复 Mask。语义组若通过契约则保存成员 ID 及 Mask 并集；本轮 groups 为空、Unknown 完整保留。',
      '9. 用量：本地2次 VLM 尝试、1次 HTTP200，服务端仅成功请求报告4012 Token、15.245s；首次失败耗时另见账本。不把用户所述外部请求纳入本地 Token 总量。',
      '10. 审核：全部自动 Region/Anchor/Relation reviewed=false、mask_reviewed=false、reliability=0；未执行人工审核，没有冻结 GT。请重点查墙/顶棚误合并、混合书脊区域、沙发过分割、透明椅及细小物体边缘。',
      '', '## 资源、测试与限制', '',
      'CPU 单元测试先运行。GPU 两次只读检查均显示8卡被其他任务占用，约30–32GiB/卡、16个计算进程；没有可用空闲卡。DINO 只用CPU、2线程，模型只加载一次，两图特征推理约29.45s，不重复特征推理。没有安装依赖、下载模型或改共享环境。DINO 负载与每图算法时长详见 merge.json；CSV 同层重复列出的加载/特征时间不得逐行求和。',
      '', '完整 CPU 单元测试88项通过（含新增13项），详见 test_results.log；产物检查852个节点、原图坐标 Mask/Label、DAG、引用、原始 SLIC 保留、现有 loader 和56个 HTML 本地链接通过，详见 validation.json。VLM JSON 语法通过但契约失败，语义质量验收未通过；无人工 GT，IoU / Boundary F1 跳过，SAM/Blender/正式评分未运行。结构合法不代表语义或边界准确。Light Coarse 在 bw_0074 的候选 Anchor 混合代理增加，故“无明显跨 Anchor”不能笼统宣布通过。',
      '', '## 文件改动与复用', '',
      '- 修改 e_harness/benchmark_evidence.py：新增简单 RAG 合并、VLM 契约与 DAG 检查；load_document 增加可选层筛选和 Label Map 引用。未改五类能量数学公式或聚合权重。',
      '- 新增 scripts/build_vlm_region_hierarchy.py：分阶段实验、既有网关调用、层级构建与静态报告。',
      '- 新增 tests/test_region_hierarchy.py：受控 CPU 图像与网关 mock（不消耗真实请求）。',
      '- 复用 local_dino_extractor、既有 SLIC/SAM 产物、compare_region_segmentation 的边界/配色函数、VLMClient、OfoxTunnel；未修改这些共享模块、Runtime blocked 或历史产物。',
      '', '## 最小复现', '',
      '查看 comparison.html 或各图片 comparison.html；原始坏回复见 vlm_final.json。无需联网或模型重跑。以下构建命令在新目录执行；不要重用已有结果目录。',
      '', '```bash', 'cd /home/xymo/projects/e-harness',
      '/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -v',
      'export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2',
      'export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1',
      'OUT=results/vlm_region_hierarchy_reproduction',
      '/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase prepare',
      '/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase merge',
      '/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase dino',
      '# 离线回放已记录的真实 API 回复；不会再发送请求',
      'cp results/vlm_region_hierarchy/vlm_final.json results/vlm_region_hierarchy/vlm_final_requests.json results/vlm_region_hierarchy/vlm_requests.json "$OUT/"',
      'cp results/vlm_region_hierarchy/bw_9064/vlm_plan.json "$OUT/bw_9064/"',
      'cp results/vlm_region_hierarchy/bw_9064/numbered_for_final.png "$OUT/bw_9064/"',
      'cp results/vlm_region_hierarchy/bw_0074/numbered_for_final.png "$OUT/bw_0074/"',
      '/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase build',
      '/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase report',
      '/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase validate',
      '```', '', '本次真实 VLM 账本已封口；不提供会自动再消耗余额的复跑链。上面复用真实历史回复，不代表新一次 VLM 成功。脚本拒绝覆盖已完成产物。下一轮若要新请求，须先重新获得明确预算。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


def validate(out):
    from html.parser import HTMLParser
    import tempfile
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,tag,attrs):
            self.paths.extend(value for key,value in attrs if key in {'src','href'})
    result=dict(tasks={},html_links=0,all_unreviewed=True,scoring_run=False,network_calls_in_validation=0)
    for task in read(out/'hierarchy.json')['tasks']:
        folder=out/task['task_id'];nodes=task['nodes'];shape=tuple(task['image_size'][::-1])
        checked=validate_region_hierarchy(nodes); cache={}
        all_ids={n['id'] for n in nodes}
        for rel in task['relations']:
            if rel['subject'] not in all_ids or rel['object'] not in all_ids or rel['reviewed'] is not False:
                raise ValueError('Invalid relation')
        for node in nodes:
            if node['mask_reviewed'] is not False or reliability(node)!=0:
                raise ValueError('Candidate review/reliability was upgraded')
            mask=None
            if 'label_map' in node:
                if node['label_map'] not in cache:
                    cache[node['label_map']]=np.asarray(Image.open(folder/node['label_map']))
                mask=cache[node['label_map']]==node['label_value']
            elif 'mask' in node:
                data=np.asarray(Image.open(folder/node['mask']))
                if set(np.unique(data))-{0,255}:raise ValueError('Expected binary mask')
                mask=data>0
            if mask is not None:
                if mask.shape!=shape or (not mask.any() and node['level']!='unknown'):
                    raise ValueError('Invalid native mask')
                if mask.any() and bbox(mask)!=node['bbox']:raise ValueError('Mask bbox differs')
                if 'pixel_count' in node and int(mask.sum())!=node['pixel_count']:raise ValueError('Area mismatch')
            if node['level']=='anchor' and node.get('mask_unavailable') and node.get('mask'):
                raise ValueError('Conflicting unavailable mask')
        checked['native_mask_rows']=sum('mask' in n or 'label_map' in n for n in nodes)
        # Load actual full Anchor subset through the established interface.
        doc=load_document(folder/'evidence.json',levels={'anchor'})
        for node in doc['anchors']:
            if 'mask' in node and node['mask'].shape!=shape: raise ValueError('Evidence loader grid mismatch')
        # One selector from each visual layer, with small bounded memory.
        for label_name in cache:
            example=next(n for n in nodes if n.get('label_map')==label_name)
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'evidence.json'
                save(path,dict(image_size=task['image_size'],regions=[dict(example,label_map=str(folder/label_name))]))
                loaded=load_document(path)['regions'][0]
                if not np.array_equal(loaded['mask']>0,cache[label_name]==example['label_value']):
                    raise ValueError('Label adapter changes mask')
        # Fine -> Medium -> Coarse membership exactly preserves the input partition.
        for method in ('light','feature'):
            if not (folder/method/'working_labels.npz').exists():continue
            with np.load(folder/method/'working_labels.npz',allow_pickle=False) as maps:
                source_path=SOURCE/'methods'/task['task_id']/'slic_200/dense_labels.npz'
                with np.load(source_path,allow_pickle=False) as original:
                    prior=original[original.files[0]]
                    _,index=np.unique(prior.ravel(),return_inverse=True)
                    if not np.array_equal(maps['fine'],index.reshape(prior.shape)):raise ValueError('Fine map changed')
                counts=[len(np.unique(maps[level])) for level in ('fine','medium','coarse')]
                if not counts[0]>counts[1]>=counts[2]>0:raise ValueError('Unexpected level counts')
                for small,big in [('fine','medium'),('medium','coarse')]:
                    for value in np.unique(maps[small]):
                        if len(np.unique(maps[big][maps[small]==value]))!=1:raise ValueError('Hierarchy splits a child')
                if not all((maps[level]>=0).all() for level in maps.files):raise ValueError('Lost pixels')
        if task['coverage']['all_layers_union']!=1. or task['coverage']['reviewed_semantic_coverage']!=0.:
            raise ValueError('Wrong coverage definition')
        checked['loader_compatible']=True;checked['fine_preserved']=True;checked['all_dense_levels_coverage']=1.
        result['tasks'][task['task_id']]=checked
    for path in out.rglob('*.html'):
        parser=Links();parser.feed(path.read_text())
        for ref in parser.paths:
            if ref.startswith(('https://','http://','#','data:')):continue
            resolved=(path.parent/ref).resolve()
            if not resolved.is_relative_to(out) or not resolved.is_file():raise ValueError('Broken or external HTML link '+ref)
            result['html_links']+=1
    ledger=read(out/'vlm_final_requests.json')
    if len(ledger)!=1 or ledger[0]['automatic_network_retry_enabled'] is not False:
        raise ValueError('Final-attempt budget violated')
    api=read(out/'vlm_evidence.json')
    if api['status']=='unavailable':
        for task in read(out/'hierarchy.json')['tasks']:
            if any(n['level']=='semantic' for n in task['nodes']):raise ValueError('Unavailable API fabricated semantic groups')
    result.update(final_request_count=1,local_total_vlm_attempts=len(read(out/'vlm_requests.json'))+len(ledger),
                  semantic_generation_status=api['status'],unit_test_log='test_results.log',passed=True)
    save(out/'validation.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=['prepare','merge','dino','plan','group','final-vlm','balance','build','report','validate'],required=True)
    parser.add_argument('--task',choices=TASKS)
    parser.add_argument('--label',default='before')
    args=parser.parse_args(); out=args.output.resolve()
    if args.phase=='prepare': prepare(out)
    elif args.phase in {'merge','dino'}: merge(out,args.phase=='dino')
    elif args.phase in {'plan','group'}:
        if not args.task: parser.error('--task required')
        vlm(out,args.task,args.phase)
    elif args.phase=='balance':
        if not re.fullmatch('[a-z0-9_]+',args.label): parser.error('Invalid balance label')
        balance(out,args.label)
    elif args.phase=='final-vlm': final_vlm(out)
    elif args.phase=='build': build(out)
    elif args.phase=='report': report(out)
    else: validate(out)


if __name__=='__main__': main()
