"""Frozen reference ROI diagnostics on one saved Agent render; never official scores."""
import argparse
import csv
import html
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_config import POLICY,FIXED_T0
from e_harness.benchmark_metrics import numerical_errors,perceptual_error
from e_harness.benchmark_evidence import local_dino_extractor
from scripts.region_grounding_experiment import read,save,edges
from scripts.region_first_generalization import write_csv,panel_grid

SOURCE=ROOT/'results/vlm_direct_grounding_bw0073'
DINO=Path('/home/xymo/models/dinov2')


def fit_render(image,size):
    """One geometry-only full-frame fit, independent of image content or ROI."""
    scale=min(size[0]/image.width,size[1]/image.height)
    resized=[max(1,round(image.width*scale)),max(1,round(image.height*scale))]
    offset=[(size[i]-resized[i])//2 for i in (0,1)]
    rgba=image.convert('RGBA').resize(tuple(resized),Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',size,(145,145,145));canvas.paste(rgba.convert('RGB'),tuple(offset))
    valid=np.zeros(size[::-1],bool);x,y=offset
    valid[y:y+resized[1],x:x+resized[0]]=np.asarray(rgba.getchannel('A'))==255
    return np.asarray(canvas),valid,dict(original_size=list(image.size),common_size=list(size),nominal_scale=scale,
        resized_size=resized,offset_xy=offset,padding_is_not_observation=True,content_alignment=False,
        transform='uniform full-frame fit with integer rounding, centered letterbox; no crop/search/warp')


def fixed_grid(shape,n):
    h,w=shape
    for iy in range(n):
        for ix in range(n):
            mask=np.zeros(shape,bool);mask[iy*h//n:(iy+1)*h//n,ix*w//n:(ix+1)*w//n]=True
            yield iy,ix,mask


def area_rectangle(mask):
    """Same bbox centre/aspect, approximately equal area; no semantic input."""
    ys,xs=np.nonzero(mask)
    if not len(xs):raise ValueError('Empty source ROI')
    x0,x1=int(xs.min()),int(xs.max()+1);y0,y1=int(ys.min()),int(ys.max()+1)
    width,height=x1-x0,y1-y0;scale=np.sqrt(mask.sum()/(width*height))
    rw,rh=max(1,round(width*scale)),max(1,round(height*scale))
    left=x0+(width-rw)//2;top=y0+(height-rh)//2
    result=np.zeros_like(mask);result[top:top+rh,left:left+rw]=True
    return result,dict(source_bbox=[x0,y0,x1,y1],control_bbox=[left,top,left+rw,top+rh],
        source_pixels=int(mask.sum()),control_pixels=int(result.sum()),
        area_ratio=float(result.sum()/mask.sum()),semantics_used=False)


def measures(a,b,mask,extract=None):
    if mask.dtype!=bool or mask.shape!=a.shape[:2] or a.shape!=b.shape:raise ValueError('Shared RGB/mask grid required')
    if mask.sum()<POLICY['min_pixels']:return None,None,'Insufficient observed pixels'
    appearance=numerical_errors(a,b,mask.astype(float))[0]['appearance']
    perceptual,reason=perceptual_error(a,b,mask.astype(float),extract)
    return appearance,perceptual,reason


def observed_area_controls(out,units,masks,valid):
    """Fix the area-control support after letterboxing, without changing any ROI."""
    extra=[];notes=[]
    for unit in units:
        if unit['group']!='polygon':continue
        roi=masks[unit['id']]&valid;control,note=area_rectangle(roi)
        identifier='valid_area_'+unit['region_id']
        path='measurement_rois/'+identifier+'.png';Image.fromarray(control).save(out/path)
        extra.append(dict(id=identifier,group='ordinary_observed_area',description='Rectangle matched to observed Polygon area/bbox; geometry only',
            mask=path,matched_to=unit['id'],reviewed=False,reliability=0.,formal_eligible=False))
        notes.append(dict(id=identifier,matched_to=unit['id'],**note,
            actual_observed_area_ratio=float((control&valid).sum()/roi.sum()),reviewed=False))
    save(out/'observed_area_controls.json',dict(units=extra,controls=notes,
        based_on_reference_and_validity_geometry_only=True,based_on_rgb_errors=False,original_rois_changed=False,reviewed=False))
    return extra


def heatmap(error,visible):
    stops=[0,.1,.25,.5,1];colors=np.array([[20,35,65],[30,130,215],[245,225,65],[250,100,35],[175,0,30]])
    out=np.stack([np.interp(error,stops,colors[:,i]) for i in range(3)],axis=-1).astype(np.uint8)
    out[~visible]=145
    return out


def masked_view(rgb,mask):
    result=np.uint8(.25*rgb+.75*np.full_like(rgb,170));result[mask]=rgb[mask]
    result[edges(mask)]=[245,180,30]
    return result


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    info=read(SOURCE/'input.json');run_id=info['provenance']['run_ids'][0]
    inventory=ROOT/'results/blenderworld_runs_inventory/selected.csv'
    rows=list(csv.DictReader(inventory.open(encoding='utf-8-sig')))
    pair=next((r for r in rows if r['task_id']=='bw_0073' and r['run_id']==run_id),None)
    if pair is None:raise ValueError('No exact inventory pair for saved Reference ROI source')
    reference=Path(info['reference_rgb']);staged=Path(pair['reference_image']);render=Path(pair['render_file'])
    if not render.is_file():raise ValueError('Paired real Agent Render unavailable; no substitute')
    if reference.read_bytes()!=staged.read_bytes():raise ValueError('ROI reference and Agent input differ')
    if reference.read_bytes()!=Path(pair['original_reference_image']).read_bytes():raise ValueError('Dataset original and ROI reference differ')
    run=ROOT.parent/'BlenderWorld/runs'/run_id;config=read(run/'config.json');result=read(run/'result.json')
    inputs=Path(info['provenance']['input_json']);task=read(info['provenance']['task_json'])
    if staged.resolve()!=(inputs.parent/'references/image_01.jpg').resolve():raise ValueError('Input reference path association differs')
    if Path(config['task']['path']).resolve()!=inputs.parents[2].resolve():raise ValueError('Run task association differs')
    if read(inputs)['task_id']!=task['task_id'] or task['task_id']!='bw_0073':raise ValueError('Task ID mismatch')
    if 'references/image_01.jpg' not in read(inputs)['files']:raise ValueError('Reference not declared in Agent inputs')
    manifest=read(run/'artifacts/manifest.json')
    if not any(r['destination']=='artifacts/workspace/exports' and r['status']=='ok' for r in manifest):raise ValueError('Missing exported artifact association')
    if render.resolve()!=(run/'artifacts/workspace/exports/final.png').resolve():raise ValueError('Unexpected render association')
    camera_path=run/'artifacts/workspace/exports/camera_parameters.json'
    camera=read(camera_path) if camera_path.exists() else None
    original=Image.open(reference).convert('RGB')
    if list(original.size)!=info['native_image_size']:raise ValueError('Reference dimensions changed')
    original.thumbnail((1536,1536),Image.Resampling.LANCZOS)
    if not np.array_equal(np.asarray(original),np.asarray(Image.open(SOURCE/'reference.png'))):raise ValueError('Working reference differs')
    shutil.copyfile(SOURCE/'reference.png',out/'reference.png')
    for name in ('region_plan.json','direct_regions.json'):shutil.copyfile(SOURCE/name,out/name)
    regions=read(out/'region_plan.json')['regions'];shape=original.size[::-1]
    (out/'measurement_rois').mkdir();(out/'frozen_reference').mkdir();units=[]
    def add(identifier,group,mask,description,**extra):
        Image.fromarray(mask).save(out/'measurement_rois'/(identifier+'.png'))
        units.append(dict(id=identifier,group=group,description=description,mask='measurement_rois/'+identifier+'.png',
            reviewed=False,reliability=0.,formal_eligible=False,**extra))
    add('global','global',np.ones(shape,bool),'Entire reference canvas')
    for n,group in [(POLICY['grid'],'dense_patch'),(4,'ordinary_grid4')]:
        for iy,ix,mask in fixed_grid(shape,n):add(f'{group}_{iy}_{ix}',group,mask,f'Fixed {n}x{n} grid [{iy},{ix}]',grid_n=n,grid_y=iy,grid_x=ix)
    controls=[]
    for group,source in [('box','B_direct_box_native'),('polygon','C_direct_polygon_native')]:
        shutil.copytree(SOURCE/source,out/'frozen_reference'/group)
        for region in regions:
            mask=np.asarray(Image.open(SOURCE/source/(region['id']+'.png')).convert('1').resize(original.size,Image.Resampling.NEAREST),bool)
            add(group+'_'+region['id'],group,mask,region['name']+'；'+region['content'],region_id=region['id'])
            control,note=area_rectangle(mask)
            if group=='polygon':
                add('area_'+region['id'],'ordinary_area',control,'Geometric area/bbox-matched rectangle; no semantic name',matched_to='polygon_'+region['id'])
                controls.append(dict(id='area_'+region['id'],matched_to='polygon_'+region['id'],**note,reviewed=False))
            else:
                if not np.array_equal(control,mask):raise ValueError('Box ordinary-rectangle identity failed')
                controls.append(dict(id=group+'_'+region['id'],ordinary_rectangle_identical=True,duplicate_inference=False,**note,reviewed=False))
    # ROI selection is complete before the Render is fitted or scored.
    save(out/'frozen_rois.json',dict(image_size=list(original.size),native_reference_size=info['native_image_size'],
        units=units,source=str(SOURCE),selection_depends_on_render=False,reviewed=False))
    save(out/'control_design.json',dict(controls=controls,grid_controls=[POLICY['grid'],4],
        rectangles_inherit_only_polygon_bbox_position=True,independent_semantic_control=False,reviewed=False))
    actual=Image.open(render);render_rgb,valid,transform=fit_render(actual,original.size)
    Image.fromarray(render_rgb).save(out/'render.png');Image.fromarray(valid).save(out/'render_valid.png')
    save(out/'pair_audit.json',dict(task_id='bw_0073',run_id=run_id,agent=pair['agent'],
        reference_rgb=str(reference.resolve()),agent_input_rgb=str(staged.resolve()),render_rgb=str(render.resolve()),
        inventory_source=str(inventory),run_config=str(run/'config.json'),task_metadata=info['provenance']['task_json'],
        input_metadata=str(inputs),artifact_manifest=str(run/'artifacts/manifest.json'),
        exact_reference_bytes_equal=True,run_task_mapping_verified=True,export_mapping_verified=True,
        run_exception=result.get('exception_info'),reference_native_size=info['native_image_size'],render_native_size=list(actual.size),
        render_alpha_range=list(actual.convert('RGBA').getchannel('A').getextrema()),
        png_metadata={k:actual.info.get(k) for k in ('Camera','Scene','File','RenderTime')},
        camera_export_source=str(camera_path),camera_export=camera,project_e_fixed_T0=FIXED_T0,
        exported_pose_matches_T0=bool(camera is not None and np.array_equal(camera.get('T_c2w'),FIXED_T0)),
        actual_blend_camera_reverified=False,reference_camera='unknown',camera_alignment_confirmed=False,
        camera_protocol='historical_camera',render_blend_sync='unknown; saved PNG metadata is not a rerender verification',
        comparison_transform=transform,observed_canvas_fraction=float(valid.mean()),
        official_benchmark_eligible=False,usage='offline provisional/debug only',reviewed=False))
    print('Paired real PNG verified; Reference ROIs frozen; historical camera only',flush=True)


def evaluate(out,use_dino=True):
    if (out/'metrics.json').exists():raise FileExistsError('Saved measurements already exist; use a new directory')
    if read(out/'offline_checks.json').get('passed') is not True:raise ValueError('Offline tests must pass first')
    start=time.monotonic();a=np.asarray(Image.open(out/'reference.png').convert('RGB'));b=np.asarray(Image.open(out/'render.png').convert('RGB'))
    valid=np.asarray(Image.open(out/'render_valid.png'),bool);units=read(out/'frozen_rois.json')['units']
    masks={u['id']:np.asarray(Image.open(out/u['mask']),bool) for u in units}
    units=units+observed_area_controls(out,units,masks,valid)
    (out/'details').mkdir();extract=None;dino_reason='DINO explicitly disabled';load_seconds=0.
    if use_dino:
        try:
            import torch
            torch.set_num_threads(2);torch.set_num_interop_threads(1);tick=time.monotonic()
            extract=local_dino_extractor(DINO,'cpu',preserve_frame=True);load_seconds=time.monotonic()-tick;dino_reason=None
        except Exception as exc:dino_reason=type(exc).__name__+': '+str(exc)
    error=np.abs(a.astype(float)-b.astype(float)).mean(2)/255
    heat=heatmap(error,valid);Image.fromarray(heat).save(out/'rgb_difference.png')
    masks={u['id']:np.asarray(Image.open(out/u['mask']),bool) for u in units}
    rows=[]
    for index,unit in enumerate(units):
        roi=masks[unit['id']];observed=roi&valid;tick=time.monotonic()
        appearance,perceptual,reason=measures(a,b,observed,extract)
        ys,xs=np.nonzero(observed)
        fill=float(observed.sum()/((ys.max()-ys.min()+1)*(xs.max()-xs.min()+1))) if len(xs) else None
        rows.append(dict(id=unit['id'],group=unit['group'],description=unit['description'],
            roi_pixels=int(roi.sum()),observed_pixels=int(observed.sum()),valid_pixel_fraction=float(observed.sum()/roi.sum()),
            appearance=appearance,perceptual=perceptual,perceptual_unavailable_reason=reason or dino_reason,
            semantic=None,spatial=None,statistical=None,
            unavailable_semantic='No reviewed semantic evidence/verifier; no new VLM requests',
            unavailable_spatial='Unconfirmed reference camera alignment; no reliable rendered correspondence',
            unavailable_statistical='No reviewed element occupancy or applicable spatial-statistical evidence; proxies not reported',
            masked_crop_fill_fraction=fill,rgb_error_mass=float(error[observed].sum()),
            seconds=time.monotonic()-tick,status='provisional_debug',reviewed=False,q=0.,formal_eligible=False))
        if unit['group'] in ('box','polygon','ordinary_area','ordinary_observed_area'):
            ys,xs=np.nonzero(roi);sl=(slice(ys.min(),ys.max()+1),slice(xs.min(),xs.max()+1))
            local_heat=heat.copy();local_heat[~observed]=145
            mask_image=np.uint8(np.repeat(roi[...,None],3,2)*255)
            panel_grid([('Reference / frozen ROI',Image.fromarray(masked_view(a,roi)[sl])),
                ('Saved Agent Render / same ROI',Image.fromarray(masked_view(b,roi)[sl])),
                ('RGB abs difference: fixed [0,1]',Image.fromarray(local_heat[sl])),
                (f'Appearance {appearance:.4f}; Perceptual '+('N/A' if perceptual is None else f'{perceptual:.4f}'),Image.fromarray(mask_image[sl]))],
                out/'details'/(unit['id']+'.png'),width=650)
        if (index+1)%4==0:print('Measured',index+1,'/',len(units),'fixed scopes',flush=True)
    save(out/'metrics.json',dict(rows=rows,formal_observation_energy=None,formal_benchmark_score=None,
        semantic_evidence_reviewed=False,region_losses_summed=False,reviewed=False))
    write_csv(out/'metrics.csv',rows)
    overlaps={}
    for group in ('box','polygon'):
        chosen=[u for u in units if u['group']==group];stack=np.stack([masks[u['id']] for u in chosen]);count=stack.sum(0)
        view=a.copy();view[count>1]=np.uint8(.76*a[count>1]+.24*np.array([255,0,220]))
        Image.fromarray(view).save(out/(group+'_overlap.png'))
        splits=[]
        for unit,roi in zip(chosen,stack):
            parts={}
            for part,mask in [('unique',roi&(count==1)&valid),('shared',roi&(count>1)&valid)]:
                parts[part]=dict(observed_pixels=int(mask.sum()),appearance=float(error[mask].mean()) if mask.any() else None)
            splits.append(dict(id=unit['id'],**parts,reviewed=False))
        pairs=[dict(first=chosen[i]['id'],second=chosen[j]['id'],pixels=int((stack[i]&stack[j]).sum()),
            observed_pixels=int((stack[i]&stack[j]&valid).sum())) for i in range(len(chosen)) for j in range(i+1,len(chosen))]
        overlaps[group]=dict(union_fraction=float((count>0).mean()),overlap_fraction=float((count>1).mean()),
            unassigned_fraction=float((count==0).mean()),pairwise=pairs,unique_shared_appearance=splits,reviewed=False)
    save(out/'overlaps.json',dict(groups=overlaps,losses_added=False,perceptual_is_not_additive=True,reviewed=False))
    self_rows=[]
    for identifier in ('global','box_R2','polygon_R2'):
        appearance,perceptual,reason=measures(a,a,masks[identifier]&valid,extract)
        self_rows.append(dict(id=identifier,appearance=appearance,perceptual=perceptual,reason=reason,reviewed=False))
    save(out/'self_checks.json',dict(reference_vs_itself=self_rows,reviewed=False))
    save(out/'execution.json',dict(cpu_wall_seconds=time.monotonic()-start,dino_loaded=extract is not None,
        dino_unavailable_reason=dino_reason,dino_load_seconds=load_seconds,model_directory=str(DINO),device='cpu',
        policy_multiscale=list(POLICY['multiscale']),dino_size=POLICY['dino_size'],preserve_frame=True,
        metric_scopes=len(rows),paid_vlm_calls=0,sam_calls=0,slic_runs=0,blender_runs=0,agent_runs=0,
        formal_scoring=False,reviewed=False))
    render_page(out,units,rows)


def render_page(out,units,rows):
    a=np.asarray(Image.open(out/'reference.png').convert('RGB'));b=np.asarray(Image.open(out/'render.png').convert('RGB'))
    heat=Image.open(out/'rgb_difference.png');valid=np.asarray(Image.open(out/'render_valid.png'),bool)
    invalid=a.copy();invalid[~valid]=[220,40,125]
    panel_grid([('Reference RGB',Image.fromarray(a)),('Saved real Agent Render',Image.fromarray(b)),
        ('RGB L1: fixed [0,1]; gray=unobserved',heat),('Unsupported pixels in pink',Image.fromarray(invalid))],out/'comparison.png',width=850)
    panels=[]
    for group in ('box','polygon'):
        selected=[u for u in units if u['group']==group]
        masks=np.stack([np.asarray(Image.open(out/u['mask']),bool) for u in selected]);count=masks.sum(0)
        for name,rgb in [('Reference',a),('Saved Render',b)]:
            view=rgb.copy()
            for i,mask in enumerate(masks):
                color=np.asarray([[240,75,65],[255,185,35],[55,140,250],[35,205,140]][i]);single=mask&(count==1)
                view[single]=np.uint8(.84*rgb[single]+.16*color);view[edges(mask)]=color
            view[count>1]=np.uint8(.76*rgb[count>1]+.24*np.array([255,0,220]))
            panels.append((name+' / frozen '+group,Image.fromarray(view)))
    panel_grid(panels,out/'roi_comparison.png',width=850)
    ramp=np.tile(np.linspace(0,1,600),(12,1));bar=Image.new('RGB',(600,43),'white')
    bar.paste(Image.fromarray(heatmap(ramp,np.ones_like(ramp,bool))),(0,0));draw=ImageDraw.Draw(bar)
    for x,label in [(0,'0'),(60,'0.1'),(150,'0.25'),(300,'0.5'),(580,'1.0')]:draw.text((x,18),label,fill='black')
    bar.save(out/'difference_scale.png')
    body=['<!doctype html><meta charset="utf-8"><title>bw_0073 real Render / frozen ROI diagnostics</title>',
        '<style>body{font:16px sans-serif;line-height:1.6;margin:24px;background:#f5f6f8}img{max-width:100%}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd2da;padding:7px;text-align:left}</style>',
        '<h1>bw_0073：真实 Agent Render 与冻结 Reference ROI</h1>',
        '<p>historical_camera，仅 provisional/debug。未确认相机配准，禁止解释为正式 Benchmark 成绩。ROI 不随 Render 检测、移动或优化。灰色留边不计入数值，另记有效像素比例。</p>',
        '<p><a href="report.md">报告与复现</a> · <a href="pair_audit.json">配对/相机审计</a> · <a href="metrics.csv">实际条件误差</a> · <a href="control_design.json">普通 ROI 对照规则</a> · <a href="observed_area_controls.json">有效面积对照</a> · <a href="overlaps.json">重叠与分解</a></p>',
        '<img src="comparison.png"><p>差异色标（固定 RGB L1 0–1；各 ROI 不单独归一化）</p><img src="difference_scale.png"><img src="roi_comparison.png">']
    if (out/'initial_review.json').exists():
        review=read(out/'initial_review.json')
        body+=['<h2>自动静态初审；全部 reviewed=false</h2><p><a href="failure_cases.html">失败案例与待审核问题</a> · <a href="initial_review.json">完整初审记录</a></p>',
            '<table><tr><th>Region</th><th>可见差异</th><th>限制 / Uncertain</th></tr>']
        for item in review['regions']:
            body+=['<tr><td>'+html.escape(item['id']+' '+item['name'])+'</td><td>'+html.escape('；'.join(item['observations']))+'</td><td>'+html.escape('；'.join(item['limits']))+'</td></tr>']
        body+=['</table>']
    def value(v):return 'N/A' if v is None else f'{v:.5f}'
    for group in ('global','dense_patch','ordinary_grid4','box','polygon','ordinary_area','ordinary_observed_area'):
        selected=[r for r in rows if r['group']==group]
        body+=['<h2>'+group+'</h2><table><tr><th>ID / 内容</th><th>有效像素</th><th>有效比例</th><th>Appearance</th><th>Perceptual</th><th>Semantic / Spatial / Statistical</th></tr>']
        for row in selected:body+=['<tr><td>'+html.escape(row['id']+' / '+row['description'])+'</td><td>'+str(row['observed_pixels'])+'</td><td>'+f'{row["valid_pixel_fraction"]:.2%}'+'</td><td>'+value(row['appearance'])+'</td><td>'+value(row['perceptual'])+'</td><td>N/A / N/A / N/A</td></tr>']
        body+=['</table>']
        if group in ('dense_patch','ordinary_grid4'):
            for metric in ('appearance','perceptual'):
                overlay=a.copy();draw_image=Image.fromarray(overlay);draw=ImageDraw.Draw(draw_image)
                for unit in units:
                    if unit['group']!=group:continue
                    mask=np.asarray(Image.open(out/unit['mask']),bool);ys,xs=np.nonzero(mask)
                    record=next(r for r in selected if r['id']==unit['id'])
                    draw.rectangle((int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())),outline='yellow',width=2)
                    label=f'({unit["grid_y"]},{unit["grid_x"]}) '+value(record[metric])
                    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
                    draw.text((int(xs.min()+8),int(ys.min()+8)),label,font=font,fill='white',stroke_width=2,stroke_fill='black')
                filename=group+'_'+metric+'.png';draw_image.save(out/filename);body+=['<p>'+metric+'</p><img src="'+filename+'">']
        for row in selected:
            if (out/'details'/(row['id']+'.png')).exists():body+=['<h3>'+html.escape(row['id'])+'</h3><img src="details/'+row['id']+'.png">']
    body+=['<h2>Region 重叠；没有相加形成总分</h2><img src="box_overlap.png"><img src="polygon_overlap.png">',
        '<p>Perceptual 使用原有带黑色 Mask 背景的裁剪及多尺度 DINO；填充率和面积/外接框对照见 metrics.json。低误差不自动证明语义区域更优。</p>']
    (out/'comparison.html').write_text('\n'.join(body))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['prepare','evaluate'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--no-dino',action='store_true')
    args=parser.parse_args()
    if args.stage=='prepare':prepare(args.output.resolve())
    else:evaluate(args.output.resolve(),not args.no_dino)
