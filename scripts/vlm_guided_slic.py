"""Frozen, CPU-only ROI/SLIC comparison; no model, API or scoring calls."""
import argparse
import html
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.region_grounding_experiment import read,save,method,edges,COLORS
from scripts.region_first_generalization import write_csv
from e_harness.benchmark_evidence import load_document

PARAMETERS=dict(c1_overlap=.5,inside_seed=.8,outside_seed=.2,position_weight=.75,
    decision_margin=.15,core_margin_pixels=2,granularities=[200,400],primary_granularity=400)
SOURCE=ROOT/'results/vlm_direct_grounding_bw0073'
CACHE=ROOT/'results/multiscene_region_extraction'


def context(rgb,labels):
    """Shared-border RGB gradient affinity, with no mean-colour merging."""
    rgb=np.asarray(rgb);labels=np.asarray(labels)
    if labels.ndim!=2 or rgb.shape!=(*labels.shape,3) or not np.issubdtype(labels.dtype,np.integer) or labels.min()<0:
        raise ValueError('Expected RGB and nonnegative integer labels on the same grid')
    if not np.isfinite(rgb).all() or rgb.min()<0 or rgb.max()>255:raise ValueError('Invalid RGB range')
    ids,inverse=np.unique(labels.ravel(),return_inverse=True);grid=inverse.reshape(labels.shape);n=len(ids)
    area=np.bincount(inverse,minlength=n)
    gray=rgb.astype(float).mean(2)/255
    gradient=np.hypot(ndimage.sobel(gray,axis=0)/4,ndimage.sobel(gray,axis=1)/4)
    lengths=np.zeros(n*n);strengths=np.zeros(n*n)
    for first,second,g in [(grid[:,:-1],grid[:,1:],np.maximum(gradient[:,:-1],gradient[:,1:])),
                           (grid[:-1,:],grid[1:,:],np.maximum(gradient[:-1,:],gradient[1:,:]))]:
        keep=first!=second;lo=np.minimum(first[keep],second[keep]);hi=np.maximum(first[keep],second[keep])
        pair=lo*n+hi
        lengths+=np.bincount(pair,minlength=n*n)
        strengths+=np.bincount(pair,weights=g[keep],minlength=n*n)
    encoded=np.flatnonzero(lengths);left,right=encoded//n,encoded%n
    mean=strengths[encoded]/lengths[encoded]
    scale=max(1e-6,float(np.quantile(mean,.75))) if len(mean) else 1e-6
    weights=lengths[encoded]/(1+mean/scale)
    return dict(ids=ids,grid=grid,area=area,left=left,right=right,weights=weights,
        shared_length=lengths[encoded],mean_gradient=mean,gradient_scale=scale)


def protected_core(roi,margin):
    core=ndimage.binary_erosion(roi,iterations=margin,border_value=0)
    parts,n=ndimage.label(roi)
    # Do not erase an entire small disconnected part (e.g. a thin component).
    for identifier in range(1,n+1):
        support=parts==identifier
        if not (core&support).any():core|=support
    return core


def select(roi,graph,parameters=None):
    pset=PARAMETERS if parameters is None else parameters;roi=np.asarray(roi)
    if roi.dtype!=bool or roi.shape!=graph['grid'].shape or not roi.any():raise ValueError('Expected nonempty boolean ROI on SLIC grid')
    grid=graph['grid'];n=len(graph['ids'])
    hit=np.bincount(grid.ravel(),weights=roi.ravel(),minlength=n);p=hit/graph['area']
    inside=p>=pset['inside_seed'];outside=p<=pset['outside_seed']
    left,right,w=graph['left'],graph['right'],graph['weights']
    def support(seed):
        return (np.bincount(left,weights=w*seed[right],minlength=n)+
                np.bincount(right,weights=w*seed[left],minlength=n))
    positive,negative=support(inside),support(outside);total=positive+negative
    vote=np.divide(positive,total,out=np.full(n,.5),where=total>0)
    score=pset['position_weight']*(2*p-1)+(1-pset['position_weight'])*(2*vote-1)
    middle=~(inside|outside)
    resolved=(total>0)&(np.abs(score)>=pset['decision_margin'])&((p-.5)*(vote-.5)>0)
    uncertain=middle&~resolved
    c1_labels=p>=pset['c1_overlap']
    raw_labels=inside|(middle&(score>=0))
    raw=raw_labels[grid]
    before_guard=np.where(uncertain[grid],roi,raw)
    core=protected_core(roi,pset['core_margin_pixels'])
    c2=before_guard|core
    rows=[dict(label_id=int(identifier),pixels=int(graph['area'][i]),roi_pixels=int(hit[i]),
        overlap_fraction=float(p[i]),adjacent_inside_vote=float(vote[i]) if total[i]>0 else None,
        decision_score=float(score[i]),c1_selected=bool(c1_labels[i]),c2_raw_selected=bool(raw_labels[i]),
        original_roi_fragment_retained=bool(uncertain[i]),reviewed=False) for i,identifier in enumerate(graph['ids'])]
    return dict(c1=c1_labels[grid],c2=c2,c2_raw=raw,c2_whole_selected=raw_labels[grid]&~uncertain[grid],
        core=core,uncertain_pixels=uncertain[grid]&roi,labels=rows,
        c2_core_restored_pixels=int((core&~before_guard).sum()),
        c2_changed_pixels_outside_roi=int((c2&~roi).sum()))


def paint(rgb,mask,color,alpha=.16):
    image=rgb.copy();color=np.asarray(color)
    image[mask]=np.uint8((1-alpha)*rgb[mask]+alpha*color);image[edges(mask)]=color
    return Image.fromarray(image)


def delta_view(rgb,base,result):
    im=rgb.copy()
    for support,color in [(result&~base,[20,210,100]),(base&~result,[245,45,95])]:
        im[support]=np.uint8(.72*rgb[support]+.28*np.asarray(color));im[edges(support)]=color
    return Image.fromarray(im)


def grid_figure(rows,path,width=500):
    height=round(rows[0][0][1].height*width/rows[0][0][1].width)
    canvas=Image.new('RGB',(width*len(rows[0]),(height+38)*len(rows)),'#18212e');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
    for y,row in enumerate(rows):
        for x,(title,im) in enumerate(row):
            draw.text((x*width+8,y*(height+38)+8),title,font=font,fill='white')
            canvas.paste(im.resize((width,height)),(x*width,y*(height+38)+38))
    canvas.save(path)


def export(out,key,rgb,regions,masks,native_size,source,native_source=None):
    stats=method(out,key,rgb,regions,masks,source=str(source))
    folder=out/key;native=out/(key+'_native');native.mkdir();rows=[]
    total=masks.sum(0);canvas=rgb.copy()
    for i,(row,mask) in enumerate(zip(regions,masks)):
        color=COLORS[i];single=mask&(total==1)
        canvas[single]=np.uint8(.84*rgb[single]+.16*color);canvas[edges(mask)]=color
        paint(rgb,mask,color).save(folder/(row['id']+'_overlay.png'))
        if native_source is None:
            Image.fromarray(mask).resize(tuple(native_size),Image.Resampling.NEAREST).save(native/(row['id']+'.png'))
        else:shutil.copyfile(native_source/(row['id']+'.png'),native/(row['id']+'.png'))
        rows.append(dict(row,mask=row['id']+'.png',reviewed=False,mask_reviewed=False,reliability=0.,
            status='uncertain',representation='coarse_evaluation_roi',semantic_GT=False))
    canvas[total>1]=np.uint8(.76*rgb[total>1]+.24*np.array([255,0,220]));Image.fromarray(canvas).save(folder/'overlay.png')
    save(native/'evidence.json',dict(image_size=native_size,regions=rows,anchors=[],relations=[],reviewed=False,
        source=str(source),decision_grid=list(rgb.shape[1::-1]),
        resampling='nearest from cached SLIC working grid' if native_source is None else 'exact historical native mask, unchanged',formal_score=False))
    return stats


def run(out):
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    for name in ('input.json','region_plan.json','direct_regions.json','reference.png'):shutil.copyfile(SOURCE/name,out/name)
    info=read(out/'input.json');regions=read(out/'region_plan.json')['regions'];native_size=info['native_image_size']
    image=Image.open(out/'reference.png').convert('RGB');rgb=np.asarray(image)
    cached_rgb=np.asarray(Image.open(CACHE/'references/bw_0073/working.png').convert('RGB'))
    if not np.array_equal(rgb,cached_rgb):raise ValueError('Cached SLIC reference differs')
    save(out/'protocol.json',dict(parameters=PARAMETERS,method_iterations=1,roi_sources=['Box','Polygon'],
        decision_grid=list(image.size),native_image_size=native_size,reference_only=True,
        recomputed_slic=False,new_paid_calls=0,gpu_runs=0,reviewed=False))
    seeds={};statistics=[];grid_audit=[]
    for key,previous in [('A_box','B_direct_box_native'),('B_polygon','C_direct_polygon_native')]:
        masks=[]
        for row in regions:
            old=Image.open(SOURCE/previous/(row['id']+'.png')).convert('1')
            small=old.resize(image.size,Image.Resampling.NEAREST);masks.append(np.asarray(small,bool))
            roundtrip=np.asarray(small.resize(tuple(native_size),Image.Resampling.NEAREST),bool);original=np.asarray(old,bool)
            grid_audit.append(dict(input=key,id=row['id'],roundtrip_added_native_pixels=int((roundtrip&~original).sum()),
                roundtrip_removed_native_pixels=int((original&~roundtrip).sum()),reviewed=False))
        seeds[key]=np.stack(masks)
        statistics.append(export(out,key,rgb,regions,seeds[key],native_size,SOURCE/previous/'evidence.json',SOURCE/previous))
    save(out/'grid_audit.json',dict(rows=grid_audit,selection_change_statistics_grid=list(image.size),reviewed=False))
    changes=[];pages=[]
    for count in PARAMETERS['granularities']:
        folder=out/('slic_'+str(count));folder.mkdir();(folder/'per_region').mkdir()
        source=CACHE/f'methods/bw_0073/slic_{count}/dense_labels.npz'
        shutil.copyfile(source,folder/'dense_labels.npz')
        with np.load(source,allow_pickle=False) as archive:labels=archive['labels']
        tick=time.monotonic();graph=context(rgb,labels);graph_seconds=time.monotonic()-tick
        save(folder/'adjacency.json',dict(gradient_scale=graph['gradient_scale'],
            shared_borders=[dict(left=int(graph['ids'][a]),right=int(graph['ids'][b]),mean_gradient=float(g),
                shared_pixels=int(length),affinity=float(w)) for a,b,g,length,w in zip(graph['left'],graph['right'],graph['mean_gradient'],graph['shared_length'],graph['weights'])],reviewed=False))
        cases={};results={}
        for seed_name,seed_key in [('Box','A_box'),('Polygon','B_polygon')]:
            tick=time.monotonic();selected=[select(mask,graph) for mask in seeds[seed_key]];seconds=time.monotonic()-tick
            results[seed_name]=selected
            proposal=folder/(seed_name+'_proposals');proposal.mkdir()
            save(proposal/'selection.json',dict(actual_superpixels=len(graph['ids']),requested_superpixels=count,
                source=str(source),graph_cpu_seconds=graph_seconds,selection_cpu_seconds=seconds,
                parameters=PARAMETERS,regions=[dict(id=row['id'],labels=res['labels'],
                c2_core_restored_pixels=res['c2_core_restored_pixels'],reviewed=False) for row,res in zip(regions,selected)],reviewed=False))
            for row,res in zip(regions,selected):
                Image.fromarray(res['c2_raw']).save(proposal/(row['id']+'_C2_raw.png'))
            for kind in ('c1','c2'):
                key=seed_name+'_'+kind.upper();masks=np.stack([res[kind] for res in selected])
                stat=export(folder,key,rgb,regions,masks,native_size,proposal/'selection.json')
                statistics.append(dict(stat,method='slic_'+str(count)+'/'+key));cases[(seed_name,kind)]=key
                for row,base,result in zip(regions,seeds[seed_key],masks):
                    added,removed=result&~base,base&~result
                    changes.append(dict(requested_superpixels=count,actual_superpixels=len(graph['ids']),input=seed_name,
                        method=kind.upper(),id=row['id'],baseline_pixels=int(base.sum()),candidate_pixels=int(result.sum()),
                        added_pixels=int(added.sum()),removed_pixels=int(removed.sum()),
                        retained_roi_fraction=float((result&base).sum()/base.sum()),
                        components=int(ndimage.label(result)[1]),reviewed=False))
                    for label,mask in [('added',added),('removed',removed)]:Image.fromarray(mask).save(folder/key/(row['id']+'_'+label+'.png'))
        overview=[]
        for seed_name in ('Box','Polygon'):
            overview.append([('Reference RGB',image),('A: Direct Box',Image.open(out/'A_box/overlay.png')),
                ('B: Direct Polygon',Image.open(out/'B_polygon/overlay.png')),
                ('C1 / '+seed_name,Image.open(folder/cases[(seed_name,'c1')]/'overlay.png')),
                ('C2 guarded / '+seed_name,Image.open(folder/cases[(seed_name,'c2')]/'overlay.png'))])
        grid_figure(overview,folder/'comparison.png',width=570)
        if count==PARAMETERS['primary_granularity']:shutil.copyfile(folder/'comparison.png',out/'comparison.png')
        for i,row in enumerate(regions):
            views=[]
            for seed_name,seed_key in [('Box','A_box'),('Polygon','B_polygon')]:
                base=seeds[seed_key][i];res=results[seed_name][i]
                for kind in ('c1','c2'):
                    candidate=res[kind];whole=res['c1'] if kind=='c1' else res['c2_whole_selected']
                    selected_image=np.asarray(paint(rgb,whole,COLORS[i])).copy()
                    selected_image[edges(labels)&whole]=[255,220,25]
                    views.append([(seed_name+' seed',paint(rgb,base,COLORS[i])),
                        (kind.upper()+': whole cells',Image.fromarray(selected_image)),
                        (kind.upper()+': final ROI',paint(rgb,candidate,COLORS[i])),
                        ('Added green / removed red',delta_view(rgb,base,candidate))])
            grid_figure(views,folder/'per_region'/(row['id']+'.png'),width=570)
        pages.append((count,len(graph['ids'])))
        print('Saved SLIC',count,'comparison for Box and Polygon; parameters unchanged',flush=True)
    write_csv(out/'summary.csv',statistics);write_csv(out/'pixel_changes.csv',changes)
    body=['<!doctype html><meta charset="utf-8"><title>bw_0073 VLM-guided SLIC</title>',
        '<style>body{font:16px sans-serif;line-height:1.6;margin:24px;background:#f5f6f8}img{max-width:100%}pre{white-space:pre-wrap}</style>',
        '<h1>bw_0073：VLM-guided SLIC</h1><p>全部 reviewed:false。C1/C2 的 Box 和 Polygon 输入分开。绿色新增、红色删除，变化不等于语义改善。C2 保留不确定 ROI 片段与内部核心，不是纯整块超像素并集。</p>',
        '<p><a href="report.md">报告及复现</a> · <a href="pixel_changes.csv">逐区像素变化</a> · <a href="summary.csv">辅助几何统计</a> · <a href="grid_audit.json">原图/工作网格转换误差</a></p>']
    for count,actual in pages:
        name='slic_'+str(count)
        body+=['<h2>请求 '+str(count)+' / 实际 '+str(actual)+' 个超像素</h2><p>上行使用 Box，下行使用 Polygon；两种输入不能互相当作 SLIC 改善。</p>',
            '<img src="'+name+'/comparison.png">']
        for row in regions:
            body+=['<h3>'+html.escape(row['id']+' '+row['name'])+'</h3><p>'+html.escape(row['content'])+'</p>',
                '<p>第1/2行：Box 的 C1/C2；第3/4行：Polygon 的 C1/C2。</p><img src="'+name+'/per_region/'+row['id']+'.png">',
                '<details><summary>保护前的 C2 原始提案（不自动推荐）</summary>']
            for seed_name,seed_key in [('Box','A_box'),('Polygon','B_polygon')]:
                file=out/name/(seed_name+'_proposals')/(row['id']+'_C2_raw.png')
                raw=np.asarray(Image.open(file),bool)
                overlay=file.with_name(row['id']+'_C2_raw_overlay.png');paint(rgb,raw,COLORS[regions.index(row)]).save(overlay)
                body+=['<p>'+seed_name+'</p><img src="'+str(overlay.relative_to(out))+'">']
            body+=['</details>']
    (out/'comparison.html').write_text('\n'.join(body))
    save(out/'run_status.json',dict(status='completed',cpu_wall_seconds=time.monotonic()-start,
        method_iterations=1,actual_labels=dict(pages),paid_calls=0,model_calls=0,gpu_runs=0,reviewed=False))
    print('Completed both ROI seeds and both cached granularities; no inference',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.output.resolve())
