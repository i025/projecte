"""M3.0: two audited historical pairs, real-answer replay, existing offline metrics.

No model/renderer/Agent entry point. Third-party RGB, masks and comparison PNGs
stay local. Publication is a separate, explicitly curated Git operation.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_offline import fit_render, run_manifest
from e_harness.benchmark_evidence import area_mask
from e_harness.verification_adapter import compare_answers, contract, import_subagent, replay
from scripts.kitchen_structural_transfer import parse_answers as kitchen_parse, compare as kitchen_compare
from scripts.structural_local_comparability import compare_local
from scripts.group_identity_context import parse_identity as identity_parse, compare_categories


def read(path):return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def rgb(path):
    with Image.open(path) as image:return np.asarray(image.convert('RGB'))


def candidate(row):
    """Schema-only adaptation: null means no optional Mask, never a valid empty Mask."""
    row=deepcopy(row)
    if row.get('reviewed') is True:raise ValueError('Frozen scope unexpectedly reviewed; do not downgrade silently')
    if row.get('mask','absent') is None:row.pop('mask')
    row.update(reviewed=False,reliability=0.)
    return row


def check_pair(scene):
    """Recheck task/run/export lineage and the old, content-independent transform."""
    old=ROOT/'results'/('region_first_real_render_bw0073' if scene=='bw_0073' else 'group_vlm_verification_bw0074')
    audit=read(old/'pair_audit.json')
    if audit['task_id']!=scene:raise ValueError('Wrong task audit')
    config=read(audit['run_config']);inputs=read(audit['input_metadata'])
    task=Path(config['task']['path']).resolve()
    if inputs['task_id']!=scene or task/'environment/inputs/input.json'!=Path(audit['input_metadata']).resolve():
        raise ValueError('Task/input mapping differs')
    if 'references/image_01.jpg' not in inputs['files']:raise ValueError('Reference not in Agent inputs')
    staged=task/'environment/inputs/references/image_01.jpg'
    if staged.read_bytes()!=Path(audit['reference_rgb']).read_bytes():raise ValueError('Agent reference differs')
    run=Path(audit['run_config']).parent
    export=[r for r in read(audit['artifact_manifest']) if r['source']=='/workspace/exports' and r['status']=='ok']
    if len(export)!=1 or (run/export[0]['destination']).resolve()!=Path(audit['render_rgb']).resolve().parent:
        raise ValueError('Run/export mapping differs')
    with Image.open(audit['reference_rgb']) as original:
        original=original.convert('RGB');native=list(original.size)
        if scene=='bw_0073':original.thumbnail((1536,1536),Image.Resampling.LANCZOS)
        reference=np.asarray(original)
    if not np.array_equal(reference,rgb(old/'reference.png')):raise ValueError('Frozen reference grid differs')
    with Image.open(audit['render_rgb']) as image:
        fitted,valid,transform=fit_render(image,reference.shape[1::-1])
    if transform!=audit['comparison_transform'] or not np.array_equal(fitted,rgb(old/'render.png')):
        raise ValueError('Historical full-frame fit differs; no alignment search allowed')
    return dict(scene=scene,run_id=audit['run_id'],reference_rgb=str(old/'reference.png'),
        render_rgb=audit['render_rgb'],native_reference=audit['reference_rgb'],
        native_reference_size=native,common_size=list(reference.shape[1::-1]),transform=transform,
        valid_pixels=int(valid.sum()),canvas_pixels=int(valid.size),
        audit_source=str(old/'pair_audit.json'),task_mapping_rechecked=True,
        reference_bytes_equal_agent_input=True,cached_reference_pixels_verified=True,
        fitted_render_pixels_verified=True,content_alignment=False,
        input_mode=inputs.get('input_mode','unknown; extra text not excluded'),
        reference_camera='unknown',historical_camera=True,png_blend_sync='unknown',
        reviewed=False,usage='provisional/debug')


def questions_from_prompt(user):
    return [m.group(1).strip() for line in user.splitlines()
        if (m:=re.match(r'\s*(?:Q)?[1-3][：:.]\s*(.+)',line))]


def replay_api(folder,pair):
    """Import actual raw API answers with their frozen contract, not a fresh CLI call."""
    protocol=read(folder/'protocol.json')
    frozen=contract(dict(system=protocol['system'],user=protocol['user'],schema=read(folder/'schema.json')))
    rows=read(folder/'verification_results.json')['results']
    texts=questions_from_prompt(protocol['user'])
    if len(texts)!=len(rows):raise ValueError('Cannot recover exact frozen question text')
    packets=[]
    for side in ('reference','render'):
        # Same-side saved RGB proves lineage; the actual submitted views had their recorded resize/outline.
        expected=rgb(pair['reference_rgb']) if side=='reference' else None
        if side=='render':
            with Image.open(pair['render_rgb']) as image:expected=fit_render(image,pair['common_size'])[0]
        if not np.array_equal(rgb(folder/(side+'.png')),expected):raise ValueError('Historical VQA RGB differs')
        old=read(folder/(side+'_answers.json'))
        if old.get('source')!='real_vlm' or old.get('response',{}).get('source')!='vlm_api':
            raise ValueError('Only explicitly recorded real API responses may enter this Replay')
        packet=replay(old['response']['raw_answer'],frozen,source_kind='historical_real',model=old['response']['model'])
        if old['status'] not in ('valid','partial'):packet['status']='unavailable'
        packet['metadata'].update(original_backend='Ofox API',source=str(folder/(side+'_answers.json')),
            historical_inputs=read(folder/'inputs.json'),new_cli_calls=0)
        packet['image_binding']=dict(source_rgb=pair['reference_rgb'] if side=='reference' else pair['render_rgb'],
            binding_scope='Rechecked historical source lineage, not the exact submitted PNG file')
        packets.append(packet)
    questions=[dict(evidence_id=pair['scene']+'_'+row['id'],field=row['id'],
        region_id=row['region_id'],group_id=row.get('group_id'),energy=row['energy'],
        question=text,provenance=dict(source=str(folder/'protocol.json'),kind='historical_frozen_question'))
        for row,text in zip(rows,texts)]
    result=compare_answers(*packets,questions,image_pair={k:pair[k] for k in ('reference_rgb','render_rgb')})
    if [r['status'] for r in result['results']]!=[r['status'] for r in rows]:
        raise ValueError('Recomputed verdict differs from historical record; audit rather than overwrite')
    return result


def extra_records(pair):
    old=read(ROOT/'results/records_group_verification_bw0074/verification_results.json')
    protocol=old['protocol']
    if Path(protocol['reference_rgb']).resolve()!=Path(ROOT/'results/vlm_direct_grounding_cross_scene/bw_0074/reference.png').resolve():
        raise ValueError('Records Reference lineage differs')
    audit=old['pair_audit']['source_audit']
    if audit['run_id']!=pair['run_id'] or Path(audit['render_rgb']).resolve()!=Path(pair['render_rgb']).resolve():
        raise ValueError('Records Run differs')
    if not np.array_equal(rgb(protocol['reference_rgb']),rgb(pair['reference_rgb'])):
        raise ValueError('Records Reference pixels differ from current pair')
    frozen=contract({k:protocol[k] for k in ('system','user','schema')})
    packets=[import_subagent(old['answers'][side],frozen) for side in ('reference','render')]
    questions=[dict(evidence_id='bw_0074_records_'+r['id'],field=r['id'],region_id='R3',
        group_id=r['group_id'],energy=r['energy'],question=r['question'],
        provenance=dict(source='results/records_group_verification_bw0074/verification_results.json',kind='historical_reference_frozen'))
        for r in old['comparison']]
    result=compare_answers(*packets,questions,image_pair={k:pair[k] for k in ('reference_rgb','render_rgb')})
    if [r['status'] for r in result['results']]!=[r['status'] for r in old['comparison']]:
        raise ValueError('Records verdict changed')
    return result,deepcopy(protocol['group'])


def structure(scene):
    if scene=='bw_0073':
        path=ROOT/'results/kitchen_structural_transfer_bw0073/structural_evidence.json';old=read(path)
        parsed={side:kitchen_parse(old['observations'][side]['raw_answer']) for side in ('reference','render')}
        rows=kitchen_compare(parsed['reference'],parsed['render'],old['reference_seed']['claims'])
        if rows!=old['comparison']:raise ValueError('Kitchen structural replay differs')
        return dict(source=str(path),rows=rows,reference_claims=old['reference_seed']['claims'],
            original_raw_answers={s:old['observations'][s]['raw_answer'] for s in parsed},
            backend='Historical Codex Subagent / gpt-6-sol; not new CLI',
            geometry='unavailable: no evaluated object-level geometry for this Run',
            reviewed=False,energy_contribution=False)
    path=ROOT/'results/structural_local_comparability_bw0074/structural_evidence.json';old=read(path)
    rows=[]
    for claim in old['local_claims']:
        result=compare_local(claim)
        if result!=claim['result']:raise ValueError('Local structural replay differs')
        rows.append(dict(id=claim['id'],description=claim['description'],reference=claim['reference'],
            render=claim['render'],result=result,reviewed=False,energy_contribution=False))
    return dict(source=str(path),rows=rows,reference_row2_review=old['reference_row2_review'],
        geometry=old['geometry_audit'],original_raw_answers=old['original_raw_answers'],
        evidence_origin='post-hoc local decomposition of saved independent VLM extraction; not new Reference GT',
        conditional_geometry_is_not_visual_absence=True,reviewed=False,energy_contribution=False)


def cached_perceptual(scene,evidence,pair):
    """Historical DINO values only when the exact fixed mask/grid matches. No inference."""
    if scene!='bw_0073':
        return dict(status='unavailable',reason='No cached DINO for this pair/ROI; no model run',energy_contribution=False)
    source=ROOT/'results/region_first_real_render_bw0073'
    old={r['id']:r for r in read(source/'metrics.json')['rows']}
    rows=[]
    for candidate_region,old_id in zip(evidence['regions'],('polygon_R2','box_R4')):
        support=(rgb(candidate_region['mask'])[:,:,0]/255 if 'mask' in candidate_region else
                 area_mask(candidate_region,pair['common_size'][::-1]))
        with Image.open(source/'measurement_rois'/(old_id+'.png')) as image:
            expected=np.asarray(image.convert('L'))>0
        if not np.array_equal(support>0,expected):
            rows.append(dict(id=candidate_region['id'],value=None,status='unavailable',reason='Cached ROI differs'))
            continue
        row=old[old_id]
        rows.append(dict(id=candidate_region['id'],historical_scope=old_id,value=row['perceptual'],
            input_fill_fraction=row['masked_crop_fill_fraction'],status='historical_diagnostic',
            source=str(source/'metrics.json'),reviewed=False,energy_contribution=False,
            limitation='Old crop/mask-black-fill DINO preprocessing, not comparable to a new extractor or official Energy'))
    return dict(status='historical_cache_only',rows=rows,new_model_calls=0,energy_contribution=False)


def prepare_case(scene,folder):
    pair=check_pair(scene)
    seed=read(ROOT/'results/group_level_evidence_pilot/reference_groups_frozen.json')
    group_case=next(c for c in seed['cases'] if c['scene_id']==scene)
    structural=structure(scene)
    previous=read(Path(structural['source']))['protocol']
    if (Path(previous['render_rgb']).resolve()!=Path(pair['render_rgb']).resolve()
            or previous['transform']!=pair['transform']
            or not np.array_equal(rgb(previous['reference_rgb']),rgb(pair['reference_rgb']))):
        raise ValueError('Structural evidence belongs to another RGB pair/transform')
    if scene=='bw_0073':
        api=ROOT/'results/region_atomic_vlm_r2_bw0073'
        reference_source=ROOT/'results/vlm_direct_grounding_bw0073/C_direct_polygon/evidence.json'
        original=read(reference_source)
        evidence=dict(image_size=original['image_size'],regions=[deepcopy(r) for r in original['regions'] if r['id']=='R2'],
            source_reference_document=str(reference_source))
        for row in evidence['regions']:
            row['mask']=str(ROOT/'results/vlm_direct_grounding_bw0073/C_direct_polygon'/row['mask'])
        # Only the old structural protocol supplies its frozen R4 scope.
        evidence['regions'].append(dict(id='R4',bbox=previous['bbox'],description=previous['region']['name'],
            metrics=['appearance','spatial','statistical','perceptual'],reviewed=False,reliability=0.))
        evidence['anchors']=deepcopy(group_case['optional_anchors'])
        groups=deepcopy(group_case['semantic_groups'])
        camera=read(Path(read(Path(pair['audit_source']))['camera_export_source']))
    else:
        api=ROOT/'results/group_vlm_verification_bw0074'
        region_plan=read(ROOT/'results/region_first_pilot_bw0074/vlm_plan.json')['regions']
        evidence=dict(image_size=pair['common_size'],anchors=[],regions=[dict(id=key,
            description=next(r['name'] for r in region_plan if r['id']==key),
            mask=str(ROOT/'results/coarse_evaluation_roi_bw0074/B2_edge_polygons'/(key+'.png')),
            metrics=['appearance','spatial','statistical','perceptual'],reviewed=False,reliability=0.) for key in ('R2','R3')])
        groups=[deepcopy(g) for g in group_case['semantic_groups'] if g['group_id']=='bw_0074_R2_books']
        graph=read(ROOT/'results/blender_scene_graph_audit_bw0074/scene_graph.json')
        if Path(graph['source_blend']).resolve().parent!=Path(pair['render_rgb']).resolve().parent:
            raise ValueError('Scene Graph belongs to another export directory')
        active=[c for c in graph['cameras'] if c['active']]
        if len(active)!=1:raise ValueError('No unambiguous saved active camera')
        camera=dict(camera=active[0],resolution=read(Path(pair['audit_source']))['render_native_size'],
            metadata_scope='Saved scene snapshot camera, exact historical PNG synchronization unknown',
            source='results/blender_scene_graph_audit_bw0074/scene_graph.json')
    for kind in ('regions','anchors'):evidence[kind]=[candidate(row) for row in evidence[kind]]
    evidence.update(reviewed=False,usage='provisional/debug',inventory_complete=False,
        selected_scope='R2/R4 kitchen or R2/R3 display; other Regions remain covered by Global/Dense',
        source='Existing frozen Reference-only candidates; no Agent object names used as Reference GT')
    folder.mkdir(parents=True,exist_ok=False)
    primary=replay_api(api,pair)
    additional=[]
    if scene=='bw_0074':
        result,group=extra_records(pair);additional.append(result);groups.append(group)
    save(folder/'reference_evidence.json',evidence)
    save(folder/'primary_verification.json',primary)
    save(folder/'groups.json',dict(groups=groups,additional_verification=additional,
        frozen_source='results/group_level_evidence_pilot/reference_groups_frozen.json',
        unverified_reference_evidence=[e for e in group_case['atomic_evidence']
            if e['id'].endswith(('chairs_frame','books_front_cover'))],
        reviewed=False,energy_contribution=False))
    save(folder/'structural_layout.json',structural)
    save(folder/'camera.json',camera)
    save(folder/'geometry.json',dict(status='unavailable',reason=(
        'No evaluated Geometry for this Run' if scene=='bw_0073' else
        'Existing Scene Graph/AABB audit is not evaluated collision/support Geometry; no reviewed triage'),
        source=None if scene=='bw_0073' else 'results/blender_scene_graph_audit_bw0074/scene_graph.json'))
    save(folder/'manifest.json',dict(reference_rgb=pair['reference_rgb'],render_rgb=pair['render_rgb'],
        reference_evidence='reference_evidence.json',render_metadata='camera.json',geometry='geometry.json',
        vlm_verification='primary_verification.json',diagnostics=dict(groups='groups.json',structural_layout='structural_layout.json'),
        coordinates=dict(convention='reference_pixel_xyxy',render_mapping='uniform_fit',
            basis='Exact previously recorded full-frame size fit; frozen Reference ROI, no camera/alignment optimization',
            expected_transform=pair['transform']),camera_comparability=dict(protocol='historical_camera',
            reference_camera='unknown',png_blend_sync='unknown'),evidence_category='historical_diagnostic',provenance=pair))
    report=run_manifest(folder/'manifest.json',folder/'evaluation')
    report['diagnostics']['cached_perceptual']=cached_perceptual(scene,evidence,pair)
    if report['formal_eligible'] or report['scene_validity']['camera_protocol']!='historical_camera':
        raise ValueError('Historical camera incorrectly qualified')
    return pair,report,primary,additional,structural


def audit_rows(scene,primary,additional,structural):
    rows=[]
    for batch in [primary,*additional]:
        for row in batch['results']:
            rows.append(dict(row,scene_id=scene,reference_evidence=row['question'],
                evidence_source='Historical frozen question; Reference answer is not GT',
                verifier_backend=batch['reference']['metadata'].get('original_backend',batch['reference']['backend']),
                picture_support='Same-side full context plus historical fixed ROI; current source pixels/fit rechecked',
                uncertainty='Historical camera differs; visibility and category confusion require review',
                human_review='unreviewed'))
    if scene=='bw_0073':
        claims={r['id']:r for r in structural['reference_claims']}
        for row in structural['rows']:
            rows.append(dict(evidence_id=scene+'_'+row['id'],scene_id=scene,region_id='R4',group_id=None,
                energy='spatial / structural_layout',reference_evidence=claims[row['id']]['claim'],
                question=claims[row['id']]['question'],reference_answer=row['effective_reference_answer'],
                render_answer=row['effective_render_answer'],status=row['status'],
                picture_support=dict(reference=row['reference']['data'],render=row['render']['data']),
                uncertainty='Visible facade organization only; no hidden mechanism GT or 3D correspondence',
                verifier_backend='Historical Codex Subagent',human_review='unreviewed',reviewed=False,value=None))
    else:
        for row in structural['rows']:
            rows.append(dict(evidence_id=scene+'_'+row['id'],scene_id=scene,region_id='R3',group_id=None,
                energy='spatial / structural_layout',reference_evidence=row['description'],question=row['description'],
                reference_answer=row['reference']['value'],render_answer=row['render']['value'],
                status=row['result']['status'],image_only_status=row['result']['image_only_status'],
                picture_support=dict(reference=row['reference'],render=row['render']),
                uncertainty=row['result']['reason'],verifier_backend='Historical local/post-hoc structural audit',
                human_review='unreviewed',reviewed=False,value=None))
    return rows


def write_summary(output,reports):
    lines=['# M3.0 Real-Agent Offline Evaluation Pilot','','**两组历史配对；reviewed:false、provisional/debug；没有正式 Benchmark 成绩。**','',
        '本轮只读复用 bw_0073 厨房和 bw_0074 陈列书柜的既有图片、冻结 ROI/Group 与真实回答。'
        '0 次新的 VLM/CLI/Subagent/Ofox 调用，0 次 Agent/Blender/GPU 执行。'
        '旧 API 与 Codex Subagent 结果分别标明来源，不与新的固定 CLI 实验混同。','',
        '| Scene | Semantic | Spatial image proxy | Appearance | Statistical image proxy | Perceptual | Independent Structural |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for scene,report in reports.items():
        value=lambda x:'N/A' if x is None else f'{x:.8f}'
        lines.append('| '+' | '.join([scene,*[value(report['energies'][k]['value']) for k in
            ('semantic','spatial','appearance','statistical','perceptual')],value(report['structural_energy'])])+' |')
    lines += ['', 'Spatial/Statistical 数字来自已有边缘/纹理代理，不是已验证的真实物体位置、密度或结构拓扑分数。'
        'Semantic 无已审核有效证据，Perceptual 本轮未运行 DINO，Structural 缺完整评估几何/审核条件，保持 N/A。'
        '未审核 VQA/Group/结构命题只进诊断；没有把 yes/no 或候选差异转为任意 0/1 Energy。','',
        '## 两组案例的主要发现','',
        '- bw_0073：岛台存在、四把椅子、吊灯在上方的旧回答全部 satisfied。它们没有覆盖岛台/吊灯的投影比例、材质与纹理等可见差异。'
        '独立历史柜体验证 K3 给出上下叠置抽屉样前面板 → 并排竖向门板的候选外立面组织差异；K1/K2/K4 为粗一致。'
        '没有把“外立面看起来像抽屉”解释为内部机构 GT。未验证的椅子支撑框架命题保持 unavailable。',
        '- bw_0074：书籍存在与 3+ 柜格回答相同，mixed → upright 保留为 candidate_violated。'
        '旧操作定义较粗，R2右缘/R3混入、书籍/唱片混淆与相机都待审核；不追溯替换成后来更明确的书堆定义。'
        '唱片三条旧回答全部 satisfied，但另一个明确标为post-hoc的类别实验在Render回答ambiguous，因此身份比较为unknown，而不是已确认缺失或语义错误。',
        '- bw_0074书柜：三条局部水平层板粗一致；V1/V3仅在“简单、独立、全深度板件”的几何查询假设下保留候选差异，image_only_status仍unknown。'
        '第二层Reference疑似漏检、左外框裁切和完整柜格计数保持Unknown。不能用柜格数简单相减，也不把未找到AABB候选当成视觉确认缺失。',
        '- 颜色、材质、纹理、局部投影比例等差异未被少数原子问题完整覆盖；当前主要由Appearance和已有图像代理响应。'
        '本轮静态观察只是Codex后验审核候选，不是独立人工GT，不能声称“只有Appearance”在所有可能指标中有效。','',
        '## 坐标、相机与可比较性','',
        'bw_0073 原图7952×4333按既有thumbnail规则得到1536×837；Render1672×941全帧等比fit为1487×837，左留24、右留25像素。'
        'bw_0074 Reference1258×855；Render1920×1300按既有全帧fit为1258×852，顶部1、底部2像素无效。'
        '原始Reference与Agent实际输入字节一致，run/task/export映射及旧缓存像素本轮重查；没有内容对齐、移动ROI或相机优化。',
        '厨房导出相机高度1.5m；书柜已有Scene Graph活动相机高度1.71m且平移/旋转也不同于T0。'
        '后者是已有场景快照，不证明历史PNG与该blend精确同步。Reference真实相机未知；两组均historical_camera。'
        '因此不能将二维差异直接归因为三维重建错误，Camera Error / Reconstruction Error不可分时保留不确定性。',
        '固定ROI选择为厨房R2岛台+R4高柜、陈列场景R2书籍+R3唱片，严格复用各历史验证的范围；其余画面由Global和Dense负责。'
        '未审核ROI不参与正式局部聚合；重叠诊断单独保留，不把命名ROI损失直接相加。连续Spatial没有可靠RGB对象定位/对应，为N/A；没有借用合成Object-ID。','',
        '## 人工审核待办','',
        '逐条填写 evidence_audit.md：核对厨房K3的局部对应、前面板/装饰缝；书籍横放堆与竖放的可见性及R3混入；'
        '唱片身份与独立柜格定义；书柜第二层漏检候选以及V1/V3几何假设。'
        '判断裁切、相机、遮挡影响，确认来源与实际Render可见性；任何条目都未自动升级reviewed。',
        '## 下一阶段受控真实 Agent 执行的必要条件','',
        '先单独审核可信Agent执行边界与资源限制，再由受控渲染链实际强制T0、记录实际内参及RGB/Geometry同次来源；'
        '统一固定参考坐标与有效像素支持，冻结Reference证据后独立验证。'
        '需要可审核的对象/集合对应、局部可观察性与弃权校准；Scene Graph名称不是GT，独立Structural还需评估几何、triage及规则。'
        '仅生成侧T0合规也不证明未知Reference相机与之对齐，仍需参考视角可比性证据或保留Camera不确定性。'
        'Runtime继续blocked；本轮不授权或启动下一阶段，不新增PyBullet、算法或权重。','',
        '## 复现与公开边界','',
        '需要服务器已有的合法Reference/Render与冻结缓存，公开仓库不分发这些第三方图片、ROI Mask或其衍生PNG。'
        '公开JSON/Markdown中的外部输入引用不是可下载资产；干净clone不能单凭公开记录重建受限素材。'
        '本轮本地 comparison/valid-pixel PNG 均不公开。','',
        '```bash','python3 -B scripts/real_agent_offline_pilot.py --output /tmp/projecte-m3-new',
        "python3 -B -m unittest discover -s tests -p 'test_real_agent_pilot.py'",'```','',
        '[审核表](evidence_audit.md) · [真实回答与Replay](verification_results.json) · '
        '[完整报告](report.json) · [接口检查](integration_checks.json)。'
        '这只是两组案例，不计算总体检出准确率；相同答案不表示重建质量好，候选差异也不是确认错误。']
    (output/'summary.md').write_text('\n'.join(lines)+'\n')


def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    reports={};verifications={};checks={};all_rows=[]
    for scene in ('bw_0073','bw_0074'):
        pair,report,primary,additional,structural=prepare_case(scene,output/scene)
        reports[scene]=deepcopy(report)
        reports[scene]['coordinates']['valid_mask']=scene+'/evaluation/valid_pixels.png'
        reports[scene]['local_comparison_png']=scene+'/evaluation/comparison.png'
        reports[scene]['comparison_png_public']=False
        verifications[scene]=dict(primary=primary,additional=additional,structural=structural)
        rows=audit_rows(scene,primary,additional,structural);all_rows.extend(rows)
        for item in read(output/scene/'groups.json')['unverified_reference_evidence']:
            all_rows.append(dict(evidence_id=item['id'],scene_id=scene,region_id=item['region_id'],group_id=item['group_id'],
                energy=item['type'],reference_evidence=item['claim'],question=item['question'],reference_answer=None,
                render_answer=None,status='unavailable',picture_support='Frozen Reference-only candidate; no real answer for this question',
                uncertainty='Missing verifier, not confirmed absence; expected seed is not GT',
                verifier_backend='none',human_review='unreviewed',reviewed=False,value=None))
        checks[scene]=dict(pair=pair,camera=report['scene_validity'],transform=reports[scene]['coordinates'],
            vlm_pair_binding=report['diagnostics']['vlm_verification']['pair_binding'],
            overlap=report['diagnostics']['region_overlap'],all_new_candidates_unreviewed=True,
            continuous_spatial=dict(value=None,status='unavailable',reason='No reliable RGB-only object localization/correspondence'),
            new_model_calls=0,new_agent_or_blender_runs=0,formal_eligible=False)
    # Identity audit is a separately defined post-hoc question: ambiguous remains Unknown.
    identity=read(ROOT/'results/group_identity_context_bw0074/verification_results.json')
    identity_rows=[]
    for scope in ('context','display'):
        packets=[identity_parse(identity['answers'][side+'_'+scope]['raw_answer']) for side in ('reference','render')]
        result=compare_categories(*packets,comparable=all(identity['crop_comparability'][side+'_'+scope]['comparable'] for side in ('reference','render')))
        identity_rows.append(dict(evidence_id='bw_0074_identity_'+scope,scene_id='bw_0074',region_id='R3',
            group_id='bw_0074_R3_records',energy='semantic / post-hoc identity',reference_evidence=identity['protocol']['user'],
            question='目标柜格内主要可辨认的陈列内容是什么？',reference_answer=result['first_answer'],render_answer=result['second_answer'],
            status=result['status'],picture_support=identity['crop_comparability'],
            uncertainty='Post-hoc different question; do not rewrite old records presence answers; camera/crop subset differs',
            verifier_backend='Historical Codex Subagent',human_review='unreviewed',reviewed=False,value=None))
    all_rows+=identity_rows
    verifications['bw_0074']['identity_caveat']=dict(rows=identity_rows,source='results/group_identity_context_bw0074/verification_results.json',
        original_raw_answers={k:v['raw_answer'] for k,v in identity['answers'].items()},reviewed=False)
    save(output/'verification_results.json',dict(cases=verifications,audit_rows=all_rows,new_model_calls=0,
        execution='historical_real Replay only; not a new Codex CLI/Subagent experiment',reviewed=False,usage='provisional/debug'))
    save(output/'report.json',dict(cases=reports,reviewed=False,usage='provisional/debug',formal_eligible=False,
        interpretation='Historical diagnostics, no overall cross-scene score or detection accuracy'))
    save(output/'integration_checks.json',dict(cases=checks,new_model_calls=0,new_blender_runs=0,
        formulas_weights_and_runtime_unchanged=True,third_party_visuals_public=False,reviewed=False))
    table=['# M3.0 Evidence Audit','','所有条目 human_review=unreviewed、reviewed=false；这是审核材料，不是独立人工 GT。','',
        '| Scene / evidence_id | Region / Group | Reference 证据与回答 | Render 回答 | 候选比较状态 | 图片支持 / 不确定性 | 人工审核 |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for row in all_rows:
        support=row['picture_support']
        if isinstance(support,dict) and 'reference' in support and 'render' in support:
            support='; '.join(side+': '+str(data.get('visibility',data.get('status','unknown')))+' / '+
                str(data.get('visual_basis',data.get('source','')))
                for side,data in support.items() if side in ('reference','render'))
        elif isinstance(support,dict):support='历史同坐标完整/局部输入；可见性未独立人工确认，完整信息见JSON'
        fields=[row['scene_id']+' / '+row['evidence_id'],row['region_id']+' / '+str(row.get('group_id')),
            row['reference_evidence'][:140]+' → '+str(row['reference_answer']),str(row['render_answer']),row['status'],
            str(support)+' / '+row['uncertainty'],'unreviewed：□Correct □Needs Correction □Remove □Uncertain']
        table.append('| '+' | '.join(x.replace('|','\\|').replace('\n',' ') for x in fields)+' |')
    (output/'evidence_audit.md').write_text('\n'.join(table)+'\n')
    write_summary(output,reports)
    return reports,verifications,checks


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
