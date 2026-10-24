"""One bounded historical-camera ID render; offline analysis never re-renders."""
import argparse
import ast
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read,save,font
from scripts.region_real_render import fit_render

SOURCE=ROOT/'results/blender_scene_graph_audit_bw0074'


def correspondence_gate(source=SOURCE):
    p=read(source/'provenance.json');g=read(source/'scene_graph.json');c=read(source/'group_correspondence.json')
    run=Path(p['run_config']).parent;trajectory=read(run/'agent/trajectory.json')
    text=None;edits=[];renders=[];commands=[]
    for i,step in enumerate(trajectory['steps']):
        for call in step.get('tool_calls',[]):
            args=call.get('arguments',{})
            if args.get('file_path')=='/workspace/exports/build_scene.py':
                if 'content' in args:text=args['content']
                elif 'old_string' in args and text is not None:
                    old=args['old_string']
                    if text.count(old)!=1 and not args.get('replace_all'):raise ValueError('Ambiguous historical edit')
                    text=text.replace(old,args['new_string'],-1 if args.get('replace_all') else 1)
                else:raise ValueError('Unrecognized script mutation')
                edits.append(i)
            command=args.get('command','')
            if command:commands.append((i,command))
            if command.startswith('blender -b ') and '--python /workspace/exports/build_scene.py >' in command:
                renders.append(i)
    if text!=Path(p['blend']).with_name('build_scene.py').read_text() or not renders or max(edits)>max(renders):
        raise ValueError('Final executed script/artifact correspondence not established')
    final=max(renders)
    allowed_post={'ls -lah /workspace/exports',
        'rm /workspace/exports/final.blend1 /workspace/exports/preview.png /workspace/exports/render_log.txt && ls -lh /workspace/exports'}
    if any(cmd not in allowed_post for i,cmd in commands if i>final):raise ValueError('Unreviewed post-render operation')
    results=trajectory['steps'][final]['observation']['results']
    meta=results[0]['extra']['tool_result_metadata']['tool_use_result']
    if meta.get('interrupted') or meta.get('stderr') or not all(x in meta.get('stdout','') for x in ('final.blend','modern_living_room.png')):
        raise ValueError('Final render delivery was not confirmed')
    tree=ast.parse(text);constants={};save_line=None;render_line=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                key=ast.unparse(target)
                if key in ('camera.location','camera_data.lens','camera_data.sensor_width'):
                    constants[key]=ast.literal_eval(node.value)
                if key=='target' and isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='Vector':
                    constants['target']=ast.literal_eval(node.value.args[0])
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            name=ast.unparse(node.value.func)
            if name=='bpy.ops.wm.save_as_mainfile':save_line=node.lineno
            if name=='bpy.ops.render.render':render_line=node.lineno
    if save_line is None or render_line is None or save_line>=render_line:raise ValueError('Save/render ordering unknown')
    active=next(cam for cam in g['cameras'] if cam['active']);matrix=np.array(active['matrix_world'])
    direction=np.array(constants['target'])-constants['camera.location'];direction/=np.linalg.norm(direction)
    if not (np.allclose(matrix[:3,3],constants['camera.location'],atol=1e-6)
            and np.allclose(-matrix[:3,2],direction,atol=1e-6)
            and active['lens_mm']==constants['camera_data.lens']
            and active['sensor_width_mm']==constants['camera_data.sensor_width']):
        raise ValueError('Saved camera differs from final executed script')
    old=read(Path(p['work'])/'historical_state.json')
    if not all(Path(path).stat().st_size==record['size'] and Path(path).stat().st_mtime_ns==record['mtime_ns'] for path,record in old.items()):
        raise ValueError('Historical artifacts changed since graph audit')
    if Path(p['blend']).read_bytes()!=(Path(p['work'])/'input.blend').read_bytes():raise ValueError('Scene differs from audited input')
    check=c['camera_render_consistency']
    if not all(check[k] for k in ('camera_name_matches_png','render_size_matches_png','scene_name_matches_png','output_basename_matches')):
        raise ValueError('PNG/camera metadata do not correspond')
    with Image.open(p['render_rgb']) as image:
        if image.size!=tuple(g['scene']['resolution']) or int(image.info['Frame'])!=g['scene']['frame']:
            raise ValueError('Historical image frame/size differs')
    return p,g,c,dict(status='documentary_correspondence_verified',final_trajectory_step=final,
        final_script_text_matches_export=True,no_later_scene_mutations_found=True,
        saved_camera_matches_final_script=True,png_camera_scene_frame_and_resolution_match=True,
        saved_before_final_render=True,pixel_exact_scene_image_equivalence_proven=False,
        basis='Final executed source, delivery observation, unchanged audited blend and PNG metadata; source never executed in this experiment',reviewed=False)


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);work=ROOT/'runs'/('group_visibility_'+str(time.time_ns()));work.mkdir()
    try:p,g,c,gate=correspondence_gate()
    except Exception as error:
        save(output/'visibility.json',dict(status='blocked',reason=str(error),render_calls=0,mask=None,reviewed=False,usage='provisional/debug'))
        raise
    objects={o['id']:o for o in g['objects']}
    mapping=[dict(index=i+1,object_id=name,row_hint=next(x['row_hint'] for x in c['projections'] if x['object_id']==name),
                  matrix_world=objects[name]['matrix_world']) for i,name in enumerate(c['candidate_object_ids'])]
    if len(mapping)!=241 or any(objects[r['object_id']]['type']!='MESH' for r in mapping):raise ValueError('Candidate set changed')
    state={str(f):dict(size=f.stat().st_size,mtime_ns=f.stat().st_mtime_ns)
           for directory in (SOURCE,ROOT/'results/records_group_verification_bw0074',Path(p['run_config']).parent)
           for f in directory.rglob('*') if f.is_file()}
    for value in (p['roi'],p['reference_cached']):
        f=Path(value);state[str(f)]=dict(size=f.stat().st_size,mtime_ns=f.stat().st_mtime_ns)
    save(work/'historical_state.json',state)
    shutil.copyfile(p['blend'],work/'input.blend');(work/'input.blend').chmod(0o444)
    helper=ROOT/'scripts/group_id_blender.py';ast.parse(helper.read_text());shutil.copyfile(helper,work/'render_id.py')
    job=dict(blend=str(work/'input.blend'),source_directory=str(Path(p['run_config']).parent),
        expected_camera=next(c for c in g['cameras'] if c['active']),expected_scene=g['scene'],mapping=mapping,
        parent_mnt_namespace=str(Path('/proc/self/ns/mnt').readlink()),parent_net_namespace=str(Path('/proc/self/ns/net').readlink()),
        pass_directory=str(work/'passes'),settings=str(work/'settings.json'),ids=str(work/'object_ids.npy'),result=str(work/'render_result.json'))
    save(work/'job.json',job)
    plan=dict(work=str(work),source=str(SOURCE),provenance=p,correspondence=gate,
        render_budget=1,maximum_long_edge=512,samples=1,cpu_threads=2,wall_seconds=90,cpu_seconds=60,
        rss_stop_bytes=1024**3,host_uid=os.getuid(),title_parts_excluded=c['candidate_decoration_part_ids'],
        title_reason='No explicit reviewed per-sleeve ownership; all title parts remain normal occluders with ID zero',
        scene_name_identity_is_gt=False,reviewed=False,usage='provisional/debug')
    save(work/'frozen_plan.json',plan);(work/'frozen_plan.json').chmod(0o444)
    save(output/'visibility.json',dict(status='prepared',protocol=plan,reviewed=False,usage='provisional/debug'))
    print(json.dumps(dict(work=str(work),correspondence=gate),ensure_ascii=False))


def render(output):
    from scripts.manual_reviewed_replay import BLENDER,LIMITS,namespace_command,monitored_process
    pending=read(output/'visibility.json');plan=pending['protocol'];work=Path(plan['work'])
    if pending['status']!='prepared' or plan!=read(work/'frozen_plan.json') or (work/'render_reserved.json').exists():
        raise ValueError('No render retry or overwrite permitted')
    # Recheck current system-wide CPU idleness; process listing is PID-namespace limited.
    def cpus():
        return {int(p[0][3:]):np.array(list(map(int,p[1:]))) for line in Path('/proc/stat').read_text().splitlines()
                if (p:=line.split()) and p[0].startswith('cpu') and p[0][3:].isdigit()}
    first=cpus();time.sleep(1);second=cpus();allowed=os.sched_getaffinity(0)
    fractions={cpu:float((second[cpu]-first[cpu])[3:5].sum()/(second[cpu]-first[cpu]).sum()) for cpu in allowed}
    chosen=sorted(fractions,key=lambda cpu:(-fractions[cpu],cpu))[:2]
    idle={str(cpu):fractions[cpu] for cpu in chosen}
    mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','MemTotal:'))}
    resource=dict(load=os.getloadavg(),selected_cpus=chosen,idle_fraction=idle,memory=mem,
        host_process_list_complete=False,process_listing_scope='Current PID namespace only',reviewed=False)
    preflight=work/('resource_preflight_'+str(len(list(work.glob('resource_preflight*.json')))+1)+'.json')
    save(preflight,resource)
    if len(chosen)<2 or min(idle.values())<.5 or mem['MemAvailable']<4*1024**3:
        raise RuntimeError('Insufficient idle CPU/memory; no render started')
    limits={**LIMITS,'step_seconds':90,'cpu_seconds':60,'rss_stop_bytes':1024**3}
    command=namespace_command([str(BLENDER),'--background','--factory-startup','--disable-autoexec','--offline-mode',
        '--threads','2','--python-exit-code','1','--python',str(work/'render_id.py'),'--',str(work/'job.json')])
    with (ROOT/'runs/.manual_reviewed_replay.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save(work/'render_reserved.json',dict(maximum_attempts=1,attempt=1,retries=False,reviewed=False))
        os.sched_setaffinity(0,chosen)
        try:
            result=monitored_process(command,work,work,None,time.monotonic()+90,'single_group_id',
                extra_env=dict(OPENIMAGEIO_THREADS='2',BLENDER_USER_SCRIPTS=str(work/'private/config'),
                               BLENDER_USER_EXTENSIONS=str(work/'private/config')),
                sample_seconds=.1,process_limit=4,limits=limits)
        finally:os.sched_setaffinity(0,allowed)
    result['resource_preflight_file']=str(preflight)
    result['selected_cpus']=chosen
    save(work/'execution_result.json',result)
    print(json.dumps(result,ensure_ascii=False))


def roi_on_grid(roi,transform,size):
    x,y=transform['offset_xy'];w,h=transform['resized_size']
    return np.asarray(roi.crop((x,y,x+w,y+h)).resize(size,Image.Resampling.NEAREST))>0


def mask_on_reference(mask,transform,size):
    canvas=Image.new('L',size);image=Image.fromarray(np.uint8(mask)*255).resize(tuple(transform['resized_size']),Image.Resampling.NEAREST)
    canvas.paste(image,tuple(transform['offset_xy']));return canvas


def analyze(ids,mapping,roi,bbox_projections):
    known={r['index'] for r in mapping}
    if ids.ndim!=2 or not np.isin(ids,list(known|{0})).all() or ids.shape!=roi.shape:
        raise ValueError('Invalid ID array or coordinate grid')
    mask=np.isin(ids,list(known));h,w=ids.shape;xs=(np.arange(w)+.5)/w;ys=(np.arange(h)+.5)/h
    proxy=np.zeros_like(mask)
    for p in bbox_projections:
        x1,y1,x2,y2=p['base_bounds_projection']['xyxy_normalized']
        proxy|=((ys[:,None]>=y1)&(ys[:,None]<y2)&(xs[None,:]>=x1)&(xs[None,:]<x2))
    counts=np.bincount(ids.ravel(),minlength=max(known)+1);members=[];rows=[]
    for r in mapping:members.append(dict(index=r['index'],object_id=r['object_id'],row_hint=r['row_hint'],
        id_pixels=int(counts[r['index']]),sampled_visible=bool(counts[r['index']]>0),reviewed=False))
    for row in sorted({r['row_hint'] for r in mapping},key=float):
        selected=[m for m in members if m['row_hint']==row];rm=np.isin(ids,[m['index'] for m in selected])
        rows.append(dict(row_hint=row,candidate_bodies=len(selected),bodies_with_sampled_id_pixels=sum(m['sampled_visible'] for m in selected),
            mask_pixels=int(rm.sum()),inside_r3_pixels=int((rm&roi).sum()),outside_r3_pixels=int((rm&~roi).sum()),reviewed=False))
    ys_m,xs_m=np.nonzero(mask)
    return dict(native_resolution=[w,h],group_pixels=int(mask.sum()),r3_pixels=int(roi.sum()),
        group_inside_r3_pixels=int((mask&roi).sum()),group_outside_r3_pixels=int((mask&~roi).sum()),
        r3_group_pixel_fraction=float((mask&roi).sum()/roi.sum()) if roi.any() else None,
        group_outside_r3_fraction=float((mask&~roi).sum()/mask.sum()) if mask.any() else None,
        sampled_support_bbox_xyxy=[int(xs_m.min()),int(ys_m.min()),int(xs_m.max()+1),int(ys_m.max()+1)] if mask.any() else None,
        candidate_body_objects=len(mapping),bodies_with_sampled_id_pixels=sum(m['sampled_visible'] for m in members),
        historical_full_resolution_visible_object_count=None,actual_semantic_record_count=None,
        bbox_proxy_pixels=int(proxy.sum()),bbox_proxy_without_group_id_pixels=int((proxy&~mask).sum()),
        group_id_outside_bbox_proxy_pixels=int((mask&~proxy).sum()),
        pixel_difference_interpretation='Proxy minus ID includes empty box interior, occluders, excluded labels, undersampling and boundary effects; not a pure occlusion ratio',
        members=members,rows=rows,reviewed=False),mask


def draw(output,plan,data,mask,reference,historical,transform):
    p=plan['provenance'];roi=Image.open(p['roi']).convert('L');crop=roi.getbbox()
    bbox=Image.open(Path(plan['source'])/'projection_full_frame.png').convert('RGB')
    if mask is None:
        visible=Image.new('RGB',reference.size,'#d9dfe7');ImageDraw.Draw(visible).text((crop[0]+8,crop[1]+30),'N/A',font=font(40),fill='black')
    else:
        m=np.asarray(mask_on_reference(mask,transform,reference.size))>0
        pixels=np.array(historical).copy();pixels[m]=(pixels[m]*.55+np.array([20,225,200])*.45).astype(np.uint8)
        visible=Image.fromarray(pixels)
    canvas=Image.new('RGB',(3120,1225),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((24,12),'bw_0074/R3 | saved historical camera | one CPU IndexOB pass | provisional/debug',font=font(31),fill='#193149')
    for i,(title,im) in enumerate(zip(('Reference / fixed R3','Historical Render / same R3','BBox proxy / NOT visibility','ID-supported body pixels / same R3'),(reference,historical,bbox,visible))):
        x=24+i*774;d.text((x,70),title,font=font(22),fill='#193149')
        canvas.paste(im.crop(crop).resize((750,844),Image.Resampling.NEAREST if i==3 else Image.Resampling.LANCZOS),(x,110))
    if mask is None:lines=['ID pass unavailable; no placeholder mask generated.',data.get('reason','')[:180]]
    else:
        stats=data['measurements'];lines=[
            f"Native ID grid: {stats['native_resolution']} | Group pixels: {stats['group_pixels']} | R3 coverage: {stats['r3_group_pixel_fraction']:.2%} | Group outside R3: {stats['group_outside_r3_fraction']:.2%}",
            f"{stats['bodies_with_sampled_id_pixels']}/{stats['candidate_body_objects']} body meshes have >=1 ID pixel at this resolution; NOT a historical high-res record count.",
            'Rows: '+' | '.join(f"{r['row_hint']}: {r['mask_pixels']} px ({r['bodies_with_sampled_id_pixels']} meshes sampled)" for r in stats['rows']),
            'Titles excluded (ownership unreviewed); other objects still occlude. Binary IndexOB edges are not antialiased.',
            '512px / 1 sample / CPU 2 threads. Upscaled mask overlay is for display only; no Reference mask GT or Energy score.',
            'Newer-file compatibility warning: exact historical-render pixel equivalence is NOT certified.'
        ]
    for i,line in enumerate(lines):d.text((24,980+i*43),line,font=font(25),fill='#694521' if i<2 else '#33495d')
    canvas.save(output/'comparison.png')


def report(output):
    pending=read(output/'visibility.json');plan=pending['protocol'];work=Path(plan['work'])
    if pending['status']!='prepared' or plan!=read(work/'frozen_plan.json'):raise ValueError('No completed-result overwrite')
    execution=read(work/'execution_result.json');p=plan['provenance'];reference=Image.open(p['reference_cached']).convert('RGB')
    resource_samples=[json.loads(line) for line in (work/'resources.jsonl').read_text().splitlines()]
    resource_observations=dict(peak_native_threads=max(sum(p['threads'] for p in r['processes']) for r in resource_samples),
        maximum_sampled_cpu_seconds=max(r['cpu_seconds'] for r in resource_samples),
        configured_render_worker_threads=2,selected_cpu_affinity=execution.get('selected_cpus'),
        process_total_native_threads_hard_limited_to_two=False)
    historical,_,transform=fit_render(Image.open(p['render_rgb']),reference.size)
    success=execution['success'] and (work/'render_result.json').exists()
    log=(work/'single_group_id.log').read_text(errors='replace')
    warnings=[]
    version_lines=[line for line in log.splitlines() if 'File written by newer Blender binary' in line]
    if version_lines:warnings.append(dict(kind='newer_file_version',messages=version_lines,
        consequence='Installed reader may lose unsupported state; exact original-renderer equivalence is not certified'))
    if 'ValueError: list.remove(x): x not in list' in log:
        warnings.append(dict(kind='cycles_unregister_cleanup',
            message='ValueError: list.remove(x): x not in list during cycles.unregister / version_update callback removal',
            consequence='ID output completed and process exited 0; factory callback clearing caused a teardown exception; preserve full log'))
    mask=None
    if success:
        raw=read(work/'render_result.json');ids=np.load(work/'object_ids.npy',allow_pickle=False)
        roi=roi_on_grid(Image.open(p['roi']).convert('L'),transform,tuple(ids.shape[::-1]))
        graph=read(Path(plan['source'])/'scene_graph.json');by_name={o['id']:o for o in graph['objects']}
        measurements,mask=analyze(ids,raw['mapping'],roi,[by_name[m['object_id']] for m in raw['mapping']])
        Image.fromarray(np.uint8(mask)*255).save(output/'visibility_mask.png')
        final=dict(status='pass_support_available',protocol=plan,pass_settings=raw['settings'],measurements=measurements,
            render_calls=1,render_seconds=raw['render_seconds'],execution=execution,
            mask='visibility_mask.png',raw_id_array=str(work/'object_ids.npy'),raw_exr=raw['raw_exr'],
            title_mask=None,mask_definition='Body-mesh pixels selected by unique IndexOB IDs, with original occluders; titles excluded',
            technical_warnings=warnings,reader_version=read(Path(plan['source'])/'scene_graph.json')['blender_build'],
            historical_render_pixel_mask_equivalence_certified=False,
            resource_observations=resource_observations,
            limitations=['Low-resolution single-sample hard IndexOB support, not pixel GT',
                'Transparency follows alpha threshold; IndexOB does not provide antialiased fractional edge coverage',
                'Subpixel/marginal/occluded bodies may produce no ID pixel',
                'Excluded unowned title geometry can occlude body pixels',
                'No Reference Group mask GT; no IoU, semantic category confirmation or formal score'],
            reviewed=False,scorable=False,usage='provisional/debug',formal_energy=None)
    else:
        final=dict(status='unavailable',protocol=plan,reason=execution['error'] or 'Missing validated ID output',
            execution=execution,render_attempts=1,mask=None,reviewed=False,usage='provisional/debug',formal_energy=None)
    (output/'visibility.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,allow_nan=False))
    draw(output,plan,final,mask,reference,Image.fromarray(historical),transform)
    if success:
        s=final['measurements'];table='\n'.join(f"| {r['row_hint']} | {r['candidate_bodies']} | {r['bodies_with_sampled_id_pixels']} | {r['mask_pixels']} | {r['inside_r3_pixels']} | {r['outside_r3_pixels']} |" for r in s['rows'])
        outcome=f'''真正提取Cycles IndexOB数据（原始EXR及逐对象uint16数组在work），并非BBox并集。原始Mask为{s['native_resolution']}，{s['group_pixels']}像素；R3内{s['group_inside_r3_pixels']} / {s['r3_pixels']}像素，占{s['r3_group_pixel_fraction']:.4%}。{s['group_outside_r3_pixels']}个Group像素在固定R3之外，占Group的{s['group_outside_r3_fraction']:.4%}。没有移动ROI。

{s['bodies_with_sampled_id_pixels']}/{s['candidate_body_objects']}个候选主体Mesh在本次低分辨率采样中各贡献至少一个ID像素；不是历史高分辨率的完整可见数量，更不是唱片实例GT。其他未采到像素的对象可能被遮挡、太薄或落在子像素，不能认定缺失。

| 名称层架Z（已用几何底Z核对） | 候选主体Mesh | 有ID像素的Mesh | Group像素 | R3内 | R3外 |
|---|---|---|---|---|---|
{table}

BBox并集有{s['bbox_proxy_pixels']}像素，其中{s['bbox_proxy_without_group_id_pixels']}没有对应Group ID支持。差集包含空包围盒内部、其他对象/标题遮挡、低分辨率漏采和边界效应，不能全部称作遮挡面积。低层BBox越过收录机的部分是特别需要审核的代理失真案例。Group ID在BBox之外有{s['group_id_outside_bbox_proxy_pixels']}像素，保留原值，不裁剪美化。'''
    else:outcome='本次受限读取/渲染或Pass提取失败：'+str(final['reason'])+'。不重试，不换引擎，不生成假零Mask；visibility_mask.png不可用。'
    text=f'''# bw_0074/R3 Group可见性最小实验

全部reviewed=false、provisional/debug。只处理既有241个封套主体候选，没有重新做语义发现、匹配或正式评分。

## 对应证据与单次渲染

同一Run `{p['run_id']}`。来源blend：`{p['blend']}`；历史PNG：`{p['render_rgb']}`。按轨迹的Write/Edit记录仅重建文本，逐字等于导出脚本；最后一次执行先保存场景再渲染，交付结果确认两文件，随后没有场景修改。静态读出的相机位置/目标/26mm焦距与已审计场景矩阵及PNG的Camera/Scene/Frame/分辨率匹配。原blend与此前审计副本字节相同。门控记录见JSON.protocol.correspondence。这是文档和数值对应证据，不是逐像素同步认证；仍属历史相机诊断，未用正式T0替换相机。

无可复用的本Run ID/Segmentation/Cryptomatte Pass。使用原Cycles、原相机和遮挡几何/材质/灯光；仅在内存给241个主体赋互异Object Index，其他对象保持ID0和正常遮挡。28个标题部件缺少已审核归属，全部排除，未当作额外唱片；它们仍可遮挡主体。用同一次渲染的IndexOB和Combined输出提取数据，没有第二次渲染。

最长边512（512×347），1 sample，CPU两线程，无自适应采样/去噪；用极小pixel-aspect补偿整数分辨率取整，保留保存相机的物理画幅比例和全部内外参。未保存blend。Autoexec/use_scripts禁用、清除载入回调，空用户配置、空GPU可见列表、断网/PID/mount命名空间，原Run和输入副本只读绑定；宿主UID {plan['host_uid']}，不提权。原有监控器设置90秒墙钟、60秒CPU、1GiB RSS停止阈值、8GiB地址空间上限、低优先级/两核亲和性；监测阈值不等于整任务内核配额。首次资源预检发现默认CPU1繁忙，在启动任何Blender前停止；第二次从允许范围选择空闲核{execution.get('selected_cpus')}，实际只启动一次渲染。两次预检均保留，实际采用的记录为 `{execution.get('resource_preflight_file')}`。PID视图仅能看到当前命名空间任务，不能声称检查了全部宿主进程。

## 实际结果

{outcome}

总进程墙钟{execution['seconds']:.3f}秒，采样峰值RSS {execution['peak_rss_bytes']/1024**2:.1f}MiB；清理完成={execution['cleanup_complete']}。完整原始输出、命令及资源日志在 `{work.relative_to(ROOT)}`。一次预约文件阻止本次自动重试。
配置的是2个渲染工作线程和两核亲和性；监测到的进程原生线程总数峰值为{resource_observations['peak_native_threads']}（含主线程和IO/库辅助线程），并未硬限制总线程数为2。采样累计CPU时间最大{resource_observations['maximum_sampled_cpu_seconds']:.2f}秒。若将“两线程”理解为包含所有辅助线程的严格总数上限，本轮未满足该更严格口径，不隐瞒此资源边界。

## 失败案例与技术警告

完整日志保留两项警告：

- `Warning: File written by newer Blender binary (402.67), expect loss of data!`：本地读取器为4.2.0，不能认证它完整保留原写入器的全部状态。相机参数、候选变换及输出尺寸检查通过，ID输出有效，但**本轮Mask只代表当前读取器中的条件性可见支持，不是原历史PNG逐像素可见性的认证**。如果要求严格历史渲染器等价，此项仍为阻塞；没有下载或更换软件重试。
- 退出时出现 `ValueError: list.remove(x): x not in list`，来自Cycles注销时试图移除已被安全读取器清理的version_update回调。Pass已输出、数组校验通过、进程退出0并清理完成；没有隐藏该异常，也没有为修复退出回调再渲染。

## 可用信息和限制

实际获得的是这一低资源配置下的渲染通道可见支持，含真实遮挡，优于BBox定位代理；不等于高分辨率、抗锯齿或人工审核的像素GT。IndexOB的透明度阈值、透明材质、薄片与边缘漏采均可能影响结果，阈值和原始设置保存在visibility.json.pass_settings。原始visibility_mask.png不含上采样；comparison的Mask仅为同坐标显示而最近邻放大。

三层归属来自既有名称提示，并在读入场景中以实际几何底Z核对，允许按层汇总可见像素分布；不从聚合Mask推断实例数量。逐对象ID仅支持统计本次采样到的候选Mesh，未解决语义类别GT或标题归属。无额外去遮挡/xray渲染，因此未采到像素的原因不逐对象强行归类。

Scene Graph名称提供候选身份，几何变换提供排列方向，ID Pass提供生成侧可见范围/分布；三者结合可辅助Group-level Spatial/Statistical。但Reference只有存在、多柜格、主要竖直的候选证据，没有可靠唱片Mask GT，故不做Mask IoU；生成侧几何也不能证明图像语义一致。此前Render类别ambiguous和三个satisfied均不改写。

值得作为可选诊断工具保留，前提是场景/相机对应、读取器兼容性、语义组审核、Pass透明度与边界规则明确、资源允许。目前不作为正式评分依据。7项纯CPU离线测试通过，涵盖逐ID统计、N/A处理、固定ROI留边映射、BBox不得冒充Mask、一次渲染预约与可信读取器约束；它们不等于像素准确率验证。没有API/GPT子Agent、没有运行历史生成代码、没有修改Runtime/ROI/Evidence/Energy、没有Git提交或HTML；完成后停止。

## 离线复现

只重放已保存的ID数组和设置、生成新报告，不启动Blender；目标必须不存在：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_visibility.py --stage replay --output results/blender_group_visibility_bw0074 --destination results/blender_group_visibility_bw0074_replay
```

本次新渲染已完成或消耗一次尝试，不自动重跑。可信读取/渲染代码为scripts/group_id_blender.py，实际命令与一次预约在work目录；重跑需要新的明确实验授权，不使用replay触发渲染。
'''
    (output/'report.md').write_text(text)
    print(json.dumps(dict(status=final['status'],output=str(output),measurements={k:v for k,v in final.get('measurements',{}).items() if k not in ('members','rows')}),ensure_ascii=False))


def replay(source,destination):
    destination.mkdir(parents=True,exist_ok=False);final=read(source/'visibility.json')
    if final['status'] not in ('pass_support_available','unavailable'):raise ValueError('Completed experiment required')
    save(destination/'visibility.json',dict(status='prepared',protocol=final['protocol']))
    report(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('prepare','render','report','replay'),required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if args.stage=='replay':
        if args.destination is None:parser.error('Fresh --destination required')
        replay(output,args.destination.resolve())
    else:globals()[args.stage](output)
