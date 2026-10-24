"""Offline proposition-level comparability; synthetic images test logic, not vision."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.records_group_verification import read,save,font
from scripts.region_real_render import fit_render
from scripts.structural_layout_pilot import parse_topology,geometry_audit


def compare_local(claim):
    """Each proposition abstains independently; partial geometry stays conditional."""
    ref,ren=claim['reference'],claim['render'];mapping=claim['correspondence']
    status='unknown';support='insufficient';reason='Local observation or correspondence unavailable'
    if ref.get('conflict'):
        reason='Reference extraction conflicts with an unreviewed audit candidate; do not accept absent/absent agreement'
    elif ref['visibility']!='visible' or ref['value']=='unknown':
        reason='Reference proposition is not sufficiently observable'
    elif mapping=='unknown':reason='Exact counterpart location is not established'
    elif ren['visibility']=='cropped':reason='Required local support is cropped; geometry cannot turn unobservability into a visual mismatch'
    elif ren['visibility']=='visible' and ren['value']!='unknown':
        status='structure_consistent' if ref['value']==ren['value'] else 'candidate_structural_layout_mismatch'
        support='local_observations';reason='Compatible local proposition with visible support on both sides'
    elif (mapping=='coarse_ordered_opening' and ren['visibility']=='partial' and ref['value']=='present'
          and claim.get('geometry',{}).get('kind')=='conditional_no_internal_slab_candidates'):
        status='candidate_structural_layout_mismatch';support='conditional_geometry'
        reason='Retain a coarse opening hypothesis under explicit simple-panel geometry assumptions; exact location and visual absence remain unknown'
    return dict(status=status,support=support,reason=reason,image_only_status='unknown' if support=='conditional_geometry' else status,
                reviewed=False,scorable=False,formal_energy=None)


def slab_query(box,geometry):
    """Replay the previous AABB predicate exactly, including its representation limits."""
    p,q=np.asarray(box,float);d=q-p;cx=(p[0]+q[0])/2
    bay=geometry['bay_bounds'];t=geometry['query']['thickness_tolerance_m'];depth=bay['y'][1]-bay['y'][0]
    return bool(bay['x'][0]+t<cx<bay['x'][1]-t and d[0]<=2*t and d[1]>=.8*depth and d[2]>2*t
        and p[1]<=bay['y'][0]+t and q[1]>=bay['y'][1]-t and q[2]>bay['z'][0] and p[2]<bay['z'][1])


def geometry_probes(geometry):
    bay=geometry['bay_bounds'];cx=sum(bay['x'])/2;cy=sum(bay['y'])/2;cz=2.10;depth=bay['y'][1]-bay['y'][0]
    def box(width,dep,height):return [[cx-width/2,cy-dep/2,cz-height/2],[cx+width/2,cy+dep/2,cz+height/2]]
    standard=box(.04,depth,.35);thin=box(.002,depth,.35)
    shallow=box(.002,.05,.35);shallow[0][1]=bay['y'][0];shallow[1][1]=bay['y'][0]+.05
    merged=[[bay['x'][0],bay['y'][0],1.8975],[bay['x'][1],bay['y'][1],2.3025]]
    theta=np.deg2rad(25);tilt=box(.02*np.cos(theta)+.35*np.sin(theta),depth,.35*np.cos(theta)+.02*np.sin(theta))
    outer=deepcopy(standard);outer[0][0]=bay['x'][0]-.02;outer[1][0]=bay['x'][0]+.02
    cases=[('isolated_panel',standard,True,'Simple full-depth isolated panel is retained'),
           ('thin_full_depth_panel',thin,True,'Thickness alone is not rejected; pixel visibility may still be poor'),
           ('thin_shallow_panel',shallow,False,'A visible shallow divider can fail the 80% depth/front-back rules'),
           ('panel_merged_with_shelf',merged,False,'A merged object AABB is wide, hiding internal partition topology'),
           ('tilted_panel_25deg',tilt,False,'World AABB becomes too wide despite the source panel being thin'),
           ('outer_frame',outer,False,'Outer frame is not an internal divider'),
           ('same_shape_nonstructural_insert',standard,True,'Geometry-only rule can also accept a nonstructural insert of the same shape')]
    return [dict(id=name,synthetic=True,aabb=b,query_hit=slab_query(b,geometry),construction_expected_query_hit=expected,
                 interpretation=note,reviewed=False) for name,b,expected,note in cases]


def synthetic_controls(output):
    """Three views of one fixed front-orthographic fixture; no detector/VLM."""
    size=(640,480);target=[313,80,327,400];viewport=[160,40,580,440]
    source=Image.new('RGB',size,'#e9e5dc');d=ImageDraw.Draw(source)
    d.rectangle((100,70,540,410),fill='#ded4c2',outline='#183d54',width=18)
    positive=source.copy();ImageDraw.Draw(positive).rectangle(tuple(target),fill='#183d54')
    cases=[]
    for name,image,window,exists,expected in [('present',positive,viewport,True,'structure_consistent'),
        ('absent',source,viewport,False,'candidate_structural_layout_mismatch'),
        ('cropped',positive,[360,40,580,440],True,'unknown')]:
        visible=window[0]<=target[0] and window[1]<=target[1] and window[2]>=target[2] and window[3]>=target[3]
        claim=dict(id='synthetic_'+name,synthetic=True,correspondence='exact_oracle',
            reference=dict(value='present',visibility='visible',conflict=False,source='construction_oracle'),
            render=dict(value=('present' if exists else 'absent') if visible else 'unknown',visibility='visible' if visible else 'cropped',
                source='construction_and_viewport_oracle',global_left_boundary_cropped=True),geometry=dict(kind='not_used'))
        result=compare_local(claim)
        assert result['status']==expected
        displayed=Image.new('RGB',size,'#aab3bd');displayed.paste(image.crop(tuple(window)),tuple(window[:2]))
        ImageDraw.Draw(displayed).rectangle((window[0],window[1],window[2]-1,window[3]-1),outline='#e48a23',width=2)
        path=output/('synthetic_'+name+'.png');displayed.save(path)
        cases.append(dict(id=name,image=path.name,synthetic=True,camera='fixed_front_orthographic_2d',canvas=list(size),
            target_bbox=target,viewport=window,construction_divider_exists=exists,oracle_local_observable=visible,
            fixed_other_geometry_and_lighting=True,construction_expected=expected,claim=claim,result=result,
            labels_source='construction_expected, not human-reviewed GT',visual_recognition_tested=False,reviewed=False))
    return cases


def reference_review(output,reference,previous):
    audit=previous['reference_posthoc_audit'];row_box=audit['audit_bbox']
    old=read(ROOT/'results/group_spatial_distribution_bw0074/distribution.json')
    cells=[u for u in old['reference']['units'] if u['unit_id'] in audit['prior_reference_unit_ids']]
    cells.sort(key=lambda u:u['bbox_xyxy'][0]);seam=[cells[0]['bbox_xyxy'][2],cells[1]['bbox_xyxy'][0]]
    center=sum(seam)/2;zoom=[max(0,int(center)-35),max(0,row_box[1]-10),min(reference.width,int(center)+35),min(reference.height,row_box[3]+10)]
    canvas=Image.new('RGB',(1660,860),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((22,18),'Reference level 2 | review candidate ONLY | human status: unreviewed',font=font(29),fill='#17354d')
    row=reference.crop(tuple(row_box)).resize((1100,277),Image.Resampling.LANCZOS);canvas.paste(row,(22,80))
    detail=reference.crop(tuple(zoom));detail=detail.resize((390,624),Image.Resampling.LANCZOS);canvas.paste(detail,(1210,80))
    lines=['Original VLM: 0 internal dividers; 1 compartment; certainty=clear.',
        'Historical U3/U4 draft suggests a seam near the left quarter; it is not GT.',
        'Inspect whether the dark strip:',
        ' - connects the upper and lower shelf boards;',
        ' - has consistent cabinet finish / thickness;',
        ' - separates openings rather than following a book or sleeve edge.',
        'Do not count an outer frame, sleeve spine, shadow or decoration as a divider.',
        'Raw VLM answer is unchanged. No automatic human approval or replacement label.',
        'Review options: internal divider / content edge / outer frame / uncertain.']
    for i,line in enumerate(lines):d.text((22,402+i*43),line,font=font(23),fill='#33495d')
    canvas.save(output/'reference_row2_review.png')
    return dict(status='unreviewed',row_crop_xyxy=row_box,zoom_crop_xyxy=zoom,
        crop_basis='Post-hoc old U3/U4 boundary gap for audit only; not a new model prediction',
        possible_internal_divider=None,reviewed=False,original_model_answer_changed=False)


def build_claims(a,b,geometry,previous):
    claims=[]
    def add(id,description,reference,render,correspondence,geo,**extra):
        claim=dict(id=id,description=description,reference=reference,render=render,correspondence=correspondence,geometry=geo,
                   reviewed=False,usage='provisional/debug',**extra)
        claim['result']=compare_local(claim);claims.append(claim)
    ordered=(a['top_to_bottom_complete']==b['top_to_bottom_complete']=='yes' and len(a['rows'])==len(b['rows']))
    for i,(line_a,line_b) in enumerate(zip(a['horizontal_shelves'],b['horizontal_shelves']),1):
        add('H'+str(i),'第 '+str(i)+' 条内部水平层板在相邻开口间可见',
            dict(value='present',visibility='visible',source='saved_predicted_internal_shelf_line',line=line_a,conflict=False),
            dict(value='present',visibility='visible',source='saved_predicted_internal_shelf_line',line=line_b,
                 row_level_partial_does_not_negate_this_line=True),
            'ordered_internal_boundary' if ordered and len(a['horizontal_shelves'])==len(b['horizontal_shelves']) else 'unknown',
            dict(kind='positive_horizontal_slab_support',source=geometry['source']),
            semantic_discriminator='Internal shelf between openings; excludes top/bottom outer frame and content edges',
            exact_metric_alignment=False)
    for i,row in enumerate(a['rows'],1):
        if row['vertical_dividers']==0:continue
        other=b['rows'][i-1] if ordered else None
        add('V'+str(i),'第 '+str(i)+' 个粗开口内存在将左右分开的内部隔板',
            dict(value='present',visibility='visible' if row['certainty']=='clear' else 'unknown',source='saved_reference_divider_prediction',
                 segments=row['divider_segments'],conflict=False),
            dict(value='unknown',reported_count=other['vertical_dividers'] if other else 'unknown',visibility='partial',
                 visible_subscope='interior of ordered opening partially visible; left outer boundary cropped',
                 exact_counterpart_visibility='unknown',exact_counterpart_position='unknown',source='saved_render_partial_answer'),
            'coarse_ordered_opening' if ordered else 'unknown',
            dict(kind='conditional_no_internal_slab_candidates' if geometry['status']=='conditional_geometry_support' and not geometry['internal_vertical_slab_candidates'] else 'unavailable',
                 scope='Simple full-depth isolated vertical panels only; no proof of general absence',source=geometry['source']),
            semantic_discriminator='Reference segment declared as an internal divider; never infer identity from thin vertical edges alone',
            existing_hypothesis_reorganized=True)
    conflict=previous['reference_posthoc_audit']
    add('V2_review','第二层疑似内部隔板：参考提取存在冲突',
        dict(value='unknown',visibility='unknown',source='raw zero-divider answer plus posthoc audit conflict',conflict=True,
             original_model_value='absent',human_review='unreviewed',audit=conflict),
        dict(value='unknown',visibility='partial',source='saved_render_partial_answer',exact_counterpart_visibility='unknown'),
        'coarse_ordered_opening',dict(kind='conditional_no_internal_slab_candidates',source=geometry['source']))
    add('frame_left','固定 R3 内的完整左外边框是否可比较',
        dict(value='present',visibility='visible',source='reference context candidate',conflict=False),
        dict(value='unknown',visibility='cropped',source='original Render unknown explanation; full image retained separately'),
        'coarse_ordered_opening',dict(kind='not_used'),semantic_discriminator='Outer frame; explicitly excluded from internal-divider count')
    add('exact_counts','整层完整独立柜格数量是否相同',
        dict(value='unknown',visibility='unknown',source='Reference second-level conflict prevents complete inventory',conflict=True),
        dict(value='unknown',visibility='partial',source='left boundary cropped; internal/outer scope incomplete'),
        'unknown',dict(kind='not_used'),no_count_subtraction=True)
    return claims


def draw_comparison(output,reference,rendered,protocol,a,b,claims,controls):
    canvas=Image.new('RGB',(2040,1930),'#f3f5f8');d=ImageDraw.Draw(canvas)
    d.text((24,14),'bw_0074/R3 | Local structural comparability | reviewed=false / provisional/debug',font=font(28),fill='#17354d')
    for x,name,image,topo in [(24,'Reference / saved model lines',reference,a),(702,'Render / same fixed ROI',rendered,b)]:
        crop=image.crop(tuple(protocol['bbox'])).resize((630,709),Image.Resampling.LANCZOS);cd=ImageDraw.Draw(crop)
        for line in topo['horizontal_shelves']:
            cd.line((line[0]*.63,line[1]*.709,line[2]*.63,line[3]*.709),fill='#28cde5',width=4)
        for row in topo['rows']:
            for line in row['divider_segments']:cd.line((line[0]*.63,line[1]*.709,line[2]*.63,line[3]*.709),fill='#ffc72e',width=4)
        d.text((x,67),name,font=font(25),fill='#17354d');canvas.paste(crop,(x,110))
    lines=['Per-proposition result',
        'H1 / H2 / H3: structure_consistent',
        'Both sides report visible shelf segments;',
        'left cropping does not erase this evidence.',
        '', 'V1 / V3: conditional mismatch candidates',
        'Existing geometry hypotheses retained.',
        'Exact counterpart position is UNKNOWN.',
        'Image-only absence remains UNKNOWN.',
        '', 'V2: UNKNOWN / reference audit conflict',
        'Left outer frame: UNKNOWN inside ROI',
        'Whole compartment count: UNKNOWN',
        '', 'No entire-region Unknown gate.',
        'No formal score; no raw answer correction.']
    for i,line in enumerate(lines):d.text((1368,95+i*39),line,font=font(23),fill='#33495d')
    d.text((24,852),'SYNTHETIC: identical front-orthographic view; Oracle positions/visibility only. No VLM or detector evaluated.',font=font(25),fill='#17354d')
    for i,c in enumerate(controls):
        x=24+i*674;im=Image.open(output/c['image']);canvas.paste(im,(x,905))
        d.text((x,1395),c['id']+' -> '+c['result']['status'],font=font(21),fill='#17354d')
    lines=['Orange = observation window. The left outer frame is cropped in ALL synthetic cases.',
        'A/B change only the internal divider. C uses A geometry but crops the target divider; camera/pixel coordinates stay fixed.',
        'Present: consistent. Missing at a visible known position: candidate mismatch. Target cropped: Unknown.',
        'Reference level 2 review is saved separately: reference_row2_review.png (unreviewed; no corrected GT).',
        'Geometry probes: thin full-depth panel retained; shallow, merged and tilted panels can evade the previous AABB query.',
        'The same shape can also be nonstructural: no geometry-only semantic identity proof.',
        '0 new VLM / subagent / Ofox / Blender / GPU calls. All historical evidence remains unchanged.']
    for i,line in enumerate(lines):d.text((24,1460+i*47),line,font=font(24),fill='#33495d')
    canvas.save(output/'comparison.png')


def run(output):
    source=ROOT/'results/structural_layout_bw0074';previous=read(source/'topology_comparison.json');protocol=previous['protocol']
    observations={side:read(source/f'topology_{side}.json') for side in ('reference','render')}
    for side,obs in observations.items():
        assert parse_topology(obs['observation']['raw_answer'])['topology']==obs['topology']
    graph_path=ROOT/'results/blender_scene_graph_audit_bw0074/scene_graph.json'
    files={p for directory in (source,graph_path.parent,ROOT/'results/group_spatial_distribution_bw0074') for p in directory.rglob('*') if p.is_file()}
    files.update(Path(protocol[k]) for k in ('reference_rgb','render_rgb','roi'))
    state={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in files}
    geometry=geometry_audit(graph_path);assert geometry==previous['geometry_audit']
    graph=read(graph_path)
    hits=[o['id'] for o in graph['objects'] if o['type']=='MESH' and o.get('world_aabb') and slab_query(o['world_aabb'],geometry)]
    assert hits==[p['object_id'] for p in geometry['internal_vertical_slab_candidates']]
    probes=geometry_probes(geometry);assert all(p['query_hit']==p['construction_expected_query_hit'] for p in probes)
    a,b=(observations[s]['topology'] for s in ('reference','render'))
    claims=build_claims(a,b,geometry,previous)
    reference=Image.open(protocol['reference_rgb']).convert('RGB');rgb,_,transform=fit_render(Image.open(protocol['render_rgb']),reference.size)
    assert transform==protocol['transform']
    output.mkdir(parents=True,exist_ok=False)
    controls=synthetic_controls(output);review=reference_review(output,reference,previous)
    draw_comparison(output,reference,Image.fromarray(rgb),protocol,a,b,claims,controls)
    unchanged=all((p.stat().st_size,p.stat().st_mtime_ns)==v for p,v in state.items());assert unchanged
    result=dict(scene='bw_0074',region_id='R3',reviewed=False,usage='provisional/debug',scorable=False,formal_energy=None,
        source_directory=str(source),protocol=protocol,original_raw_answers={side:obs['observation']['raw_answer'] for side,obs in observations.items()},
        original_topologies={side:obs['topology'] for side,obs in observations.items()},original_comparison=previous['comparison'],
        local_claims=claims,reference_row2_review=review,geometry_audit=geometry,geometry_query_risk_probes=probes,
        synthetic_controls=controls,synthetic_test_scope='Deterministic comparison with construction/viewport Oracle inputs; no visual recognition validation',
        execution=dict(vlm=0,subagents=0,ofox=0,blender=0,gpu=0),
        checks=dict(historical_sources_unchanged=unchanged,raw_answers_preserved=True,original_geometry_query_reproduced=True,
                    synthetic_comparison_cases_passed=len(controls),geometry_query_probe_cases_passed=len(probes)),
        conclusion='Three local shelf agreements survive; two existing geometry-conditional hypotheses retained; exact counterpart visibility, Reference conflict and full counts remain Unknown')
    save(output/'structural_evidence.json',result);write_report(output,result)
    print(json.dumps(dict(output=str(output),results={c['id']:c['result']['status'] for c in claims},checks=result['checks']),ensure_ascii=False))


def write_report(output,result):
    table='\n'.join(f"| {c['id']} | {c['description']} | {c['reference']['visibility']} | {c['render']['visibility']} | {c['result']['status']} / {c['result']['support']} |" for c in result['local_claims'])
    probes='\n'.join(f"| {p['id']} | {p['query_hit']} | {p['interpretation']} |" for p in result['geometry_query_risk_probes'])
    text=f'''# 结构证据局部可比较性：bw_0074/R3

**可以保留有依据的局部结果，避免整层 Partial 无条件阻塞所有条目；但不能凭拆分命题解决尚未建立的精确对应。** 本轮得到 3 条局部水平层板一致候选，保留 2 条已有的几何条件性结构差异假设；第二层冲突、左外框与完整柜格计数分别保持 Unknown。两条差异假设并非本轮新视觉识别成果，也未升级为确认缺失。

全部 reviewed=false、provisional/debug，正式 Spatial Energy=N/A。新增 VLM/子 Agent/Ofox/Blender/GPU 调用均为 0；未运行历史 Agent 代码、修改 ROI、历史证据、权重或正式公式。

## 逐命题比较

| ID | 命题 | Reference 可观察性 | Render 可观察性 | 结果 / 依据 |
| --- | --- | --- | --- | --- |
{table}

H1–H3 的证据分别是双方保存的内部水平层板线段，几何还提供对应的连续薄水平板支持。原先“左边界超出 ROI”影响完整层范围，但不否定这些已报告的可见线段。按粗开口顺序比较的是层板存在性，不计算精确位置误差，仍待人工审核。

V1/V3 保留 Reference 明确内部隔板候选及生成侧全深薄板查询为空的条件性证据。Render 对应粗开口部分可见，但**该参考隔板在 Render 的精确对应位置与可见性仍 Unknown**；不能把粗开口顺序当作精确位置匹配，也不能把旧 zero/partial 改成已确认 absent。故 image_only_status 仍 Unknown，仅在“孤立全深薄板几何表示、粗层次可比”的前提下保留 candidate_structural_layout_mismatch。没有从 Reference 像素坐标复制隔板位置到 Render。

V2 的原始“0 隔板、clear”与事后参考图审核候选冲突，不能因为 Render 也报 0 就判一致。冲突仅影响此命题，H2 等其他条目继续可用。精确柜格计数本就依赖完整边界与参考清单，因此继续 Unknown。左外框属于外边界命题，明确不计入内部隔板；其在固定 R3 中被裁切，不等于整个书柜不可观察。

这是诊断状态列表，不是总分，不把隔板存在与柜格合并当作两次独立惩罚，也不将 Unknown 填成零。

## Reference 第二层审核与漏检处理

单独的 `reference_row2_review.png` 同时展示第二层整段及疑似缝隙放大图。裁剪来自先前 U3/U4 候选边界，仅用于事后审核，未加入原始 VLM 线段。审核状态 unreviewed，`possible_internal_divider=null`。判断应检查该竖条是否连接上下层板、具有柜体厚度/饰面、确实分开开口；排除书脊、封套边缘、阴影和外框。不能由名称或颜色独立确定类别。

防止漏检造成不完整证据的最小机制是：保留原始自动提取结果、另记冲突/遗漏候选、暂停依赖完整清单的数量结论，并提出有定位的人工审核项。本轮没有自动纠正漏检，也没有证明未来提取器能发现所有遗漏。新方法不是将事后审核意见伪装为 Reference GT。

## 几何查询漏检风险：实际重放和合成探针

旧查询在所有现有 Mesh AABB 上重放，结果仍为 0 个内部全深薄竖板候选。以下 **synthetic AABB probes** 仅验证原查询的表示限制，不渲染、不修改历史场景：

| 探针 | 是否被原查询接纳 | 含义 |
| --- | --- | --- |
{probes}

要区分“薄”与“浅”：旧规则没有最小 x 厚度门槛，独立且全深的极薄隔板仍会被接纳；浅隔板因深度不足被漏掉。合并 Mesh 的整体 AABB 和倾斜后的宽 AABB 会掩盖分隔结构；相同形状的非结构插片反而可能被误收。故查询为空不能证明任意形式的隔板不存在，查询命中也不能证明其结构身份。旧模型的 certainty、名称、Mesh 数量都不是几何或类别 GT。

## 同相机 synthetic 最小对照

使用 Pillow 绘制一个安全、确定性的正视正交 2D 柜框，画布 640×480，目标隔板 bbox 为 [313,80,327,400]。没有 Blender、光照随机变化或历史 Agent 代码。A/B 的观察窗口相同 [160,40,580,440]，两者都裁掉左外框；A 有内部隔板，B 只移除该隔板。C 沿用 A 几何、同一相机和像素坐标，仅将观察窗口改为 [360,40,580,440]，使隔板被裁掉；灰区表示未观察范围，未重新缩放或对齐。

| Synthetic 情形 | 目标位置是否可观察 | 比较结果 |
| --- | --- | --- |
| present | 是；左外框仍被裁切 | structure_consistent |
| absent | 是；相同位置明确无隔板 | candidate_structural_layout_mismatch |
| cropped | 否；源场景仍有隔板 | unknown |

这验证了“局部可观察的缺失”与“目标不可观察”能被确定性比较区分，也验证外框裁切不会无条件影响可见的内部目标。输入位置与存在性来自构造 Oracle，不是模型检测；标签仅 construction_expected、reviewed=false。**三个对照通过不代表 VLM 能识别隔板、理解裁切或可靠预测可见性。**

## 限制与下一步条件

历史 Reference 相机未知，Render 相机不同，粗层带顺序不能自动建立精确局部对应；已有 Scene Graph 读取器与原 PNG 逐像素一致性也未认证。当前两条差异仍是已知表示假设下的候选。若要升级，需要独立审核 Reference 第二层及其他隔板、可靠的局部对应范围、遮挡/裁切判定，以及覆盖浅板、倾斜板、合并几何的结构证据。以后可在同相机真实渲染正负对照中测试实际视觉提取器；本轮不扩展。

## 运行与复现

3 个 synthetic 比较对照、7 个 AABB 查询探针均按构造预期通过；历史原始回答逐字保留，源文件大小/mtime 未改变。单元测试另覆盖局部 Unknown 不影响邻条、裁切不能被几何强行升级、参考冲突阻止虚假一致。

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/structural_local_comparability.py --output results/structural_local_comparability_bw0074_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_structural_local_comparability.py'
```

目标目录必须不存在。输出 comparison.png、structural_evidence.json、report.md，另有要求的 reference_row2_review.png 与三个标明 synthetic 的构造图；不生成 HTML。完成后停止。
'''
    (output/'report.md').write_text(text)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.output.resolve())
