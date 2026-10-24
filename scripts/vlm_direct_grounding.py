"""One-request-per-image direct coarse Box/Polygon grounding experiment."""
import argparse
from copy import deepcopy
import html
import json
import math
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.region_first_e2e import configuration,sanitized,check_frozen
from scripts.region_first_generalization import panel_grid,write_csv
from scripts.region_grounding_experiment import read,save,method
from e_harness.benchmark_evidence import validate_region_first_plan,load_document
from benchmark.vlm import VLMClient

PREVIOUS=ROOT/'results/region_first_e2e_generalization'
SYSTEM='你是图像评价区域定位器。根据 RGB 图像和给定的区域描述，定位各区域的可见范围。区域可以包含多个物体，是粗粒度功能区域，不是物体分割。优先保留区域主要内容，尽量减少无关背景。不要推断遮挡后的内容。只输出 JSON。'


def prompt_for(plan):
    rows=[{k:r[k] for k in ('id','name','location','content')} for r in plan['regions']]
    validate_region_first_plan({'regions':rows})
    return '''请定位以下已确定的评价区域：
'''+json.dumps(rows,ensure_ascii=False,indent=2)+'''

图像坐标归一化到 0–1000，左上角为 (0,0)，右下角为 (1000,1000)。
每个区域输出：
1. bbox：粗矩形 [x1,y1,x2,y2]。
2. polygons：1–2 个粗多边形，每个 3–8 个顶点。
3. 无法可靠定位时使用 null 和空数组。

要求：
- 一个区域可以包含多个物体，不要逐物体分割。
- 可以使用不连续的多边形表示分离的可见部分。
- 不需要沿物体轮廓精确描边。
- 不要强制覆盖背景。
- 不要为了消除重叠而遗漏重要内容。
- 不要输出解释或额外字段。

仅输出以下 JSON 格式：
{"regions":[{"id":"R1","bbox":[100,200,400,600],"polygons":[[[100,200],[400,200],[400,600],[100,600]]]}]}
以上坐标只是格式示例，不能作为实际定位结果。
必须根据图片为全部四个 Region 输出结果。Box 和 Polygon 分别直接预测，不要仅通过 Polygon 的外接矩形产生 Box。'''


def schema_for(ids):
    number={'type':'number','minimum':0,'maximum':1000}
    point={'type':'array','minItems':2,'maxItems':2,'items':number}
    polygon={'type':'array','minItems':3,'maxItems':8,'items':point}
    bbox={'type':'array','minItems':4,'maxItems':4,'items':number}
    return {'type':'object','additionalProperties':False,'required':['regions'],'properties':{'regions':{
        'type':'array','minItems':len(ids),'maxItems':len(ids),'items':{'type':'object','additionalProperties':False,
        'required':['id','bbox','polygons'],'properties':{'id':{'enum':ids},'bbox':{'anyOf':[bbox,{'type':'null'}]},
        'polygons':{'type':'array','minItems':0,'maxItems':2,'items':polygon}}}}}}


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def intersects(a,b,c,d):
    turns=[cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)]
    if turns[0]*turns[1]<0 and turns[2]*turns[3]<0:return True
    def on(a,b,p):return min(a[0],b[0])<=p[0]<=max(a[0],b[0]) and min(a[1],b[1])<=p[1]<=max(a[1],b[1])
    return any(t==0 and on(u,v,p) for t,u,v,p in [(turns[0],a,b,c),(turns[1],a,b,d),(turns[2],c,d,a),(turns[3],c,d,b)])


def validate_direct(answer,ids):
    """Strict contract; invalid coordinates are rejected, never repaired."""
    def numeric(value):return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1000
    if not isinstance(answer,dict) or set(answer)!={'regions'}:raise ValueError('Expected only regions')
    rows=answer['regions']
    if not isinstance(rows,list) or len(rows)!=len(ids):raise ValueError('Expected every planned Region')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'id','bbox','polygons'}:raise ValueError('Unexpected Region fields')
        if not isinstance(row['id'],str) or row['id'] not in ids or row['id'] in seen:raise ValueError('Missing, duplicate or unknown Region ID')
        seen.add(row['id']);box=row['bbox']
        if box is not None:
            if not isinstance(box,list) or len(box)!=4 or not all(numeric(v) for v in box):raise ValueError('Invalid bbox coordinates')
            if not (box[0]<box[2] and box[1]<box[3]):raise ValueError('Invalid bbox order or degenerate bbox')
        polygons=row['polygons']
        if not isinstance(polygons,list) or len(polygons)>2:raise ValueError('Expected zero to two polygons')
        for polygon in polygons:
            if not isinstance(polygon,list) or not 3<=len(polygon)<=8:raise ValueError('Expected 3–8 vertices')
            if not all(isinstance(p,list) and len(p)==2 and all(numeric(v) for v in p) for p in polygon):raise ValueError('Invalid polygon coordinate')
            # A repeated closing vertex is retained in the output. Ignore only
            # that conventional duplicate for geometric validity checks.
            ring=polygon[:-1] if polygon[0]==polygon[-1] else polygon
            if len(ring)<3 or len({tuple(p) for p in ring})!=len(ring):raise ValueError('Degenerate or repeated polygon vertices')
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1]))
            if area==0:raise ValueError('Zero-area polygon')
            n=len(ring)
            for i in range(n):
                for j in range(i+1,n):
                    if j==i+1 or (i==0 and j==n-1):continue
                    if intersects(ring[i],ring[(i+1)%n],ring[j],ring[(j+1)%n]):raise ValueError('Self-intersecting polygon')
    if seen!=set(ids):raise ValueError('Missing Region ID')
    return deepcopy(answer)


def native_coordinates(row,size):
    w,h=size
    return dict(id=row['id'],bbox=None if row['bbox'] is None else [v*scale/1000 for v,scale in zip(row['bbox'],[w,h,w,h])],
        polygons=[[[x*w/1000,y*h/1000] for x,y in polygon] for polygon in row['polygons']])


def masks_for(row,size):
    """Native, pixel-center rasterization with one-bit storage and O(width) memory.

    Continuous coordinates use pixel edges [0,W] × [0,H]. Center (x+.5,y+.5)
    is inside a box on its left/top and outside its right/bottom boundaries.
    Polygon unions preserve disjoint parts; no conflict clipping or repairs.
    """
    w,h=size;box_mask=Image.new('1',size,0);poly_mask=Image.new('1',size,0)
    if row['bbox'] is not None:
        x0,y0,x1,y1=[math.ceil(v-.5) for v in row['bbox']]
        if x0>=x1 or y0>=y1:raise ValueError('Box has no pixels at native resolution')
        ImageDraw.Draw(box_mask).rectangle((x0,y0,x1-1,y1-1),fill=1)
    draw=ImageDraw.Draw(poly_mask)
    for polygon in row['polygons']:
        edges=list(zip(polygon,polygon[1:]+polygon[:1]))
        start=math.ceil(min(p[1] for p in polygon)-.5);end=math.ceil(max(p[1] for p in polygon)-.5)
        for y in range(start,end):
            sy=y+.5
            xs=sorted(a[0]+(sy-a[1])*(b[0]-a[0])/(b[1]-a[1]) for a,b in edges if (a[1]>sy)!=(b[1]>sy))
            for left,right in zip(xs[::2],xs[1::2]):
                x0,x1=math.ceil(left-.5),math.ceil(right-.5)
                if x1>x0:draw.line((x0,y,x1-1,y),fill=1)
    if row['polygons'] and not poly_mask.getbbox():raise ValueError('Polygons have no pixels at native resolution')
    return box_mask,poly_mask


def request_payload(payload,prompt):
    result=deepcopy(payload);content=result['messages'][1]['content']
    if len(content)!=2 or content[0]!={'type':'text','text':prompt} or content[1]['type']!='image_url':raise ValueError('Expected one RGB and the saved Plan prompt')
    if not content[1]['image_url']['url'].startswith('data:image/png;base64,'):raise ValueError('Expected actual RGB payload')
    result['messages'][0]['content']=SYSTEM;result.pop('response_format',None);result['temperature']=.1
    return result


def prepare(out,task='bw_0073'):
    if task not in ('bw_0073','bw_0074','bw_9064'):raise ValueError('Unexpected task')
    check_frozen();out.mkdir(parents=True,exist_ok=False)
    previous=ROOT/'results/region_first_pilot_bw0074' if task=='bw_0074' else PREVIOUS/task
    historical=(ROOT/'results/coarse_evaluation_roi_bw0074/B2_edge_polygons/evidence.json'
                if task=='bw_0074' else previous/'B2_frozen/evidence.json')
    info=read(previous/'input.json');plan=read(previous/'vlm_plan.json')
    original=Path(info['reference_rgb'])
    native=list(Image.open(original).size)
    if native!=info.get('native_image_size',info['image_size']):raise ValueError('Original reference dimensions differ')
    if (previous/'reference.png').exists():shutil.copyfile(previous/'reference.png',out/'reference.png')
    else:
        image=Image.open(original).convert('RGB');image.thumbnail((1536,1536),Image.Resampling.LANCZOS)
        image.info.clear();image.save(out/'reference.png')
    for source,dest in [(previous/'request_image.png','request_image.png'),(previous/'vlm_plan.json','region_plan.json')]:shutil.copyfile(source,out/dest)
    save(out/'input.json',dict(info,native_image_size=native,plan_source=str(previous/'vlm_plan.json'),
        historical_evidence=str(historical),render_used=False,reviewed=False))
    save(out/'prompt.json',dict(system=SYSTEM,user=prompt_for(plan),model='openai/gpt-6-sol',max_tokens=2200,
        temperature=.1,json_mode=False,request_limit=1,automatic_retries=False,image_file='request_image.png'))
    save(out/'schema.json',schema_for([r['id'] for r in plan['regions']]))
    print('Prepared '+task+'; 0 API calls',flush=True)


def reserve(out):
    if (out/'vlm_requests.json').exists() and len(read(out/'vlm_requests.json'))>=1:raise ValueError('One-attempt budget exhausted')
    save(out/'attempt_reserved.json',dict(maximum_paid_attempts=1,automatic_retry=False,reviewed=False))


def request(out):
    import requests
    from requests.adapters import HTTPAdapter
    check_frozen()
    if any((out/name).exists() for name in ('direct_regions.json','vlm_response.json','replay_info.json')):
        raise FileExistsError('Saved response or replay exists; no additional paid request')
    if read(out/'offline_checks.json').get('passed') is not True:raise ValueError('Offline tests must pass first')
    config=configuration();prompt=read(out/'prompt.json');reserve(out)
    sys.path.insert(0,str(ROOT.parent/'BlenderWorld/scripts'))
    from ofox_tunnel import OfoxTunnel
    try:
        client=VLMClient(out/'vlm_requests.json',api_key=config['VLM_API_KEY'],base_url=config['VLM_BASE_URL'],
            model=config['VLM_MODEL'],request_limit=1)
        with OfoxTunnel(ip='47.83.144.71') as tunnel:
            with requests.Session() as session:
                tunnel.configure_session(session);session.mount('https://',HTTPAdapter(max_retries=0))
                def post(url,*,json,**kwargs):
                    body=request_payload(json,prompt['user']);summary=deepcopy(body)
                    summary['messages'][1]['content'][1]['image_url']['url']='[actual PNG data URL; request_image.png]'
                    save(out/'request_parameters.json',dict(body=summary,image_count=1,credentials_recorded=False))
                    response=session.post(url,json=body,**kwargs)
                    try:raw=response.json()
                    except ValueError:raw=dict(non_json_response_text=response.text)
                    safe=sanitized(raw,config['VLM_API_KEY'])
                    save(out/'provider_response.json',dict(http_status=response.status_code,body=safe,reviewed=False))
                    return SimpleNamespace(status_code=response.status_code,json=lambda:safe)
                packet=client.call([out/'request_image.png'],prompt['user'],read(out/'input.json')['task_id']+':direct_box_and_polygon',
                    session=SimpleNamespace(post=post),max_tokens=prompt['max_tokens'],token_parameter='max_tokens',
                    retry_network=False,read_timeout=300)
        result=dict(packet,status='unavailable',reviewed=False)
        if packet.get('evaluation_status')=='answered':
            try:
                ids=[r['id'] for r in read(out/'region_plan.json')['regions']]
                clean=validate_direct(packet['parsed_answer'],ids)
                save(out/'direct_regions.json',dict(regions=[dict(r,reviewed=False) for r in clean['regions']],
                    coordinate_system='normalized 0–1000; top-left origin',reviewed=False))
                result['status']='coordinates_valid'
            except (ValueError,KeyError,TypeError) as exc:result['validation_error']=str(exc)
        save(out/'vlm_response.json',sanitized(result,config['VLM_API_KEY']))
        print('Direct grounding:',result['status'],flush=True)
    except Exception as exc:
        if not (out/'vlm_response.json').exists():save(out/'vlm_response.json',dict(status='unavailable',error_type=type(exc).__name__,reviewed=False))
        print('Request unavailable; no retry',flush=True)


def render(out):
    check_frozen();info=read(out/'input.json');native_size=info['native_image_size']
    if not (out/'direct_regions.json').exists():return render_unavailable(out)
    task=info['task_id']
    image=Image.open(out/'reference.png').convert('RGB');rgb=np.asarray(image);plan=read(out/'region_plan.json')['regions']
    direct={}
    if (out/'direct_regions.json').exists():
        saved=read(out/'direct_regions.json')['regions']
        clean=validate_direct({'regions':[{k:r[k] for k in ('id','bbox','polygons')} for r in saved]},[r['id'] for r in plan])
        direct={r['id']:r for r in clean['regions']}
    historical_path=Path(info['historical_evidence']);historical=read(historical_path)
    old={r['id']:r for r in historical['regions']}
    keys=('A_historical','B_direct_box','C_direct_polygon');stacks={k:[] for k in keys};rows={k:[] for k in keys}
    native_counts={k:np.zeros(tuple(native_size[::-1]),np.uint8) for k in keys}
    for key in keys:(out/(key+'_native')).mkdir()
    converted=[]
    for region in plan:
        identifier=region['id'];row=direct.get(identifier,dict(id=identifier,bbox=None,polygons=[]))
        coords=native_coordinates(row,native_size);converted.append(dict(coords,reviewed=False))
        b,c=masks_for(coords,native_size)
        historical_mask=Image.open(historical_path.parent/old[identifier]['mask']).convert('1')
        a=historical_mask.resize(tuple(native_size),Image.Resampling.NEAREST)
        for key,mask in zip(keys,(a,b,c)):
            path=out/(key+'_native')/(identifier+'.png');mask.save(path)
            support=np.asarray(mask,dtype=bool);native_counts[key]+=support
            area=int(support.sum());del support
            display=historical_mask if key=='A_historical' else mask
            stacks[key].append(np.asarray(display.resize(image.size,Image.Resampling.NEAREST),bool))
            record=dict(region,mask=identifier+'.png',reviewed=False,mask_reviewed=False,reliability=0.,
                representation='coarse_evaluation_roi',status='candidate' if area else 'unavailable',
                native_pixel_count=area,semantic_GT=False)
            if key=='B_direct_box':record.update(predicted_bbox_normalized=row['bbox'],predicted_bbox_native=coords['bbox'])
            elif key=='C_direct_polygon':record.update(predicted_polygons_normalized=row['polygons'],predicted_polygons_native=coords['polygons'])
            else:record.update(historical_source=str(historical_path),resampling='nearest from historical working grid; no grounding rerun')
            rows[key].append(record)
    stats=[]
    for key in keys:
        masks=np.stack(stacks[key]);stat=method(out,key,rgb,plan,masks,source=str(out/'region_plan.json'))
        count=native_counts.pop(key);stat.update(native_union_fraction=float((count>0).mean()),native_overlap_fraction=float((count>1).mean()),
            native_unassigned_fraction=float((count==0).mean()),located_region_count=sum(r['native_pixel_count']>0 for r in rows[key]),reviewed=False)
        save(out/(key+'_native')/'evidence.json',dict(image_size=native_size,regions=rows[key],anchors=[],relations=[],reviewed=False,
            coordinate_convention='pixel edges, continuous xy; masks sampled at pixel centers',formal_score=False))
        load_document(out/key/'evidence.json')
        stats.append(stat)
    save(out/'native_coordinates.json',dict(image_size=native_size,regions=converted,reviewed=False,coordinates_repaired=False))
    write_csv(out/'summary.csv',stats)
    panel_grid([('Reference RGB',image),('A: historical B2',Image.open(out/'A_historical/overlay.png')),
        ('B: independent direct Box',Image.open(out/'B_direct_box/overlay.png')),
        ('C: direct Polygon union',Image.open(out/'C_direct_polygon/overlay.png'))],out/'comparison.png',width=850)
    (out/'per_region').mkdir()
    body=['<!doctype html><meta charset="utf-8"><title>'+task+' — VLM direct grounding</title>',
      '<style>body{font:16px sans-serif;margin:24px;background:#f3f5f8}img{max-width:100%}table{width:100%;table-layout:fixed;border-collapse:collapse}td,th{padding:8px;vertical-align:top;border:1px solid #ccd2da}pre{white-space:pre-wrap}</style>',
      '<h1>'+task+'：一次 VLM 调用直接预测 Box 与 Polygon</h1><p>自动候选 reviewed:false；没有像素 GT、正式评分或冲突消解。洋红表示重叠，不是错误分数。</p>',
      '<p><a href="report.md">报告</a> · <a href="region_plan.json">既有真实 Plan</a> · <a href="direct_regions.json">原始归一化坐标</a> · <a href="native_coordinates.json">原分辨率坐标</a> · <a href="summary.csv">辅助统计</a></p>',
      '<img src="comparison.png"><table><tr><th>Reference RGB</th><th>A Historical</th><th>B Direct Box</th><th>C Direct Polygon</th></tr><tr><td><img src="reference.png"></td>'+''.join('<td><img src="'+key+'/overlay.png"></td>' for key in keys)+'</tr></table>']
    for region in plan:
        identifier=region['id'];panels=[('Reference RGB',image)]
        panels += [(key.split('_',1)[0]+': '+identifier+(' candidate' if rows[key][plan.index(region)]['native_pixel_count'] else ' N/A'),Image.open(out/key/(identifier+'_overlay.png'))) for key in keys]
        panel_grid(panels,out/'per_region'/(identifier+'.png'))
        body += ['<h2>'+html.escape(identifier+' '+region['name'])+'</h2><p>'+html.escape(region['location']+'；'+region['content'])+'</p>',
          '<p><a href="per_region/'+identifier+'.png">独立四方案对照图</a></p><img src="per_region/'+identifier+'.png">',
          '<details><summary>VLM 的独立 Box 与 Polygon 坐标</summary><pre>'+html.escape(json.dumps(direct.get(identifier),ensure_ascii=False,indent=2))+'</pre></details>']
    body+=['<h2>重叠及未分配区域</h2><table><tr><th>方法</th><th>Overlap</th><th>Unassigned</th></tr>']
    for key in keys:body.append('<tr><td>'+key+'</td><td><img src="'+key+'/overlap.png"></td><td><img src="'+key+'/unassigned_overlay.png"></td></tr>')
    body.append('</table>')
    if (out/'initial_review.json').exists():body.append(review_html(read(out/'initial_review.json')))
    (out/'comparison.html').write_text('\n'.join(body));check_frozen()
    print('Native masks, independent predictions and comparisons saved; no API calls',flush=True)


def render_unavailable(out):
    """Failure review only: never rasterize or repair a rejected VLM response."""
    info=read(out/'input.json');task=info['task_id'];plan=read(out/'region_plan.json')['regions']
    image=Image.open(out/'reference.png').convert('RGB');historical=Path(info['historical_evidence'])
    old={r['id']:r for r in read(historical)['regions']};native_size=tuple(info['native_image_size'])
    native=out/'A_historical_native';native.mkdir();masks=[];rows=[];count=np.zeros(native_size[::-1],np.uint8)
    for row in plan:
        mask=Image.open(historical.parent/old[row['id']]['mask']).convert('1')
        full=mask.resize(native_size,Image.Resampling.NEAREST);full.save(native/(row['id']+'.png'))
        support=np.asarray(full,bool);count+=support
        masks.append(np.asarray(mask.resize(image.size,Image.Resampling.NEAREST),bool))
        rows.append(dict(row,mask=row['id']+'.png',reviewed=False,mask_reviewed=False,reliability=0.,
            native_pixel_count=int(support.sum()),historical_source=str(historical),
            representation='coarse_evaluation_roi',resampling='nearest from historical working grid; no grounding rerun'))
    stats=method(out,'A_historical',np.asarray(image),plan,np.stack(masks),source=str(historical))
    stats.update(native_union_fraction=float((count>0).mean()),native_overlap_fraction=float((count>1).mean()),
        native_unassigned_fraction=float((count==0).mean()),located_region_count=sum(r['native_pixel_count']>0 for r in rows),reviewed=False)
    save(native/'evidence.json',dict(image_size=list(native_size),regions=rows,anchors=[],relations=[],reviewed=False,formal_score=False))
    write_csv(out/'summary.csv',[stats]);(out/'per_region').mkdir()
    packet=read(out/'vlm_response.json');error=packet.get('validation_error',packet.get('error','No valid saved response'))
    missing=Image.new('RGB',image.size,'#ecedf0');draw=ImageDraw.Draw(missing)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',max(12,round(image.width*.023)))
    draw.text((24,24),'N/A: entire response rejected',font=font,fill='black')
    draw.text((24,70),'No direct ROI masks generated',font=font,fill='black')
    draw.text((24,116),str(error),font=font,fill='black')
    panels=[('Reference RGB',image),('A: historical B2',Image.open(out/'A_historical/overlay.png')),
        ('B: direct Box unavailable',missing),('C: direct Polygon unavailable',missing)]
    panel_grid(panels,out/'comparison.png',width=850)
    body=['<!doctype html><meta charset="utf-8"><title>'+task+' — rejected grounding response</title>',
        '<style>body{font:16px sans-serif;margin:24px}img{max-width:100%}pre{white-space:pre-wrap}</style>',
        '<h1>'+task+'：Direct Grounding 未通过冻结校验</h1>',
        '<p>'+html.escape(str(error))+'。保留原始响应；未修补坐标、未接受部分结果、未生成 Direct Mask。reviewed:false。</p>',
        '<p><a href="report.md">报告</a> · <a href="region_plan.json">既有 Plan</a> · <a href="vlm_response.json">脱敏原始回答及解析错误</a></p>',
        '<img src="comparison.png">']
    for row in plan:
        identifier=row['id']
        panel_grid([('Reference RGB',image),('A: '+identifier,Image.open(out/'A_historical'/(identifier+'_overlay.png'))),
            ('B: N/A, rejected response',missing),('C: N/A, rejected response',missing)],out/'per_region'/(identifier+'.png'))
        body.extend(['<h2>'+html.escape(identifier+' '+row['name'])+'</h2><p>'+html.escape(row['content'])+'</p>',
            '<img src="per_region/'+identifier+'.png">'])
    if (out/'initial_review.json').exists():body.append(review_html(read(out/'initial_review.json')))
    body.append('<details><summary>实际回答原文（未接受为 ROI）</summary><pre>'+html.escape(packet.get('raw_answer',''))+'</pre></details>')
    (out/'comparison.html').write_text('\n'.join(body));check_frozen()
    print(task+': failure review saved; no direct masks, repairs or API calls',flush=True)


def review_html(review):
    result=['<h2>参考 RGB 静态初审，未经过人工审核</h2><table><tr><th>Region</th><th>A Historical</th><th>B Direct Box</th><th>C Direct Polygon</th><th>Uncertain / 限制</th></tr>']
    for row in review['regions']:
        result.append('<tr>'+''.join('<td>'+html.escape(row[key])+'</td>' for key in ['id','historical','box','polygon','uncertain'])+'</tr>')
    result.append('</table><p>几何可用不等于内容完整性通过；所有候选 reviewed:false。不得把覆盖率、低重叠或 VLM 坐标解释为准确率/GT。</p>')
    return '\n'.join(result)


def replay(out,source):
    prepare(out,read(source/'input.json')['task_id'])
    for name in ('direct_regions.json','vlm_response.json','provider_response.json','report.md','initial_review.json'):
        if (source/name).exists():shutil.copyfile(source/name,out/name)
    save(out/'replay_info.json',dict(source=str(source),new_api_calls=0,reviewed=False));render(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['prepare','request','render','replay'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--source',type=Path)
    parser.add_argument('--task',choices=['bw_0073','bw_0074','bw_9064'],default='bw_0073')
    args=parser.parse_args()
    if args.stage=='replay':
        if args.source is None:parser.error('replay needs --source')
        replay(args.output.resolve(),args.source.resolve())
    elif args.stage=='prepare':prepare(args.output.resolve(),args.task)
    else:globals()[args.stage](args.output.resolve())
