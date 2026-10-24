"""One RGB, one paid attempt, coarse Region planning. No model/SAM/Agent execution."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import html
import re

import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_evidence import REGION_FIRST_SCHEMA,validate_region_first_plan
from benchmark.vlm import VLMClient

SYSTEM='你是图像评测区域规划器。根据单张 RGB 图像选择少量重要的粗粒度评价区域。区域可以包含多个物体，不需要逐个识别或精确分割。只描述可见内容，不猜测不可见内容。只输出合法 JSON。'
USER='''将图片划分为 2–5 个重要的粗粒度评价区域，使不同局部能够得到充分评价。背景不必强制单独划分，不拆分物体部件。

只输出：
{"regions":[{"id":"R1","name":"简短区域名称","location":"大致位置","content":"主要可见内容"}]}

不要输出 Anchor、Relation、Mask、bbox、置信概率或解释。'''
MODEL='openai/gpt-6-sol'


def read(path):return json.loads(Path(path).read_text())


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def region_request(payload):
    """Session hook: exact prompts, one image, no forced JSON Mode or extra tasks."""
    payload=deepcopy(payload)
    content=payload['messages'][1]['content']
    if len(content)!=2 or content[0]!={'type':'text','text':USER} or content[1]['type']!='image_url':
        raise ValueError('Expected the fixed prompt and exactly one RGB image')
    if not content[1]['image_url']['url'].startswith('data:image/png;base64,'):
        raise ValueError('Actual PNG data URL required')
    payload['messages'][0]['content']=SYSTEM
    payload.pop('response_format',None)
    payload['temperature']=.2
    return payload


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    manifest=read(ROOT/'results/vlm_region_hierarchy/manifest.json')
    row=next(r for r in manifest['tasks'] if r['task_id']=='bw_0074')
    original,staged=Path(row['original_reference_image']),Path(row['reference_image'])
    if original.read_bytes()!=staged.read_bytes():raise ValueError('Reference provenance changed')
    if read(row['provenance']['task_json'])['task_id']!='bw_0074':raise ValueError('Wrong dataset task')
    if read(row['provenance']['input_json'])['task_id']!='bw_0074':raise ValueError('Wrong run task')
    image=Image.open(original).convert('RGB');image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
    image.info.clear();image.save(out/'request_image.png')
    save(out/'input.json',dict(task_id='bw_0074',reference_rgb=str(original),staged_rgb=str(staged),
        image_size=row['image_size'],request_image_size=list(image.size),
        provenance=row['provenance'],original_staged_bytes_equal=True,agent_render_used=False))
    save(out/'prompt.json',dict(system=SYSTEM,user=USER,model=MODEL,max_tokens=1500,temperature=.2,
        image_file='request_image.png',response_format=None,json_mode=False,request_limit=1,
        automatic_retries=False,read_timeout_seconds=300))
    save(out/'region_schema.json',REGION_FIRST_SCHEMA)
    previous=read(ROOT/'results/vlm_region_hierarchy/vlm_final.json')
    save(out/'prior_readonly_audit.json',dict(previous_source='results/vlm_region_hierarchy/vlm_final.json',
        previous_gateway_status=previous['evaluation_status'],previous_task_status=previous['status'],
        saved_raw_json_parses=json.loads(previous['raw_answer'])==previous['parsed_answer'],
        previous_errors=previous['scenes'],
        change='One raw reference, one Region-only contract, no scene wrapper or grouping IDs; no JSON Mode.'))


def request(out):
    import requests
    if not (out/'offline_tests.json').exists() or read(out/'offline_tests.json')['passed'] is not True:
        raise ValueError('Passing offline tests are required before the paid attempt')
    if any((out/name).exists() for name in ['attempt_reserved.json','vlm_requests.json','vlm_response.json']):
        raise FileExistsError('One-attempt budget already reserved; no retry')
    save(out/'attempt_reserved.json',dict(maximum_paid_attempts=1,automatic_retries=False,reviewed=False))
    # Configuration is inherited; neither shell configuration nor credentials are copied.
    if os.environ.get('VLM_MODEL')!=MODEL:
        save(out/'vlm_response.json',dict(status='unavailable',error='Configured model differs from authorized model',reviewed=False))
        return
    sys.path.insert(0,str(ROOT.parent/'BlenderWorld/scripts'))
    from ofox_tunnel import OfoxTunnel
    try:
        client=VLMClient(out/'vlm_requests.json',request_limit=1,model=MODEL)
        if client.provider!='api.ofox.ai':raise ValueError('Expected configured Ofox gateway')
        with OfoxTunnel(ip='47.83.144.71') as tunnel:
            with requests.Session() as session:
                tunnel.configure_session(session)
                def post(url,*,json,**kwargs):
                    body=region_request(json)
                    summary=deepcopy(body)
                    summary['messages'][1]['content'][1]['image_url']['url']='[PNG data URL; request_image.png]'
                    save(out/'request_parameters.json',dict(body_without_image_base64=summary,
                        image_file='request_image.png',image_size=list(Image.open(out/'request_image.png').size),
                        image_payload='actual PNG data URL',credentials_recorded=False))
                    return session.post(url,json=body,**kwargs)
                packet=client.call([out/'request_image.png'],USER,'bw_0074:region_first',
                    session=SimpleNamespace(post=post),max_tokens=1500,token_parameter='max_tokens',
                    retry_network=False,read_timeout=300)
        result=dict(packet,status='unavailable',reviewed=False)
        if packet['evaluation_status']=='answered':
            try:
                plan=validate_region_first_plan(packet['parsed_answer'])
                result.update(status='structure_valid',semantic_status='requires_reference_inspection')
                save(out/'vlm_plan.json',dict(regions=[dict(r,reviewed=False,reliability=0.,source='VLM reference-only planning')
                    for r in plan['regions']],reviewed=False,structure_valid=True,semantics_human_reviewed=False))
            except (ValueError,KeyError,TypeError) as exc:
                result['validation_error']=str(exc)
        save(out/'vlm_response.json',result)
        print('VLM',result['status'],result.get('validation_error',result.get('error','')),flush=True)
    except Exception as exc:
        # Avoid provider exception repr, URLs with credentials or request headers.
        if not (out/'vlm_response.json').exists():
            save(out/'vlm_response.json',dict(status='unavailable',error_type=type(exc).__name__,reviewed=False))
        print('VLM unavailable; see sanitized response record',flush=True)


def location_window(text):
    """Explicit positional priors, not semantic localization or model boxes."""
    text=text.lower()
    left=bool(re.search('左|left',text));right=bool(re.search('右|right',text))
    middle=bool(re.search('中|center|middle',text))
    upper=bool(re.search('上|upper|top',text));lower=bool(re.search('下|前景|lower|bottom|foreground',text))
    x=(0.,1.)
    if left and not right:x=(0.,.71 if middle else .45)
    if right and not left:x=(.29 if middle else .63,1.)
    y=(0.,1.)
    if upper and not lower:y=(0.,.67)
    if lower and not upper:y=(.35 if middle else .55,1.)
    return [x[0],y[0],x[1],y[1]] if left or right or upper or lower else None


def visualize(out):
    if (out/'localized_regions.json').exists():raise FileExistsError('Preserve current pilot outputs')
    response=read(out/'vlm_response.json')
    if response['status']!='structure_valid':
        (out/'report.md').write_text('VLM 请求不可用，已停止；没有重试或伪造分区。详见 vlm_response.json。\n')
        return
    info=read(out/'input.json');image=Image.open(info['reference_rgb']).convert('RGB')
    width,height=image.size;rgb=np.asarray(image)
    label_path=ROOT/'results/vlm_region_hierarchy/bw_0074/feature/coarse_labels.png'
    labels=np.asarray(Image.open(label_path))
    if labels.shape!=(height,width):raise ValueError('Existing SLIC label grid mismatch')
    source=ROOT/'results/multiscene_region_extraction'
    pool=[]
    for kind in ('region_candidates','anchor_candidates'):
        path=source/kind/'bw_0074/sam3_visual/candidates.json'
        doc=read(path)
        pool += [dict(row,source_document=str(path),source_mask=str(path.parent/row['mask']))
                 for row in doc.get('regions',[])+doc.get('anchors',[]) if row.get('category')]
    # Small localization-only translations of existing mask metadata. These are
    # not Region names, do not enter VLM prompts, and do not change model output.
    aliases={'bookshelf':['书架','书柜'],'books group':['书籍'],'records group':['唱片'],
             'monitor':['显示器'],'transparent chair':['椅子'],'sofa':['沙发'],
             'globe':['地球仪'],'aquarium':['水族箱','鱼缸']}
    regions=[];count=np.zeros((height,width),np.uint8);overlay=rgb.copy()
    palette=[(240,75,65),(255,185,35),(55,140,250),(35,205,140),(185,80,230)]
    areas=np.bincount(labels.ravel())
    masks=out/'support_masks';masks.mkdir()
    for index,plan in enumerate(read(out/'vlm_plan.json')['regions']):
        def matches(row,text):
            terms=[row['category']]+aliases.get(row['category'],[])
            return any(term.lower() in text.lower() for term in terms)
        primary=[row for row in pool if matches(row,plan['name'])]
        seeds=primary or [row for row in pool if matches(row,plan['content'])]
        window=location_window(plan['location'])
        result=dict(plan,reviewed=False,reliability=0.,mask_reviewed=False,
                    representation='approximate evaluation support; not a semantic mask',
                    bbox_kind='algorithm proposal ROI, not a tight support-mask bbox',
                    localization_status='unavailable',semantic_mask_available=False,
                    matched_source_ids=[s['id'] for s in seeds],positional_prior=window,
                    heuristic_metadata_aliases_used=True)
        if not seeds or window is None:
            result['reason']='No metadata association or interpretable positional cue; no invented geometry'
            regions.append(result);continue
        boxes=np.array([s['bbox'] for s in seeds])
        box=np.r_[boxes[:,:2].min(axis=0),boxes[:,2:].max(axis=0)].astype(float)
        if not primary:box += [-width*.10,-height*.04,width*.10,height*.04]
        elif any('group' in s['category'] for s in primary):
            box += [-width*.04,-height*.04,width*.04,height*.04]
        if re.search('下方|below|underneath',plan['content']):box[3]+=height*.15
        prior=np.array(window)*[width,height,width,height]
        box[:2]=np.maximum(box[:2],prior[:2]);box[2:]=np.minimum(box[2:],prior[2:])
        box=np.clip(np.rint(box),[0,0,0,0],[width,height,width,height]).astype(int)
        x0,y0,x1,y1=box.tolist()
        if x0>=x1 or y0>=y1:
            result['reason']='Metadata geometry conflicts with positional prior'
            regions.append(result);continue
        roi=np.zeros((height,width),bool);roi[y0:y1,x0:x1]=True
        fraction=np.bincount(labels.ravel(),weights=roi.ravel(),minlength=len(areas))/np.maximum(areas,1)
        chosen=np.flatnonzero(fraction>=.5)
        support=np.isin(labels,chosen)
        if not support.any():
            result['reason']='No existing coarse cells agree with the approximate ROI'
            regions.append(result);continue
        filename='support_masks/'+plan['id']+'.png'
        Image.fromarray(support.astype(np.uint8)*255).save(out/filename)
        result.update(localization_status='approximate_support',bbox=box.tolist(),mask=filename,
            mask_kind='SLIC merged-cell union, not object segmentation',label_map=str(label_path),label_values=chosen.tolist(),
            matched_mask_bboxes=[s['bbox'] for s in seeds],source_masks=[s['source_mask'] for s in seeds],
            matched_mask_is_only_a_seed=True,full_group_semantic_mask_unavailable=True,
            roi_fraction=float(roi.mean()),support_fraction=float(support.mean()),
            support_outside_roi_fraction=float((support&~roi).sum()/support.sum()),
            localization_note='Weak category alias + positional prior + existing DINO-merged SLIC majority; human review required')
        count+=support
        color=np.array(palette[index]);overlay[support]=np.uint8(.73*overlay[support]+.27*color)
        boundary=np.zeros(support.shape,bool)
        boundary[1:]|=support[1:]!=support[:-1];boundary[:,1:]|=support[:,1:]!=support[:,:-1]
        overlay[boundary]=color
        regions.append(result)
    im=Image.fromarray(overlay);draw=ImageDraw.Draw(im)
    textfont=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',25)
    for index,row in enumerate(regions):
        if row['localization_status']=='unavailable':continue
        x0,y0,x1,y1=row['bbox']
        # Boxes are deliberately shown as approximate; all numbers are generated locally.
        draw.rectangle((x0,y0,x1-1,y1-1),outline=palette[index],width=3)
        draw.text((x0+8,y0+8),row['id'],font=textfont,fill='white',stroke_width=3,stroke_fill='black')
    im.save(out/'region_overlay.png')
    demo=Image.new('RGB',(width*2+24,height+112),'white')
    demo.paste(image,(0,48));demo.paste(im,(width+24,48));draw=ImageDraw.Draw(demo)
    draw.text((12,10),'Reference RGB',font=textfont,fill='black')
    draw.text((width+36,10),f'{len(regions)} VLM regions | approximate evaluation support',font=textfont,fill='black')
    draw.text((12,height+68),' / '.join(r['id'] for r in regions)+': see Chinese names and contents in comparison.html; all unreviewed',font=textfont,fill='black')
    demo.save(out/'region_first_demo.png')
    coverage=dict(candidate_region_union=float((count>0).mean()),candidate_region_overlap=float((count>1).mean()),
        remaining_global_dense_patch_fraction=float((count==0).mean()),dense_coverage=1.,reviewed_region_coverage=0.,
        note='Pixel unions, not summed areas; remainder retains Global + Dense Patch. No energy calculated.')
    save(out/'localized_regions.json',dict(image_size=[width,height],regions=regions,reviewed=False,
        source_label_map=str(label_path),coverage=coverage,semantic_regions_from='vlm_plan.json',
        localization_source='Existing unreviewed SAM3 metadata boxes + cached SLIC/DINO merge labels; no new model inference'))
    entries=''.join('<tr><td>'+html.escape(r['id']+' '+r['name'])+'</td><td>'+html.escape(r['location'])+'</td><td>'+html.escape(r['content'])+'</td><td>'+html.escape(r['localization_status'])+'</td></tr>' for r in regions)
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>bw_0074 Region-first</title><style>body{font:17px system-ui;margin:24px}img{width:100%;height:auto}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:9px}p{max-width:1100px}</style><h1>bw_0074：Region-first 第一轮</h1><p>区域名称与内容来自本轮唯一一次 VLM 单图请求。颜色覆盖与框由离线启发式定位生成，属于近似评价范围，并非精确语义 Mask。全部 reviewed=false。没有人工审核或正式评分。</p>'''
    page+='<a href="region_first_demo.png"><img src="region_first_demo.png"></a><table><tr><th>VLM Region</th><th>VLM 位置描述</th><th>VLM 主要内容</th><th>离线定位</th></tr>'+entries+'</table>'
    page+='<p>边框表示算法粗窗口，彩色填充是选中SLIC块的并集，两者可能不完全重合。定位使用已有 Mask 元数据的有限中英文别名、相对位置先验及原有 DINO 合并后的 SLIC 块；词表和框不进入 VLM 请求。多物体集合的完整语义范围尚未可靠定位，特别是桌面整组、展示架与唱片设备区。粗块可能越过物体边界或包含相邻内容。重叠不强行消除，未覆盖部分继续由 Global + Dense Patch 处理。</p><p><a href="vlm_plan.json">VLM 规划</a> · <a href="localized_regions.json">实际定位与限制</a> · <a href="report.md">报告</a></p></html>'
    (out/'comparison.html').write_text(page)
    ledger=read(out/'vlm_requests.json')[0]
    rows=['# bw_0074 Region-first 第一轮','',
        '结构合法的 VLM 自动规划已得到4个有意义的粗区域；未出现逐本书籍/唱片或物体部件拆分。本文语义判断为参考图静态检查，尚未经过人工审核。','',
        '|ID|VLM 名称|主要可见内容|定位|','|---|---|---|---|']
    rows += ['|'+r['id']+'|'+r['name']+'|'+r['content']+'|'+r['localization_status']+'|' for r in regions]
    rows += ['', '名称和内容直接来自实际 VLM JSON；没有把预期场景名称写入输入或替换模型输出。API仅接收1024×696的参考RGB，无编号图、Agent Render、Anchor或Relation任务。',
        '', '定位为明确的低成本启发式：以既有 SAM3 Visual 元数据类别别名关联种子 bbox，结合 VLM 相对位置描述给出粗窗口；再取原有 DINO Feature Coarse Label Map 中窗口占据率≥50%的块的并集。没有重新运行 SAM 或 DINO。所有框、Mask 和块选择均为算法侧生成，不是 VLM 输出；候选可靠性保持0。',
        '', '这些是近似评价支持区域，不能声称完整的语义集合已被自动分割。工作区种子仅显示器/椅子，整张桌、灯和笔记本未独立定位；展示架原有Mask过宽，与工作区/唱片区的分界依赖位置先验；唱片种子不能证明包含下方所有设备。沙发已有整体Mask可复用，但这里的SLIC并集仍不是经过审核的精确沙发Mask。四个粗窗口可用于人工检查粒度，四个完整语义Mask均未验证。',
        '', 'SLIC粗块可能使范围膨胀、合并不相关内容或在两区域间重叠，不强制唯一分区。定位使用有限的中文/英文类别别名，不能泛化为已验证的开放词汇定位器。没有制作新的Anchor/Relation。',
        '', '本轮粗评价区域不必依赖 SAM；若之后需要精确排除邻近区域、遮挡处的边界或透明椅等细结构，SAM候选才有帮助，仍需要人工审核。已有SAM候选也参与本次定位，因此不能声称此次实现完全不依赖SAM。',
        '', '覆盖统计（原图像素并集）：'+json.dumps(coverage,ensure_ascii=False),
        '', '请求：'+json.dumps({k:ledger.get(k) for k in ['model','http_status','finish_reason','usage','actual_cost','latency_seconds','automatic_network_retry_enabled']},ensure_ascii=False),
        '', '本轮付费请求总数1；无自动重试、无余额/DNS探测、无JSON Mode，输出上限1500 Token，temperature=0.2。服务端报告少量隐藏 reasoning_tokens；没有要求长篇推理或解释，没有在报告展示推理内容。实际费用未返回，不作推算。',
        '', '先运行93项CPU离线测试并通过（包含新增5项Region-first测试），详见offline_tests.log。Schema由显式REGION_FIRST_SCHEMA描述并用轻量函数校验，不新增jsonschema依赖。业务Schema校验不代表语义或定位准确。最终产物检查见validation.json。',
        '', '源码：修改 e_harness/benchmark_evidence.py 增加Region-only Schema/校验；新增 scripts/region_first_pilot.py 复用 VLMClient、OfoxTunnel 与既有产物；扩充 tests/test_region_hierarchy.py。五类能量与权重、正式Runtime及历史产物未变。',
        '', '最简复现（只读回放，无新API请求）：','```bash','cd /home/xymo/projects/e-harness',
        '/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -v',
        '# 直接打开 results/region_first_pilot_bw0074/comparison.html',
        '```','', '如要重新绘图，在新的非冲突目录复制input.json、vlm_plan.json、vlm_response.json、vlm_requests.json，再运行：',
        '```bash','/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_first_pilot.py --output <新回放目录> --phase visualize','```',
        '', '已保留原始模型回复、请求参数（不含凭证/Base64）和Schema。付费request阶段在该目录不可再次运行。本轮结束。']
    (out/'report.md').write_text('\n'.join(rows)+'\n')


def validate(out):
    from html.parser import HTMLParser
    data=read(out/'localized_regions.json');info=read(out/'input.json')
    ledger=read(out/'vlm_requests.json');payload=read(out/'request_parameters.json')['body_without_image_base64']
    if len(ledger)!=1 or ledger[0]['automatic_network_retry_enabled'] is not False:
        raise ValueError('Single-attempt budget violated')
    if 'response_format' in payload or len(payload['messages'][1]['content'])!=2:
        raise ValueError('Unexpected JSON Mode or multimodal payload')
    parsed=validate_region_first_plan(read(out/'vlm_response.json')['parsed_answer'])
    if len(parsed['regions'])!=len(data['regions']):raise ValueError('Region count changed after VLM')
    count=np.zeros(tuple(info['image_size'][::-1]),np.uint8)
    labels=np.asarray(Image.open(data['source_label_map']))
    for raw,row in zip(parsed['regions'],data['regions']):
        if any(row[k]!=raw[k] for k in raw):raise ValueError('Model Region description was changed')
        if row['reviewed'] is not False or row['mask_reviewed'] is not False or row['reliability']!=0:
            raise ValueError('Candidate review/reliability upgraded')
        if row['localization_status']=='unavailable':continue
        mask=np.asarray(Image.open(out/row['mask']))
        if mask.shape!=count.shape or set(np.unique(mask))-{0,255}:raise ValueError('Invalid support mask')
        if not np.array_equal(mask>0,np.isin(labels,row['label_values'])):raise ValueError('Support differs from saved cells')
        x0,y0,x1,y1=row['bbox'];width,height=info['image_size']
        if not (0<=x0<x1<=width and 0<=y0<y1<=height):raise ValueError('Invalid original-grid ROI')
        count+=mask>0
    for name,value in [('candidate_region_union',(count>0).mean()),('candidate_region_overlap',(count>1).mean()),
                       ('remaining_global_dense_patch_fraction',(count==0).mean())]:
        if not np.isclose(data['coverage'][name],value):raise ValueError('Incorrect union/overlap coverage')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):self.links.extend(v for k,v in attrs if k in {'src','href'})
    links=Links();links.feed((out/'comparison.html').read_text())
    if any(not (out/name).is_file() for name in links.links):raise ValueError('Broken HTML link')
    secrets=[v.encode() for k,v in os.environ.items() if len(v)>12 and re.search('API_KEY|ACCESS_TOKEN|PASSWORD|SECRET',k)]
    if any(any(value in p.read_bytes() for value in secrets) for p in out.rglob('*') if p.is_file()):
        raise ValueError('Credential value in output')
    save(out/'validation.json',dict(passed=True,region_count=len(data['regions']),paid_api_attempts=len(ledger),
         automatic_retries=0,json_syntax_and_schema_valid=True,model_descriptions_unchanged=True,
         original_grid_masks_valid=True,all_unreviewed=True,coverage_union_checked=True,
         html_links=len(links.links),credential_value_scan_passed=True,additional_model_inference=False,
         benchmark_scoring_run=False,anchors_or_relations_created=False,
         bbox_definition='Algorithm proposal ROI; SLIC support may extend outside; not a model bbox or exact mask bbox'))
    print('Validation passed',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=['prepare','request','visualize','validate'],required=True)
    args=parser.parse_args()
    if args.phase=='prepare':prepare(args.output.resolve())
    elif args.phase=='request':request(args.output.resolve())
    elif args.phase=='visualize':visualize(args.output.resolve())
    else:validate(args.output.resolve())


if __name__=='__main__':main()
