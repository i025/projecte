"""CPU-only Spatial pilot. Reads fixed candidates; never invokes a model or Agent."""
import argparse
import csv
import html
from itertools import product
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_evidence import area_mask, load_document, reliability
from e_harness.spatial_diagnostics import measure_pair, compare_pairs

FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 17)
COLORS = {'island': (32, 161, 225), 'pendant': (240, 136, 25)}


def save_json(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def table(rows):
    if not rows:
        return ''
    columns = list(rows[0])
    def text(value):
        return 'N/A' if value is None else f'{value:.6f}' if isinstance(value, float) else str(value)
    return '<table><tr>'+''.join(f'<th>{html.escape(k)}</th>' for k in columns)+'</tr>'+''.join(
        '<tr>'+''.join(f'<td>{html.escape(text(row[k]))}</td>' for k in columns)+'</tr>' for row in rows)+'</table>'


def sheet(images, labels, width=760):
    height = round(images[0].height*width/images[0].width)
    canvas = Image.new('RGB', (width*len(images), height+40), 'white')
    draw = ImageDraw.Draw(canvas)
    for n, (image, label) in enumerate(zip(images, labels)):
        canvas.paste(image.resize((width, height)), (n*width, 40))
        draw.text((n*width+8, 10), label, font=FONT, fill='black')
    return canvas


def overlay(image, objects, roi=None):
    image = image.convert('RGB').copy()
    draw = ImageDraw.Draw(image)
    if roi is not None:
        mask = np.asarray(roi) > 0
        edge = mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) &
                        np.roll(mask, 1, 1) & np.roll(mask, -1, 1))
        image.paste((185, 40, 200), (0, 0), Image.fromarray(np.uint8(edge)*255))
        draw = ImageDraw.Draw(image)
    centers = []
    for key, row in objects.items():
        box = row['bbox']; color = COLORS[key]
        draw.rectangle(box, outline=color, width=3)
        x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
        centers.append((x, y))
        draw.line((x-9, y, x+9, y), fill=color, width=3)
        draw.line((x, y-9, x, y+9), fill=color, width=3)
        label = f'{key}: candidate, unreviewed'
        draw.rectangle((box[0], box[1]-25, box[0]+330, box[1]), fill='white')
        draw.text((box[0]+4, box[1]-23), label, font=FONT, fill=color)
    if len(centers) == 2:
        draw.line((*centers[0], *centers[1]), fill=(215, 40, 100), width=3)
        x, y = centers[1]
        draw.ellipse((x-5, y-5, x+5, y+5), fill=(215, 40, 100))
    return image


def oracle_objects(shift=(0, 0), lamp_shift=(0, 0), lamp_scale=1):
    """Exact synthetic visible masks; no detector or photographic annotation."""
    objects = {}
    for key, box, category in [('island', [50, 70, 150, 100], 'island'),
                               ('pendant', [90, 10, 110, 30], 'pendant light')]:
        box = np.asarray(box, float)
        if key == 'pendant':
            center = (box[:2]+box[2:])/2
            box = np.r_[center+(box[:2]-center)*lamp_scale,
                        center+(box[2:]-center)*lamp_scale]
            box += np.tile(lamp_shift, 2)
        box += np.tile(shift, 2)
        mask = area_mask({'bbox': box}, (120, 200))
        if key == 'pendant':
            # A known hole proves mask area and bbox area are different quantities.
            cx, cy = (box[:2]+box[2:])/2
            half = 5*lamp_scale
            mask[int(cy-half):int(cy+half), int(cx-half):int(cx+half)] = 0
        objects[key] = dict(category=category, bbox=box.tolist(), status='matched',
            reviewed=True, reliability=1., source='synthetic_oracle',
            extent_definition=key+' known visible synthetic shape', mask=mask,
            mask_reviewed=True, mask_scope='visible_object')
    return objects


def synthetic_controls(out):
    folder = out/'synthetic_controls'; folder.mkdir()
    baseline = oracle_objects()
    cases = [('positive_unchanged', oracle_objects(), [0, 0, 0, 0]),
             ('negative_horizontal_20px', oracle_objects(lamp_shift=(20, 0)), [.1, 0, 0, 0]),
             ('negative_vertical_12px', oracle_objects(lamp_shift=(0, 12)), [0, .1, 0, 0]),
             ('negative_visible_area_x4', oracle_objects(lamp_scale=2), [0, 0, .4, .3]),
             ('invariance_common_translation', oracle_objects(shift=(10, 5)), [0, 0, 0, 0])]
    for status in ('unknown', 'confirmed_missing', 'semantic_mismatch'):
        missing = oracle_objects(); missing['pendant']['status'] = status
        cases.append(('unlocatable_'+status, missing, [None]*4))
    rows, panels, panel_labels, inputs = [], [], [], {}
    ref = measure_pair(baseline, [200, 120])
    keys = ['delta_x_change', 'delta_y_change', 'bbox_area_ratio_proxy_change', 'visible_mask_area_ratio_change']
    for name, objects, expected in cases:
        measurement = measure_pair(objects, [200, 120])
        changes = compare_pairs(ref, measurement)
        passed = all(changes[k] is None if target is None else
                     changes[k] is not None and np.isclose(changes[k], target, atol=1e-12)
                     for k, target in zip(keys, expected))
        if not passed:
            raise AssertionError((name, changes, expected))
        rows.append(dict(case=name, **{k: changes[k] for k in keys}, passed=bool(passed)))
        inputs[name] = {}
        rgb = np.full((120, 200, 3), 245, np.uint8)
        for key, obj in objects.items():
            inputs[name][key] = {k: v for k, v in obj.items() if k != 'mask'}
            maskfile = f'{name}_{key}.png'
            inputs[name][key]['mask'] = maskfile
            Image.fromarray(np.uint8(obj['mask'])*255).save(folder/maskfile)
            if obj['status'] in ('matched', 'misplaced'):
                rgb[obj['mask'] > 0] = COLORS[key]
        picture = Image.fromarray(rgb).resize((400, 240), Image.Resampling.NEAREST)
        panels.append(picture); panel_labels.append(name)
    # Known displacement magnitudes, not another detector experiment.
    strength = []
    for pixels in (0, 5, 10, 20, 40):
        changes = compare_pairs(ref, measure_pair(oracle_objects(lamp_shift=(pixels, 0)), [200, 120]))
        assert np.isclose(changes['delta_x_change'], pixels/200)
        strength.append(dict(lamp_horizontal_pixels=pixels, **changes))
    save_json(folder/'oracle_inputs.json', dict(image_size=[200, 120], source='synthetic_oracle',
        note='reviewed=true here denotes exact generated geometry only; no real candidate was reviewed', cases=inputs))
    save_json(out/'synthetic_results.json', dict(baseline=ref, controls=rows, horizontal_strength=strength,
        assertion='All expected values checked numerically; this does not validate object localization'))
    with (out/'synthetic_results.csv').open('x', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    grid = Image.new('RGB', (800, 4*280), 'white')
    for i in range(4):
        grid.paste(sheet(panels[2*i:2*i+2], panel_labels[2*i:2*i+2], 400), (0, 280*i))
    grid.save(out/'synthetic_controls.png')
    return rows


def envelope(objects, image_size):
    """Worst-case combinations of draft edge ranges; NOT statistical intervals."""
    width, height = image_size
    values = {}
    for key, obj in objects.items():
        boxes = [np.asarray(b, float) for b in product(*obj['boundary_ranges_xyxy'])]
        centers = np.array([[(b[0]+b[2])/2/width, (b[1]+b[3])/2/height] for b in boxes])
        areas = [(b[2]-b[0])*(b[3]-b[1]) for b in boxes]
        values[key] = dict(min=centers.min(0), max=centers.max(0), area=[min(areas), max(areas)])
    a, b = values['island'], values['pendant']
    return dict(delta_x=[float(b['min'][0]-a['max'][0]), float(b['max'][0]-a['min'][0])],
                delta_y=[float(b['min'][1]-a['max'][1]), float(b['max'][1]-a['min'][1])],
                bbox_area_ratio_proxy=[float(b['area'][0]/a['area'][1]), float(b['area'][1]/a['area'][0])])


def cache_audit(out, reference):
    base = ROOT/'results/multiscene_region_extraction'
    specs = [('anchor_candidates', 'sam2_prompted', 'm004'), ('anchor_candidates', 'sam3_visual', 'm004'),
             ('anchor_candidates', 'sam3_text', 'm029'), ('region_candidates', 'sam2_prompted', 'm010'),
             ('region_candidates', 'sam3_visual', 'm010'), ('region_candidates', 'sam3_text', 'm028')]
    rows, panels, labels = [], [], []
    for kind, method, suffix in specs:
        path = base/kind/'bw_0073'/method/'candidates.json'
        doc = json.loads(path.read_text())
        row = next(r for r in doc['anchors' if kind == 'anchor_candidates' else 'regions'] if r['id'].endswith(suffix))
        maskpath = path.parent/row['mask']
        with Image.open(maskpath) as native:
            assert list(native.size) == doc['image_size']
            pixels = int(np.count_nonzero(np.asarray(native)))
            small = np.asarray(native.convert('L').resize(reference.size, Image.Resampling.NEAREST)) > 0
        assert row['reviewed'] is False and row['mask_reviewed'] is False and reliability(row) == 0
        rows.append(dict(id=row['id'], category=row['category'], source_json=str(path), mask=str(maskpath),
                         image_size=doc['image_size'], bbox=row['bbox'], candidate_mask_pixels=pixels,
                         reviewed=False, mask_reviewed=False, reliability=0.,
                         whole_island=False, valid_visible_area=False,
                         limitation='Only countertop, not whole island' if kind == 'region_candidates' else
                                    'Suspension/holes unreviewed; candidate area is not validated object area'))
        rgb = np.asarray(reference).copy()
        rgb[small] = np.uint8(.65*rgb[small]+.35*np.array([10, 200, 70]))
        panels.append(Image.fromarray(rgb));labels.append(method+' '+row['category'])
    grid = Image.new('RGB', (1560, 2*round(837*520/1536)+80), 'white')
    for i in range(2):
        row = sheet(panels[3*i:3*i+3], labels[3*i:3*i+3], 520)
        grid.paste(row, (0, i*row.height))
    grid.save(out/'cached_reference_masks.png')
    save_json(out/'cached_reference_candidates.json', rows)
    return rows


def run(out, inputs):
    allowed = {'reference_object_candidates.json', 'render_object_candidates.json'}
    if out.exists() and any(p.name not in allowed for p in out.iterdir()):
        raise FileExistsError('Output contains prior experiment files; choose a fresh directory')
    out.mkdir(parents=True, exist_ok=True)
    for name in sorted(allowed):
        original = (inputs/name).read_bytes()
        if (out/name).exists():
            if (out/name).read_bytes() != original:
                raise ValueError('Refuse to overwrite differing candidates')
        else:
            (out/name).write_bytes(original)
    (out/'reference_object_candidates.json').chmod(0o444)
    frozen_path = ROOT/'results/atomic_evidence_discriminability_bw0073/reference_evidence_frozen.json'
    frozen_bytes = frozen_path.read_bytes()
    # Use the existing evidence loader, with no mutation of the frozen document.
    frozen = load_document(frozen_path)
    assert any(r['id'] == 'R2' for r in frozen['regions'])
    references = [json.loads((out/name).read_text()) for name in ('reference_object_candidates.json', 'render_object_candidates.json')]
    ref_doc, ren_doc = references
    images = [Image.open(d['source_image']).convert('RGB') for d in references]
    assert all(list(im.size) == d['image_size'] == [1536, 837] for im, d in zip(images, references))
    pair_audit = json.loads((ROOT/'results/region_first_real_render_bw0073/pair_audit.json').read_text())
    save_json(out/'pair_provenance.json', dict(original_pair_audit=str(ROOT/'results/region_first_real_render_bw0073/pair_audit.json'),
        reference_rgb=pair_audit['reference_rgb'], render_rgb=pair_audit['render_rgb'],
        render_camera_height_m=1.5, protocol_height_m=2., reference_camera='unknown',
        comparison_transform=pair_audit['comparison_transform'], official_benchmark_eligible=False,
        scope='Historical camera; full-frame letterbox reused, no new alignment'))
    roi_path = ROOT/'results/vlm_direct_grounding_bw0073/C_direct_polygon/R2.png'
    roi_bytes = roi_path.read_bytes()
    shutil.copyfile(roi_path, out/'fixed_R2_roi.png')
    roi = Image.open(roi_path).convert('L')
    assert roi.size == images[0].size
    for image, side in zip(images, ('reference', 'render')):
        image.save(out/f'{side}.png')
    overlays = [overlay(im, d['conditional_debug_objects'], roi) for im, d in zip(images, references)]
    for im, side in zip(overlays, ('reference', 'render')):
        im.save(out/f'{side}_candidates.png')
    sheet(overlays, ['Reference: independent draft boxes; fixed R2 purple', 'Render: independent draft boxes; same fixed R2']).save(out/'comparison.png')
    for key in ('island', 'pendant'):
        sheet([overlay(im, {key:d['conditional_debug_objects'][key]}, roi) for im,d in zip(images,references)],
              ['Reference '+key+' candidate', 'Render '+key+' candidate']).save(out/f'{key}_comparison.png')
    auto = [measure_pair(d['automatic_objects'], d['image_size']) for d in references]
    review_gated = [measure_pair(d['conditional_debug_objects'], d['image_size']) for d in references]
    debug = [measure_pair(d['conditional_debug_objects'], d['image_size'], allow_provisional=True) for d in references]
    changes = compare_pairs(*debug)
    ranges = [envelope(d['conditional_debug_objects'], d['image_size']) for d in references]
    range_changes = {key: [ranges[1][key][0]-ranges[0][key][1], ranges[1][key][1]-ranges[0][key][0]] for key in ranges[0]}
    roi_stats = []
    roi_array = np.asarray(roi) > 0
    valid = np.asarray(Image.open(ROOT/'results/region_first_real_render_bw0073/render_valid.png').convert('L')) > 0
    for side, doc in zip(('reference', 'render'), references):
        for key, obj in doc['conditional_debug_objects'].items():
            box = area_mask(obj, roi_array.shape) > 0
            roi_stats.append(dict(side=side, object=key,
                bbox_inside_fixed_R2_fraction=float((box & roi_array).sum()/box.sum()),
                bbox_in_valid_frame_fraction=1. if side == 'reference' else float((box & valid).sum()/box.sum()),
                definition='bbox diagnostic only; outside R2 does not mean object missing'))
    measurements = dict(usage='provisional/debug; no formal Spatial Energy', reviewed=False,
        automatic_reference=auto[0], automatic_render=auto[1], automatic_comparison=compare_pairs(*auto),
        review_gated_reference=review_gated[0], review_gated_render=review_gated[1],
        conditional_debug_reference=debug[0], conditional_debug_render=debug[1], conditional_debug_comparison=changes,
        uncertainty=dict(method='Independent extremes of uncalibrated draft edge ranges; not confidence intervals',
                         reference=ranges[0], render=ranges[1], render_minus_reference=range_changes),
        fixed_roi_diagnostics=roi_stats, score=None, participates_in_energy=False)
    save_json(out/'spatial_measurements.json', measurements)
    rows = []
    for method, measurements_pair in [('automatic', auto), ('review_gated_drafts', review_gated), ('conditional_bbox_debug', debug)]:
        for side, measurement in zip(('reference', 'render'), measurements_pair):
            rows.append(dict(method=method, side=side, **{key: measurement[key] for key in
                ('delta_x', 'delta_y', 'bbox_area_ratio_proxy', 'visible_mask_area_ratio', 'status')}, score=None))
    with (out/'spatial_measurements.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    controls = synthetic_controls(out)
    caches = cache_audit(out, images[0])
    # Baseline source snapshots already present in the project; compare bytes,
    # no hashes, and no attempt to restore or change any core module.
    unchanged = {name:(ROOT/'e_harness'/name).read_bytes() ==
                 (ROOT/'results/region_first_real_render_bw0073/source_snapshot'/name).read_bytes()
                 for name in ('benchmark_evidence.py', 'benchmark_metrics.py', 'benchmark_config.py')}
    # tests/ is a discovery directory, not an importable "tests" package.
    test_code = ('import unittest,sys; loader=unittest.TestLoader(); '
                 'suite=unittest.TestSuite(loader.discover("tests",pattern=p) for p in '
                 '("test_spatial_minimal.py","test_missing_evidence.py","test_benchmark.py")); '
                 'result=unittest.TextTestRunner(verbosity=1).run(suite); sys.exit(not result.wasSuccessful())')
    tests = subprocess.run([sys.executable, '-B', '-c', test_code], cwd=ROOT,
                           capture_output=True, text=True, timeout=90)
    (out/'tests.txt').write_text(tests.stdout+tests.stderr)
    checks = dict(unit_tests_exit_code=tests.returncode, synthetic_controls_passed=len(controls),
        formal_source_unchanged=unchanged, original_reference_evidence_unchanged=frozen_path.read_bytes() == frozen_bytes,
        fixed_roi_unchanged=roi_path.read_bytes() == roi_bytes, candidate_review_states_preserved=True,
        paid_requests=0, gpu_model_runs=0, blender_runs=0, reviewed=False)
    assert all(unchanged.values()) and checks['original_reference_evidence_unchanged'] and checks['fixed_roi_unchanged']
    assert all(o['reviewed'] is False and reliability(o) == 0 for d in references for o in d['conditional_debug_objects'].values())
    assert all(m['delta_x'] is None and m['visible_mask_area_ratio'] is None for m in auto+review_gated)
    save_json(out/'validation_checks.json', checks)
    metric_rows = [dict(metric=k, Reference=debug[0][k], Render=debug[1][k],
                        Render_minus_Reference=changes[k+'_change'])
                   for k in ('delta_x', 'delta_y', 'bbox_area_ratio_proxy', 'visible_mask_area_ratio')]
    report = f'''# Spatial Energy 最小有效性验证：bw_0073 R2

本轮验证二维投影度量，不产生正式 Spatial Energy。0 次 API 请求、0 次 GPU/模型/Blender运行。所有真实图像候选 reviewed:false、reliability:0。

## 结果

- 受控 Oracle 几何：{len(controls)}/{len(controls)} 对照通过；独立 CPU 单元及现有 Benchmark/Missing Evidence 回归见 tests.txt（exit={tests.returncode}）。
- 主自动定位路径：Reference 仅有吊灯、台面候选，没有完整岛台；Render 无可复用的对象定位结果。两侧自动 Δx、Δy、面积比均 N/A，不能称为已打通自动 Spatial Energy。
- 人工式草拟粗框经正常审核门控也全部 N/A。显式 allow_provisional 的有条件 debug 测量另列，不能冒充自动检测、人工 GT 或 Energy。
- 条件粗框：Reference Δx={debug[0]['delta_x']:.6f}、Δy={debug[0]['delta_y']:.6f}；Render Δx={debug[1]['delta_x']:.6f}、Δy={debug[1]['delta_y']:.6f}。
- Render−Reference：Δx变化={changes['delta_x_change']:.6f}、Δy变化={changes['delta_y_change']:.6f}。y向下为正；条件下吊灯与岛台 bbox 中心的竖向距离变小。水平变化很小且草拟范围含零，不能认定水平错位。
- BBox面积比代理：{debug[0]['bbox_area_ratio_proxy']:.6f} → {debug[1]['bbox_area_ratio_proxy']:.6f}，点估计变化 {changes['bbox_area_ratio_proxy_change']:.6f}，但草拟边界下的变化范围也跨零，不能稳健认定面积代理减小。不是物体可见投影面积比；柜体遮挡、粗框内的椅子/空洞和边界定义都会影响它。真实可见 Mask 面积比两侧均 N/A。
- 草拟边界极值传播的 Δy变化范围={range_changes['delta_y']}；Δx变化范围={range_changes['delta_x']}；BBox面积比变化范围={range_changes['bbox_area_ratio_proxy']}。这些只是在给定草拟边界下的敏感性，不是置信区间，也不覆盖模型或相机系统误差。

## 来源与冻结

原始图像、Run、相机和既有全图适配见 pair_provenance.json。1536×837公共网格，左上原点、x右/y下；bbox为连续像素边界xyxy，中心分别除以W/H。复用历史 Render 等比全图适配1487×837、左侧24像素留边；没有裁剪、内容对齐、搜索或变形。真实原图7952×4333、Render1672×941。

Reference既有冻结证据只读经load_document读取；其中Region和关系scope框没有用作物体框。Reference候选由只获Reference访问的独立检查者草拟并冻结，再由只获Render访问的独立检查者提供Render候选；两者未交换坐标。主代理此前知道Render内容，故本轮不是严格盲测。草拟框不是自动定位成功，也没有升级审核状态。

R2 ROI保持原文件像素不变。紫色线表示固定ROI，蓝色框表示岛台可见台面+可见柜体、排除椅子与摆件的粗外包范围，橙色框表示吊灯含顶座/悬挂线/灯体。框内仍会包含遮挡物和背景。Render吊灯部分位于固定R2之外，但全图可见；不能据此判断Missing。完整岛台的近侧底沿被椅子遮挡，两侧粗框的确定性有限。

## 现有缓存与面积限制

只读复用6份Reference SAM缓存，见cached_reference_candidates.json及cached_reference_masks.png。三份吊灯框主要一致，但细链漏分、环带孔洞被填充等问题未审核。其余三份仅是台面，不是完整岛台。候选Mask像素数仅为文件统计，不是真实可见面积。没有可靠的两对象、两侧可见Mask，未混用Mask面积与BBox面积，也没有从Region Mask推造物体。

## 度量有效性与重复处罚

复用area_mask、reliability、load_document；现有match_anchors提供匹配/缺失状态，compare提供单物体中心偏移和定性关系，但没有本轮连续相对偏移或面积比。只增加spatial_diagnostics.py的两个诊断函数及CPU实验/测试，没有改benchmark_metrics.py、benchmark_evidence.py、benchmark_config.py或正式聚合。

相对偏移为pendant−island，比较为Render−Reference；中心是BBox中心，非Mask质心。BBox面积按连续宽×高计算，Mask面积按[0,1]权重和计算，两种量分开存储，比例不截断为[0,1]。Unknown、不可定位、语义不匹配、Confirmed Missing不产生最大Spatial惩罚；输入视角不可见、scene-only和冲突对象不可计算。允许Misplaced但仍可见的匹配对象，不要求两个对象仍在原ROI内。

Oracle包含不变、灯水平移动20px、灯竖移12px、灯面积4倍、共同平移、Unknown/Confirmed Missing/类别不匹配三类N/A；另检验水平移动0/5/10/20/40px的响应。已知灯Mask有空洞，证明Mask比和BBox比不同。正/负对照只检验数学，不证明真实定位有效。没有把连续有符号量塞入[0,1]Energy，也没有将同一缺失重复计分。

## 失败、Uncertain与正式评分缺口

主要瓶颈是完整岛台与吊灯的可靠对象定位、可见范围定义及两图对应，而不是本轮坐标算术。当前缺少独立审核的两侧对象框、可见Mask及一致语义对应；真实灯具几何形态也不完全相同，bbox中心受外形变化影响。Reference相机未知，历史Render相机高度1.5m，正式协议2m，未重新验证blend/PNG同步。即使粗框差值稳定，也不能把它认定为真实三维位置/尺寸错误。相对度量抵消共同平移，但不消除视角、透视、缩放和遮挡影响。此前“吊灯位于岛台上方”的yes/yes只能判断方向，不能排除间距变化。

SAM/检测器只产生可审候选，不是缺失验证器；本轮不运行新模型。自动定位缺失和未审核是明确失败/阻塞项，不以草拟框替代。本轮未产生正式Energy，无综合分数。

## 复现

在项目根目录执行（只使用已保存图像/候选及CPU）：

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /home/xymo/environments/relateanything-inference/bin/python -B scripts/spatial_minimal_validation.py --inputs {out.relative_to(ROOT)} --output results/spatial_minimal_validation_bw0073_replay
```

输出目录必须全新；离线重放使用冻结的草拟候选，不会重新“自动提取”对象。comparison.html可直接打开；tests.txt、validation_checks.json列出实际检查。API/SAM/SLIC/DINO/GPU/Blender全部未执行；自动定位端到端准确性、人工GT和正式Spatial评分未验证。
'''
    (out/'report.md').write_text(report)
    document = '''<!doctype html><meta charset="utf-8"><title>Spatial pilot bw_0073 R2</title>
<style>body{font:16px system-ui;max-width:1500px;margin:24px auto;padding:0 16px;line-height:1.6}img{max-width:100%}table{border-collapse:collapse;margin:16px 0}td,th{border:1px solid #bbb;padding:7px;text-align:left}p.note{background:#fff3d8;padding:16px}.pair{display:flex;gap:10px}.pair>div{width:50%}a{color:#1759a0}</style>
<h1>bw_0073 R2：Spatial最小有效性验证</h1>
<p class="note">provisional/debug，非正式成绩。自动定位路径与正常审核门控均N/A。下方数字只来自独立目视草拟粗框；reviewed=false、q=0，不是检测结果或GT。BBox面积代理不是真实投影面积。</p>
<p><a href="report.md">完整报告</a> · <a href="spatial_measurements.json">测量与N/A原因</a> · <a href="reference_object_candidates.json">冻结Reference候选</a> · <a href="render_object_candidates.json">独立Render候选</a> · <a href="tests.txt">CPU测试</a></p>
<h2>原始工作图像：全图上下文</h2><div class="pair"><div>Reference<img src="reference.png"></div><div>真实历史Agent Render<img src="render.png"></div></div>
<h2>独立粗框、中心与相对偏移</h2><p>蓝：可见岛台台面+柜体的草拟外包框；橙：灯具整体。紫：未移动的原R2。连接线从岛台bbox中心指向灯具bbox中心，不是三维距离。</p><img src="comparison.png">
<h2>逐对象审核</h2><img src="island_comparison.png"><img src="pendant_comparison.png">
<h2>有条件BBox诊断；自动路径全部N/A</h2>'''+table(metric_rows)+table(roi_stats)+'''
<p>y向下为正；两侧bbox的竖向中心差仍为负（灯在上方），但差的大小不同。不能因“above=yes”忽略间距差。面积比仅BBox代理，真实Mask面积比N/A。边界范围敏感性及原因见JSON。不能认定这是三维重建错误。</p>
<h2>既有Reference模型候选与失败</h2><p>上排吊灯、下排台面。台面不能改称完整岛台；吊链断裂、空洞填充未审核，候选面积不是可见物体面积。Render没有相应缓存。没有运行新模型。</p><img src="cached_reference_masks.png">
<h2>Oracle合成对照</h2><p>人工构造的已知几何，不依赖定位器，不是实际Agent或模型预测。Unknown/Missing/错类的空图只是Oracle输入状态，不是实际缺失判断。</p><img src="synthetic_controls.png">'''+table(controls)+'''
<h2>Uncertain与审核项目</h2><ul><li>岛台柜体被椅子遮挡；外包框内包括椅子、背景和孔洞，不能当精确面积。</li><li>灯具两侧形态不同；必须审核是否同一功能对象及相同外延定义。</li><li>Render灯具部分超出原R2但在全图可见，保留Misplaced/投影变化可能，不能标Confirmed Missing。</li><li>Reference相机未知，Render高1.5m而正式要求2m；没有重新对齐或运行Blender。</li><li>所有真实候选待人工审核，无正式Spatial Energy，无重复缺失惩罚。</li></ul>
<p>逐项人工状态：□ Correct　□ Needs Correction　□ Remove　□ Uncertain。页面没有自动批准操作。</p>'''
    (out/'comparison.html').write_text(document)
    # Every local HTML link resolves; no request is made to external services.
    import re
    links = re.findall(r'(?:src|href)="([^"]+)"', document)
    assert all((out/link).is_file() for link in links)
    if tests.returncode:
        raise RuntimeError('CPU tests failed; see tests.txt')
    print(json.dumps(dict(output=str(out), checks=checks, conditional_debug=changes), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=ROOT/'results/spatial_minimal_validation_bw0073')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.inputs.resolve())
