"""Frozen single-image topology extraction and offline comparison; no model launcher."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read,save,font,collect
from scripts.region_real_render import fit_render

SYSTEM='你是图像空间结构分析器。只分析图片中的书柜结构，不分析摆放物的数量。识别清晰可见的水平层板、竖向结构隔板及由它们形成的独立柜格。不要把书脊、唱片封套或装饰品边缘误认为柜体隔板。无法区分时返回 unknown。只输出简洁 JSON。'
USER='''分析图中目标书柜的可见结构，输出：

1. 可辨认的主要水平层次。
2. 每个层次内清晰的竖向分隔。
3. 是否形成多个左右独立的柜格。
4. 不能确定的结构。

不要推测遮挡后的隔板。仅输出 JSON，不要解释。'''
FORMAT='''左侧为完整图片，橙框为目标；右侧为同坐标目标放大图。完整图仅提供上下文，只分析橙框内目标柜体；不把框线或图像裁切边缘当作隔板。
统一定义：rows 是自上而下的可见开口层带，不是摆放物高度组；vertical_dividers 只数同一层内部清晰的结构隔板，排除外侧框架；separate_compartments 是该层实际可辨的左右独立开口数量。不能确认时计数为字符串 unknown，不根据摆放物分簇推定柜格。horizontal_shelves 只标层带之间可见的内部水平层板，不含外顶板/底座。
所有位置均相对于右侧目标裁剪图，归一化到0–1000；原点在左上，x向右、y向下。线段坐标为[x1,y1,x2,y2]，只需粗定位；不确定的线不画。y_range 为该开口层带粗略的上下位置，无法定位则null。
严格输出对象字段：
- top_to_bottom_complete：yes/no/unknown，表示能否确认目标柜体从最上可见开口到最下可见开口的垂直范围均包含在输入中（不代表左右边界完整）。
- horizontal_shelves：可见内部水平层板的粗线段数组。
- rows：按图像从上到下排列，每项仅含 id（唯一字符串）、y_range、vertical_dividers（非负整数或unknown）、separate_compartments（正整数或unknown）、divider_segments（该层清晰隔板的粗线段数组）、certainty（clear/partial/unknown）。已明确计数的隔板应有对应线段。
- unknown：简短的不确定结构说明字符串数组。
不预设层数或柜格数，不输出其他字段或推理过程。'''


def parse_topology(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate key: '+key)
            result[key]=value
        return result
    def number(x):return type(x) in (int,float) and np.isfinite(x) and 0<=x<=1000
    def segment(line):return isinstance(line,list) and len(line)==4 and all(number(v) for v in line) and line[:2]!=line[2:]
    try:
        x=json.loads(raw,object_pairs_hook=unique)
        if not isinstance(x,dict) or set(x)!={'top_to_bottom_complete','horizontal_shelves','rows','unknown'}:raise ValueError('Unexpected or missing top-level keys')
        if x['top_to_bottom_complete'] not in ('yes','no','unknown'):raise ValueError('Invalid completeness')
        if not isinstance(x['horizontal_shelves'],list) or not all(segment(s) for s in x['horizontal_shelves']):raise ValueError('Invalid horizontal coordinates')
        if not isinstance(x['unknown'],list) or not all(isinstance(t,str) for t in x['unknown']):raise ValueError('Invalid unknown list')
        if not isinstance(x['rows'],list):raise ValueError('Invalid rows')
        seen=set();last=-1
        for row in x['rows']:
            if not isinstance(row,dict) or set(row)!={'id','y_range','vertical_dividers','separate_compartments','divider_segments','certainty'}:raise ValueError('Invalid row keys')
            if not isinstance(row['id'],str) or not row['id'] or row['id'] in seen:raise ValueError('Invalid/duplicate row ID')
            seen.add(row['id']);yr=row['y_range']
            if yr is not None:
                if not isinstance(yr,list) or len(yr)!=2 or not all(number(v) for v in yr) or yr[0]>=yr[1] or sum(yr)/2<=last:raise ValueError('Invalid row position/order')
                last=sum(yr)/2
            for key,minimum in [('vertical_dividers',0),('separate_compartments',1)]:
                value=row[key]
                if value!='unknown' and not (type(value)==int and value>=minimum):raise ValueError('Invalid count '+key)
            if row['certainty'] not in ('clear','partial','unknown'):raise ValueError('Invalid certainty')
            if not isinstance(row['divider_segments'],list) or not all(segment(s) for s in row['divider_segments']):raise ValueError('Invalid divider coordinates')
            if type(row['vertical_dividers'])==int and row['vertical_dividers']!=len(row['divider_segments']):raise ValueError('Divider count and line list disagree')
        return dict(status='valid',topology=x)
    except (ValueError,TypeError,KeyError) as error:return dict(status='unavailable',topology=None,error=str(error))


def compare_topology(reference,render):
    if any(p.get('status')!='valid' for p in (reference,render)):
        return dict(status='unavailable',rows=[],reason='One or both responses invalid/unavailable',reviewed=False)
    a,b=reference['topology'],render['topology']
    complete=a['top_to_bottom_complete']==b['top_to_bottom_complete']=='yes'
    row_count_status=('unknown' if not complete else 'coarse_structural_agreement' if len(a['rows'])==len(b['rows']) else 'candidate_structural_layout_mismatch')
    rows=[]
    if complete and len(a['rows'])==len(b['rows']):
        for order,(ra,rb) in enumerate(zip(a['rows'],b['rows']),1):
            fields={}
            for key in ('vertical_dividers','separate_compartments'):
                va,vb=ra[key],rb[key]
                usable=ra['certainty']==rb['certainty']=='clear' and type(va)==type(vb)==int
                fields[key]=dict(reference=va,render=vb,status='unknown' if not usable else
                    'coarse_structural_agreement' if va==vb else 'candidate_structural_layout_mismatch')
            states=[f['status'] for f in fields.values()]
            status='candidate_structural_layout_mismatch' if 'candidate_structural_layout_mismatch' in states else 'unknown' if 'unknown' in states else 'coarse_structural_agreement'
            rows.append(dict(order=order,reference_row_id=ra['id'],render_row_id=rb['id'],fields=fields,status=status,
                event_count=1 if status=='candidate_structural_layout_mismatch' else 0,
                reason='Top-to-bottom level order only; divider and compartment changes describe one correlated structural event, not two penalties',reviewed=False))
    overall='candidate_structural_layout_mismatch' if row_count_status=='candidate_structural_layout_mismatch' or any(r['status']=='candidate_structural_layout_mismatch' for r in rows) else 'unknown' if row_count_status=='unknown' or any(r['status']=='unknown' for r in rows) else 'coarse_structural_agreement'
    return dict(status=overall,rows=rows,horizontal_levels=dict(reference=len(a['rows']),render=len(b['rows']),status=row_count_status),
        reported_internal_shelf_lines=dict(reference=len(a['horizontal_shelves']),render=len(b['horizontal_shelves']),interpretation='Predicted line segments, not guaranteed physical board count'),
        basis='Equal complete ordered levels may be compared in order; no compartment ID matching or spatial reordering. Camera differences remain a limitation.',
        per_level_comparison_available=bool(rows),unmatched_levels_reason=None if rows else 'Vertical extent incomplete or level counts differ; no forced alignment',
        reviewed=False,scorable=False,formal_energy=None)


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    work=ROOT/'runs'/('structural_layout_'+uuid.uuid4().hex);work.mkdir()
    source=ROOT/'results/records_group_verification_bw0074/verification_results.json';old=read(source)
    reference=Image.open(old['protocol']['reference_rgb']).convert('RGB');roi=Image.open(old['protocol']['roi']).convert('L')
    rendered,_,transform=fit_render(Image.open(old['pair_audit']['render_rgb']),reference.size)
    if transform!=old['pair_audit']['transform']:raise ValueError('Historical image fit changed')
    bbox=roi.getbbox();protocol=dict(work=str(work),reference_rgb=old['protocol']['reference_rgb'],render_rgb=old['pair_audit']['render_rgb'],roi=old['protocol']['roi'],
        bbox=list(bbox),image_size=list(reference.size),transform=transform,system=SYSTEM,user=USER,format=FORMAT,
        backend='Codex Subagent',model='gpt-6-sol',maximum_verifiers=2,serial=True,automatic_retries=False,
        images='Full image at native size plus 2x fixed ROI crop; no expected answers, no topology markup',
        no_u1_u7_input=True,prior_coordinator_knowledge_disclosed=True,strict_blind_test=False,reviewed=False,usage='provisional/debug')
    requests={};staged={};(work/'images').mkdir()
    for side,rgb in [('reference',reference),('render',Image.fromarray(rendered))]:
        marked=rgb.copy();ImageDraw.Draw(marked).rectangle((bbox[0],bbox[1],bbox[2]-1,bbox[3]-1),outline='#ff931e',width=3)
        crop=rgb.crop(bbox).resize(((bbox[2]-bbox[0])*2,(bbox[3]-bbox[1])*2),Image.Resampling.LANCZOS)
        sheet=Image.new('RGB',(reference.width+20+crop.width,max(reference.height,crop.height)), '#e5e7eb')
        sheet.paste(marked,(0,0));sheet.paste(crop,(reference.width+20,0))
        folder=Path('/tmp')/uuid.uuid4().hex;folder.mkdir(mode=0o700)
        path=folder/(uuid.uuid4().hex+'.png');local=work/'images'/path.name;sheet.save(local);shutil.copyfile(local,path);path.chmod(0o444)
        task='v_'+uuid.uuid4().hex[:12]
        message='只观察下面指定的一张PNG。仅允许一次view_image读取该图，设置detail="original"，并用image(result.image_url,"original")转交图片；不读取其他文件，不联网，不调用其他模型，不写文件，不请求澄清。最终只输出规定JSON。\n\n图像：'+str(path)+'\n\nSystem：\n'+SYSTEM+'\n\nUser：\n'+USER+'\n\n输出约定：\n'+FORMAT
        requests[side]=dict(task_name=task,model='gpt-6-sol',fork_turns='none',message=message)
        staged[side]=dict(path=str(path),source=str(local),agent_task=task)
    tracked={Path(protocol[k]) for k in ('reference_rgb','render_rgb','roi')}
    for directory in ('group_spatial_distribution_bw0074','reference_blender_group_evidence_bw0074','blender_scene_graph_audit_bw0074'):
        tracked.update(p for p in (ROOT/'results'/directory).rglob('*') if p.is_file())
    save(work/'source_state.json',{str(p):dict(size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in tracked})
    save(work/'frozen_plan.json',protocol);(work/'frozen_plan.json').chmod(0o444)
    save(work/'frozen_agent_inputs.json',requests);(work/'frozen_agent_inputs.json').chmod(0o444)
    save(work/'staged_inputs.json',staged)
    save(output/'verification_results.json',dict(status='prepared',protocol=protocol,reviewed=False))
    print(json.dumps(dict(work=str(work),output=str(output),requests=requests),ensure_ascii=False))


def geometry_audit(graph_path):
    graph=read(graph_path);meshes={m['id']:m for m in graph['meshes']}
    # Names retrieve candidates only. Shape, shared depth/span and stored projections are checked separately.
    shelves=[o for o in graph['objects'] if o['name'].startswith('record library continuous shelf')]
    if not shelves:return dict(status='unavailable',reason='No saved shelf candidates',reviewed=False)
    bounds=np.array([o['world_aabb'] for o in shelves]);low=bounds[:,0].min(axis=0);high=bounds[:,1].max(axis=0)
    thickness=float(np.max(bounds[:,1,2]-bounds[:,0,2]));depth=float(high[1]-low[1])
    checked=[]
    for o in shelves:
        dims=np.array(o['object_dimensions']);mesh=meshes[o['data_id']]
        ok=bool(dims[0]>5*dims[2] and dims[1]>5*dims[2] and mesh['vertex_count']==8 and mesh['polygon_count']==6 and not o['hide_render'] and not o['modifiers'])
        checked.append(dict(object_id=o['id'],world_aabb=o['world_aabb'],dimensions=o['object_dimensions'],
            slab_geometry_supported=ok,projection=o.get('base_bounds_projection'),reviewed=False))
    if not all(x['slab_geometry_supported'] for x in checked):return dict(status='unavailable',shelves=checked,reason='Simple slab assumption unsupported',reviewed=False)
    objects={o['id']:o for o in graph['objects']}
    bottom=objects['main shelf at desk / turntable height']['world_aabb'][1][2]
    top=objects['cabinet cornice top full width']['world_aabb'][0][2]
    panels=[]
    for o in graph['objects']:
        if o['type']!='MESH' or not o.get('world_aabb'):continue
        p,q=np.array(o['world_aabb']);d=q-p;cx=(p[0]+q[0])/2
        if (low[0]+thickness<cx<high[0]-thickness and d[0]<=2*thickness and d[1]>=.8*depth and d[2]>2*thickness
                and p[1]<=low[1]+thickness and q[1]>=high[1]-thickness and q[2]>bottom and p[2]<top):
            panels.append(dict(object_id=o['id'],world_aabb=o['world_aabb'],reviewed=False))
    z_ranges=[];cursor=bottom
    for box in sorted(bounds.tolist(),key=lambda box:box[0][2]):
        z_ranges.append([cursor,box[0][2]]);cursor=box[1][2]
    z_ranges.append([cursor,top]);z_ranges.reverse()
    return dict(status='conditional_geometry_support',source=str(graph_path),shelves=checked,
        bay_bounds=dict(x=[float(low[0]),float(high[0])],y=[float(low[1]),float(high[1])],z=[bottom,top]),
        openings_top_to_bottom_world_z=z_ranges,internal_vertical_slab_candidates=panels,
        query=dict(thickness_tolerance_m=thickness,minimum_depth_fraction=.8,maximum_x_thickness_factor=2,
                   minimum_z_extent_factor=2,scope='All stored Mesh AABBs; internal x only, front-depth panel shapes; not name-only filtering'),
        reason='Three distinct broad, deep, thin horizontal cuboids; no full-depth internal vertical slab candidate under this explicit query',
        limitations=['Base AABBs cannot certify absence of shallow, oblique, combined-mesh or modifier-generated partitions.',
                     'Query is supplementary exploratory geometry evidence, not a general divider detector or semantic GT.',
                     'Stored bbox projection is not a visible mask; compatibility with historical PNG remains conditional.'],reviewed=False)


def assisted_hypotheses(reference,render,geometry):
    """Separate post-hoc corroboration; never upgrades the original VLM certainty."""
    if reference.get('status')!='valid' or render.get('status')!='valid' or geometry.get('status')!='conditional_geometry_support':return []
    a,b=reference['topology'],render['topology'];openings=geometry['openings_top_to_bottom_world_z']
    if not (a['top_to_bottom_complete']==b['top_to_bottom_complete']=='yes' and len(a['rows'])==len(b['rows'])==len(openings)):return []
    result=[]
    for order,(ra,rb,interval) in enumerate(zip(a['rows'],b['rows'],openings),1):
        if ra['certainty']!='clear' or type(ra['vertical_dividers'])!=int or ra['vertical_dividers']<=0 or rb['vertical_dividers']!=0:continue
        overlapping=[p for p in geometry['internal_vertical_slab_candidates'] if p['world_aabb'][1][2]>interval[0] and p['world_aabb'][0][2]<interval[1]]
        if overlapping:continue
        result.append(dict(order=order,status='candidate_structural_layout_mismatch',
            reference_clear_dividers=ra['vertical_dividers'],render_vlm_dividers=rb['vertical_dividers'],render_vlm_certainty=rb['certainty'],
            source='post_hoc_scene_graph_assisted_hypothesis',
            basis='Independent Reference divider observation; Render zero-divider answer; saved broad shelves and zero interior slab candidates in corresponding ordered opening',
            conditions='Only valid under simple full-depth separate-slab representation and coarse ordered-opening correspondence; no precise cabinet matching',
            does_not_override_primary_unknown=True,reviewed=False,scorable=False,formal_energy=None))
    return result


def draw_result(output,protocol,packets,comparison,hypotheses,geometry,posthoc):
    ref=Image.open(protocol['reference_rgb']).convert('RGB');rgb,_,_=fit_render(Image.open(protocol['render_rgb']),ref.size)
    bbox=protocol['bbox'];width,height=750,844
    canvas=Image.new('RGB',(2400,1770),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((24,15),'bw_0074/R3 | independent structural extraction + separate geometry corroboration',font=font(29),fill='#15334b')
    d.text((24,57),'Cyan = predicted internal shelves; yellow = predicted vertical divider. No coordinates were repaired.',font=font(24),fill='#33495d')
    for side,x,image in [('reference',24,ref),('render',815,Image.fromarray(rgb))]:
        crop=image.crop(bbox).resize((width,height),Image.Resampling.LANCZOS);cd=ImageDraw.Draw(crop)
        parsed=packets[side]['parsed']
        if parsed['status']=='valid':
            topo=parsed['topology']
            def line(coords,color):cd.line((coords[0]*width/1000,coords[1]*height/1000,coords[2]*width/1000,coords[3]*height/1000),fill=color,width=4)
            for coords in topo['horizontal_shelves']:line(coords,'#23cde9')
            for i,row in enumerate(topo['rows'],1):
                for coords in row['divider_segments']:line(coords,'#ffc928')
                if row['y_range']:
                    yy=int(sum(row['y_range'])/2*height/1000)
                    cd.rectangle((8,yy-17,218,yy+17),fill='#162533')
                    cd.text((14,yy-14),f"L{i}: {row['vertical_dividers']} div / {row['separate_compartments']} cells",font=font(19),fill='white')
                    if side=='render' and any(h['order']==i for h in hypotheses):
                        cd.rectangle((2,int(row['y_range'][0]*height/1000),width-3,int(row['y_range'][1]*height/1000)),outline='#ee7768',width=3)
        d.text((x,107),side.title()+' / raw model lines',font=font(27),fill='#15334b');canvas.paste(crop,(x,150))
    x=1606
    d.text((x,107),'Post-hoc audit / not a model correction',font=font(25),fill='#15334b')
    # Only an audit crop from prior frozen U3/U4 windows, read after both model returns.
    audit=ref.crop(tuple(posthoc['audit_bbox']));audit=audit.resize((750,294),Image.Resampling.LANCZOS)
    canvas.paste(audit,(x,150))
    lines=['Reference level 2: possible missed divider',
           'Raw model: 0 dividers, certainty=clear.',
           'A dark structural seam is visible near the left',
           'quarter; prior frozen cells also suggest a split.',
           'Audit candidate only; original answer unchanged.',
           '',
           'Render geometry (saved metadata only)',
           f"{len(geometry.get('shelves',[]))} broad horizontal slab candidates verified.",
           'Each: 1.65 m wide x 0.522 m deep x 0.055 m.',
           f"Interior full-depth vertical slab candidates: {len(geometry.get('internal_vertical_slab_candidates',[]))}.",
           'Names alone were not used as proof.',
           'Shallow/oblique/merged geometry may evade query.',
           'No new render; no claim of exact visibility GT.']
    for i,line in enumerate(lines):d.text((x,467+i*34),line,font=font(23),fill='#33495d')
    y=1032
    lines=['Level      Reference (dividers / cells)     Render (dividers / cells)        Frozen VLM-only comparison',
           *[f"{r['order']:<11}{r['fields']['vertical_dividers']['reference']} / {r['fields']['separate_compartments']['reference']}                                      {r['fields']['vertical_dividers']['render']} / {r['fields']['separate_compartments']['render']}                               {r['status']}" for r in comparison.get('rows',[])],
           'Both report 4 visible levels + 3 internal shelves. Render marks every row partial: left boundary cropped.',
           'VLM-only: no accepted per-level mismatch; the frozen gate retains Unknown for partial observations.',
           'Separate metadata-assisted hypotheses: levels '+', '.join(str(h['order']) for h in hypotheses)+' -> candidate_structural_layout_mismatch.',
           'Red row outlines mark those hypotheses, not a predicted missing-divider location or a confirmed 3D error.',
           'Reference level 2 miss remains visible above; the experiment did not detect every structural difference.',
           'Old Group yes/yes/yes did not encode dividers. New evidence can expose split-versus-continuous organization.',
           'Historical camera differs; same fixed R3, no relocation. All reviewed=false / provisional/debug; formal Spatial=N/A.',
           'Exactly 2 single-image gpt-6-sol subagents, serial, fork_turns=none; no Ofox, Blender, GPU, SAM or SLIC.']
    for i,line in enumerate(lines):d.text((24,y+i*42),line,font=font(24),fill='#15334b')
    canvas.save(output/'comparison.png')


def report_result(source_output,destination):
    pending=read(source_output/'verification_results.json');protocol=pending['protocol'];work=Path(protocol['work'])
    if protocol!=read(work/'frozen_plan.json'):raise ValueError('Frozen plan changed')
    packets=read(work/'raw_observations.json')
    for side,p in packets.items():
        if p['parsed']!=parse_topology(p['raw_answer']):raise ValueError('Invalid or modified recorded response')
    comparison=compare_topology(packets['reference']['parsed'],packets['render']['parsed'])
    geometry=geometry_audit(ROOT/'results/blender_scene_graph_audit_bw0074/scene_graph.json')
    hypotheses=assisted_hypotheses(packets['reference']['parsed'],packets['render']['parsed'],geometry)
    # The old units are used ONLY after both independent observations, for a separately labeled audit.
    old_distribution=read(ROOT/'results/group_spatial_distribution_bw0074/distribution.json')
    band=next(b for b in old_distribution['reference']['bands'] if b['id']=='F2')
    prior_cells=[u['unit_id'] for u in old_distribution['reference']['units'] if u['band_id']=='F2']
    posthoc=dict(reference_level=2,audit_bbox=band['bbox'],prior_reference_unit_ids=prior_cells,
        status='possible_reference_divider_false_negative',source='Coordinator post-hoc static audit after both model responses',
        observation='Reference second display band shows a dark vertical structural seam near left quarter; model reported zero clear dividers. Needs independent human review.',
        original_response_changed=False,independent_gt=False,reviewed=False)
    old=read(ROOT/'results/records_group_verification_bw0074/verification_results.json')
    usage={}
    for packet in packets.values():
        for key,value in (packet['usage'] or {}).items():usage[key]=usage.get(key,0)+value
    state=read(work/'source_state.json');unchanged=all(Path(p).stat().st_size==s['size'] and Path(p).stat().st_mtime_ns==s['mtime_ns'] for p,s in state.items())
    requests=read(work/'frozen_agent_inputs.json');staged=read(work/'staged_inputs.json')
    same_prompt=requests['reference']['message'].replace(staged['reference']['path'],'{IMAGE}')==requests['render']['message'].replace(staged['render']['path'],'{IMAGE}')
    if not unchanged or not same_prompt:raise ValueError('Source state or symmetric prompt changed')
    result=dict(protocol=protocol,comparison= comparison,geometry_assisted_hypotheses=hypotheses,geometry_audit=geometry,
        reference_posthoc_audit=posthoc,baseline_group_comparison=old['comparison'],
        execution=dict(backend='Codex Subagent',model='gpt-6-sol',sessions=2,serial=True,automatic_retries=0,ofox=0,blender=0,gpu=0,
            session_seconds=sum(p['duration_seconds'] or 0 for p in packets.values()),token_usage=usage,
            token_scope='Whole verifier sessions incl. platform/image/tool context; parent excluded. Cached input is a subset of input; reasoning is a subset of output.',actual_currency_cost=None),
        isolation=dict(fork_turns='none',one_image_read_per_session=all(p['read_audit_passed'] for p in packets.values()),
            prompts_identical_except_anonymous_path=same_prompt,expected_answers_provided=False,shared_filesystem_not_hard_isolated=True,
            parent_history_not_forwarded=True,received_task_text_independently_readable=False,strict_blind_test=False),
        checks=dict(source_files_unchanged=unchanged,raw_response_schema_valid=True,coordinate_bounds_valid=True,offline_unit_tests=5),
        reviewed=False,usage='provisional/debug',scorable=False,formal_energy=None)
    if destination!=source_output:destination.mkdir(parents=True,exist_ok=False)
    for filename in ('topology_reference.json','topology_render.json','topology_comparison.json','comparison.png','report.md'):
        if (destination/filename).exists():raise ValueError('Refuse to overwrite completed artifacts')
    for side in ('reference','render'):
        save(destination/f'topology_{side}.json',dict(backend='Codex Subagent',model='gpt-6-sol',observation=packets[side],
            topology=packets[side]['parsed']['topology'],reviewed=False,usage='provisional/debug',scorable=False))
    save(destination/'topology_comparison.json',result)
    draw_result(destination,protocol,packets,comparison,hypotheses,geometry,posthoc)
    write_report(destination,result)
    if destination==source_output:
        pending.update(status='completed',result='topology_comparison.json',real_verifier_sessions=2)
        (source_output/'verification_results.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(output=str(destination),primary_status=comparison['status'],hypotheses=hypotheses,execution=result['execution']),ensure_ascii=False))


def write_report(output,result):
    p=result['protocol'];e=result['execution'];rows=result['comparison']['rows']
    table='\n'.join(f"| {r['order']} | {r['fields']['vertical_dividers']['reference']} / {r['fields']['separate_compartments']['reference']} | {r['fields']['vertical_dividers']['render']} / {r['fields']['separate_compartments']['render']} | {r['status']} |" for r in rows)
    text=f'''# bw_0074/R3 Structural Layout 自动提取最小实验

结论：独立提取确实产生了隔板组织差异信号，但**冻结的纯 VLM 比较保留 Unknown**，因为 Render 四层都返回 partial。场景几何辅助检查额外支持第 1、3 层的 `candidate_structural_layout_mismatch` 假设；这组补充假设属于事后探索，没有覆盖或提升模型原始 certainty。Reference 第二层疑似漏检，不能宣称本轮完整识别所有结构差异。

全部 reviewed=false、provisional/debug；没有正式 Spatial 分数或第六类 Energy。未改变 Region、ROI、历史回答或评分权重。

## 实际输入和隔离

复用原 Reference、历史 Render 和固定 R3 bbox {p['bbox']}。Render 只按既有等比例全帧缩放及留边规则映射到 Reference 坐标，没有配准或移动 ROI。每个子 Agent 仅收到一张匿名 PNG：左为一侧完整原图及橙框，右为同坐标 2 倍放大的 R3。原图没有另一侧或预期标签，也没有 U1–U7、历史答案、几何对象信息或本轮预期结论。

使用用户指定的 System/User 原文，另冻结统一输出/坐标定义：自上而下可见开口层带，内部竖隔板不含外框；水平线只标内部层板；粗坐标为目标裁剪图 0–1000。Prompt 没有给示例数量。匿名实际输入图、完整请求文本、协议和原始会话输出位于 `{p['work']}`；topology_reference/render.json 保存模型标识、原始回答和工具读取审计。

严格串行 2 个新 gpt-6-sol 子 Agent，各一次、不重试，fork_turns=none。日志均显示只读取各自一张匿名图，模型标识核对通过。共享文件系统并无强制单文件隔离，持久日志也不能独立明文重读父任务正文；主 Agent 已知历史结构，因此不能声称严格盲测或固定 API 等价。没有追加验证。

## 模型实际结构与冻结比较

两侧均报告从最上到最下可见开口完整，均为 4 层和 3 条内部水平层板。这个计数来自本轮独立结构识别，**不是 U1–U7 与三个唱片高度组的 7−3**。Reference 行 certainty 均为 clear；Render 均为 partial，原因原文为“左侧边界超出目标裁剪图，无法确认各层开口向左延伸的范围。”

| 自上而下层次 | Reference 隔板 / 柜格 | Render 隔板 / 柜格 | 冻结纯 VLM 比较 |
| --- | --- | --- | --- |
{table}

程序只在双方确认垂直范围、开口层数相等时按上到下顺序比较，未建立逐柜格 ID 匹配，也未重排空间位置。对 clear 观测中明确不同的隔板/柜格数量，预先测试的规则返回 candidate_structural_layout_mismatch；对 partial/unknown 仍弃权。因此这轮纯 VLM 实测没有通过可靠性条件的逐层差异，不能拿受控单元测试通过冒充真实自动检测成功。每层隔板变化与柜格变化是同一结构事件，不重复施加惩罚。

## Scene Graph 辅助证据与额外候选

只读取既有 scene_graph.json。名称用于检索候选后，实际检查了三块宽 1.65 m、深 0.522 m、厚 0.055 m 的独立 Mesh：均为 8 顶点/6 面的薄水平立方体，无 modifier、未 hide_render，已有包围盒投影与目标位置相符。它们位于约 z=1.42、1.87、2.33 m；上下外边界由既存桌高层板与顶冠几何限定，形成四个粗开口区间。投影只代表包围范围，不是可见 Mask。

对全部已存 Mesh AABB 查询柜体内部的薄竖板：x 位置在长层板内部、厚度不超过两倍层板厚度、深度至少为层板的 80%、前后覆盖到层板深度容差内、并与开口 z 区间相交。**找到 0 个候选**。唱片薄片因尺寸/深度和位置条件不会被当作这些全深隔板；柜体左右框不算内部隔板。没有以对象名称或对象数量直接代替柜格。

在“独立全深薄板表示、粗开口顺序可比”的条件下，第 1、3 层 Reference 明确隔板观测与生成侧连续长层板构成两个 **场景几何辅助差异候选**。这项补充分析在模型回答后完成，保存为 post_hoc_scene_graph_assisted_hypothesis；原纯 VLM Unknown 和 Render partial 原样保留。

该查询不是完备的隔板检测器：浅隔板、斜板、合并 Mesh、未评估 modifier 几何可能遗漏；不把“查询为空”升级为确认三维缺失。历史读取器兼容性、像素可见性也未在本轮重新认证。因此这些是可审核的结构布局不一致候选，不是 Reconstruction Error GT。

## 提取失败与可视化

Reference 第二层模型输出 0 隔板、1 柜格且 clear；事后静态检查与既有 U3/U4 候选提示该层左侧约四分之一处可能有竖向结构隔板。图中单独放大，未把该位置加入模型预测线，也未将答案修正为 1/2。此为待独立人工审核的漏检候选；没有用旧单元作为模型输入或预期标签。

comparison.png 的青线/黄线直接来自实际模型输出，未修补。Render 红色层范围只表示几何辅助的候选差异，不虚构缺失隔板在 Render 中的精确位置。完整定位坐标、未知说明和原始回答均保留。

## 相比唱片 Group 验证增加什么

旧方法回答集合存在、多柜格、主要竖放，三个结果 satisfied，但不描述柜体本身。新结构证据可表达每层是否左右分隔、隔板是否错层，以及“分开的柜格变为连续开口”的候选变化，不需逐张唱片或逐柜格匹配。

本轮实际新增的是两条带条件的几何辅助布局候选及一条 Reference 提取失败候选；没有证明稳定检出率，也没有自动确认所有结构缺失。历史相机不同、固定 R3 左缘裁切导致 Render 弃权；柜内遮挡与隔板/封套边缘混淆影响 Reference。相同行数不能单独证明物理层架身份相同。

值得继续作为 Spatial 的辅助候选证据研究，但目前不能直接纳入正式惩罚。下一步需要独立人工审核结构线与层带可比性，验证同视角已知有/无隔板的正负对照，并校准 partial 与 unknown 的判定；本轮不执行这些扩展。

## 执行、测试与复现

2 个真实子 Agent 会话共 {e['session_seconds']:.3f} 秒。Token：{json.dumps(e['token_usage'],ensure_ascii=False)}。统计包含验证子会话的平台上下文、图像工具阶段，排除主 Agent；缓存包含于输入、推理包含于输出，不重复相加。实际货币成本未知。Ofox/Blender/GPU/SAM/SLIC 调用为 0。

5 项离线单元测试通过：清晰合并产生候选、部分可见弃权且不强制对齐、非法坐标/重复 ID 拒绝、响应失败不伪造零误差，以及几何辅助假设不改变原 VLM partial/Unknown。前 4 项在模型运行前完成，第 5 项用于事后辅助通路的隔离检查。初次模块式测试调用因 tests 不是包而失败，改用 discover 后通过；不是模型或指标测试失败。实际两个响应 Schema/坐标合法；源文件大小与 mtime 检查未变。

只重放已有回答并画到新目录，不调用模型：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/structural_layout_pilot.py --stage report --output results/structural_layout_bw0074 --destination results/structural_layout_bw0074_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_structural_layout_pilot.py'
```

输出为 PNG、三个 topology JSON 和本报告；准备阶段协议保留在 verification_results.json。无 HTML、无历史结果修改、无 Git 提交。完成后停止。
'''
    (output/'report.md').write_text(text)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','collect','report'],required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path)
    args=parser.parse_args()
    if args.stage=='prepare':prepare(args.output.resolve())
    elif args.stage=='collect':collect(args.output.resolve(),parse=parse_topology)
    else:report_result(args.output.resolve(),args.destination.resolve() if args.destination else args.output.resolve())
