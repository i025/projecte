"""One reference-only SAM2 comparison; no VLM requests or energy scoring."""
import argparse
import html
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from e_harness.benchmark_evidence import sam2_box_masks,load_document
from scripts.vlm_direct_grounding import native_coordinates,validate_direct
from scripts.region_grounding_experiment import read,save,method,edges
from scripts.region_first_generalization import panel_grid,write_csv
from compare_multiscene_regions import gpu_check

SOURCE=ROOT/'results/vlm_direct_grounding_bw0073'
CHECKPOINT=Path('/home/xymo/models/sam2')


def conservative_hybrid(box,sam):
    """A box-prompt mask and its quality score cannot establish group completeness."""
    box=np.asarray(box,bool)
    if box.ndim!=2 or not box.any():raise ValueError('Expected a nonempty HxW Box mask')
    if sam is not None and np.asarray(sam).shape!=box.shape:raise ValueError('SAM and Box grids differ')
    return box.copy(),dict(decision='retain_box',status='uncertain',reviewed=False,
        reason='No independent functional-content completeness evidence; SAM quality and geometry alone cannot authorize deleting Box pixels')


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    for name in ('input.json','region_plan.json','direct_regions.json','reference.png'):
        shutil.copyfile(SOURCE/name,out/name)
    info=read(out/'input.json');plan=read(out/'region_plan.json')
    answer={'regions':[{k:r[k] for k in ('id','bbox','polygons')} for r in read(out/'direct_regions.json')['regions']]}
    validate_direct(answer,[r['id'] for r in plan['regions']])
    assert info['task_id']=='bw_0073'
    assert list(Image.open(info['reference_rgb']).size)==info['native_image_size']
    (out/'A_box_native').mkdir()
    boxes=[]
    for row in answer['regions']:
        if row['bbox'] is None:raise ValueError('A saved Direct Box is required')
        shutil.copyfile(SOURCE/'B_direct_box_native'/(row['id']+'.png'),out/'A_box_native'/(row['id']+'.png'))
        boxes.append(dict(id=row['id'],normalized_bbox=row['bbox'],
            native_bbox=native_coordinates(row,info['native_image_size'])['bbox'],reviewed=False))
    save(out/'box_prompts.json',dict(image_size=info['native_image_size'],regions=boxes,source=str(SOURCE/'direct_regions.json'),reviewed=False))
    save(out/'protocol.json',dict(task_id='bw_0073',reference_only=True,source=str(SOURCE),
        checkpoint=str(CHECKPOINT),adapter='existing benchmark.evidence.sam2_box_masks',
        multimask_output=False,candidates_per_box=1,prompt_count=len(boxes),new_vlm_calls=0,
        hybrid_rule='Retain Box, uncertain, unless independent completeness evidence exists; none supplied in this experiment',
        candidate_union=False,mask_repairs=False,reviewed=False))
    print('Prepared saved Plan and original Direct Boxes; no inference',flush=True)


def infer(out):
    import torch
    uuid=os.environ.get('CUDA_VISIBLE_DEVICES','')
    if not uuid.startswith('GPU-') or ',' in uuid:raise ValueError('One explicit GPU UUID required')
    if (out/'inference_status.json').exists():raise FileExistsError('One comparison already attempted')
    if read(out/'offline_checks.json').get('passed') is not True:raise ValueError('Offline checks required')
    save(out/'inference_reserved.json',dict(maximum_attempts=1,reviewed=False))
    observations=[]
    try:
        observations.append(gpu_check(uuid,idle=True));time.sleep(3)
        observations.append(gpu_check(uuid,idle=True))
        torch.set_num_threads(2);torch.set_num_interop_threads(1)
        torch.cuda.set_per_process_memory_fraction(.20,0)
        info=read(out/'input.json');image=Image.open(info['reference_rgb']).convert('RGB')
        prompts=read(out/'box_prompts.json')['regions'];torch.cuda.reset_peak_memory_stats()
        start=time.monotonic()
        masks,scores,details=sam2_box_masks(image,[r['native_bbox'] for r in prompts],CHECKPOINT,device='cuda:0')
        torch.cuda.synchronize();seconds=time.monotonic()-start
        (out/'sam_raw').mkdir();rows=[]
        for row,mask,score in zip(prompts,masks,scores):
            Image.fromarray(mask).save(out/'sam_raw'/(row['id']+'.png'))
            rows.append(dict(row,mask=row['id']+'.png',raw_iou_head_score=float(score),
                quality_is_correctness_probability=False,mask_reviewed=False,reliability=0.,reviewed=False))
        save(out/'sam_raw/candidates.json',dict(image_size=info['native_image_size'],regions=rows,
            reference_rgb=info['reference_rgb'],postprocessing=details['postprocessing'],reviewed=False))
        save(out/'inference_status.json',dict(status='available',inference_calls=1,box_prompts=len(rows),
            wall_seconds_including_model_load_and_postprocessing=seconds,
            gpu_peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
            gpu_peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
            gpu_observations=observations,gpu_after=gpu_check(uuid),info=details,reviewed=False))
        del masks;torch.cuda.empty_cache()
        print('SAM2 native masks saved; no mask repair or unions',flush=True)
    except Exception as exc:
        if not (out/'inference_status.json').exists():
            save(out/'inference_status.json',dict(status='unavailable',error_type=type(exc).__name__,
                error=str(exc),gpu_observations=observations,automatic_retry=False,reviewed=False))
        raise


def tint(rgb,mask,color,alpha=.20):
    result=rgb.copy();color=np.array(color)
    result[mask]=np.uint8((1-alpha)*rgb[mask]+alpha*color);result[edges(mask)]=color
    return Image.fromarray(result)


def render(out):
    info=read(out/'input.json');plan=read(out/'region_plan.json')['regions'];size=info['native_image_size']
    image=Image.open(out/'reference.png').convert('RGB');rgb=np.asarray(image)
    available=(out/'sam_raw/candidates.json').exists()
    keys=['A_box']+(['B_sam'] if available else [])+['C_hybrid']
    stacks={k:[] for k in keys};counts={k:np.zeros(tuple(size[::-1]),np.uint8) for k in keys}
    records={k:[] for k in keys};diagnostics=[]
    (out/'C_hybrid_native').mkdir();(out/'differences').mkdir();(out/'per_region').mkdir()
    for row in plan:
        rid=row['id'];a=np.asarray(Image.open(out/'A_box_native'/(rid+'.png')),bool)
        b=np.asarray(Image.open(out/'sam_raw'/(rid+'.png')),bool) if available else None
        c,decision=conservative_hybrid(a,b);Image.fromarray(c).save(out/'C_hybrid_native'/(rid+'.png'))
        group={'A_box':a,'C_hybrid':c}
        if available:group['B_sam']=b
        per=dict(id=rid,hybrid_decision=decision,reviewed=False)
        for key,mask in group.items():
            counts[key]+=mask
            small=np.asarray(Image.fromarray(mask).resize(image.size,Image.Resampling.NEAREST),bool)
            stacks[key].append(small)
            labels,n=ndimage.label(small);sizes=np.bincount(labels.ravel())[1:]
            per[key]=dict(native_pixels=int(mask.sum()),working_grid_components=n,
                largest_component_fraction=float(sizes.max()/sizes.sum()) if len(sizes) else None,
                component_statistics_grid=list(image.size))
            records[key].append(dict(row,mask=rid+'.png',reviewed=False,mask_reviewed=False,
                reliability=0.,representation='coarse_evaluation_roi',native_pixel_count=int(mask.sum()),
                status='uncertain' if key=='C_hybrid' else 'candidate',semantic_GT=False))
        if available:
            removed=a&~b;outside=b&~a
            for label,mask,color in [('removed_from_box',removed,[245,65,105]),('outside_box',outside,[245,155,25])]:
                Image.fromarray(mask).save(out/'differences'/(rid+'_'+label+'.png'))
                small=np.asarray(Image.fromarray(mask).resize(image.size,Image.Resampling.NEAREST),bool)
                tint(rgb,small,color).save(out/'differences'/(rid+'_'+label+'_overlay.png'))
            per.update(sam_retained_box_fraction=float((a&b).sum()/a.sum()),
                sam_removed_box_pixels=int(removed.sum()),sam_outside_box_pixels=int(outside.sum()),
                removed_pixels_are_not_verified_background=True)
        diagnostics.append(per)
    stats=[]
    for key in keys:
        mask=np.stack(stacks[key]);stat=method(out,key,rgb,plan,mask,source=str(out/'box_prompts.json'))
        count=counts[key];stat.update(native_union_fraction=float((count>0).mean()),
            native_overlap_fraction=float((count>1).mean()),native_unassigned_fraction=float((count==0).mean()))
        directory=out/('sam_raw' if key=='B_sam' else key+'_native')
        save(directory/'evidence.json',dict(image_size=size,regions=records[key],anchors=[],relations=[],reviewed=False,formal_score=False))
        load_document(out/key/'evidence.json');stats.append(stat)
        # Light fill leaves RGB content visible, including at overlaps.
        canvas=rgb.copy();total=mask.sum(0)
        for index,support in enumerate(mask):
            color=np.array([[235,65,55],[245,180,20],[45,135,245],[30,200,135]][index])
            single=support&(total==1);canvas[single]=np.uint8(.84*rgb[single]+.16*color)
            canvas[edges(support)]=color
            tint(rgb,support,color,alpha=.16).save(out/key/(plan[index]['id']+'_overlay.png'))
        canvas[total>1]=np.uint8(.76*rgb[total>1]+.24*np.array([255,0,220]))
        im=Image.fromarray(canvas);draw=ImageDraw.Draw(im)
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
        for row,support in zip(plan,mask):
            if support.any():
                distance=ndimage.distance_transform_edt(support);y,x=np.unravel_index(distance.argmax(),support.shape)
                draw.text((int(x),int(y)),row['id'],fill='white',font=font,stroke_width=2,stroke_fill='black')
        im.save(out/key/'overlay.png')
    save(out/'diagnostics.json',dict(regions=diagnostics,reviewed=False,accuracy_available=False))
    write_csv(out/'summary.csv',stats)
    na=Image.new('RGB',image.size,'#dddddd');ImageDraw.Draw(na).text((20,20),'SAM unavailable: see inference_status.json',fill='black')
    panels=[('Reference RGB',image),('A: saved Direct Box',Image.open(out/'A_box/overlay.png')),
        ('B: raw SAM2 Box prompt',Image.open(out/'B_sam/overlay.png') if available else na),
        ('C: Hybrid retains Box (uncertain)',Image.open(out/'C_hybrid/overlay.png'))]
    panel_grid(panels,out/'comparison.png',width=850)
    body=['<!doctype html><meta charset="utf-8"><title>bw_0073 Box / SAM2 / Hybrid</title>',
        '<style>body{font:16px sans-serif;line-height:1.6;margin:24px;background:#f5f6f8}img{max-width:100%}table{width:100%;table-layout:fixed;border-collapse:collapse}td,th{border:1px solid #ccd2da;padding:8px;vertical-align:top}</style>',
        '<h1>bw_0073：Direct Box / SAM2 / Hybrid</h1>',
        '<p>全部候选 reviewed:false。SAM 原始输出与 Hybrid 决策分开保存；无独立内容完整性依据，Hybrid 全部回退 Box 并标为 uncertain。粉色删除像素不等于背景。</p>',
        '<p><a href="report.md">报告与离线复现</a> · <a href="region_plan.json">原始 Plan</a> · <a href="box_prompts.json">实际 Box Prompt</a> · <a href="inference_status.json">推理资源与原始质量信息</a> · <a href="diagnostics.json">几何诊断</a></p><img src="comparison.png">']
    for row in plan:
        rid=row['id'];p=[('Reference RGB',image),('A: '+rid,Image.open(out/'A_box'/(rid+'_overlay.png'))),
            ('B: '+rid,Image.open(out/'B_sam'/(rid+'_overlay.png')) if available else na),
            ('C: '+rid+' uncertain',Image.open(out/'C_hybrid'/(rid+'_overlay.png')))]
        panel_grid(p,out/'per_region'/(rid+'.png'))
        body+=['<h2>'+html.escape(rid+' '+row['name'])+'</h2><p>'+html.escape(row['content'])+'</p><img src="per_region/'+rid+'.png">']
        if available:body+=['<table><tr><th>SAM 从 Box 删除的像素（不等于背景）</th><th>SAM 延伸到 Box 外部</th></tr><tr><td><img src="differences/'+rid+'_removed_from_box_overlay.png"></td><td><img src="differences/'+rid+'_outside_box_overlay.png"></td></tr></table>']
    body.append('<h2>方法间重叠与未分配</h2><table><tr><th>方法</th><th>Overlap</th><th>Unassigned</th></tr>')
    for key in keys:body.append('<tr><td>'+key+'</td><td><img src="'+key+'/overlap.png"></td><td><img src="'+key+'/unassigned_overlay.png"></td></tr>')
    body.append('</table>')
    if (out/'initial_review.json').exists():
        body.append('<h2>助手静态初审，未人工审核</h2><table><tr><th>Region</th><th>SAM 内容诊断</th><th>Hybrid</th><th>Uncertain</th></tr>')
        for row in read(out/'initial_review.json')['regions']:
            body.append('<tr>'+''.join('<td>'+html.escape(row[k])+'</td>' for k in ('id','sam','hybrid','uncertain'))+'</tr>')
        body.append('</table>')
    (out/'comparison.html').write_text('\n'.join(body))
    print('Comparison and original-grid diagnostics saved; no inference',flush=True)


def replay(out,source):
    prepare(out)
    for name in ('inference_status.json','initial_review.json','report.md'):
        if (source/name).exists():shutil.copyfile(source/name,out/name)
    if (source/'sam_raw').exists():
        (out/'sam_raw').mkdir()
        for name in ['candidates.json']+[r['id']+'.png' for r in read(source/'region_plan.json')['regions']]:
            shutil.copyfile(source/'sam_raw'/name,out/'sam_raw'/name)
    save(out/'replay_info.json',dict(source=str(source),new_gpu_runs=0,new_model_calls=0,reviewed=False));render(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','infer','render','replay']);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path);args=parser.parse_args()
    if args.stage=='replay':
        if args.source is None:parser.error('replay requires --source')
        replay(args.output.resolve(),args.source.resolve())
    else:globals()[args.stage](args.output.resolve())
