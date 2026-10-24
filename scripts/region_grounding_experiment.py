"""CPU cached-SAM3 grounding experiment: no APIs, model loads, Agent or Blender.

Fresh plan-derived SAM3 prompts are saved separately. When no GPU is idle, this
experiment must not relabel historical prompted masks as new automatic inference.
"""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_evidence import (ground_region_candidates,resolve_region_conflicts,
    region_sam3_prompts,grounding_concepts,validate_region_first_plan,load_document,consensus_sam_candidates)


def read(path):return json.loads(Path(path).read_text())


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def box(mask):
    y,x=np.nonzero(mask)
    return [int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)] if len(x) else None


def edges(mask):
    result=np.zeros(mask.shape,bool)
    result[1:]|=mask[1:]!=mask[:-1];result[:,1:]|=mask[:,1:]!=mask[:,:-1]
    return result


COLORS=np.array([[240,75,65],[255,185,35],[55,140,250],[35,205,140],[180,70,235]])


def views(folder,rgb,regions,masks,reason=None):
    """Overlap always magenta, never hidden by painter's Region ordering."""
    count=masks.sum(axis=0);image=rgb.copy()
    for index,(region,mask) in enumerate(zip(regions,masks)):
        color=COLORS[index];only=mask&(count==1)
        image[only]=np.uint8(.72*rgb[only]+.28*color)
        image[edges(mask)&(count<=1)]=color
        solo=rgb.copy();solo[mask]=np.uint8(.65*rgb[mask]+.35*color);solo[edges(mask)]=color
        Image.fromarray(solo).save(folder/(region['id']+'_overlay.png'))
        Image.fromarray(mask.astype(np.uint8)*255).save(folder/(region['id']+'.png'))
    image[count>1]=np.uint8(.35*rgb[count>1]+.65*np.array([255,0,220]))
    im=Image.fromarray(image);draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
    for row,mask in zip(regions,masks):
        if not mask.any():continue
        distance=ndimage.distance_transform_edt(mask);y,x=np.unravel_index(distance.argmax(),mask.shape)
        x=int(np.clip(x,28,im.width-28));y=int(np.clip(y,15,im.height-15))
        draw.text((x,y),row['id'],font=font,anchor='mm',fill='white',stroke_width=3,stroke_fill='black')
    im.save(folder/'overlay.png')
    unknown=count==0
    Image.fromarray(unknown.astype(np.uint8)*255).save(folder/'unassigned.png')
    Image.fromarray((count>1).astype(np.uint8)*255).save(folder/'overlap.png')
    unassigned=rgb.copy();unassigned[unknown]=np.uint8(.25*rgb[unknown]+.75*np.array([150,150,150]))
    Image.fromarray(unassigned).save(folder/'unassigned_overlay.png')
    if reason is not None:
        Image.fromarray(reason).save(folder/'conflict_reasons.png')
        conflicts=rgb.copy()
        conflicts[reason==2]=np.uint8(.4*rgb[reason==2]+.6*np.array([40,230,100]))
        conflicts[reason==3]=np.uint8(.3*rgb[reason==3]+.7*np.array([255,0,220]))
        Image.fromarray(conflicts).save(folder/'conflict_overlay.png')
    return dict(region_union_fraction=float((count>0).mean()),overlap_fraction=float((count>1).mean()),
                unassigned_fraction=float(unknown.mean()),per_region_pixels=[int(m.sum()) for m in masks],
                pixel_count=int(count.size),dense_global_coverage=1.,reviewed_region_coverage=0.)


def method(out,key,rgb,regions,masks,reason=None,source=None):
    folder=out/key;folder.mkdir()
    stats=views(folder,rgb,regions,masks,reason)
    rows=[]
    for row,mask in zip(regions,masks):
        geometry=box(mask)
        item=dict(row,mask=row['id']+'.png',bbox=geometry,reviewed=False,mask_reviewed=False,reliability=0.,
                  localization_status='candidate_partial_support' if geometry else 'unavailable_no_valid_support',
                  source=source,metrics=['semantic','spatial','appearance','statistical','perceptual'],
                  inventory_complete=False,semantic_extent_verified=False)
        if geometry is None:item.pop('bbox')
        rows.append(item)
    save(folder/'evidence.json',dict(image_size=[rgb.shape[1],rgb.shape[0]],regions=rows,anchors=[],relations=[],
         reviewed=False,inventory_complete=False,source=source,formal_score=False,statistics=stats))
    save(folder/'statistics.json',stats)
    return dict(method=key,**stats)


def run(out):
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    pilot=ROOT/'results/region_first_pilot_bw0074';cache=ROOT/'results/multiscene_region_extraction'
    source_plan=read(pilot/'vlm_plan.json')
    plan=validate_region_first_plan(dict(regions=[{k:r[k] for k in ['id','name','location','content']} for r in source_plan['regions']]))
    regions=plan['regions'];info=read(pilot/'input.json')
    original=Path(info['reference_rgb']);image=Image.open(original).convert('RGB');rgb=np.asarray(image)
    if list(image.size)!=info['image_size']:raise ValueError('Original reference dimensions changed')
    shutil.copyfile(original,out/('reference'+original.suffix))
    save(out/'plan.json',source_plan)
    save(out/'source.json',dict(reference_rgb=str(original),vlm_plan=str(pilot/'vlm_plan.json'),image_size=list(image.size),
         task_id='bw_0074',agent_render_used=False,paid_vlm_calls=0,new_sam3_inference=False))
    save(out/'plan_derived_sam3_prompts.json',dict(regions=region_sam3_prompts(regions),executed=False,
         reason='Both GPU observations show all eight GPUs occupied; use cached historical SAM3 masks only',
         location_usage='Soft prior only; no hand-authored boxes, points or Region-ID priorities'))
    rawdir=out/'raw_candidates';rawdir.mkdir();candidates=[];metadata=[]
    for method_name in ('sam3_text','sam3_visual'):
        for kind in ('region_candidates','anchor_candidates'):
            path=cache/kind/'bw_0074'/method_name/'candidates.json'
            document=read(path)
            for row in document.get('regions',[])+document.get('anchors',[]):
                if not row.get('category'):continue
                source_mask=path.parent/row['mask']
                mask=np.asarray(Image.open(source_mask))>0
                if mask.shape!=rgb.shape[:2]:raise ValueError('Native SAM3 coordinate grid mismatch')
                relative=row['id']+'.png';shutil.copyfile(source_mask,rawdir/relative)
                meta=dict(id=row['id'],category=row['category'],mask=relative,bbox=box(mask),
                    source_document=str(path),source_mask=str(source_mask),method=method_name,
                    prompt_source='Historical reference-side concept prompt' if method_name=='sam3_text' else 'Historical assistant-authored RGB loose bbox',
                    prompt_bbox=row.get('prompt_bbox'),reviewed=False,mask_reviewed=False,reliability=0.,
                    raw_model_score=row.get('raw_model_score',row.get('raw_iou_head_score')))
                metadata.append(meta);candidates.append(dict(meta,mask=mask))
    save(rawdir/'candidates.json',dict(image_size=list(image.size),candidates=metadata,reviewed=False,
         warning='Historical visual candidates used manual-style loose prompts; not new fully automatic plan-prompted SAM3 results'))
    rawviews=out/'raw_candidate_overlays';rawviews.mkdir()
    for candidate in candidates:
        mask=candidate['mask'];canvas=rgb.copy();canvas[mask]=np.uint8(.6*rgb[mask]+.4*np.array([255,180,30]))
        canvas[edges(mask)]=[255,80,30];Image.fromarray(canvas).save(rawviews/(candidate['id']+'.png'))
    baseline_doc=read(pilot/'localized_regions.json')
    a=np.stack([np.asarray(Image.open(pilot/r['mask']))>0 for r in baseline_doc['regions']])
    summaries=[method(out,'A_baseline',rgb,regions,a,source='Unchanged historical Region-first SLIC/DINO support')]
    for number,specific in [(1,False),(2,True)]:
        tick=time.monotonic();association=ground_region_candidates(regions,candidates,rgb.shape[:2],specific=specific)
        masks=association['masks']
        summaries.append(method(out,f'round{number}_B_union',rgb,regions,masks,
                  source='Historical SAM3 candidates; '+('name/content association' if not specific else 'specific-name incidental-mention filtering')))
        resolved=resolve_region_conflicts(masks,association['scores'] if specific else None,margin=.08)
        summaries.append(method(out,f'round{number}_C_resolved',rgb,regions,resolved['masks'],resolved['reason'],
                  source='All conflicts abstain' if not specific else 'Semantic specificity + SAM boundary interior + position; weak margins abstain'))
        folder=out/f'round{number}_C_resolved'
        Image.fromarray(resolved['conflict'].astype(np.uint8)*255).save(folder/'input_conflicts.png')
        associations=association['associations']
        save(out/f'round{number}_associations.json',dict(rows=associations,heuristic_score_definition=association['score_definition'],
             score_weights=dict(named_semantics=.9,mentioned_semantics=.85,area_penalty=.5,interior=.04,position=.04),
             per_region_order=[r['id'] for r in regions],reliability_used=False,reviewed=False))
        reason=resolved['reason'];components,n=ndimage.label(reason==3)
        ambiguity=[]
        for component,slices in enumerate(ndimage.find_objects(components),1):
            if slices is None:continue
            local=components[slices]==component
            ambiguity.append(dict(component=component,pixels=int(local.sum()),
                bbox=[slices[1].start,slices[0].start,slices[1].stop,slices[0].stop],
                reason='Conflicting supported Regions have insufficient evidence separation; kept Unassigned'))
        save(folder/'conflicts.json',dict(input_conflict_pixels=int(resolved['conflict'].sum()),
             separated_pixels=int((reason==2).sum()),ambiguous_pixels=int((reason==3).sum()),
             reason_legend={'0':'no candidate support','1':'single supported Region','2':'separated heuristic winner','3':'ambiguous conflict; Unassigned'},
             margin=.08,unassigned_components=ambiguity,reviewed=False))
        permutation=list(reversed(range(len(regions))))
        again=ground_region_candidates([regions[i] for i in permutation],candidates[::-1],rgb.shape[:2],specific=specific)
        other=resolve_region_conflicts(again['masks'],again['scores'] if specific else None,margin=.08)
        if not np.array_equal(resolved['masks'][permutation],other['masks']):raise ValueError('Region ordering changed assignment')
        if not np.array_equal(resolved['unassigned'],other['unassigned']):raise ValueError('Ordering changed abstention')
        save(folder/'invariants.json',dict(order_and_candidate_permutation_invariant=True,
             disjoint=not (resolved['masks'].sum(axis=0)>1).any(),
             subset_of_input_support=not (resolved['masks']&~masks).any(),
             local_cpu_seconds=time.monotonic()-tick,model_forward_calls=0))
        retention=[]
        for region_index,row in enumerate(regions):
            for candidate in candidates:
                if not any(a['region_id']==row['id'] and a['candidate_id']==candidate['id'] and not a['suppressed_incidental_mention'] for a in associations):continue
                retention.append(dict(region_id=row['id'],candidate_id=candidate['id'],category=candidate['category'],
                    retained_fraction=float((candidate['mask']&resolved['masks'][region_index]).sum()/candidate['mask'].sum()),
                    definition='Agreement with the same input candidate, not content recall or segmentation accuracy'))
        save(folder/'candidate_retention.json',retention)
    audit=[]
    for task in ('bw_9064','bw_0073'):
        qualified=[]
        for p in (ROOT/'results').rglob('vlm_plan.json'):
            if task not in str(p):continue
            d=read(p)
            if d.get('structure_valid') is True and d.get('regions'):qualified.append(str(p))
        cached={name:read(cache/'methods'/task/name/'run.json') for name in ('sam3_text','sam3_visual')}
        audit.append(dict(task_id=task,valid_region_first_plan_files=qualified,
             grounding_status='blocked_no_valid_vlm_region_plan' if not qualified else 'not_executed_in_this_pilot',
             cached_candidates={name:dict(mask_count=d['mask_count'],coverage=d['raw_mask_union_coverage'],statistics_grid=d.get('statistics_grid')) for name,d in cached.items()},
             paid_vlm_calls=0,reason='Do not invent a Region plan or reuse a failed/Anchor-style plan as Region-first output'))
    save(out/'generalization_audit.json',audit)
    with (out/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    save(out/'run.json',dict(rounds=2,methods=summaries,source_sam3_candidates=len(candidates),
        new_model_inference_calls=0,paid_api_calls=0,cpu_seconds=time.monotonic()-start,
        parameters_tuned_to_image=False,reviewed=False,accuracy_metrics_not_computed=True))
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>Region Grounding</title><style>body{font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}img{width:100%}figure{margin:0}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:6px}</style><h1>bw_0074：Region Grounding + Conflict Resolution</h1><p>全部候选 reviewed=false。GPU全部占用，仅复用历史SAM3；新生成的Plan prompts未执行。洋红色表示重叠，灰色表示Unassigned（可能包含漏掉的前景，不能等同已确认背景）。</p>'
    page+='<p>'+html.escape('；'.join(r['id']+' '+r['name'] for r in regions))+'</p><div class="grid"><figure>Reference RGB<img src="reference'+original.suffix+'"></figure><figure>A：旧粗块基线<img src="A_baseline/overlay.png"></figure></div>'
    for number in (1,2):
        b=f'round{number}_B_union';c=f'round{number}_C_resolved'
        page+=f'<h2>第{number}轮（固定规则，未按本图调参）</h2><div class="grid"><figure>B：SAM3候选并集<img src="{b}/overlay.png"></figure><figure>C：冲突消解<img src="{c}/overlay.png"></figure><figure>原冲突：绿=分离，洋红=弃权<img src="{c}/conflict_overlay.png"></figure><figure>Unassigned<img src="{c}/unassigned_overlay.png"></figure></div><details><summary>每个Region对照</summary><div class="grid">'
        for r in regions:page+=f'<figure>{html.escape(r["id"]+" "+r["name"])} B<img src="{b}/{r["id"]}_overlay.png"></figure><figure>C<img src="{c}/{r["id"]}_overlay.png"></figure>'
        page+='</div></details>'
    page+='<h2>原始SAM3候选</h2><p>历史文本提示与人工风格的松bbox提示来源分开记录，不能当作新的全自动Plan Grounding。</p><div class="grid">'
    for row in metadata:page+='<figure>'+html.escape(row['id']+' | '+row['category']+' | '+row['method'])+'<img loading="lazy" src="raw_candidate_overlays/'+row['id']+'.png"></figure>'
    page+='</div><p><a href="report.md">报告</a> · <a href="summary.csv">统计</a> · <a href="round2_C_resolved/evidence.json">最终候选Evidence</a> · <a href="plan_derived_sam3_prompts.json">未执行的Plan prompts</a></p></html>'
    (out/'comparison.html').write_text(page)
    print(json.dumps(dict(output=str(out),seconds=time.monotonic()-start,summary=summaries),ensure_ascii=False),flush=True)


def round_three(out):
    """One final fixed-source-consensus diagnostic; no per-image mask repair."""
    regions=[{k:r[k] for k in ['id','name','location','content']} for r in read(out/'plan.json')['regions']]
    image=Image.open(read(out/'source.json')['reference_rgb']).convert('RGB');rgb=np.asarray(image)
    raw=read(out/'raw_candidates/candidates.json')['candidates']
    candidates=[dict(r,mask=np.asarray(Image.open(out/'raw_candidates'/r['mask']))>0) for r in raw]
    consolidated=consensus_sam_candidates(candidates)
    folder=out/'round3_consensus_candidates';folder.mkdir()
    meta=[]
    for r in consolidated:
        path=r['id']+'.png';Image.fromarray(r['mask'].astype(np.uint8)*255).save(folder/path)
        meta.append(dict(r,mask=path))
    save(folder/'candidates.json',dict(candidates=meta,reviewed=False,
         definition='Per concept: union within prompt source, intersection across sources if present. Missing detections are not absence.'))
    tick=time.monotonic();association=ground_region_candidates(regions,consolidated,rgb.shape[:2],specific=True)
    resolved=resolve_region_conflicts(association['masks'],association['scores'])
    b=method(out,'round3_B_union',rgb,regions,association['masks'],source='Conservative cross-prompt-source agreement candidates')
    c=method(out,'round3_C_resolved',rgb,regions,resolved['masks'],resolved['reason'],source='Consensus candidates plus semantic/boundary conflict margin')
    permutation=list(reversed(range(len(regions))))
    reordered=ground_region_candidates([regions[i] for i in permutation],consolidated[::-1],rgb.shape[:2],specific=True)
    repeat=resolve_region_conflicts(reordered['masks'],reordered['scores'])
    if not np.array_equal(resolved['masks'][permutation],repeat['masks']):raise ValueError('Round3 ordering dependence')
    save(out/'round3_C_resolved/invariants.json',dict(order_and_candidate_permutation_invariant=True,
         disjoint=not (resolved['masks'].sum(axis=0)>1).any(),subset_of_input_support=not (resolved['masks']&~association['masks']).any(),
         local_cpu_seconds=time.monotonic()-tick,model_forward_calls=0))
    Image.fromarray(resolved['conflict'].astype(np.uint8)*255).save(out/'round3_C_resolved/input_conflicts.png')
    reason=resolved['reason']
    save(out/'round3_C_resolved/conflicts.json',dict(input_conflict_pixels=int(resolved['conflict'].sum()),
         separated_pixels=int((reason==2).sum()),ambiguous_pixels=int((reason==3).sum()),margin=.08,
         reason_legend={'0':'no candidate support','1':'single supported Region','2':'separated heuristic winner','3':'ambiguous conflict; Unassigned'},reviewed=False))
    save(out/'round3_associations.json',dict(rows=association['associations'],reviewed=False))
    save(out/'round3_summary.json',dict(methods=[b,c],cpu_seconds=time.monotonic()-tick,reviewed=False))
    page=(out/'comparison.html').read_text()
    append='<h2>第3轮：同概念跨提示来源一致支持（保守诊断）</h2><p>没有新推理。仅单来源的候选明确标记单来源，不把零检测解释为缺失。交集可能丢失真实内容，不能视作已验证的提高。</p><div class="grid">'
    for method_name,label in [('round3_B_union','B：一致候选并集'),('round3_C_resolved','C：进一步消解')]:
        append+=f'<figure>{label}<img src="{method_name}/overlay.png"></figure>'
    append+='<figure>冲突处理<img src="round3_C_resolved/conflict_overlay.png"></figure><figure>Unassigned<img src="round3_C_resolved/unassigned_overlay.png"></figure></div><details><summary>逐Region第3轮结果</summary><div class="grid">'
    for r in regions:append+=f'<figure>{html.escape(r["id"]+" "+r["name"])}<img src="round3_C_resolved/{r["id"]}_overlay.png"></figure>'
    append+='</div></details>'
    page=page.replace('href="summary.csv"','href="summary_all_rounds.csv"')
    (out/'comparison.html').write_text(page.replace('</html>',append+'</html>'))


def finalize(out):
    from html.parser import HTMLParser
    if (out/'validation.json').exists():raise FileExistsError('Preserve completed experiment')
    initial=read(out/'run.json');third=read(out/'round3_summary.json')
    summaries=initial['methods']+third['methods']
    raw=read(out/'raw_candidates/candidates.json')['candidates']
    assertions={};shape=tuple(read(out/'source.json')['image_size'][::-1])
    for summary in summaries:
        name=summary['method'];folder=out/name;doc=load_document(folder/'evidence.json')
        masks=np.stack([r['mask']>0 for r in doc['regions']]);count=masks.sum(axis=0)
        for row,mask in zip(doc['regions'],masks):
            if mask.shape!=shape or row['reviewed'] is not False or row['mask_reviewed'] is not False or row['reliability']!=0:
                raise ValueError('Invalid candidate flags/grid')
            if mask.any() and row['bbox']!=box(mask):raise ValueError('Native bbox mismatch')
        if not np.isclose((count>1).mean(),summary['overlap_fraction']):raise ValueError('Overlap statistic mismatch')
        if not np.isclose((count==0).mean(),summary['unassigned_fraction']):raise ValueError('Unassigned statistic mismatch')
        if not np.array_equal(np.asarray(Image.open(folder/'unassigned.png'))>0,count==0):raise ValueError('Unassigned not exact complement')
        if '_C_' in name:
            invariant=read(folder/'invariants.json')
            if (count>1).any() or not all(invariant[k] for k in ['order_and_candidate_permutation_invariant','disjoint','subset_of_input_support']):
                raise ValueError('Conflict invariant failed')
        assertions[name]=dict(regions=len(masks),loader_compatible=True,unreviewed=True,
            component_counts=[int(ndimage.label(mask)[1]) for mask in masks],
            overlap_fraction=float((count>1).mean()),unassigned_fraction=float((count==0).mean()))
    for row in raw:
        if (out/'raw_candidates'/row['mask']).read_bytes()!=Path(row['source_mask']).read_bytes():raise ValueError('Historical mask copy differs')
    with (out/'summary_all_rounds.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    ledger=dict(rounds=3,methods=summaries,source_sam3_candidates=len(raw),paid_api_calls=0,new_model_inference_calls=0,
        cpu_experiment_seconds=initial['cpu_seconds']+third['cpu_seconds'],gpu_inference='skipped_all_GPUs_busy',
        accuracy_metrics_not_computed=True,all_candidates_reviewed=False)
    save(out/'experiment_summary.json',ledger)
    width,height=shape[::-1]
    sheet=Image.new('RGB',(width*2+20,(height+46)*2+20),'white');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',23)
    panels=[('Reference RGB','reference.jpg'),('A | historical SLIC/DINO support','A_baseline/overlay.png'),
            ('B | cached SAM3 semantic union (round2)','round2_B_union/overlay.png'),
            ('C | conflict resolution (round2; unreviewed)','round2_C_resolved/overlay.png')]
    for i,(label,path) in enumerate(panels):
        x=(i%2)*(width+20);y=(i//2)*(height+66)
        draw.text((x+8,y+8),label,font=font,fill='black');sheet.paste(Image.open(out/path).convert('RGB'),(x,y+46))
    sheet.save(out/'comparison_round2.png')
    lines=['# Region Grounding + Conflict Resolution：bw_0074','',
        '结论：目前不能确认“默认SAM3即可稳定地得到内容完整、背景干扰少的粗Region”。本轮可以保证冲突后的Mask无重叠、编号顺序不影响归属，但缓存候选缺失的工作设施和音响设备无法靠冲突消解恢复。禁止人工修补，全部候选未审核，不进入正式评分。','',
        '本轮仅复用上轮成功的4区VLM JSON。新付费API请求0次、新模型推理0次；两次GPU观察均为8张40GiB卡被其他任务占用，每张约31GiB、16个外部计算进程。因此没有启动新SAM3/DINO。官方代码、隔离环境和本地sam3.pt仍存在，Plan通用生成的提示保存在plan_derived_sam3_prompts.json，**没有执行**。','',
        '## 对照与三轮固定规则','',
        '|方法|候选并集覆盖|区域重叠|Unassigned|','|---|---:|---:|---:|']
    lines+=['|'+s['method']+'|'+f'{s["region_union_fraction"]:.2%}'+'|'+f'{s["overlap_fraction"]:.2%}'+'|'+f'{s["unassigned_fraction"]:.2%}'+'|' for s in summaries]
    lines += ['', '上表均为原图像素并集/交叠统计，不是准确率。Unassigned包含背景与漏掉的前景，不能视作已确认背景。Global/Dense Patch始终负责全图覆盖，不能以Region覆盖率越大越好选择方法。','',
        '- A：直接复制历史Region-first SLIC/DINO粗块支持，未重新调其窗口。',
        '- 第1轮 B：VLM名称/内容名词与历史SAM3类别匹配后取并集；C对所有区域冲突对称弃权。结果虽无重叠，但大范围共同书架候选使大量正确内容一并被弃权，是保留的失败案例。',
        '- 第2轮 B：若某概念直接命名另一Region，则抑制当前Region对该概念的顺带提及；例如组成描述中的“书架上”不能自动吞并整个书架。C以语义匹配、面积特异性、SAM边界内侧距离、软位置先验比较支持，差距不足0.08则Unassigned。没有按R编号、预设优先级、手工像素或bbox裁剪。',
        '- 第3轮：对同一概念先在同一历史提示来源内取并集，再对多个来源取交集，之后沿用第2轮归属规则。单来源保留并标记single_source_unverified，不把零检测当物体不存在。交集减少一部分宽泛支持，同时损失书架陈列与沙发织物，是保守诊断，不宣布更优。','',
        '归属支持的启发式公式：semantic × (1 − 0.5 × candidate_area_fraction) + 0.04 × mask_interior + 0.04 × position_prior；名称匹配0.9、组成匹配0.85。区域内多个候选取max，重复候选不会累加票数。所有权重均未校准；没有使用SAM分数作为正确概率或Evidence reliability。只生成候选，reliability=0。阈值全局固定，没有按这张图扫参。','',
        '## 逐区静态检查与失败','',
        '- R1工作区：显示器、透明椅等可保留；书桌、台灯、笔记本整组缺少历史候选。大量工作台背景仍被宽泛书架候选归入R2。不能声称工作区完整定位。',
        '- R2展示书架：陈列物和框架有支持，但宽泛候选带入工作区墙板、桌面、部分下柜/地板；跨来源交集仍未解决语义边界。第1轮完全弃权导致严重漏分，第3轮交集又产生孔洞和碎片。',
        '- R3唱片与音响区：主要只得到部分唱片；收录机和唱盘没有对应历史Mask，保留了明确的完整性失败。新生成提示包括实际Plan中的boombox/turntable，但GPU不可用，未推理，也未把唱片Mask延展成音响Mask。',
        '- R4沙发区：大部分可见主体有历史Mask支持，背景混入比旧粗块更少的视觉迹象需要人工确认；织物、抱枕边界仍有漏分，第3轮交集尤其丢失部分彩色织物。无人工GT，不声称准确率提高。','',
        '以上是助手对参考图与Overlay的静态检查，**不是人工审核通过**。最终4区数目沿用VLM，无逐书逐唱片评分；多连通分量可以组成一个Region，但碎片/孔洞仍需审核。各方法每区Overlay、原始候选、冲突图和Unassigned图均保留。','',
        '第2轮C可作为较宽松的人工审核候选；第3轮作为更保守的失败对照。两者都不应自动冻结为正式Evidence。所有最终C均0重叠，仅证明几何互斥，不证明语义正确或内容完整。','',
        '## 来源与泛化限制','',
        f'复用{len(raw)}个真实历史SAM3候选（文本和Visual两类）。Visual来源含之前助手提供的松bbox，文本概念也是参考侧固定提示；它们不是本轮由VLM Plan自动新生成的分割。当前同义词表是有限的中英文名词匹配，未验证开放词汇泛化，不能当作完整语义理解器。','',
        'bw_9064、bw_0073的已有SAM3候选元数据已清点，但没有成功的Region-first VLM Plan；bw_9064上次多任务回复结构失败，不能拿局部残片或手工Evidence当有效Plan。本轮不调用付费VLM、不凭目标答案补Plan，故真实跨场景Grounding验证阻塞。详见generalization_audit.json。','',
        '## 工程、验证与成本','',
        '新增/修改：benchmark_evidence.py中添加通用概念提取、Plan提示生成、SAM候选关联、对称冲突消解和跨来源一致支持；新增scripts/region_grounding_experiment.py；扩展tests/test_region_hierarchy.py。复用现有Evidence loader、原始RGB、SLIC/DINO基线、SAM3官方历史产物。未修改五能量数学公式、权重、Runtime blocked或历史产物，未执行Agent/Blender，未提交Git。','',
        'evidence.json沿用regions/anchors/relations格式（没有新建Anchor/Relation），所有reviewed=false、mask_reviewed=false、reliability=0。无支持的Region仍保留并标unavailable_no_valid_support，不伪造零误差。独立Region Mask默认来自resolve_region_conflicts，其Unassigned为精确补集。','',
        f'本地CPU实验约{ledger["cpu_experiment_seconds"]:.2f}秒（含保存图、真实图像顺序置换复查；不含人工等待）。本轮GPU峰值与SAM3新推理时间为N/A，未拿旧GPU占用充当新测量。API成本0次请求；没有下载模型/依赖。测试详见tests.log，产物和互斥不变量见validation.json。','',
        '不计算IoU、Boundary F1、真内容召回率或分割准确率；candidate_retention.json只是与同一批输入Mask的一致性比例，不是独立质量证据。泛化未完成，默认新SAM3是否稳定尚未得到本轮验证。','',
        '## 复现（CPU缓存模式，零API）','', '```bash','cd /home/xymo/projects/e-harness',
        'OUT=results/region_grounding_conflict_resolution_replay',
        'export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_grounding_experiment.py --output "$OUT" --phase initial',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_grounding_experiment.py --output "$OUT" --phase round3',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_grounding_experiment.py --output "$OUT" --phase finalize',
        '/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -v','```','',
        '输出目录必须不存在，避免覆盖。新SAM3 Plan提示需要空闲GPU才能执行，本脚本不自动加载模型或连接网络；当前结果明确为缓存候选探索。已到3轮上限，本轮停止。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,tag,attrs):self.paths.extend(v for k,v in attrs if k in {'src','href'})
    links=Links();links.feed((out/'comparison.html').read_text())
    for ref in links.paths:
        if not (out/ref).is_file():raise ValueError('Broken HTML link '+ref)
    save(out/'validation.json',dict(passed=True,methods=assertions,html_links=len(links.paths),
        native_mask_grid=list(shape[::-1]),raw_candidates_preserved=len(raw),
        paid_api_calls=0,new_model_inference_calls=0,region_id_priority_used=False,
        all_final_C_disjoint=True,all_final_C_order_invariant=True,all_final_C_subset_of_candidate_support=True,
        semantic_accuracy_claimed=False,all_unreviewed=True,formal_scoring_run=False))
    print('Finalization and validation passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=['initial','round3','finalize'],default='initial')
    args=parser.parse_args()
    if args.phase=='initial':run(args.output.resolve())
    elif args.phase=='round3':round_three(args.output.resolve())
    else:finalize(args.output.resolve())
