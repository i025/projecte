"""Bounded read-only Blender metadata extraction and offline R3 audit report."""
import argparse
import ast
from collections import Counter
import fcntl
import json
from pathlib import Path
import re
import shutil
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read,save,font
from scripts.region_real_render import fit_render


def extract(output):
    from scripts.manual_reviewed_replay import BLENDER,namespace_command,monitored_process
    output.mkdir(parents=True,exist_ok=False)
    work=ROOT/'runs'/('scene_graph_audit_'+str(time.time_ns()));work.mkdir()
    old=read(ROOT/'results/records_group_verification_bw0074/verification_results.json')
    audit=old['pair_audit']['source_audit'];run=Path(audit['run_config']).parent
    blend=run/'artifacts/workspace/exports/final.blend';config=read(run/'config.json')
    manifest=read(run/'artifacts/manifest.json');inputs=read(audit['input_metadata'])
    if not (config['trial_name']==run.name and inputs['task_id']=='bw_0074' and
            Path(config['task']['path'])/'environment/inputs/input.json'==Path(audit['input_metadata']) and
            inputs['files']==['references/image_01.jpg'] and
            Path(audit['render_rgb']).parent==blend.parent and
            any(r['source']=='/workspace/exports' and r['destination']=='artifacts/workspace/exports'
                and r['status']=='ok' for r in manifest)):
        raise ValueError('Reference/Run/artifact correspondence failed')
    with blend.open('rb') as stream:
        if stream.read(12)!=b'BLENDER-v402':raise ValueError('Unreviewed Blender file-format compatibility')
    state={str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in run.rglob('*') if p.is_file()}
    for directory in ('results/records_group_verification_bw0074','results/group_identity_context_bw0074'):
        state.update({str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)
                      for p in (ROOT/directory).rglob('*') if p.is_file()})
    for value in (old['protocol']['roi'],old['protocol']['reference_rgb']):
        p=Path(value);state[str(p)]=dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)
    save(work/'historical_state.json',state)
    helper=ROOT/'scripts/scene_graph_readonly_blender.py'
    calls=[ast.unparse(n.func) for n in ast.walk(ast.parse(helper.read_text())) if isinstance(n,ast.Call)]
    if any(c in calls for c in ('bpy.ops.render.render','bpy.ops.wm.save_as_mainfile','exec','eval','runpy.run_path')):
        raise ValueError('Inspector contains disallowed execution/render/save operation')
    shutil.copyfile(blend,work/'input.blend');(work/'input.blend').chmod(0o444)
    if (work/'input.blend').read_bytes()!=blend.read_bytes():raise ValueError('Input copy differs')
    shutil.copyfile(helper,work/'reader.py')
    job=dict(blend=str(work/'input.blend'),source_blend=str(blend),source_directory=str(run),
        result=str(output/'scene_graph.json'),parent_mount_namespace=str(Path('/proc/self/ns/mnt').readlink()),
        parent_net_namespace=str(Path('/proc/self/ns/net').readlink()))
    save(work/'job.json',job)
    provenance=dict(run_id=str(run.relative_to(ROOT.parent/'BlenderWorld/runs')),reference_rgb=audit['reference_rgb'],
        reference_cached=old['protocol']['reference_rgb'],render_rgb=audit['render_rgb'],blend=str(blend),
        run_config=str(run/'config.json'),manifest=str(run/'artifacts/manifest.json'),input_metadata=audit['input_metadata'],
        same_run_verified=True,pixel_synchronization_reverified=False,roi=old['protocol']['roi'],
        reference_group_id='bw_0074_R3_records',group_source=str(ROOT/'results/records_group_verification_bw0074/verification_results.json'),
        work=str(work),reviewed=False,usage='provisional/debug')
    save(output/'provenance.json',provenance)
    command=namespace_command([str(BLENDER),'--background','--factory-startup','--disable-autoexec',
        '--offline-mode','--threads','2','--python-exit-code','1','--python',str(work/'reader.py'),'--',str(work/'job.json')])
    with (ROOT/'runs/.manual_reviewed_replay.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=monitored_process(command,work,work,None,time.monotonic()+60,'readonly_metadata',
            extra_env=dict(OPENIMAGEIO_THREADS='2',BLENDER_USER_SCRIPTS=str(work/'private/config'),
                           BLENDER_USER_EXTENSIONS=str(work/'private/config')),sample_seconds=.1,process_limit=4)
    save(work/'execution_result.json',result)
    if not result['success']:
        if not (output/'scene_graph.json').exists():
            save(output/'scene_graph.json',dict(status='unavailable',reason=result['error'],reviewed=False))
        raise RuntimeError('Extraction stopped; see execution_result.json; no fallback or render')
    return result


def map_bounds(normalized,transform):
    x1,y1,x2,y2=normalized;w,h=transform['resized_size'];ox,oy=transform['offset_xy']
    return [x1*w+ox,y1*h+oy,x2*w+ox,y2*h+oy]


def intersection(a,b):
    return max(0.,min(a[2],b[2])-max(a[0],b[0]))*max(0.,min(a[3],b[3])-max(a[1],b[1]))


def row_key(obj):
    match=re.match(r'VINYL archival sleeve row (\d+\.\d+) ',obj['name'])
    return match.group(1) if match else None


def summary(graph,provenance,transform):
    bodies=[o for o in graph['objects'] if row_key(o) is not None]
    labels=[o for o in graph['objects'] if o['name'].startswith('LP colored paper narrow title')]
    books=[o for o in graph['objects'] if re.search(r' book \d',o['name'])]
    context=[o['id'] for o in graph['objects'] if re.search(r'boombox|speaker|turntable|DJ deck chassis|spinning platter|record library',o['name'],re.I)]
    mesh={m['id']:m for m in graph['meshes']}
    rows=[]
    def range_of(values):return [round(float(min(values)),7),round(float(max(values)),7)]
    for key in sorted({row_key(o) for o in bodies},key=float):
        members=[o for o in bodies if row_key(o)==key]
        axes=[np.array(o['matrix_world'])[:3,2] for o in members]
        angles=[np.degrees(np.arccos(np.clip(v[2]/np.linalg.norm(v),-1,1))) for v in axes]
        x=[o['world_origin'][0] for o in members]
        rows.append(dict(name_row_hint=key,candidate_body_objects=len(members),
            actual_world_x_center_range=range_of(x),actual_world_y_center_range=range_of([o['world_origin'][1] for o in members]),
            actual_base_aabb_bottom_z_range=range_of([o['world_aabb'][0][2] for o in members]),
            tilt_from_world_up_degrees_range=range_of(angles),
            object_center_x_histogram_8_bins=np.histogram(x,bins=8)[0].tolist(),
            histogram_scope='Declared candidate body centers, per-row range; not visible density or GT element count',reviewed=False))
    with Image.open(provenance['roi']) as mask:roi=list(mask.getbbox())
    projections=[]
    for obj in bodies:
        p=obj.get('base_bounds_projection') or {}
        if p.get('status')!='geometric_bbox_only':continue
        bbox=map_bounds(p['xyxy_normalized'],transform)
        projections.append(dict(object_id=obj['id'],row_hint=row_key(obj),xyxy_common_pixels=bbox,
            bbox_intersects_fixed_roi=intersection(bbox,roi)>0,
            bbox_fully_inside_fixed_roi=bool(roi[0]<=bbox[0] and roi[1]<=bbox[1] and bbox[2]<=roi[2] and bbox[3]<=roi[3]),
            kind='base_bbox_projection_not_visible_mask',actual_visibility='unknown',reviewed=False))
    positive=all(all(d>0 for d in o['object_dimensions']) for o in bodies)
    dimensions=[range_of([o['object_dimensions'][i] for o in bodies]) for i in range(3)] if bodies else None
    active=next((c for c in graph['cameras'] if c['active']),None)
    with Image.open(provenance['render_rgb']) as image:
        png=dict(size=list(image.size),camera=image.info.get('Camera'),scene=image.info.get('Scene'),
                 file=image.info.get('File'),frame=image.info.get('Frame'))
    consistency=dict(camera_name_matches_png=bool(active and active['object_id']==png['camera']),
        render_size_matches_png=graph['scene']['resolution']==png['size'],
        scene_name_matches_png=graph['scene']['name']==png['scene'],
        output_basename_matches=Path(graph['scene']['render_path']).name==Path(provenance['render_rgb']).name,
        pixel_synchronization_reverified=False,png_metadata=png)
    return dict(reference_group_id=provenance['reference_group_id'],reference_group_source=provenance['group_source'],
        candidate_object_ids=[o['id'] for o in bodies],candidate_decoration_part_ids=[o['id'] for o in labels],
        candidate_collection_ids=sorted({c for o in bodies for c in o['collection_ids']}),
        contextual_object_ids=context,matching_status='candidate_intent_and_geometry; semantic correctness unreviewed',
        name_clues='VINYL archival sleeve row / LP title names; vinyl sleeve materials; separate book names/materials',
        hierarchy=dict(semantic_collection_present=False,body_parent_links=sum(o['parent_id'] is not None for o in bodies),
                       title_to_body_links='unavailable; independent objects, no saved parent/Group IDs'),
        geometry=dict(candidate_body_objects=len(bodies),decoration_part_objects=len(labels),book_named_body_objects=len(books),
            unique_body_meshes=len({o['data_id'] for o in bodies}),
            body_base_topology=dict(Counter(str((mesh[o['data_id']]['vertex_count'],mesh[o['data_id']]['polygon_count'])) for o in bodies)),
            positive_3d_extents=positive,local_dimensions_xyz_range=dimensions,
            height_to_depth_ratio_range=range_of([o['object_dimensions'][2]/o['object_dimensions'][1] for o in bodies]) if bodies else None,
            rows=rows,counts_are_mesh_metadata_not_record_gt=True,
            scope='Stored base mesh/transform only; no evaluated modifier, sleeve interior, contact or collision check'),
        projections=projections,camera_render_consistency=consistency,
        projection_summary=dict(available_bbox_projections=len(projections),
            intersects_roi=sum(p['bbox_intersects_fixed_roi'] for p in projections),
            fully_inside_roi=sum(p['bbox_fully_inside_fixed_roi'] for p in projections),
            actual_visible_mask='N/A',actual_visible_object_count=None,occlusion_test='not performed',
            group_visible_position=None,group_visible_density=None),
        limitations=['Names/material names are Agent declarations, not category GT',
            'Thin cuboid body geometry overlaps book-like geometry; visual category remains unconfirmed',
            'Title parts have no explicit per-sleeve ownership',
            'No Object-ID/segmentation pass, all object pass_index values are zero',
            'Stored camera/PNG metadata agree but final scene vs saved pixels not re-render verified',
            'Historical camera differs from fixed-T0 protocol; no Reference 3D or exact Group-mask GT'],
        reviewed=False,scorable=False,usage='provisional/debug',formal_energy=None)


def figures(output,provenance,group,reference,rendered):
    with Image.open(provenance['roi']) as mask:roi=mask.getbbox()
    a=reference.crop(roi);b=rendered.crop(roi)
    overlay=Image.new('RGBA',rendered.size);draw=ImageDraw.Draw(overlay)
    colors={'1.45':(240,145,40,70),'1.90':(40,210,130,70),'2.36':(75,155,255,70)}
    for p in group['projections']:
        draw.rectangle(p['xyxy_common_pixels'],outline=colors[p['row_hint']],width=1)
    projected=Image.alpha_composite(rendered.convert('RGBA'),overlay).convert('RGB')
    projected.save(output/'projection_full_frame.png')
    c=projected.crop(roi)
    canvas=Image.new('RGB',(2346,1220),'#f4f6f8');d=ImageDraw.Draw(canvas)
    d.text((24,12),'bw_0074 / R3 | Scene Graph audit | stored base-bounds projections, NOT visible masks',font=font(30),fill='#182e45')
    for n,(title,image) in enumerate(zip(('Reference / fixed R3','Historical Render / same R3','Stored-camera bbox proxies / same R3'),(a,b,c))):
        x=24+n*774;d.text((x,68),title,font=font(23),fill='#182e45')
        canvas.paste(image.resize((750,844),Image.Resampling.LANCZOS),(x,108))
    lines=[
        f"{group['geometry']['candidate_body_objects']} sleeve-body name claims + {group['geometry']['decoration_part_objects']} separate label parts; these are NOT verified record counts.",
        'Blue = row hint 2.36 | Green = 1.90 | Orange = 1.45. Boxes include occluded depth and may overlap.',
        f"BBox/ROI intersection: {group['projection_summary']['intersects_roi']}/{len(group['projections'])}; fully inside: {group['projection_summary']['fully_inside_roi']}/{len(group['projections'])}. Neither means visible.",
        'Actual visible masks / visible density: N/A. No Object-ID pass, no new rendering, no occlusion test.',
        'Camera/PNG metadata agree; final scene vs saved pixels not re-render verified. Projection is conditional.',
        'All reviewed=false; provisional/debug; historical camera; no formal Energy or category GT.'
    ]
    for i,line in enumerate(lines):d.text((24,975+i*37),line,font=font(25 if i==0 else 23),fill='#6b4824' if i==0 else '#33475b')
    canvas.save(output/'comparison.png')


def report(output):
    graph=read(output/'scene_graph.json');provenance=read(output/'provenance.json');work=Path(provenance['work'])
    if (output/'group_correspondence.json').exists():raise FileExistsError('Audit report already exists')
    reference=Image.open(provenance['reference_cached']).convert('RGB')
    rendered,_,transform=fit_render(Image.open(provenance['render_rgb']),reference.size)
    group=summary(graph,provenance,transform);save(output/'group_correspondence.json',group)
    figures(output,provenance,group,reference,Image.fromarray(rendered))
    execution=read(work/'execution_result.json');g=group['geometry'];camera=next(c for c in graph['cameras'] if c['active'])
    row_text='\n'.join(f"| {r['name_row_hint']} | {r['candidate_body_objects']} | {r['actual_base_aabb_bottom_z_range']} | {r['tilt_from_world_up_degrees_range']} |" for r in g['rows'])
    text=f'''# bw_0074/R3 Blender Scene Graph 审计

仅 Reference Group **{group['reference_group_id']}**。所有对应和观察均 reviewed=false、provisional/debug；不产生正式Energy，不修改Reference/ROI或历史结果。

## 来源与读取

Run：`{provenance['run_id']}`。Reference：`{provenance['reference_rgb']}`；Render：`{provenance['render_rgb']}`；blend：`{provenance['blend']}`。
Run config的task.path → input.json的task_id/files → 原始参考图；同一Run artifact manifest将/workspace/exports映射到同一交付目录，其中包含这张PNG和final.blend。PNG的Camera、Scene、File、Frame及尺寸与保存场景相符；历史build_scene.py仅作为文本/AST读取，其305行保存final.blend，310行渲染PNG，未执行。确认同一重建来源，不等于重新验证blend与PNG逐像素同步。

没有已有Scene Graph或Object-ID文件。使用原有受限CPU启动器读取7.3MB输入副本，--factory-startup --disable-autoexec --offline-mode、open_mainfile(use_scripts=False,load_ui=False)，载入前清理回调；文本自动执行、Python drivers均禁用。独立用户/网络/PID/mount命名空间，原Run目录与输入副本只读bind mount；私有配置和空GPU可见列表，2核/线程、低优先级、60秒墙钟及CPU监测阈值、1GiB RSS停止阈值、8GiB地址空间上限、进程数4。监测阈值不是整任务内核配额；没有改正式Runtime blocked状态。

实际提取 {execution['seconds']:.3f} 秒，采样峰值RSS {execution['peak_rss_bytes']/1024**2:.1f} MiB，退出0且清理完成。没有渲染/保存、历史Python执行或GPT/API调用。实际保存场景无Text块、driver或外链库。几何只读基础Mesh和存储变换，不求值修改器，不做遮挡或碰撞检查。

## 名称、层级与几何

共 {len(graph['objects'])} 对象、{len(graph['meshes'])} Mesh datablocks、{sum(o['type']=='CURVE' for o in graph['objects'])} Curve；所有对象都在一个Collection，全部无parent。Object名称常有明确建模意图，Mesh数据名仍多为Cube.*。没有独立唱片Collection、Group ID或标题块归属层级。

名称找到 **{g['candidate_body_objects']} 个VINYL封套主体候选**，各有独立基础Mesh，均为8顶点/6面长方体并带小倒角/法线修改器；另有 **{g['decoration_part_objects']} 个LP标题小块Mesh**，没有parent关联。因此不能把269个组件称为269张唱片，也不能将241个声明直接当作真实可见唱片数量。历史脚本文本显示一封套主体加间歇独立标题块的建模意图；没有逐封套的内部圆盘或精确封套结构验证。

另找到{g['book_named_body_objects']}个书籍主体名称。书籍与唱片有不同名称/材料名、粗空间分区，但都使用薄长方体，几何不构成可靠类别判别。封套局部XYZ尺寸范围为{g['local_dimensions_xyz_range']}（场景单位米），高度/深度比{g['height_to_depth_ratio_range']}；均有正厚度，排列近竖直。部分形状并非近方形，这可作为外观可辨识性的疑点，不能当作已确认语义或几何错误。

| 名称提示行底Z | 主体组件数（非GT数量） | 实测基础AABB底Z范围 | 长轴偏离世界+Z角度范围（度） |
|---|---|---|---|
{row_text}

名称提示三层与实际几何高度吻合，最低层在X方向分为两簇；所有候选中心Y约-0.28m。可读取世界坐标、范围、长轴方向和候选中心分布，无需Reference逐实例ID。但这些是模型组件组织，不是经过可见性验证的真实物体密度。

## 相机、投影与对应

保存相机位置约(2.07,-5.22,1.71)m，PERSP，实际lens={camera['lens_mm']}mm、sensor_width={camera['sensor_width_mm']}mm、1920×1300、frame1，矩阵和内参见scene_graph.json。相机数据名含“30mm”，数值却是26mm，是名称不可充当参数真值的具体例子。历史相机不满足正式固定外参证据，Reference相机未知。

Group候选由名称、材料名、三层薄片几何及保存相机投影共同支持；宣称意图比较明确，视觉类别是否正确仍未审核。241个基础包围盒均可投影；{group['projection_summary']['intersects_roi']}个包围盒与固定R3相交、{group['projection_summary']['fully_inside_roi']}个完整落在R3内。这不是可见数量或分割准确率；部分候选投影在固定ROI之外，不能判缺失。

PNG与场景的相机名、场景名、分辨率及输出名一致，几何投影大致落在Render右侧陈列带。comparison.png右栏只画基础8角包围盒投影，未求值倒角，也不处理遮挡；projection_full_frame.png保留全幅位置。所有pass_index为0，Object Index/Material Index/Cryptomatte均关闭，因此**实际可见Mask、可见对象数、Group可见范围/密度均N/A**。不能用bbox并集冒充可见Mask。

历史中立分类实验的Render回答为ambiguous，而Scene Graph名称宣称VINYL；这体现“建模意图明确，但图像类别可辨识性不足”的候选落差，不足以确认唱片被建成书籍。仍需独立视觉/人工审核或经过验证的VLM，且不得追溯修改此前三个satisfied。

## 对Energy的帮助与结论

- Semantic：名称和材料名可提供可审计的语义意图与候选检索，但不能证明类别正确；需要图像可辨识证据和独立审核。
- Spatial：实际世界变换、几何范围和保存视角的bbox投影可用；可见位置仍需要可靠Object-ID/遮挡支持与Reference对应，历史视角差异限制归因。
- Statistical：可以对候选集合汇总方向、三层组织及中心位置分布，避免Reference逐张匹配；不能把Mesh计数、bbox面积或组件分布直接当作真实可见数量/密度。
- Appearance/Perceptual沿用既有图像比较，本轮未重算；五类Energy/权重及独立3D Structural Energy均未改。

值得将Scene Graph作为辅助证据来源，优先支持候选生成、语义意图审计和几何验证；当前不足以作为自动Group类别GT、正式匹配或评分输入。主要瓶颈是语义正确性、组件归属、像素可见性及Reference–Render对应，不是读出更多Mesh。

## 复现

离线重画（不启动Blender，目标目录必须不存在）：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/audit_scene_graph.py --stage replay --output results/blender_scene_graph_audit_bw0074 --destination results/blender_scene_graph_audit_bw0074_replay
```

需要重新提取时，只运行本轮可信读取器，仍不渲染；资源不可用或只读mount失败即停止，无降级执行：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/audit_scene_graph.py --stage extract --output results/blender_scene_graph_audit_bw0074_reextract
/home/xymo/environments/relateanything-inference/bin/python -B scripts/audit_scene_graph.py --stage report --output results/blender_scene_graph_audit_bw0074_reextract
```

5项CPU单元测试通过，覆盖留边坐标转换、bbox交集、组件候选边界、不得由几何生成可见Mask/语义GT，以及读取器禁止保存/渲染/文本执行的约束。真实来源、完整命令、资源日志、源文件前后状态及最终检查在 `{work.relative_to(ROOT)}`。本轮无HTML、无新渲染、无GPU、无Agent/GPT/API调用、无Git提交；审计后停止。
'''
    (output/'report.md').write_text(text)
    print(json.dumps(dict(objects=len(graph['objects']),body_candidates=len(group['candidate_object_ids']),projection=group['projection_summary'],output=str(output)),ensure_ascii=False))


def replay(source,destination):
    destination.mkdir(parents=True,exist_ok=False)
    for name in ('scene_graph.json','provenance.json'):shutil.copyfile(source/name,destination/name)
    report(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('extract','report','replay'),required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='replay':
        if args.destination is None:parser.error('Fresh --destination required')
        replay(output,args.destination.resolve())
    else:globals()[args.stage](output)
