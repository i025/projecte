"""Offline comparison of saved R3 evidence; never opens Blender or calls a model."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.group_visibility import analyze, mask_on_reference, roi_on_grid
from scripts.records_group_verification import font, read
from scripts.region_real_render import fit_render


def support_bounds(mask):
    y, x = np.nonzero(mask)
    return [int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)] if len(x) else None


def outside_partition(mask, roi):
    """Disjoint diagnostic sides relative to the raster ROI bounding box."""
    left, top, right, bottom = support_bounds(roi)
    y, x = np.indices(roi.shape)
    outside = mask & ~roi
    sides = {}
    remaining = outside.copy()
    for name, condition in [('left', x < left), ('right', x >= right),
                            ('above', y < top), ('below', y >= bottom)]:
        selected = remaining & condition
        sides[name] = int(selected.sum())
        remaining &= ~selected
    sides['inside_bbox_outside_roi'] = int(remaining.sum())
    assert sum(sides.values()) == int(outside.sum())
    return sides


def figure(output, reference, rendered, roi_image, ids, mapping, transform, data):
    colors = [(65, 190, 230), (115, 205, 110), (200, 135, 240)]
    layer = Image.new('RGB', reference.size, '#151e28')
    for row, color in zip(data['render_measurements']['rows'], colors):
        indices = [r['index'] for r in mapping if r['row_hint'] == row['row_hint']]
        visible = mask_on_reference(np.isin(ids, indices), transform, reference.size)
        layer.paste(color, mask=visible)
    outside = mask_on_reference((ids > 0) & ~roi_on_grid(roi_image, transform, (ids.shape[1], ids.shape[0])), transform, reference.size)
    layer.paste((255, 140, 30), mask=outside)
    bbox = roi_image.getbbox()
    panels = []
    for im in (reference, rendered, layer):
        im = im.copy()
        ImageDraw.Draw(im).rectangle((bbox[0], bbox[1], bbox[2]-1, bbox[3]-1), outline='#ff8c1e', width=3)
        panels.append(im)
    canvas = Image.new('RGB', (2460, 1730), '#f3f5f8')
    d = ImageDraw.Draw(canvas)
    d.text((24, 14), 'bw_0074 / R3 | Reference - Blender Group Evidence | provisional/debug', font=font(32), fill='#193149')
    titles = ['Reference / fixed R3', 'Historical Render / same R3', 'Cached ID support / NOT historical PNG GT']
    for i, (im, title) in enumerate(zip(panels, titles)):
        x = 24 + i*812
        d.text((x, 70), title, font=font(23), fill='#193149')
        canvas.paste(im.resize((790, 537), Image.Resampling.LANCZOS if i < 2 else Image.Resampling.NEAREST), (x, 108))
    d.text((24, 661), 'Detail window includes R3 + left strip for inspection only; evaluation ROI is unchanged.', font=font(25), fill='#193149')
    # A display window derived from the union of fixed ROI and measured support, never an evaluation ROI.
    union = Image.fromarray(np.maximum(np.asarray(roi_image), np.asarray(mask_on_reference(ids > 0, transform, reference.size))))
    box = union.getbbox()
    for i, im in enumerate(panels):
        crop = im.crop(box)
        crop.thumbnail((790, 360), Image.Resampling.NEAREST if i == 2 else Image.Resampling.LANCZOS)
        canvas.paste(crop, (24+i*812, 703))
    lines = [
        'Property           Reference evidence                 Render evidence                        Comparable conclusion',
        'Presence           VQA: yes                           VQA: yes; 6,437 ID pixels               Answer agreement only; identity unknown',
        'Identity           vinyl_sleeves (both inputs)        ambiguous (both inputs); VINYL names    Unknown; names/geometry are not class GT',
        'Distribution       >=2 cabinet sections: yes          VQA: yes; 3 world-height bands          Numeric pair comparison: N/A',
        'Orientation        mainly upright: yes                VQA: yes; near world +Z in geometry     Image/world axes differ; pair error N/A',
        '',
        'Row z hint      Candidate meshes      Sampled meshes      ID pixels      Share of Group      Outside R3',
    ]
    for row in data['render_measurements']['rows']:
        lines.append(f"{row['row_hint']:<16}{row['candidate_bodies']:<22}{row['bodies_with_sampled_id_pixels']:<20}{row['mask_pixels']:<15}{row['share_of_group_pixels']:.2%}                 {row['outside_r3_pixels']}")
    lines += [
        '805 / 6,437 Group pixels (12.51%) lie outside fixed R3: ALL on the LEFT. Orange = outside; other colors = height bands.',
        'Generated-view support can expose ROI undercoverage. Camera/viewpoint differences cannot be separated with these data.',
        '241 meshes != 241 records; 228 sampled IDs != historical full-resolution visible count. Titles excluded; 512 x 347, 1 sample.',
        'No Reference Group mask / continuous orientation GT. Newer-file reader warning; exact historical PNG mask is NOT certified.',
        'All candidates reviewed=false. No new model, Blender, GPU or scoring run. Old satisfied results are preserved unchanged.',
    ]
    for i, line in enumerate(lines):
        d.text((24, 1090+i*34), line, font=font(22), fill='#193149')
    canvas.save(output/'comparison.png')


def run(output):
    directories = {key: ROOT/'results'/name for key, name in {
        'graph': 'blender_scene_graph_audit_bw0074', 'visibility': 'blender_group_visibility_bw0074',
        'records': 'records_group_verification_bw0074', 'identity': 'group_identity_context_bw0074'}.items()}
    paths = {key: directory/filename for key, directory, filename in [
        ('graph', directories['graph'], 'scene_graph.json'), ('correspondence', directories['graph'], 'group_correspondence.json'),
        ('visibility', directories['visibility'], 'visibility.json'), ('records', directories['records'], 'verification_results.json'),
        ('identity', directories['identity'], 'verification_results.json')]}
    loaded = {key: read(path) for key, path in paths.items()}
    v, c, records, identity = (loaded[k] for k in ('visibility', 'correspondence', 'records', 'identity'))
    provenance = v['protocol']['provenance']
    raw = Path(v['raw_id_array'])
    mapping_file = Path(v['protocol']['work'])/'render_result.json'
    files = {p for directory in directories.values() for p in directory.rglob('*') if p.is_file()}
    files.update([raw, mapping_file, *(Path(provenance[k]) for k in ('reference_cached', 'render_rgb', 'roi'))])
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    ids = np.load(raw, allow_pickle=False)
    mapping = read(mapping_file)['mapping']
    assert len(mapping) == 241 and len({r['index'] for r in mapping}) == 241
    assert set(r['object_id'] for r in mapping) == set(c['candidate_object_ids'])
    assert records['protocol']['group']['group_id'] == c['reference_group_id'] == provenance['reference_group_id']
    reference = Image.open(provenance['reference_cached']).convert('RGB')
    roi_image = Image.open(provenance['roi']).convert('L')
    rendered, _, transform = fit_render(Image.open(provenance['render_rgb']).convert('RGB'), reference.size)
    assert transform == records['pair_audit']['transform'] and roi_image.size == reference.size
    roi = roi_on_grid(roi_image, transform, (ids.shape[1], ids.shape[0]))
    objects = {o['id']: o for o in loaded['graph']['objects']}
    measured, mask = analyze(ids, mapping, roi, [objects[r['object_id']] for r in mapping])
    assert measured == v['measurements'], 'Cached measurements no longer reproduce'
    assert np.array_equal(mask, np.asarray(Image.open(directories['visibility']/v['mask'])) > 0)
    for row in measured['rows']:
        row['share_of_group_pixels'] = row['mask_pixels']/measured['group_pixels']
        row['outside_fraction_of_row'] = row['outside_r3_pixels']/row['mask_pixels']
        selected = np.isin(ids, [m['index'] for m in mapping if m['row_hint'] == row['row_hint']])
        row['sampled_support_bbox_xyxy'] = support_bounds(selected)
        row['outside_sides'] = outside_partition(selected, roi)
        geometry = next(g for g in c['geometry']['rows'] if g['name_row_hint'] == row['row_hint'])
        row['stored_world_geometry'] = geometry
        # Verify that the name-based row membership agrees with stored base geometry.
        bottoms = [objects[m['object_id']]['world_aabb'][0][2] for m in mapping if m['row_hint'] == row['row_hint']]
        assert np.allclose([min(bottoms), max(bottoms)], geometry['actual_base_aabb_bottom_z_range'], atol=1e-6)
    outside = mask & ~roi
    outside_details = dict(sides=outside_partition(mask, roi), native_bbox_xyxy=support_bounds(outside),
                           fraction_of_group=float(outside.sum()/mask.sum()), reference_grid_display_only_bbox_xyxy=mask_on_reference(outside, transform, reference.size).getbbox(),
                           attribution='Generated-view support extends left of fixed R3; ROI undercoverage and historical viewpoint mismatch are not separately identifiable.', reviewed=False)
    assert outside_details['sides']['left'] == 805
    properties = []
    for key, reason in [
        ('present', 'Same visual yes answers, but record identity remains unreviewed/ambiguous. ID pixels prove candidate geometry support, not vinyl identity.'),
        ('multiple_sections', 'At least two visually separated cabinet compartments is not the same definition as three world-height rows. Reference has no compatible mask or per-band allocation.'),
        ('upright_display', 'Qualitative image-view upright answers agree. Stored geometric orientation is relative to world +Z; no compatible Reference continuous orientation measurement.')]:
        old = next(x for x in records['comparison'] if x['id'] == key)
        properties.append(dict(property=key, historical_answer_comparison=old, reliable_pair_comparison='unknown',
                               continuous_pair_error=None, reason=reason, reviewed=False, scorable=False))
    properties.insert(1, dict(property='semantic_identity', reference={k: identity['answers'][k]['raw_answer'] for k in ('reference_context', 'reference_display')},
                             render={k: identity['answers'][k]['raw_answer'] for k in ('render_context', 'render_display')},
                             reliable_pair_comparison='unknown', reason='Different post-hoc categorical question; not a correction of prior satisfied results. Render category is ambiguous, not confirmed mismatch/missing.', reviewed=False, scorable=False))
    checks = dict(cached_statistics_reproduced=True, saved_binary_mask_matches_ids=True, all_241_assignments_resolve=True,
                  row_names_checked_against_world_bottom_z=True, layer_pixels_conserve_total=sum(r['mask_pixels'] for r in measured['rows']) == measured['group_pixels'],
                  outside_partition_conserves_total=sum(outside_details['sides'].values()) == measured['group_outside_r3_pixels'],
                  original_files_unchanged=all((p.stat().st_size, p.stat().st_mtime_ns) == state for p, state in before.items()))
    assert all(checks.values())
    result = dict(scene='bw_0074', region_id='R3', group_id=c['reference_group_id'], reviewed=False, usage='provisional/debug', scorable=False,
        sources={k: str(p) for k, p in paths.items()}, provenance=provenance, coordinate_transform=transform,
        reference_group=records['protocol']['group'], historical_vlm=dict(backend=records['backend'], model=records['model'],
            answers={k: a['raw_answer'] for k, a in records['answers'].items()}, identity_answers={k: a['raw_answer'] for k, a in identity['answers'].items()},
            identity_crop_comparability=identity['crop_comparability'], source_answers_are_gt=False),
        evidence_roles=dict(agent_declared_names='semantic intent only', stored_base_geometry='world-space transforms and bounding geometry; not semantic class GT',
            index_pass='sampled candidate-object pixel support under saved camera and current reader, not exact historical PNG GT', vlm_visual_answers='unreviewed visual judgments; not Reference GT'),
        candidate_assignments=mapping, generated_geometry=c['geometry'], render_measurements=measured, outside_roi=outside_details, property_comparison=properties,
        mask_scope=dict(native_resolution=measured['native_resolution'], title_parts_excluded=28, settings=v['pass_settings'],
            technical_warnings=v['technical_warnings'], exact_historical_png_equivalence=False, reference_mask_available=False,
            reference_render_mask_iou=None, semantic_record_count=None, world_height_rows_are_cabinet_compartments=False),
        formal_energy=dict(semantic=None, spatial=None, statistical=None), new_execution=dict(blender=0, gpu=0, vlm=0, segmentation=0), checks=checks)
    output.mkdir(parents=True, exist_ok=False)
    figure(output, reference, Image.fromarray(rendered), roi_image, ids, mapping, transform, result)
    assert all((p.stat().st_size, p.stat().st_mtime_ns) == state for p, state in before.items())
    (output/'group_evidence_comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    report(output, result)
    print(json.dumps(dict(output=str(output), checks=checks, outside_roi=outside_details), ensure_ascii=False))


def report(output, data):
    rows = '\n'.join(f"| {r['row_hint']} | {r['candidate_bodies']} | {r['bodies_with_sampled_id_pixels']} | {r['mask_pixels']} | {r['share_of_group_pixels']:.2%} | {r['outside_r3_pixels']} |" for r in data['render_measurements']['rows'])
    text = f'''# bw_0074/R3 Reference–Blender Group Evidence 离线对照

全部 reviewed=false、provisional/debug，不生成正式分数。本轮新增 Blender/GPU/VLM/分割调用均为 0；只读取已有 JSON、PNG 与 ID 数组，新增三个输出文件及一个轻量复现脚本。历史结果和 Reference Evidence 未修改。

## 属性级结论

| 属性 | Reference | Render | 可比较结论 |
| --- | --- | --- | --- |
| 集合存在 | 参考候选及历史 VQA yes，无审核 GT | 历史 VQA yes；候选几何有 6437 个 ID 支持像素 | 保留旧 satisfied 作为回答一致；真实唱片存在性仍 Unknown，ID 不能证明类别 |
| 语义身份 | 后续完整/局部分类均 vinyl_sleeves | 后续完整/局部分类均 ambiguous；对象名含 VINYL | Unknown；名称是建模意图，薄盒几何也不能区分书籍/封套 |
| 粗空间分布 | 历史问题是至少两个独立柜格，回答 yes | 同问题 yes；另有三个世界高度层的实际采样像素 | 定性回答一致；高度层不等于柜格，缺少参考侧同定义定位，分布差值 N/A |
| 排列方向 | 可辨认封套主要竖直：yes | 同问题 yes；几何接近世界 +Z（最大偏角约 3.43°） | 图像竖直与世界竖直的轴定义不同；缺少参考连续测量，方向误差 N/A |

历史真实模型回答来自 **Codex Subagent / gpt-6-sol**，并非 Ofox。原始字符串保存在输出 JSON。后续身份问题是 post-hoc exploratory，问题、裁剪和可见范围不同；不能把 ambiguous 当作对旧二值回答的直接逻辑否定，也不能追溯改写三个 satisfied。局部输入仍有残余上下文，Render 局部只包含部分层架，不能视作严格上下文因果消融。历史已有 Render 知识，本轮也不是盲测。

## 可重算的生成侧可见分布

原始 ID 网格 512×347，分母为候选主体 ID 的并集 6437 像素；不在放大图上计算面积。三层归属使用已保存的对象 ID 映射，并核对其基底世界 z 范围，没有按图片位置猜层。

| 世界高度提示 m | 候选 Mesh | 有采样像素 Mesh | ID 像素 | 占 Group 像素 | R3 外像素 |
| --- | --- | --- | --- | --- | --- |
{rows}

三层像素守恒（1519+3165+1753=6437）。228/241 个候选主体在这一次低分辨率 ID Pass 中至少贡献一个像素；这不是唱片数量，也不是历史全分辨率 PNG 的可见实例数量。13 个无像素 Mesh 可能被遮挡或未被低分辨率采样，不能直接判定缺失。28 个标题部件因归属未审核而排除，但仍正常遮挡。三层由几何归属区分，不意味着 Reference 已确认有三个可匹配柜格。

### R3 外 12.51%

805/6437=12.5058% 的 Group 像素在固定 R3 外，**全部位于左缘**；三层分别 301、331、173 像素。其原生网格范围为 {data['outside_roi']['native_bbox_xyxy']}（xyxy，右下界不含）。同坐标展示范围为 {list(data['outside_roi']['reference_grid_display_only_bbox_xyxy'])}，仅是低分辨率 Mask 的最近邻映射，不是精确历史边界。

这证明当前生成侧候选支持超出固定参考 ROI，支持“该 ROI 对当前视图的生成集合覆盖不足”的诊断。它不能单独区分参考 ROI 范围不足、Agent 布局偏移或历史相机差异。Reference 相机未知；历史保存相机 z=1.71 m、镜头数值为 26 mm，不能由数据名中的 30mm 推定内参，也不满足固定 T0 合规证明。未移动 ROI、未做内容对齐或重新投影来提高结果。图中详细窗口仅用于展示 R3 及左侧条带。

## 比纯 VLM 增加什么

Scene Graph 增加可追溯的 241 个主体候选、几何层归属、世界范围及轴方向；Group-ID 增加考虑遮挡的像素支持、投影范围、分层面积占比和 ROI 外支持位置。它们使生成侧部分 Spatial/Statistical 属性成为可重复测量的数据，不再只有 yes/no。

但双方尚无同定义、可靠的参考 Group Mask、分层定位或方向测量，语义身份也未审核，因此不能计算可信的 Reference–Render 分布误差、Mask IoU、密度误差或正式 Spatial/Statistical Energy。物体名称不是语义 GT；ID 不包含类别；像素面积不是数量；对象中心直方图不是可见密度。世界 +Z 近似竖直可检验建模组织，却不能替代参考视角的图像关系验证。仍需要参考侧粗集合定位/可见性审核、语义验证和可比较相机条件。

## Mask 技术限制

复用一次已有 Cycles IndexOB CPU Pass（512×347、1 sample、alpha threshold 0.5）；本轮未渲染。Mask 保留历史保存相机，但它是当前读取器状态下的低分辨率支持，**不是历史 PNG 的精确 Mask**。旧记录包含 newer-file 警告 `File written by newer Blender binary (402.67), expect loss of data!`；清理阶段另有 `ValueError: list.remove(x): x not in list`，当时输出完成且退出码 0。边缘无抗锯齿、透明材质阈值及细薄几何欠采样均有限制。BBox 代理的 8048 像素比 ID 多 1611，差值混合空包围盒、遮挡、排除标题和采样效应，不能称为纯遮挡率。

## 检查与复现

通过：原始 ID 与已存二值 Mask 一致；旧统计完整重现；241 个对象及层归属可解析；层像素和 ROI 外分区守恒；坐标转换与历史记录完全一致；读取前后源文件大小及 mtime 未变。未新增模型或正式评分测试。图像标签为英文以使用已有字体，JSON/报告保留中文语义。

从项目目录运行（必须指定未存在的新目录）：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_reference_blender_group.py --output results/reference_blender_group_evidence_bw0074_replay
```

输入路径及原始回答见 `group_evidence_comparison.json`。输出仅 `comparison.png`、该 JSON、`report.md`。结论：**生成侧部分空间/统计证据已更客观可测；跨参考和重建的可靠误差仍为 Unknown/N/A，不能升级为正式 Benchmark 成绩。**
'''
    (output/'report.md').write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
