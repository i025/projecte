"""Small reference-only SLIC / existing SAM2 / boundary-split comparison.

SAM2 is optional and uses the existing box adapter with a checked single device.
This script never reads an Agent render or Blender file.
"""
import argparse
from copy import deepcopy
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_config import write_json
from e_harness.benchmark_evidence import area_mask, coverage_audit, load_document


def bbox(mask):
    y,x=np.nonzero(mask)
    return [int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)]


def boundary(labels):
    edges=np.zeros(labels.shape,bool)
    edges[1:] |= labels[1:]!=labels[:-1]
    edges[:,1:] |= labels[:,1:]!=labels[:,:-1]
    return edges


def colors(labels):
    rng=np.random.default_rng(9064)
    palette=rng.integers(40,235,size=(int(labels.max())+1,3),dtype=np.uint8)
    return palette[labels]


def save_views(folder,image,labels,region_rows,anchor_masks,prompt_anchors):
    folder.mkdir(exist_ok=True)
    np.save(folder/'labels.npy',labels.astype(np.int32),allow_pickle=False)
    color=colors(labels)
    Image.fromarray(color).save(folder/'segmentation.png')
    overlay=np.uint8(.7*image+.3*color)
    overlay[boundary(labels)]=[255,225,20]
    Image.fromarray(overlay).save(folder/'mask_overlay.png')
    union=np.zeros(labels.shape,bool)
    for row in region_rows:
        if row.get('region_role')!='unknown_fallback':union |= row['mask']>0
    uncovered=image.copy()
    uncovered[~union]=np.uint8(.35*image[~union]+.65*np.array([255,30,80]))
    Image.fromarray(uncovered).save(folder/'uncovered.png')
    anchor_image=image.copy()
    for index,mask in enumerate(anchor_masks):
        color=np.array(prompt_anchors[index].get('overlay_color',[255,150,30]))
        anchor_image[mask]=np.uint8(.55*image[mask]+.45*color)
        anchor_image[boundary(mask.astype(int))]=color
    im=Image.fromarray(anchor_image);draw=ImageDraw.Draw(im)
    for a in prompt_anchors:
        box=a['bbox'];draw.rectangle(box,outline=tuple(a.get('overlay_color',[255,150,30])),width=2)
        draw.text((box[0],max(0,box[1]-14)),a['id'],fill=(0,0,0),stroke_width=1,stroke_fill=(255,255,255))
    if not anchor_masks:draw.text((15,15),'SLIC: no instance masks; boxes are prompts only',fill=(0,0,0),stroke_width=2,stroke_fill=(255,255,255))
    im.save(folder/'anchor_overlay.png')


def sam2_candidates(out,doc,device):
    """One explicit local inference; offline weights, no automatic GPU choice."""
    if doc.get('task_id')!='bw_9064' or doc['image_size']!=[1672,941]:
        raise ValueError('The five surface prompts are specific to the bw_9064 original RGB')
    folder=out/'sam2';folder.mkdir(exist_ok=True)
    if (folder/'raw_masks.npz').exists():raise FileExistsError('Preserve existing SAM2 outputs')
    resource=dict(cpu_threads=2,device=device)
    if device.startswith('cuda'):
        selected=os.environ.get('CUDA_VISIBLE_DEVICES','')
        if not selected.startswith('GPU-') or ',' in selected:
            raise ValueError('Explicitly select one idle GPU UUID using CUDA_VISIBLE_DEVICES')
        query=subprocess.run(['nvidia-smi','-i',selected,'--query-gpu=uuid,memory.total,memory.used,utilization.gpu',
                              '--format=csv,noheader,nounits'],capture_output=True,text=True,check=True).stdout
        uuid,total,used,util=[v.strip() for v in query.split(',')]
        if int(used)>128 or int(util)>0 or int(total)<8192:raise RuntimeError('GPU is not idle; do not start inference')
        resource.update(uuid=uuid,memory_total_mib=int(total),memory_used_mib=int(used),utilization_percent=int(util),process_memory_fraction=.12)
    write_json(folder/'resource_check.json',resource)
    import torch
    from e_harness.benchmark_evidence import sam2_box_masks
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    if device.startswith('cuda'):torch.cuda.set_per_process_memory_fraction(.12,0)
    prompts=[dict(id=r['id'],category=r['category'],bbox=r['bbox'],role='anchor') for r in doc['anchors']]
    prompts += [dict(id=key,category=category,bbox=box,role='surface') for key,category,box in [
        ('sam_wall_back','wall',[248,105,1429,743]),('sam_ceiling','ceiling',[78,0,1595,107]),
        ('sam_floor','wood_floor',[0,741,1672,941]),('sam_wall_left','wall',[0,0,249,851]),
        ('sam_wall_right','wall',[1428,0,1672,851])]]
    start=time.monotonic()
    masks,scores,info=sam2_box_masks(Image.open(doc['reference_image']).convert('RGB'),
        [p['bbox'] for p in prompts],'/home/xymo/models/sam2',device=device)
    np.savez_compressed(folder/'raw_masks.npz',**{p['id']:mask for p,mask in zip(prompts,masks)})
    write_json(folder/'run.json',dict(status='available',device=device,wall_seconds=time.monotonic()-start,
        prompts=[dict(p,raw_iou_head_score=float(s),reviewed=False,mask_reviewed=False) for p,s in zip(prompts,scores)],
        source=doc['reference_image'],model_directory='/home/xymo/models/sam2',info=info,reviewed=False,
        gpu_peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2 if device.startswith('cuda') else None,
        score_note='Raw SAM2 head scores are not semantic correctness probabilities or reliability weights'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reference-evidence',type=Path,default=ROOT/'results/bw_9064_evidence_review/candidate_evidence.json')
    parser.add_argument('--sam-device',choices=['cpu','cuda:0'],help='Explicit optional one-pass local SAM2; otherwise reuse saved masks')
    args=parser.parse_args()
    out=args.output.resolve()
    if (out/'segmentation_summary.json').exists():raise SystemExit('Preserve existing experiment; choose a new directory')
    out.mkdir(exist_ok=True,parents=True)
    from skimage.segmentation import slic
    import skimage
    old=load_document(args.reference_evidence)
    image=np.array(Image.open(old['reference_image']).convert('RGB'))
    shape=image.shape[:2]
    assert list(shape[::-1])==old['image_size']
    if args.sam_device:
        try:
            sam2_candidates(out,old,args.sam_device)
        except FileExistsError:
            raise  # Existing outputs must not be overwritten, even by failure metadata.
        except Exception as exc:
            (out/'sam2').mkdir(exist_ok=True)
            write_json(out/'sam2/run.json',dict(status='unavailable',reviewed=False,
                reason=f'{type(exc).__name__}: {exc}'))
    raw=out/'sam2/raw_masks.npz'
    sam_info=json.loads((out/'sam2/run.json').read_text()) if (out/'sam2/run.json').exists() else dict(status='unavailable',reason='No resource-approved SAM2 masks')
    sam_masks={}
    if raw.exists() and sam_info['status']=='available':
        with np.load(raw,allow_pickle=False) as z:sam_masks={k:z[k].copy() for k in z.files}
    all_regions=[];mask_archive={};methods={};slic_settings={}

    def region(key,mask,method,description,category=None,**extra):
        row=dict(id=key,description=description,bbox=bbox(mask),metrics=['appearance','spatial','statistical','perceptual'],
                 reliability=0.,reviewed=False,mask_reviewed=False,status='observable',method=method,
                 provenance=dict(reference=old['reference_image'],source_evidence=str(args.reference_evidence.resolve()),
                                 algorithm=method,render_used=False),**extra)
        if category:row.update(category=category,presence_evidence=True,metrics=['semantic']+row['metrics'])
        mask_archive[key]=mask.astype(bool)
        all_regions.append(row)
        return dict(row,mask=mask)

    anchor_masks=[sam_masks[a['id']] for a in old['anchors']] if sam_masks else []
    anchors=[]
    for a in old['anchors']:
        a=deepcopy(a)
        if a['id'] in sam_masks:
            mask=sam_masks[a['id']]
            folder=out/'sam2/anchor_masks';folder.mkdir(exist_ok=True)
            Image.fromarray(mask.astype(np.uint8)*255).save(folder/(a['id']+'.png'))
            a.update(prompt_bbox=a['bbox'],bbox=bbox(mask),mask='sam2/anchor_masks/'+a['id']+'.png',
                     mask_provenance=dict(model='/home/xymo/models/sam2',adapter='existing sam2_box_masks',reference=old['reference_image']),
                     position=[(bbox(mask)[0]+bbox(mask)[2])/2,(bbox(mask)[1]+bbox(mask)[3])/2])
        a.update(reviewed=False,mask_reviewed=False,reliability=0.)
        anchors.append(a)
    anchor_doc=dict(image_size=old['image_size'],reference_image=old['reference_image'],reviewed=False,
                    inventory_complete=False,regions=[],anchors=anchors,relations=[],
                    score_note='SAM2 head scores remain in sam2/run.json, never used as reliability')
    write_json(out/'candidate_anchors.json',anchor_doc)

    def boundary_crossings(labels):
        # Number of cells straddling at least one candidate Anchor mask boundary.
        hits=set()
        for mask in anchor_masks:
            inside=np.unique(labels[mask]);outside=np.unique(labels[~mask])
            hits.update(set(inside)&set(outside))
        return len(hits)

    for count in [100,200,400]:
        start=time.monotonic()
        labels=slic(image,n_segments=count,compactness=10.,sigma=1.,max_num_iter=10,
                    convert2lab=True,enforce_connectivity=True,start_label=0,channel_axis=-1)
        counts=np.bincount(labels.ravel());slices=ndimage.find_objects(labels+1)
        fill=[counts[i]/((s[0].stop-s[0].start)*(s[1].stop-s[1].start)) for i,s in enumerate(slices)]
        stats=dict(requested_segments=count,actual_segments=len(counts),seconds=time.monotonic()-start,
                   pixel_size_quantiles=dict(zip(['min','p25','median','p75','p95','max'],np.quantile(counts,[0,.25,.5,.75,.95,1]).tolist())),
                   nonrectangular_region_fraction=float(np.mean(np.array(fill)<.99)),
                   median_bbox_fill=float(np.median(fill)),boundary_pixel_fraction=float(boundary(labels).mean()),
                   anchor_boundary_straddling_cells=boundary_crossings(labels),
                   params=dict(compactness=10.,sigma=1.,max_num_iter=10,convert2lab=True,enforce_connectivity=True),
                   reviewed=False,semantic_claim=False)
        slic_settings[str(count)]=stats
        folder=out/f'slic_{count}'
        if count==200:
            slic_labels=labels.copy()
            rows=[region(f'slic_sp_{i:03d}',labels==i,'slic','Unknown semantic region: connected color/position superpixel',
                         superpixel_label=i) for i in range(len(counts))]
            methods['slic']=dict(status='available',illustrative_setting=200,coverage=coverage_audit(rows,shape,labels),
                                 anchor_masks=0,anchor_boundary_straddling_cells=stats['anchor_boundary_straddling_cells'])
            slic_rows=rows
        else:
            rows=[]
        # All SLIC pixels are assigned; no semantic label is manufactured.
        view_rows=rows or [dict(mask=np.ones(shape,bool))]
        save_views(folder,image,labels,view_rows,[],old['anchors'])

    if sam_masks:
        surfaces=[p for p in sam_info['prompts'] if p['role']=='surface']
        rows=[region(p['id'],sam_masks[p['id']],'sam2','Box-prompt surface candidate; name comes from unreviewed RGB prompt',
                     p['category'],prompt_bbox=p['bbox']) for p in surfaces]
        raw_rows=list(rows)
        raw_union=np.logical_or.reduce([r['mask'] for r in rows])
        # Dense assignment is supplied by transparent coordinate fallback, not SAM2.
        grid=np.zeros(shape,np.int32)
        for iy in range(2):
            for ix in range(2):
                tile=np.zeros(shape,bool);tile[iy*shape[0]//2:(iy+1)*shape[0]//2,ix*shape[1]//2:(ix+1)*shape[1]//2]=True
                grid[tile]=iy*2+ix
                mask=tile&~raw_union
                if mask.any():rows.append(region(f'sam_unknown_{iy}_{ix}',mask,'sam2','Unknown fallback; unassigned by surface prompts',region_role='unknown_fallback'))
        methods['sam2']=dict(status='available',coverage=coverage_audit(rows,shape,grid),
                             raw_prompt_region_coverage=float(raw_union.mean()),
                             raw_prompt_overlap_fraction=float((sum(r['mask'].astype(int) for r in raw_rows)>1).mean()),
                             anchor_masks=len(anchor_masks),dense_source='deterministic 2x2 fallback plus raw SAM2 masks',
                             inference=sam_info)
        # Color chart is a display partition, not overlap resolution or semantic GT.
        display=grid.copy()
        for i,r in enumerate(raw_rows,4):display[r['mask']]=i
        save_views(out/'sam2',image,display,rows,anchor_masks,old['anchors'])

        prompts=sam_info['prompts']
        signatures=np.zeros(shape,np.int64)
        for i,p in enumerate(prompts):signatures |= sam_masks[p['id']].astype(np.int64)<<i
        keys,inverse=np.unique(slic_labels.astype(np.int64)*(1<<len(prompts))+signatures,return_inverse=True)
        labels=inverse.reshape(shape).astype(np.int32)
        rows=[]
        anchor_bits=(1<<len(old['anchors']))-1
        for i,key in enumerate(keys):
            signature=int(key % (1<<len(prompts)))
            active=[p for j,p in enumerate(prompts) if signature&(1<<j)]
            surfaces_active=[p for p in active if p['role']=='surface']
            category=surfaces_active[0]['category'] if len(surfaces_active)==1 and not signature&anchor_bits else None
            rows.append(region(f'combined_piece_{i:03d}',labels==i,'combined',
                'SLIC cell split at every candidate SAM2 boundary; semantic class unknown unless a unique surface prompt applies',
                category,source_superpixel=int(key//(1<<len(prompts))),sam_signature=signature,
                candidate_prompt_ids=[p['id'] for p in active]))
        crossing=boundary_crossings(labels)
        assert crossing==0
        methods['combined']=dict(status='available',coverage=coverage_audit(rows,shape,labels),
                                 anchor_masks=len(anchor_masks),anchor_masks_changed=False,
                                 anchor_boundary_straddling_cells=crossing,
                                 fusion='Split (SLIC label, SAM2 mask membership bits); no forced semantic merge or deletion of small pieces',
                                 warning='Candidate boundaries are not reliable GT; splitting can amplify oversegmentation')
        counts=np.bincount(labels.ravel())
        methods['combined']['piece_sizes']=dict(min=int(counts.min()),median=float(np.median(counts)),
            max=int(counts.max()),below_16_pixels=int((counts<16).sum()),pixels_in_tiny_pieces=int(counts[counts<16].sum()))
        save_views(out/'combined',image,labels,rows,anchor_masks,old['anchors'])
    else:
        methods.update(sam2=dict(status='unavailable',reason=sam_info.get('reason')),
                       combined=dict(status='unavailable',reason='No SAM2 candidates to combine'))

    np.savez_compressed(out/'region_masks.npz',**mask_archive)
    write_json(out/'candidate_regions.json',dict(image_size=old['image_size'],reference_image=old['reference_image'],
        reviewed=False,inventory_complete=False,mask_archive='region_masks.npz',regions=all_regions,anchors=[],relations=[],
        methods=list(methods),
        note='All method alternatives retained; not a selected/frozen scoring reference. Unknown cells retain dense coverage.'))
    summary=dict(image_size=old['image_size'],source=old['reference_image'],render_used=False,
                 slic_implementation=dict(package='scikit-image',version=skimage.__version__,dependency_path=next(p for p in sys.path if 'project_e_slic_deps_' in p)),
                 slic_granularities=slic_settings,methods=methods,
                 previous_roi_coverage=coverage_audit(old['regions'],shape),
                 anchor_mask_stats=[dict(id=a['id'],area_pixels=int(sam_masks[a['id']].sum()),mask_bbox=bbox(sam_masks[a['id']]),
                    fraction_outside_prompt=float((sam_masks[a['id']] & ~area_mask({'bbox':a['bbox']},shape).astype(bool)).sum()/sam_masks[a['id']].sum()))
                    for a in old['anchors']] if sam_masks else [],
                 no_final_method_selected=True,reviewed=False,semantic_coverage_note='No human semantic review: all reviewed semantic coverage must remain zero')
    if anchor_masks:
        multiplicity=sum(mask.astype(np.uint8) for mask in anchor_masks)
        summary['anchor_overlap']=dict(overlap_pixels=int((multiplicity>1).sum()),
            union_pixels=int((multiplicity>0).sum()),max_multiplicity=int(multiplicity.max()),
            pairwise_pixels={old['anchors'][i]['id']+' / '+old['anchors'][j]['id']:int((a&b).sum())
                             for i,a in enumerate(anchor_masks) for j,b in enumerate(anchor_masks) if i<j})
    summary['failure_cases']=dict(
        slic=['Large smooth walls/ceiling are oversegmented; important objects cross superpixel boundaries.',
              'Plant foliage, chair legs and floor seams are not instance semantics.'],
        sam2=[f'{summary.get("anchor_overlap", {}).get("overlap_pixels", "unavailable")} overlapping Anchor pixels need review; no mask is auto-resolved.',
              'Table/pot and table/left-chair contact boundaries, plant leaf gaps, refrigerator feet and baseboards need human review.'],
        combined=['Splitting preserves every candidate boundary but increases fragmentation; Anchor masks are unchanged.',
                  'Unverified SAM2 errors propagate; tiny pieces are retained as Unknown, not erased for better coverage.'])
    write_json(out/'segmentation_summary.json',summary)

    def url(p):return os.path.relpath(Path(p).resolve(),out)
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>bw_9064 Region 方法对照</title>',
           '<style>body{font:15px system-ui;margin:22px;color:#222}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{border:1px solid #ccc;padding:10px;vertical-align:top}img{width:100%;height:auto}code{overflow-wrap:anywhere}pre{white-space:pre-wrap}small{color:#555}</style>',
           '<h1>bw_9064：SLIC / SAM2 / 组合方法候选</h1><p>原图唯一来源；未查看 Agent Render。所有新候选 reviewed=false、mask_reviewed=false，可靠性暂为0。Dense=100% 不等于语义理解正确。没有自动选择最终方法。</p>',
           f'<p><a href="{url(old["reference_image"])}">原始 RGB（1672×941）</a> · <a href="{url(args.reference_evidence.parent/"review.html")}">旧 ROI 审核材料（保留）</a> · <a href="candidate_regions.json">Region JSON</a> · <a href="candidate_anchors.json">Anchor JSON</a> · <a href="segmentation_summary.json">完整统计</a> · <a href="report.md">实验报告</a></p>',
           '<table><tr><th>SLIC（展示200设置）</th><th>SAM2 + Unknown 网格补全</th><th>SLIC + SAM2 边界分割</th></tr>']
    folders=['slic_200','sam2','combined']
    for title,file in [('彩色区域','segmentation.png'),('原图 Mask Overlay','mask_overlay.png'),('Anchor Mask Overlay','anchor_overlay.png'),('未由原始候选分配的区域（红色；补全不改变此诊断）','uncovered.png')]:
        parts.append('<tr>'+''.join(f'<td><b>{title}</b><a href="{folder}/{file}"><img loading="lazy" src="{folder}/{file}" alt="{folder} {title}"></a></td>' if (out/folder/file).exists() else '<td>方法不可用</td>' for folder in folders)+'</tr>')
    parts.append('<tr>'+''.join('<td><pre>'+html.escape(json.dumps({k:v for k,v in methods[m].items() if k not in {'inference'}},ensure_ascii=False,indent=2))+'</pre></td>' for m in ['slic','sam2','combined'])+'</tr></table>')
    parts.append('<h2>SLIC 粒度小范围对照</h2><table><tr>'+''.join(f'<th>{n} 请求区域</th>' for n in [100,200,400])+'</tr><tr>'+''.join(f'<td><a href="slic_{n}/mask_overlay.png"><img loading="lazy" src="slic_{n}/mask_overlay.png" alt="SLIC {n}"></a><pre>{html.escape(json.dumps(slic_settings[str(n)],ensure_ascii=False,indent=2))}</pre></td>' for n in [100,200,400])+'</tr></table>')
    parts.append('<p>人工审核重点：椅子空隙与细腿、桌子立柱和底座、小盆栽叶缘、踢脚线、墙地交界。SAM2 的提示类别和模型头分数不是语义 GT。组合只保证不跨候选边界，不证明边界更正确；细碎区域不自动合并成语义区域。</p></html>')
    (out/'comparison.html').write_text('\n'.join(parts))
    # Load a method-neutral draft with the existing API. No build_reference/evaluate.
    loaded=load_document(out/'candidate_anchors.json')
    assert all(a['reviewed'] is False and a['mask_reviewed'] is False for a in loaded['anchors'])
    del loaded
    print(json.dumps(dict(output=str(out),methods={m:{k:v for k,v in item.items() if k in {'status','coverage','anchor_masks','anchor_boundary_straddling_cells'}} for m,item in methods.items()},regions=len(all_regions)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
