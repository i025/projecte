"""Offline, reference-frozen coarse distribution inspection for bw_0074/R3."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.group_visibility import analyze, mask_on_reference, roi_on_grid
from scripts.compare_reference_blender_group import outside_partition, support_bounds
from scripts.records_group_verification import read, font
from scripts.region_real_render import fit_render


def rectangle(size, bbox):
    result = Image.new('L', size)
    x1, y1, x2, y2 = bbox
    ImageDraw.Draw(result).rectangle((x1, y1, x2-1, y2-1), fill=255)
    return result


def draw(output, frozen, reference, rendered, roi, ids, transform, layers, result):
    colors = ['#d293ec', '#76cf76', '#50bfdf']
    reference = reference.copy()
    d = ImageDraw.Draw(reference)
    for u in frozen['units']:
        x1, y1, x2, y2 = u['bbox_xyxy']
        d.rectangle((x1, y1, x2-1, y2-1), outline='#ffcd32', width=2)
        d.rectangle((x1+2, y1+2, x1+34, y1+23), fill='#162432')
        d.text((x1+4, y1+2), u['unit_id'], font=font(17), fill='white')
    supported = Image.new('RGB', reference.size, '#17212d')
    rendered = Image.fromarray(rendered)
    rd = ImageDraw.Draw(rendered)
    for layer, color in zip(layers, colors):
        visible = mask_on_reference(np.isin(ids, layer['indices']), transform, reference.size)
        supported.paste(color, mask=visible)
        box = visible.getbbox()
        rd.text((box[2]+4, box[1]), layer['id'], font=font(20), fill=color, stroke_width=1, stroke_fill='black')
    native_roi = roi_on_grid(roi, transform, (ids.shape[1], ids.shape[0]))
    supported.paste('#ff8c1e', mask=mask_on_reference((ids > 0) & ~native_roi, transform, reference.size))
    bbox = roi.getbbox()
    for im in (reference, rendered, supported):
        ImageDraw.Draw(im).rectangle((bbox[0], bbox[1], bbox[2]-1, bbox[3]-1), outline='#ff8c1e', width=2)
    # Expand the DISPLAY window to include support outside R3; never change the evaluation ROI.
    union = Image.fromarray(np.maximum(np.asarray(roi), np.asarray(mask_on_reference(ids > 0, transform, reference.size))))
    window = union.getbbox()
    canvas = Image.new('RGB', (2490, 1850), '#f3f5f8'); d = ImageDraw.Draw(canvas)
    d.text((24, 16), 'bw_0074/R3 | Coarse spatial units | reviewed=false / provisional/debug', font=font(32), fill='#17324a')
    d.text((24, 62), 'Reference units frozen before this Render read; prior Render knowledge disclosed. No blind-test claim.', font=font(24), fill='#33495d')
    for i, (im, title) in enumerate(zip((reference, rendered, supported),
            ('Reference: 6 clear cells + U7 unknown', 'Historical Render: G1 / G2 / G3 support bands', 'Cached ID: orange pixels remain outside R3'))):
        x = 24+i*824
        d.text((x, 110), title, font=font(22), fill='#17324a')
        crop = im.crop(window).resize((790, 823), Image.Resampling.NEAREST if i == 2 else Image.Resampling.LANCZOS)
        canvas.paste(crop, (x, 150))
    lines = [
        'Reference cells        Frozen observation                         Render correspondence / comparison',
        'U1 + U2 / upper        dense, upright or leaning                  G1: upper repeated display; coarse agreement ONLY; cell split unconfirmed',
        'U3 + U4 / second       dense left; partial right (speaker/gap)    G2: more continuous display; candidate distribution/divider difference',
        'U5 + U6 / stereo       sparse left-cell cluster; dense right      G3: two side clusters around stereo; coarse agreement; cell mapping unknown',
        'U7 / turntable         presence / density / direction: unknown   No separate candidate ID layer; not evidence of confirmed missing records',
        'All six cell pairs: unique correspondence Unknown. Continuous Reference-Render density error: N/A.',
        '',
        'Fixed REFERENCE windows: Render ID pixels (diagnostic only; rows are NOT matched Render cells)',
        'Unit            G1 upper             G2 middle             G3 lower              Total',
    ]
    for u in result['fixed_window_diagnostic']['units']:
        count = u['render_id_pixels_by_band']
        lines.append(f"{u['unit_id']:<19}{count['G1']:<24}{count['G2']:<24}{count['G3']:<24}{sum(count.values())}")
    lines += [
        'Different shelf bands cross the same fixed windows; zero support is NOT confirmed absence of the corresponding Reference collection.',
        '805 / 6,437 ID pixels (12.51%) remain LEFT of R3. No ROI relocation; display window includes this strip.',
        'Identity unresolved: old binary yes/yes/yes preserved; later categorical Render answer ambiguous. VINYL names are not GT.',
        'No numeric density conversion, object counting, new VLM/Blender/GPU call or formal Energy. Low-res ID is not exact historical PNG visibility.',
    ]
    for i, line in enumerate(lines):
        d.text((24, 997+i*35), line, font=font(22), fill='#17324a')
    canvas.save(output/'comparison.png')


def run(frozen_path, output):
    frozen_bytes = frozen_path.read_bytes(); frozen = json.loads(frozen_bytes)
    assert not frozen_path.stat().st_mode & 0o222, 'Reference draft must already be frozen'
    source = ROOT/'results'
    paths = dict(graph=source/'blender_scene_graph_audit_bw0074/scene_graph.json',
                 candidates=source/'blender_scene_graph_audit_bw0074/group_correspondence.json',
                 visibility=source/'blender_group_visibility_bw0074/visibility.json',
                 records=source/'records_group_verification_bw0074/verification_results.json',
                 identity=source/'group_identity_context_bw0074/verification_results.json')
    inputs = {key: read(path) for key, path in paths.items()}; v = inputs['visibility']; c = inputs['candidates']
    raw = Path(v['raw_id_array']); map_path = Path(v['protocol']['work'])/'render_result.json'
    files = {p for path in paths.values() for p in path.parent.rglob('*') if p.is_file()}
    files.update([frozen_path, raw, map_path, Path(frozen['reference_image']), Path(frozen['fixed_roi']), Path(v['protocol']['provenance']['render_rgb'])])
    snapshot = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    reference = Image.open(frozen['reference_image']).convert('RGB'); roi_image = Image.open(frozen['fixed_roi']).convert('L')
    rendered, _, transform = fit_render(Image.open(v['protocol']['provenance']['render_rgb']).convert('RGB'), reference.size)
    assert transform == inputs['records']['pair_audit']['transform']
    ids = np.load(raw, allow_pickle=False); mapping = read(map_path)['mapping']
    roi = roi_on_grid(roi_image, transform, (ids.shape[1], ids.shape[0]))
    objects = {o['id']: o for o in inputs['graph']['objects']}
    stats, support = analyze(ids, mapping, roi, [objects[m['object_id']] for m in mapping])
    assert stats == v['measurements']
    layers = []
    for row in stats['rows']:
        selected = [m['index'] for m in mapping if m['row_hint'] == row['row_hint']]
        mask = np.isin(ids, selected)
        layers.append(dict(indices=selected, source_world_row=row['row_hint'], **{k: value for k, value in row.items() if k != 'row_hint'},
            native_support_bbox=support_bounds(mask), image_centroid_y=float(np.nonzero(mask)[0].mean()),
            origin='Existing candidate ID mapping; world-height grouping checked in previous audit; G order independently follows projected pixel height',
            semantic_identity='unknown'))
    layers.sort(key=lambda layer: layer['image_centroid_y'])
    for i, layer in enumerate(layers):
        layer['id'] = f'G{i+1}'
        layer['visual_candidate'] = dict(source='assistant_postfreeze_render_inspection',
            collection_shape='Repeated thin upright forms' if i < 2 else 'Two separated side clusters around visible stereo',
            main_orientation='upright_or_leaning', density='not_assigned_without_comparable_cell_scope', reviewed=False)
    assert len(layers) == 3
    windows = []; allocated = np.zeros_like(support)
    for u in frozen['units']:
        x1, y1, x2, y2 = u['bbox_xyxy']
        assert 0 <= x1 < x2 <= reference.width and 0 <= y1 < y2 <= reference.height
        r = roi_on_grid(rectangle(reference.size, u['bbox_xyxy']), transform, (ids.shape[1], ids.shape[0]))
        assert not (r & ~roi).any() and not (r & allocated).any()
        allocated |= r
        windows.append(dict(unit_id=u['unit_id'], render_id_pixels_by_band={layer['id']: int((r & np.isin(ids, layer['indices'])).sum()) for layer in layers},
                            meaning='Support in fixed Reference coordinates only, NOT corresponding Render cabinet occupancy or a missing-object judgment', reviewed=False))
    correspondence = [
        dict(reference_band='F1', reference_units=['U1','U2'], render_band_candidate='G1', topology='two Reference cells versus a continuous-looking Render opening',
             basis='Both are the upper visible display above the next display band and stereo; no Z label used as a Reference label',
             coarse_attribute_status='coarse_consistent', observation='Repeated thin upright content spans the upper display in both images; visible divider structure differs.'),
        dict(reference_band='F2', reference_units=['U3','U4'], render_band_candidate='G2', topology='two Reference cells versus a continuous-looking Render opening',
             basis='Display immediately above the stereo-containing band, with another display above it',
             coarse_attribute_status='candidate_difference', observation='Reference right cell contains a speaker/gap; Render middle display looks more continuous. Scope/divider mismatch prevents a density error.'),
        dict(reference_band='F3', reference_units=['U5','U6'], render_band_candidate='G3', topology='Reference divider separates stereo cell from right cell; Render appears to share a wider opening',
             basis='Stereo supplies an image-visible contextual landmark; candidate thin contents occur on both sides',
             coarse_attribute_status='coarse_consistent', observation='Side clusters around a central stereo are visible in both; no unique one-to-one cabinet mapping.'),
        dict(reference_band='F4', reference_units=['U7'], render_band_candidate=None, topology='Reference target identity and extent unknown',
             basis='Turntable-containing lower area is observable; Reference left-edge thin objects are uncertain',
             coarse_attribute_status='unknown', observation='No fourth layer in the declared candidate ID set does not prove the semantic target is absent.')]
    for row in correspondence:
        row.update(correspondence_status='candidate_only' if row['render_band_candidate'] else 'unknown',
                   reliable_cell_correspondence='unknown', semantic_collection_match='unknown', continuous_density_error=None,
                   orientation_comparison_scope='Qualitative image-view static observations only; global prior VQA is not per-cell evidence; world +Z is separate',
                   reviewed=False, scorable=False)
    remaining = int((support & roi & ~allocated).sum()); outside = int((support & ~roi).sum())
    assert sum(sum(u['render_id_pixels_by_band'].values()) for u in windows)+remaining+outside == stats['group_pixels']
    result = dict(scene='bw_0074', region_id='R3', reviewed=False, usage='provisional/debug', scorable=False,
        reference_frozen_file=str(frozen_path), reference=frozen, sources={k: str(p) for k,p in paths.items()},
        provenance=v['protocol']['provenance'], transform=transform, render_layers=layers, correspondence=correspondence,
        historical_answers=dict(backend=inputs['records']['backend'], model=inputs['records']['model'],
            binary={k:a['raw_answer'] for k,a in inputs['records']['answers'].items()}, binary_comparison_unchanged=inputs['records']['comparison'],
            identity={k:a['raw_answer'] for k,a in inputs['identity']['answers'].items()}, applies_to='whole historical Group/crop, not each newly proposed Reference cell'),
        fixed_window_diagnostic=dict(units=windows, inside_r3_outside_coarse_units_pixels=remaining, interpretation='Sampling diagnostic, not matched-cell comparison', reviewed=False),
        outside_roi=dict(pixels=outside, fraction_of_group=outside/stats['group_pixels'], sides=outside_partition(support,roi), retained=True, roi_modified=False),
        comparability=dict(identity='unknown', cell_correspondence='unknown', coarse_image_layout='candidate qualitative comparison',
            continuous_density_error=None, reference_group_mask=None, quantitative_occupancy_error=None,
            camera='Reference unknown; historical camera z=1.71m/lens26mm; no fixed-T0 or same-view proof',
            mask='Cached 512x347 IndexOB, 1 sample; current-reader support not exact historical PNG mask; 28 unowned title parts excluded',
            technical_warnings=v['technical_warnings'], counts='241 Mesh candidates and 228 sampled Mesh IDs are not record counts'),
        new_execution=dict(blender=0,gpu=0,vlm=0,subagents=0), formal_energy=None,
        checks=dict(original_stats_reproduced=True, reference_units_in_range_nonoverlapping=True, pixel_conservation=True,
            reference_draft_unchanged=frozen_path.read_bytes()==frozen_bytes,
            source_files_unchanged=all((p.stat().st_size,p.stat().st_mtime_ns)==state for p,state in snapshot.items())))
    assert all(result['checks'].values())
    output.mkdir(parents=True, exist_ok=False)
    draw(output, frozen, reference, rendered, roi_image, ids, transform, layers, result)
    assert frozen_path.read_bytes()==frozen_bytes
    assert all((p.stat().st_size,p.stat().st_mtime_ns)==state for p,state in snapshot.items())
    (output/'distribution.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    write_report(output, result)
    print(json.dumps(dict(output=str(output), checks=result['checks'], fixed_windows=result['fixed_window_diagnostic'],outside_roi=result['outside_roi']),ensure_ascii=False))


def write_report(output, data):
    table='\n'.join(f"| {u['unit_id']} | {u['name']} | {u['collection_presence']} | {u['coarse_density']} | {u['main_orientation']} |" for u in data['reference']['units'])
    matrix='\n'.join(f"| {u['unit_id']} | {u['render_id_pixels_by_band']['G1']} | {u['render_id_pixels_by_band']['G2']} | {u['render_id_pixels_by_band']['G3']} |" for u in data['fixed_window_diagnostic']['units'])
    text=f'''# bw_0074/R3 集合粗空间分布对照

全部 reviewed=false、provisional/debug。仅离线读取已有图像、Scene Graph、ID 数组和历史回答；新 Blender/GPU/VLM/子 Agent 调用均为 0。未调整 R3、历史证据、五类 Energy 或权重，不计算正式分数。

## Reference 先行与冻结

本轮先查看原始 Reference 和 R3 局部，按可见水平层板与竖向隔板提出 **4 个层带、7 个粗空间单元**，随后将候选写入只读 `{data['reference_frozen_file']}`，才在本轮读取 Render/ID。前三层各有两个可辨认柜格；唱机下层另保留一个不确定单元。没有按 Blender 三个世界 Z 值决定 Reference 划分。BBox 只是粗检查窗口，不是 Group Mask，不声明精确边界。

这是主 Agent 的参考图静态候选，不是人工 GT 或自动 VLM 提取。此前对话已暴露历史 Render、三层结构和可见性统计，不能声称严格盲测。冻结后未根据生成图改写任何参考命题；通过字节相等检查而非哈希验证。

| 单元 | 参考可见范围 | 集合存在候选 | 粗密度 | 主要方向 |
| --- | --- | --- | --- | --- |
{table}

dense/partial/sparse 仅表示该可见柜格内的定性占据：大部分横向跨度有重复封套、封套与其他内容/间隙共存、小局部簇。没有转换为面积比例、实例密度或数值误差。右缘柜格范围被图像截断。U7 左缘薄片类别和遮挡不明确，三个属性均 Unknown；没有为了得到第四层目标而补造存在性。

## 双方粗对应与属性结论

生成侧沿用 241 个主体候选 ID；G1/G2/G3 按自身可见像素的图像高度排序，分别来自已保存的世界高度层 2.36/1.90/1.45。对应 ID 像素为 1753/3165/1519。命名和几何层归属不能变成 Reference 柜格标签。28 个无审核归属的标题部件未纳入。

| 参考范围 | 生成候选 | 对应依据 | 可比较结论 |
| --- | --- | --- | --- |
| F1：U1/U2 | G1 | 可见最上层陈列、下方另有陈列及收录机层 | 重复薄片主要竖放的粗形态一致；Reference 两柜格而 Render 看似长柜格，单元对应 Unknown |
| F2：U3/U4 | G2 | 收录机层正上方、且上方另有陈列 | 候选差异：Reference 右格含扬声器/间隙，Render 更连续；定义和范围不完全一致，不计算密度差 |
| F3：U5/U6 | G3 | 图像内可见收录机作为上下文定位线索，两侧有陈列簇 | 两侧簇的粗布局一致；分隔形式不同，不能确定逐柜格对应 |
| F4：U7 | 无可靠集合层对应 | 下方唱机区域可见，但参考目标类别不确定 | Unknown；ID 中没有第四候选层不能推出 Confirmed Missing |

以上是图像结构层面的未审核初审，可使用 coarse_consistent / candidate_difference / unknown；唱片类别是否匹配仍 Unknown。无法提供对应参考测量的连续密度、可见面积、方向角误差均 N/A。未将一个生成层面积分摊给两个参考柜格，也不重复计分。没有以“排序相同”证明物理柜格对应：候选依据同时包括可见层板顺序、收录机与唱机上下文；上下文用于定位，不用于证明唱片类别。

上两层及收录机层的 Reference 竖向分隔，在 Render 中未见明确对应，属于可审核的边界/组织差异候选，不能立即确认为建模缺失。三项旧 VQA yes/yes/yes 和 satisfied 原样保留，只适用于原始 Group 范围，不能传播为七个单元逐格已验证。独立类别问题中 Reference 为 vinyl_sleeves、Render 为 ambiguous，故 VINYL 名称、薄盒几何和 ID 支持都不能补足语义类别 GT。

## 固定坐标可比性检查

保持 1920×1300 Render 等比缩放为 1258×852、置于 1258×855 的 (0,1)，无内容对齐；R3 坐标不变。以下是同坐标参考窗口内的生成侧 ID 采样数量，**不是对应柜格占据率，也不是集合缺失判断**。

| 固定参考窗口 | G1 像素 | G2 像素 | G3 像素 |
| --- | --- | --- | --- |
{matrix}

不同生成层跨入同一个参考层窗口，说明直接逐窗口比较会混淆相机/布局与局部集合变化。参考窗口覆盖外的 R3 内支持为 {data['fixed_window_diagnostic']['inside_r3_outside_coarse_units_pixels']} 像素（含粗框间隙），没有强制分配。R3 外全部 805 像素保留，占 6437 个 Group 像素的 12.5058%，位于左缘。图中仅将显示窗口扩展到包含该条带，没有移动/扩大评价 ROI。

## 相机及技术限制

Reference 相机未知；历史相机高度 1.71 m、焦距数值 26 mm，未满足正式固定 T0 合规证据。视点改变可影响柜格投影高度、宽度、竖向隔板可见性、集合被遮挡的比例及固定 ROI 截断。对上下层顺序、收录机两侧簇可作有限粗描述；对分格数量、密度和固定像素覆盖的影响更大，当前不能分离相机与建模因素。

ID 是已有 512×347、1 sample 的 Cycles IndexOB 支持，保留已存相机但不是历史 PNG 精确 Mask。已有 newer-file 读取器兼容警告；透明阈值、无抗锯齿边界和薄片欠采样会影响像素分布。241 Mesh/228 有采样 ID 不等于唱片数量，像素面积也不是唱片密度。Reference 未有同定义 Group Mask，因此面积与连续密度误差保持 N/A。

## 成立的结论与下一步条件

少量参考粗单元能将全局“多柜格、主要竖放”细化为：上方连续陈列、第二层混合音响/间隙、收录机两侧簇、下层不确定内容；生成侧 ID 使这些候选的像素支持和 ROI 外分布可以复算。当前可形成有上下文解释的粗对应与差异候选，但尚未获得可靠的一对一柜格对应或连续分布误差。

后续需先由独立人工审核参考柜格、边界、语义身份与可见性；在新受控样本中已知同一相机内外参和构图、冻结单元后，对集合位置/排列作预先定义的扰动，再检查 coarse_consistent 与 candidate_difference 能否区分目标变化。不能以任意固定相机重渲染未知相机的现有 Reference 来宣称配准。若要连续密度，应先定义相同的可见面积分母、完成两侧粗 Group 定位和遮挡规则审核；否则继续使用定性占据并允许 Unknown。统一相机也不能自动解决类别歧义和隔板缺失造成的对应失败。

## 检查与复现

已通过已有统计重现、7 个参考窗口范围/互不重叠检查、ID 像素守恒、冻结文件未变及历史源文件大小/mtime 未变检查。结果保持 reviewed=false；没有模型准确率或正式 Energy 测试。

从项目目录执行，目标目录必须不存在：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_spatial_distribution.py --reference-frozen {data['reference_frozen_file']} --output results/group_spatial_distribution_bw0074_replay
```

该命令只重放冻结候选和缓存，不能重现一个严格盲测。输出 comparison.png、distribution.json、report.md，无 HTML。完成后停止。
'''
    (output/'report.md').write_text(text)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-frozen',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.reference_frozen.resolve(),args.output.resolve())
