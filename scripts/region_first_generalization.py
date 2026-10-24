"""Frozen B2 geometry controls and synthetic RGB sensitivity; CPU/cache only.

Absent VLM plans remain absent. Existing reference-side region boxes may test
geometry conditionally, but are never promoted to a VLM plan or reviewed GT.
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
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.coarse_roi_experiment import (rectangles, content_hints, coarse_polygons,
    polygon_loops, raster_polygons)
from scripts.region_grounding_experiment import read, save, method
from e_harness.benchmark_evidence import load_document, grounding_concepts, validate_region_first_plan
from e_harness.benchmark_metrics import numerical_errors
from e_harness.benchmark_config import POLICY


def scale_box(box, old_size, new_size):
    value = np.rint(np.asarray(box)*np.tile(np.asarray(new_size)/old_size, 2)).astype(int)
    return value.tolist()


def interior_patch(common, short_fraction=.06):
    """Same square in A and B, inside one ROI and outside every other ROI."""
    # Outside-image pixels are not valid support, including for edge-touching
    # ROIs. Without padding the EDT can choose a center on the image border.
    distance = ndimage.distance_transform_edt(np.pad(common,1))[1:-1,1:-1]
    y, x = np.unravel_index(distance.argmax(), common.shape)
    half = min(round(short_fraction*min(common.shape)), int(distance[y, x]/np.sqrt(2)))
    if half < 2:
        return None
    return [int(x-half), int(y-half), int(x+half), int(y+half)]


def perturb(rgb, box, kind, strength):
    """Local pixel simulation, not an Agent scene or a semantic error oracle."""
    x0,y0,x1,y1 = box
    if not (0 <= x0 < x1 <= rgb.shape[1] and 0 <= y0 < y1 <= rgb.shape[0] and 0 <= strength <= 1):
        raise ValueError('Invalid synthetic patch bounds or strength')
    source = rgb[y0:y1,x0:x1]
    if kind == 'color':
        target = np.clip(source.astype(float)+[60.,-60.,0.], 0, 255)
    elif kind == 'blur':
        target = np.asarray(Image.fromarray(source).filter(ImageFilter.GaussianBlur(3)))
    else:
        raise ValueError('Unknown synthetic perturbation')
    result = rgb.copy()
    result[y0:y1,x0:x1] = np.uint8(np.rint((1-strength)*source+strength*target))
    return result


def write_csv(path, rows):
    with path.open('x') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def panel_grid(panels, path, width=700):
    height = round(panels[0][1].height*width/panels[0][1].width)
    canvas = Image.new('RGB',(width*2,(height+42)*2),'#18212e'); draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',22)
    for index,(title,image) in enumerate(panels):
        x=index%2*width; y=index//2*(height+42)
        draw.text((x+12,y+8),title,font=font,fill='white')
        canvas.paste(image.resize((width,height)),(x,y+42))
    canvas.save(path)


def availability():
    paths = sorted((ROOT/'results').rglob('*plan*.json'))
    findings = []
    for task in ('bw_9064','bw_0073'):
        relevant = [str(p) for p in paths if task in str(p)]
        failures=[];valid=[]
        for path in relevant:
            if Path(path).name != 'vlm_plan.json':continue
            doc=read(path)
            try:
                validate_region_first_plan(dict(regions=[{k:r[k] for k in ('id','name','location','content')}
                                                        for r in doc.get('regions',[])]))
                valid.append(path)
            except (ValueError,KeyError,TypeError) as exc:
                failures.append(dict(path=path,status=doc.get('status'),saved_error=doc.get('error'),
                                     schema_error=str(exc)))
        findings.append(dict(task_id=task, usable_vlm_plan=bool(valid),valid_plan_paths=valid,
            reason='No valid saved coarse Region Plan' if relevant else 'No saved VLM Region Plan found',
            examined_plan_files=relevant,failures=failures,reviewed=False))
    return findings


def cached_candidates(task,old_size,new_size):
    candidates=[]
    for mode in ('sam3_text','sam3_visual'):
        for kind in ('region_candidates','anchor_candidates'):
            source=ROOT/'results/multiscene_region_extraction'/kind/task/mode/'candidates.json'
            doc=read(source)
            for row in doc.get('regions',[])+doc.get('anchors',[]):
                if not row.get('category'):continue
                candidates.append(dict(row,bbox=scale_box(row['bbox'],old_size,new_size),
                    source_document=str(source),prompt_source=('historical reference text concept'
                    if mode=='sam3_text' else 'historical assistant reference RGB bbox')))
    return candidates


def geometry_control(out, task):
    """Use only pre-existing manifest region boxes, not newly authored regions."""
    folder=out/task['task_id'];folder.mkdir();started=time.perf_counter()
    original=Path(task['original_reference_image']); staged=Path(task['reference_image'])
    for key in ('input_json','task_json'):
        if read(task['provenance'][key])['task_id'] != task['task_id']:
            raise ValueError('Reference task mismatch')
    if original.read_bytes() != staged.read_bytes():
        raise ValueError('Staged and original reference differ')
    with Image.open(original) as native:
        old_size=list(native.size); image=native.convert('RGB')
    if old_size != task['image_size']:raise ValueError('Native reference size mismatch')
    image.thumbnail((1536,1536),Image.Resampling.LANCZOS);rgb=np.asarray(image)
    image.save(folder/'reference.png'); regions=[];boxes=[]
    for row in task['visual_prompts']:
        if row['role'] != 'region': continue
        regions.append(dict(id=row['id'],name=row['category'],content=row['category'],
            location='Existing cached reference bbox; not a VLM location description',
            reviewed=False,reliability=0.,representation='coarse_evaluation_roi',
            semantic_mask_available=False,plan_origin='historical_assistant_reference_bbox'))
        boxes.append(scale_box(row['bbox'],old_size,list(image.size)))
    candidates=cached_candidates(task['task_id'],old_size,list(image.size))
    hints,hint_records=content_hints(regions,candidates,rgb.shape[:2],boxes)
    save(folder/'cached_roi_input.json',dict(regions=regions,boxes=boxes,reviewed=False,
        origin='existing manifest visual_prompts with role=region; NOT a VLM Region Plan'))
    save(folder/'content_hints.json',dict(regions=hint_records,
        unrecognized_vocabulary=[r['name'] for r in regions if not grounding_concepts(r['content'])],
        reviewed=False, note='Frozen noun vocabulary is not extended for new images'))
    save(folder/'source.json',dict(task_id=task['task_id'],reference_rgb=str(original),
        provenance=task['provenance'],original_staged_bytes_equal=True,render_used=False,
        native_image_size=old_size,image_size=list(image.size),geometry_max_side=1536,
        source_manifest=str(ROOT/'results/multiscene_region_extraction/manifest.json'),
        plan_status='unavailable',experiment='conditional_cached_bbox_geometry_control',reviewed=False))
    a=rectangles(rgb.shape[:2],boxes);t=time.perf_counter()
    b,diagnostics=coarse_polygons(rgb,boxes,hints,snap=True);seconds=time.perf_counter()-t
    # No parameter or mask adjustment after this frozen call.
    reverse,_=coarse_polygons(rgb,boxes[::-1],hints[::-1],snap=True)
    np.testing.assert_array_equal(b,reverse[::-1])
    old_params=read(ROOT/'results/coarse_evaluation_roi_bw0074/B2_edge_polygons/diagnostics.json')['parameters']
    assert diagnostics['parameters']==old_params
    stats=[]
    for key,masks in [('A_rectangles',a),('B2_frozen',b)]:
        row=method(folder,key,rgb,regions,masks,source=str(folder/'source.json'))
        row.update(task_id=task['task_id'],roi_count=len(regions),
            experiment='conditional_cached_bbox_geometry_control',usable_vlm_plan=False,
            geometry_seconds=seconds if key=='B2_frozen' else None)
        stats.append(row)
        if key=='B2_frozen':
            loops=[polygon_loops(m) for m in masks]
            save(folder/key/'polygons.json',dict(image_size=list(image.size),
                 regions=[dict(id=r['id'],polygons=p,reviewed=False) for r,p in zip(regions,loops)]))
            for m,p in zip(masks,loops):np.testing.assert_array_equal(m,raster_polygons(m.shape,p))
        doc=load_document(folder/key/'evidence.json')
        assert all(r['reviewed'] is False and r['mask_reviewed'] is False and r['reliability']==0 for r in doc['regions'])
    save(folder/'B2_frozen/diagnostics.json',diagnostics)
    save(folder/'vlm_plan_status.json',next(r for r in availability() if r['task_id']==task['task_id']))
    text=Image.new('RGB',image.size,'#263345');d=ImageDraw.Draw(text)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',max(16,image.width//52))
    lines=['VLM Region Plan: N/A','No valid cached plan; no new API request.',
           'Conditional control: existing reference boxes only.','']
    lines += [r['id']+' / '+r['name'] for r in regions]
    lines += ['', 'Not a VLM plan. Not semantic GT.', 'All automatic evidence: reviewed=false']
    d.multiline_text((25,25),'\n'.join(lines),font=font,fill='white',spacing=12)
    panel_grid([('Reference RGB',image),('VLM Region Plan / availability',text),
        ('A: cached reference rectangles',Image.open(folder/'A_rectangles/overlay.png')),
        ('B2: frozen algorithm and parameters',Image.open(folder/'B2_frozen/overlay.png'))],folder/'comparison.png')
    save(folder/'geometry_validation.json',dict(order_invariance=True,parameters_unchanged=True,
        polygon_raster_matches=True,all_unreviewed=True,total_seconds=time.perf_counter()-started))
    print(task['task_id']+' geometry finished',flush=True)
    return stats


def sensitivity(out, scenes):
    rows=[];cases=[];skips=[];started=time.perf_counter();energies=('appearance','spatial','statistical')
    for task,folder,a_key,b_key in scenes:
        image=Image.open(folder/'reference.png').convert('RGB')
        native_size=image.size;image.thumbnail((768,768),Image.Resampling.LANCZOS);rgb=np.asarray(image)
        docs=[read(folder/k/'evidence.json') for k in (a_key,b_key)]
        ids=[r['id'] for r in docs[0]['regions']]
        if ids != [r['id'] for r in docs[1]['regions']]:raise ValueError('ROI correspondence mismatch')
        masks=[]
        for key,doc in zip((a_key,b_key),docs):
            masks.append(np.stack([np.asarray(Image.open(folder/key/r['mask']).resize(image.size,Image.Resampling.NEAREST))>0 for r in doc['regions']]))
        a,b=masks;common=a&b&(a.sum(0)==1)&(b.sum(0)==1)
        patches=[interior_patch(m) for m in common]
        focus=int(np.argmax([0 if p is None else (p[2]-p[0])*(p[3]-p[1]) for p in patches]))
        supports=[('Global',np.ones(rgb.shape[:2],bool))]
        supports += [('A/'+key,m) for key,m in zip(ids,a)]+[('B2/'+key,m) for key,m in zip(ids,b)]
        grid=POLICY['grid'];h,w=rgb.shape[:2]
        dense_boxes=[[x*w//grid,y*h//grid,(x+1)*w//grid,(y+1)*h//grid] for y in range(grid) for x in range(grid)]
        supports += [('Dense/'+str(i),m) for i,m in enumerate(rectangles((h,w),dense_boxes))]
        baseline={key:numerical_errors(rgb,rgb,m)[0] for key,m in supports}
        assert all(all(abs(v)<1e-12 for v in values.values()) for values in baseline.values())
        simdir=out/'synthetic'/task;simdir.mkdir(parents=True)
        for index,patch in enumerate(patches):
            if patch is None:
                skips.append(dict(task_id=task,region_id=ids[index],reason='No sufficiently large exclusive common A/B patch'))
                continue
            # Only one target per scene receives the strength sweep; all ROIs
            # get full-strength color and blur tests. No semantic target choice.
            strengths=(.25,.5,1.) if index==focus else (1.,)
            for kind in ('color','blur'):
                for strength in strengths:
                    changed=perturb(rgb,patch,kind,strength);delta_pixels=np.any(rgb!=changed,axis=2)
                    if kind == 'color' and not delta_pixels.any():raise AssertionError('Color edit must change pixels')
                    case=ids[index]+'_'+kind+'_'+str(strength)
                    filename=task+'/'+case+'.png';Image.fromarray(changed).save(simdir/(case+'.png'))
                    cases.append(dict(task_id=task,case=case,target_region=ids[index],kind=kind,strength=strength,
                        patch_xyxy=patch,image_size=list(image.size),geometry_image_size=list(native_size),
                        changed_pixels=int(delta_pixels.sum()),changed_fraction=float(delta_pixels.mean()),
                        image='synthetic/'+filename,origin='synthetic_local_RGB_edit_not_Agent_reconstruction',reviewed=False))
                    for scope,mask in supports:
                        values,details=numerical_errors(rgb,changed,mask)
                        row=dict(task_id=task,case=case,target_region=ids[index],perturbation=kind,strength=strength,
                            scope=scope,mask_pixels=int(mask.sum()),changed_pixels_in_scope=int((delta_pixels&mask).sum()),
                            semantic=None,perceptual=None,unavailable_reason='No reviewed semantic verdict or DINO inference; numerical ROI diagnostic only',
                            reviewed=False,formal_score=False)
                        for energy in energies:
                            row['baseline_'+energy]=baseline[scope][energy]
                            row[energy]=values[energy];row['delta_'+energy]=values[energy]-baseline[scope][energy]
                        rows.append(row)
                    print(task+' '+case+' measured',flush=True)
    write_csv(out/'sensitivity.csv',rows);save(out/'synthetic_cases.json',dict(cases=cases,skips=skips,
        metric_source='e_harness.benchmark_metrics.numerical_errors (unchanged)',
        candidate_evidence_promoted_to_reviewed=False,formal_benchmark=False,seconds=time.perf_counter()-started))
    return rows,cases,skips


def summarize_sensitivity(out,rows,cases):
    """Report conditional changes and dilution; no new energy aggregation."""
    groups={}
    for row in rows:groups.setdefault((row['task_id'],row['case']),{})[row['scope']]=row
    summary=[];cross_leak=0.;dense_accounting=0.
    for case in cases:
        values=groups[(case['task_id'],case['case'])];target=case['target_region']
        a,b,g=[values[key] for key in ('A/'+target,'B2/'+target,'Global')]
        dense=[v for key,v in values.items() if key.startswith('Dense/')]
        dense_mean=sum(v['appearance']*v['mask_pixels'] for v in dense)/sum(v['mask_pixels'] for v in dense)
        dense_accounting=max(dense_accounting,abs(dense_mean-g['appearance']))
        other=[v['appearance'] for key,v in values.items() if key.startswith(('A/','B2/')) and key.split('/',1)[1]!=target]
        cross_leak=max(cross_leak,max(other,default=0.))
        entry=dict(task_id=case['task_id'],case=case['case'],target_region=target,
            perturbation=case['kind'],strength=case['strength'],changed_pixels=case['changed_pixels'],
            effective_edit=case['changed_pixels']>0,A_appearance=a['delta_appearance'],
            B2_appearance=b['delta_appearance'],Global_appearance=g['delta_appearance'],
            Dense_area_weighted_appearance=dense_mean,Dense_max_patch_appearance=max(v['appearance'] for v in dense),
            B2_to_Global_appearance=b['appearance']/g['appearance'] if g['appearance']>0 else None,
            B2_to_A_appearance=b['appearance']/a['appearance'] if a['appearance']>0 else None,
            B2_spatial=b['delta_spatial'],B2_statistical=b['delta_statistical'],
            semantic=None,perceptual=None,formal_score=False)
        summary.append(entry)
    write_csv(out/'sensitivity_summary.csv',summary)
    sweeps=[]
    for task in sorted({r['task_id'] for r in summary}):
        for kind in ('color','blur'):
            target=next(r['target_region'] for r in summary if r['task_id']==task and r['perturbation']==kind and r['strength']==.25)
            points=sorted([r for r in summary if r['task_id']==task and r['perturbation']==kind and r['target_region']==target],key=lambda r:r['strength'])
            sweeps.append(dict(task_id=task,kind=kind,target_region=target,
                values=[dict(strength=r['strength'],appearance=r['B2_appearance'],spatial=r['B2_spatial'],statistical=r['B2_statistical']) for r in points],
                nondecreasing={k:all(points[i][k]<=points[i+1][k]+1e-12 for i in range(len(points)-1))
                               for k in ('B2_appearance','B2_spatial','B2_statistical')}))
    audit=dict(baseline_all_zero=all(r['baseline_'+e]==0 for r in rows for e in ('appearance','spatial','statistical')),
        case_count=len(cases),effective_edits=sum(c['changed_pixels']>0 for c in cases),
        no_effect_case_ids=[c['task_id']+'/'+c['case'] for c in cases if not c['changed_pixels']],
        non_target_roi_appearance_max=cross_leak,dense_global_L1_accounting_max_abs_error=dense_accounting,
        sweeps=sweeps,interpretation='Amplification is conditional normalization by ROI area, not proof of semantic ROI quality')
    save(out/'sensitivity_audit.json',audit)
    return audit


def exclusion_probe(out,scenes):
    """Counter-control: pixels retained by A but excluded from every B2 ROI.

    Their semantic relevance is deliberately unknown. A zero B2 response here
    demonstrates why sensitivity within retained support is insufficient.
    """
    rows=[];cases=[];skips=[];folder=out/'exclusion_probe';folder.mkdir()
    for task,source,a_key,b_key in scenes:
        image=Image.open(source/'reference.png').convert('RGB');image.thumbnail((768,768),Image.Resampling.LANCZOS)
        rgb=np.asarray(image);docs=[read(source/k/'evidence.json') for k in (a_key,b_key)];stacks=[]
        for key,doc in zip((a_key,b_key),docs):
            stacks.append(np.stack([np.asarray(Image.open(source/key/r['mask']).resize(image.size,Image.Resampling.NEAREST))>0 for r in doc['regions']]))
        a,b=stacks;ids=[r['id'] for r in docs[0]['regions']]
        patches=[interior_patch(mask&~b.any(0)&(a.sum(0)==1)) for mask in a]
        areas=[0 if p is None else (p[2]-p[0])*(p[3]-p[1]) for p in patches]
        if not max(areas):
            skips.append(dict(task_id=task,reason='No sufficiently large A-only area outside every B2 ROI'));continue
        index=int(np.argmax(areas));patch=patches[index];changed=perturb(rgb,patch,'color',1.)
        image_path='exclusion_probe/'+task+'.png';Image.fromarray(changed).save(out/image_path)
        cases.append(dict(task_id=task,target_region=ids[index],patch_xyxy=patch,image=image_path,
                          interpretation='A-only support probe; semantic relevance unknown',reviewed=False))
        h,w=rgb.shape[:2];grid=POLICY['grid']
        dense=rectangles((h,w),[[x*w//grid,y*h//grid,(x+1)*w//grid,(y+1)*h//grid] for y in range(grid) for x in range(grid)])
        supports=[('Global',np.ones((h,w),bool)),('A/'+ids[index],a[index])]
        supports += [('B2/'+key,m) for key,m in zip(ids,b)]+[('Dense/'+str(i),m) for i,m in enumerate(dense)]
        for name,mask in supports:
            values,_=numerical_errors(rgb,changed,mask)
            rows.append(dict(task_id=task,target_region=ids[index],scope=name,**values,
                             semantic=None,perceptual=None,formal_score=False,reviewed=False))
    if rows:write_csv(out/'exclusion_probe.csv',rows)
    save(out/'exclusion_cases.json',dict(cases=cases,skips=skips,semantic_relevance='unknown, no GT'))
    return cases


def presentation(out,stats,cases):
    body=['<!doctype html><meta charset="utf-8"><title>Frozen B2 — generalization controls</title>',
      '<style>body{font:16px sans-serif;margin:24px;background:#f5f6f8}img{max-width:100%}table{width:100%;table-layout:fixed}td{padding:6px;vertical-align:top}</style>',
      '<h1>冻结 B2：泛化条件测试</h1><p>bw_9064、bw_0073 均缺少可用 VLM Region Plan。以下几何结果仅来自已有参考侧 bbox，不能认作完整 Region-first 泛化验证。全部自动候选仍 reviewed=false。</p>',
      '<p><a href="report.md">报告与复现</a> · <a href="plan_availability.json">Plan 缺失依据</a> · <a href="geometry_summary.csv">几何统计</a> · <a href="sensitivity.csv">模拟扰动数据</a></p>']
    body.append('<p><a href="sensitivity_summary.csv">局部/Global/Dense 对照摘要</a> · <a href="sensitivity_audit.json">零误差、泄漏与强度检查</a></p>')
    for task in ('bw_9064','bw_0073'):
        body += ['<h2>'+task+'</h2><img src="'+task+'/comparison.png">',
          '<p>VLM Plan：N/A。<a href="'+task+'/vlm_plan_status.json">原因</a> · <a href="'+task+'/cached_roi_input.json">非 VLM 缓存框</a> · <a href="'+task+'/B2_frozen/diagnostics.json">冻结 B2 决策</a></p>',
          '<table><tr><th>已有 Region 提示</th><th>矩形</th><th>B2</th></tr>']
        for row in read(out/task/'cached_roi_input.json')['regions']:
            body.append('<tr><td>'+html.escape(row['id']+' / '+row['name'])+'</td>'+''.join(
                '<td><img src="'+task+'/'+key+'/'+row['id']+'_overlay.png"></td>' for key in ('A_rectangles','B2_frozen'))+'</tr>')
        body += ['</table><table><tr><td>B2 overlap<img src="'+task+'/B2_frozen/overlap.png"></td><td>B2 unassigned<img src="'+task+'/B2_frozen/unassigned_overlay.png"></td></tr></table>']
    body.append('<h2>模拟局部扰动，非真实 Agent 错误</h2><p>图像缩至最长边 768；同一扰动用于 A/B2/Global/Dense。颜色与模糊各对每个可用 ROI 测试一次，另一个几何选定目标有 0.25/0.5/1.0 强度实验。</p><table>')
    for case in cases:
        if case['strength']!=1:continue
        body.append('<tr><td>'+html.escape(case['task_id']+' '+case['case'])+'</td><td><img src="'+case['image']+'"></td><td>'+html.escape(str(case['patch_xyxy']))+'</td></tr>')
    body.append('</table><h2>A 保留、B2 排除区域的反向检查</h2><p>语义相关性未知；检查 ROI 未覆盖内容仍由 Global/Dense 观察。<a href="exclusion_probe.csv">数值</a> · <a href="exclusion_cases.json">样本与跳过原因</a></p>')
    for probe in read(out/'exclusion_cases.json')['cases']:
        body.append('<p>'+html.escape(probe['task_id']+' / '+probe['target_region'])+'</p><img src="'+probe['image']+'">')
    (out/'comparison.html').write_text('\n'.join(body))
    table='\n'.join('| '+r['task_id']+' | '+r['method']+' | '+str(r['roi_count'])+' | '+f"{100*r['region_union_fraction']:.2f}% | {100*r['overlap_fraction']:.2f}% | {100*r['unassigned_fraction']:.2f}% |" for r in stats)
    (out/'report.md').write_text('''# 冻结 B2 泛化验证：条件测试，完整结论仍受 Plan 缺失限制

用户已确认 bw_0074 B2 的区域粒度和大致完整性符合预期；这不是像素级语义 GT。原算法、参数和旧实验目录保持原样。源文件快照见 source_snapshot；freeze_note.json 记录人工反馈范围。未新增 VLM/API/模型推理、GPU、Blender 或 Agent 执行。

bw_9064 保存的 VLM Plan 是 unavailable/SSLError，后续组合响应未通过 schema 校验；bw_0073 没有保存 Region Plan。没有修复或补造它们。本轮完整 VLM→ROI 泛化测试因此跳过。作为有限补充，仅将既有 manifest 的 role=region 参考框输入冻结 B2，结果称为“缓存框条件几何测试”。框由历史助手从原图提出，不是 VLM 输出；两图均含 5 个旧区域，未补造家具组。

几何计算最长边 1536，所有坐标按统一比例从原图缓存框映射，A/B2 在同一网格比较。bw_0073 原图 7952×4333，缩放可能影响细结构。冻结的 noun aliases 没有扩充；不认识的类别记录在 content_hints.json。B2 不读取 Agent Render 或新 SAM 像素 Mask。

| 图片 | 方法 | ROI 数 | ROI 并集 | 重叠/全图 | 未分配 |
| --- | --- | ---: | ---: | ---: | ---: |
'''+table+'''

这些数值不是分割准确率。背景无需强制分配，主要内容保留情况仍需原图静态审核。逐区图、原图/Plan 状态/A/B2 对照见 comparison.html。

## 局部模拟扰动

直接调用未修改的 numerical_errors，计算 Appearance RGB L1、Spatial 粗边缘分布代理、Statistical 纹理/边缘分布代理。全部候选证据依旧 q=0/未审核；这是固定几何支撑上的数值敏感性实验，没有绕过审核运行正式 Benchmark、Observation 或 3D 分数。Semantic/Perceptual 为 N/A，没有语义验证或 DINO 推理。

统一将图像缩至最长边 768，选择 A 与 B2 同一 Region 的共同独占部分，在最大内接位置放一个小方块；无合适位置则记录跳过。局部编辑为颜色偏移 [60,-60,0]（裁剪到 RGB 范围）及半径 3 的高斯模糊，并保持其余像素完全不变。每个可用 ROI 有 1.0 强度的两种扰动；每图按可用内接方块大小选一个目标测试 0.25/0.5/1.0。目标按几何选择，不代表物体的重要性或真实重建失败。

另外检查 A 保留、但所有 B2 都排除的位置；其语义重要性未知，不能直接当作丢失重要物体的证据。反向方块和测量保存在 exclusion_cases.json、exclusion_probe.csv。共同支撑测试本身不检查 ROI 外部遗漏。

同一编辑逐项比较矩形 ROI、B2 ROI、Global 和 POLICY.grid=2 的四个 Dense Patch，输出每项实际数值、零扰动 Baseline 和 Δ。没有将 Region 均值/最大值聚合成新的评分。Dense 应查看逐 Patch；其面积加权 RGB L1 平均等于 Global，因此平均也会稀释小范围错误。完整 CSV 与模拟图见 sensitivity.csv、synthetic_cases.json。空间/统计指标共享边缘代理，不能解读为相互独立。

## 复现

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \\
  /home/xymo/environments/relateanything-inference/bin/python \\
  scripts/region_first_generalization.py --output results/region_first_generalization_repeat
```

输出目录必须尚不存在。只需现有 NumPy/Pillow/SciPy 环境与缓存，不联网或加载模型。测试日志、实际成本及完整性检查见 tests.log、validation.json。
''')


def run(out,reuse_geometry=None):
    out.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    frozen=ROOT/'scripts/coarse_roi_experiment.py';before=frozen.read_bytes()
    (out/'source_snapshot').mkdir();shutil.copyfile(frozen,out/'source_snapshot'/frozen.name)
    shutil.copyfile(ROOT/'e_harness/benchmark_evidence.py',out/'source_snapshot/benchmark_evidence.py')
    save(out/'freeze_note.json',dict(source=str(frozen),parameters=read(ROOT/'results/coarse_evaluation_roi_bw0074/B2_edge_polygons/diagnostics.json')['parameters'],
        human_feedback='bw_0074 B2 granularity and approximate completeness accepted as preferred candidate',
        pixelwise_semantic_GT=False,automatic_candidates_remain_unreviewed=True,parameter_tuning=False))
    plans=availability()
    if any(r['usable_vlm_plan'] for r in plans):
        raise ValueError('New usable Plan found; reassess conditional geometry setup explicitly')
    save(out/'plan_availability.json',dict(tasks=plans,new_paid_calls=0,reviewed=False,
        validation_record=str(ROOT/'results/vlm_region_hierarchy/vlm_evidence.json')))
    tasks=read(ROOT/'results/multiscene_region_extraction/manifest.json')['tasks'];stats=[]
    for task in tasks:
        if task['task_id'] not in ('bw_9064','bw_0073'):continue
        if reuse_geometry is None:
            stats+=geometry_control(out,task)
        else:
            cached=reuse_geometry/task['task_id'];shutil.copytree(cached,out/task['task_id'])
            for key in ('A_rectangles','B2_frozen'):
                stat=read(cached/key/'statistics.json');stat.update(method=key,task_id=task['task_id'],
                    roi_count=len(read(cached/key/'evidence.json')['regions']),
                    experiment='conditional_cached_bbox_geometry_control',usable_vlm_plan=False,
                    geometry_seconds=None)
                stats.append(stat)
    write_csv(out/'geometry_summary.csv',stats)
    control=ROOT/'results/coarse_evaluation_roi_bw0074'
    # Existing accepted candidate is used verbatim, with no new boundary tuning.
    # A reference copy keeps sensitivity inputs independent of Agent artifacts.
    source_image=next(control.glob('reference.*'))
    scenarios=[(task,out/task,'A_rectangles','B2_frozen') for task in ('bw_9064','bw_0073')]
    baseline=out/'bw_0074_control';baseline.mkdir()
    with Image.open(source_image) as image:image.convert('RGB').save(baseline/'reference.png')
    for src,dest in [('A_rectangles','A_rectangles'),('B2_edge_polygons','B2_frozen')]:
        (baseline/dest).mkdir();doc=read(control/src/'evidence.json')
        for row in doc['regions']:shutil.copyfile(control/src/row['mask'],baseline/dest/row['mask'])
        save(baseline/dest/'evidence.json',doc)
    scenarios.append(('bw_0074',baseline,'A_rectangles','B2_frozen'))
    rows,cases,skips=sensitivity(out,scenarios);audit=summarize_sensitivity(out,rows,cases)
    probes=exclusion_probe(out,scenarios);presentation(out,stats,cases)
    assert frozen.read_bytes()==before==(out/'source_snapshot'/frozen.name).read_bytes()
    save(out/'validation.json',dict(frozen_source_text_unchanged=True,parameters_unchanged=True,
        automatic_evidence_reviewed=False,formal_scoring_executed=False,geometry_controls=2,
        valid_new_scene_vlm_plans=0,paid_calls=0,model_inferences=0,gpu_used=False,
        synthetic_cases=len(cases),measurement_rows=len(rows),skipped_patches=skips,
        geometry_reused_from=str(reuse_geometry) if reuse_geometry else None,
        synthetic_patch_bounds_checked=True,effective_synthetic_edits=audit['effective_edits'],
        exclusion_probe_cases=len(probes),cpu_thread_limit=2,seconds=time.perf_counter()-started))
    print(json.dumps(dict(output=str(out),seconds=time.perf_counter()-started,cases=len(cases)),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reuse-geometry',type=Path)
    args=parser.parse_args();run(args.output.resolve(),args.reuse_geometry.resolve() if args.reuse_geometry else None)
