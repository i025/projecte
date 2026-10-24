"""Bounded CPU experiment on cached reference ROIs; no model/API/scoring calls.

Geometry is derived from input rectangles, content-hint boxes and RGB edges.
There are no task-specific coordinates, Region names or ownership priorities.
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
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_evidence import grounding_concepts, load_document, validate_region_first_plan
from scripts.region_grounding_experiment import method, read, save


def rectangles(shape, boxes):
    h, w = shape
    result = np.zeros((len(boxes), h, w), bool)
    for mask, coords in zip(result, boxes):
        x0, y0, x1, y1 = coords
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError('Invalid native-coordinate rectangle')
        mask[y0:y1, x0:x1] = True
    return result


def content_hints(regions, candidates, shape, boxes):
    """Optional cached bbox hints, NOT masks or calibrated semantic evidence.

    Content nouns take precedence over Region names. A noun naming another
    Region is treated as context rather than borrowing that entire Region.
    Missing nouns remain missing; they are not inferred from generated images.
    """
    names = [grounding_concepts(r['name']) for r in regions]
    masks = np.zeros((len(regions), *shape), bool)
    records = []
    base = rectangles(shape, boxes)
    for i, region in enumerate(regions):
        target = set(grounding_concepts(region['content']) or names[i])
        other_names = set().union(*(v for j, v in enumerate(names) if i != j))
        target -= other_names - names[i]
        matched = []; observed = set()
        for candidate in candidates:
            concepts = grounding_concepts(candidate['category']) & target
            if not concepts or not candidate.get('bbox'):
                continue
            hint = rectangles(shape, [candidate['bbox']])[0] & base[i]
            if not hint.any():
                continue
            masks[i] |= hint; observed |= concepts
            matched.append(dict(id=candidate['id'], bbox=candidate['bbox'],
                                concepts=sorted(concepts), source=candidate['source_document'],
                                prompt_source=candidate['prompt_source'], reviewed=False))
        records.append(dict(id=region['id'], matched=matched,
                            unmatched_concepts=sorted(target-observed), reviewed=False))
    return masks, records


def coarse_polygons(rgb, boxes, hints, snap=False):
    """Broad orthogonal ROIs: optional inward edge snap, then local notches.

    Pair decisions use immutable inputs and geometric ordering, never Region
    IDs. A symmetric uncertainty band deliberately retains some overlap.
    Thin object contours, SAM pixels and Region-specific thresholds are absent.
    """
    h, w = rgb.shape[:2]
    initial = rectangles((h, w), boxes)
    if hints.shape != initial.shape:
        raise ValueError('Content hints must use the native ROI grid')
    gray = np.asarray(rgb, float).mean(axis=2)/255.
    # Horizontal/vertical derivatives at a coarse image scale, not semantic edges.
    smooth = ndimage.gaussian_filter(gray, max(1., min(h, w)/400))
    energy = [np.abs(ndimage.sobel(smooth, axis=a))/8 for a in (0, 1)]
    adjusted = [list(b) for b in boxes]; snap_log = []
    if snap:
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            yy, xx = np.nonzero(hints[i] & initial[i])
            for side, old in enumerate((x0, y0, x1, y1)):
                axis = 1 if side % 2 == 0 else 0
                length = x1-x0 if axis == 1 else y1-y0
                limit = max(1, int(min(.12*min(h, w), .20*length)))
                inward = 1 if side < 2 else -1
                points = np.arange(old, old+inward*(limit+1), inward)
                if len(xx):
                    lower = int(xx.min()) if axis == 1 else int(yy.min())
                    upper = int(xx.max()+1) if axis == 1 else int(yy.max()+1)
                    points = points[points <= lower] if side < 2 else points[points >= upper]
                profile = (energy[axis][y0:y1, :].mean(axis=0) if axis == 1
                           else energy[axis][:, x0:x1].mean(axis=1))
                profile = ndimage.gaussian_filter1d(profile, max(1., min(h, w)/500))
                values = profile[np.clip(points, 0, len(profile)-1)]
                chosen = int(points[values.argmax()]); previous = float(values[0])
                # Flat/weak edges do not justify changing a coarse window.
                if float(values.max()) <= 1.2*previous+.002:
                    chosen = old
                adjusted[i][side] = chosen
                snap_log.append(dict(region_index=i, side=side, old=old, new=chosen,
                                     reason='stronger projected edge, cached content boxes guarded',
                                     maximum_shift=limit))
    base = rectangles((h, w), adjusted)
    keep = base.copy(); pair_log = []
    yy, xx = np.indices((h, w))
    band = max(1, round(.015*min(h, w)))
    for i in range(len(base)):
        for j in range(i+1, len(base)):
            overlap = base[i] & base[j]
            if not overlap.any():
                continue
            centers = [(np.array(adjusted[k][:2])+adjusted[k][2:])/2 for k in (i, j)]
            delta = (centers[1]-centers[0])/np.array([w, h])
            axis = 1 if abs(delta[0]) >= abs(delta[1]) else 0
            if abs(delta[1-axis]) < 1e-12:
                pair_log.append(dict(region_indices=[i, j], reason='coincident centers: keep ambiguous overlap'))
                continue
            coord = xx if axis == 1 else yy
            low, high = (i, j) if centers[0][1-axis] <= centers[1][1-axis] else (j, i)
            positions = coord[overlap]; lo, hi = int(positions.min()), int(positions.max()+1)
            cuts = np.arange(lo, hi+1)
            # Loss is a soft hint cost. Contradictory/unreviewed boxes may lose
            # support; the full loss is logged rather than hidden as accuracy.
            low_hist = np.bincount(coord[overlap & hints[low]], minlength=(w if axis == 1 else h))
            high_hist = np.bincount(coord[overlap & hints[high]], minlength=len(low_hist))
            low_sum = np.r_[0, np.cumsum(low_hist)]; high_sum = np.r_[0, np.cumsum(high_hist)]
            low_loss = (low_sum[-1]-low_sum[np.clip(cuts+band, 0, len(low_hist))])/max(1, low_sum[-1])
            high_loss = high_sum[np.clip(cuts-band, 0, len(high_hist))]/max(1, high_sum[-1])
            weights = np.bincount(positions, weights=energy[axis][overlap], minlength=len(low_hist))
            counts = np.bincount(positions, minlength=len(low_hist))
            profile = ndimage.gaussian_filter1d(weights/np.maximum(1, counts), max(1., min(h, w)/500))
            strength = profile[np.clip(cuts, 0, len(profile)-1)]
            strength /= max(.002, float(strength.max()))
            center_penalty = abs(cuts-(lo+hi)/2)/max(1, hi-lo)
            cost = 4*(low_loss+high_loss)-.35*strength+.05*center_penalty
            chosen = int(cuts[cost.argmin()])
            # Apply all pair proposals to separate keep arrays, so order cannot
            # give a Region first claim on shared pixels.
            keep[low] &= ~overlap | (coord < chosen+band)
            keep[high] &= ~overlap | (coord >= chosen-band)
            pair_log.append(dict(region_indices=[low, high], axis='x' if axis == 1 else 'y',
                                 cut=chosen, overlap_band_each_side=band,
                                 hint_loss=[float(low_loss[cost.argmin()]), float(high_loss[cost.argmin()])],
                                 reason='coarse edge and cached content support; symmetric overlap retained'))
    return keep, dict(snap=snap, adjusted_boxes=adjusted, side_adjustments=snap_log,
                      pair_decisions=pair_log, parameters=dict(snap_limit_short_image=.12,
                      snap_limit_roi_side=.20, overlap_band_short_image=.015,
                      hint_loss_weight=4., edge_weight=.35, center_weight=.05))


def polygon_loops(mask):
    """Pixel-edge polygons, reduced to coarse corners; also handles holes."""
    m = np.asarray(mask, bool); h, w = m.shape; padded = np.pad(m, 1)
    edges = {}
    def add(active, start, end):
        for y, x in zip(*np.nonzero(active)):
            a = (int(x+start[0]), int(y+start[1])); b = (int(x+end[0]), int(y+end[1]))
            edges.setdefault(a, set()).add(b)
    add(m & ~padded[:h, 1:w+1], (0, 0), (1, 0))
    add(m & ~padded[1:h+1, 2:], (1, 0), (1, 1))
    add(m & ~padded[2:, 1:w+1], (1, 1), (0, 1))
    add(m & ~padded[1:h+1, :w], (0, 1), (0, 0))
    result = []; directions = {(1, 0):0, (0, 1):1, (-1, 0):2, (0, -1):3}
    while edges:
        start = min(edges); current = start; previous_dir = 0; loop = []
        while True:
            loop.append(current)
            options = edges[current]
            def direction(b): return directions[(b[0]-current[0], b[1]-current[1])]
            chosen = min(options, key=lambda b: ({1:0, 0:1, 3:2, 2:3}[(direction(b)-previous_dir)%4], b))
            previous_dir = direction(chosen); options.remove(chosen)
            if not options: del edges[current]
            current = chosen
            if current == start: break
        corners = []
        for k, point in enumerate(loop):
            a, b = loop[k-1], loop[(k+1)%len(loop)]
            if (point[0]-a[0])*(b[1]-point[1]) != (point[1]-a[1])*(b[0]-point[0]):
                corners.append(list(point))
        area2 = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(corners, corners[1:]+corners[:1]))
        result.append(dict(vertices=corners, hole=area2 < 0))
    return result


def raster_polygons(shape, loops):
    yy, xx = np.indices(shape); x = xx+.5; y = yy+.5
    result = np.zeros(shape, bool)
    for loop in loops:
        inside = np.zeros(shape, bool); points = loop['vertices']
        for a, b in zip(points, points[1:]+points[:1]):
            if a[1] == b[1]: continue
            cross = a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
            inside ^= ((a[1] > y) != (b[1] > y)) & (x < cross)
        result ^= inside
    return result


def allocation_shares(masks):
    """Audit proposal only; this is NOT evidence reliability or a scoring change."""
    return masks.astype(np.float32)/np.maximum(1, masks.sum(axis=0))


def comparison(out, folders, image):
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 25)
    panels = [('Reference RGB', image)] + [(title, Image.open(out/folder/'overlay.png'))
        for folder, title in folders]
    cell_w = 900; cell_h = round(image.height*cell_w/image.width); title_h = 45
    canvas = Image.new('RGB', (2*cell_w, 2*(cell_h+title_h)), '#151b26'); draw = ImageDraw.Draw(canvas)
    for i, (title, panel) in enumerate(panels):
        x = (i%2)*cell_w; y = (i//2)*(cell_h+title_h)
        draw.text((x+15, y+8), title, font=font, fill='white')
        canvas.paste(panel.resize((cell_w, cell_h)), (x, y+title_h))
    canvas.save(out/'comparison.png')


def review_materials(out):
    """Presentation and static inspection notes; never adjusts any ROI."""
    regions = read(out/'plan.json')['regions']
    selected = [('A_rectangles','A: initial rectangles'), ('B2_edge_polygons','B: coarse edge polygons'),
                ('C_cached_SAM3','C: cached SAM3 control')]
    folder = out/'per_region'; folder.mkdir()
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 23)
    for region in regions:
        canvas = Image.new('RGB', (1950, 485), '#151b26'); draw = ImageDraw.Draw(canvas)
        for index, (key, title) in enumerate(selected):
            draw.text((650*index+12, 8), region['id']+' / '+title, font=font, fill='white')
            with Image.open(out/key/(region['id']+'_overlay.png')) as image:
                canvas.paste(image.resize((650, 442)), (650*index, 43))
        canvas.save(folder/(region['id']+'_comparison.png'))
    with (out/'summary.csv').open() as f: rows = list(csv.DictReader(f))
    stats = {r['method']:r for r in rows}; base = stats['A_rectangles']
    table = []
    for row in rows:
        overlap = float(row['overlap_fraction']); union = float(row['region_union_fraction'])
        unassigned = float(row['unassigned_fraction'])
        table.append(f"| {row['method']} | 4 | {100*union:.2f}% | {100*overlap:.2f}% | {100*unassigned:.2f}% | "
                     f"{100*(overlap-float(base['overlap_fraction'])):+.2f} pp | {100*(unassigned-float(base['unassigned_fraction'])):+.2f} pp | {float(row['geometry_seconds']):.4f} s |")
    geometry = []
    for region, index in zip(regions, range(len(regions))):
        areas = [json.loads(stats[key]['per_region_pixels'])[index] for key,_ in selected]
        geometry.append('| '+region['id']+' '+region['name']+' | '+' | '.join(str(n) for n in areas)+' |')
    missing = ['- '+r['id']+'：'+', '.join(r['unmatched_concepts'])
               for r in read(out/'content_hints.json')['regions'] if r['unmatched_concepts']]
    validation = read(out/'validation.json')
    report = '''# bw_0074：Coarse Evaluation ROI 有界探索

只复用既有四区 VLM Plan、矩形窗口、参考 RGB 和缓存候选。实际进行了 **两轮**多边形探索，随后停止。未调用 API、未运行 SAM3/SAM2/DINO、未使用 GPU、Agent Render、Agent 代码或 Blender。未修改正式 Evidence Extraction、五类能量或聚合公式。

![Reference / A / B / C](comparison.png)

## 方法与适用边界

- **A 最初矩形**：直接读取 `region_first_pilot_bw0074/localized_regions.json` 的 `bbox` 并栅格化。不是该目录中的旧 SLIC 并集 Mask。
- **B1 第一轮粗多边形**：保持原矩形外沿；仅在相邻窗口相交处，按相对中心位置选择分离方向，结合粗图像边缘和缓存内容 bbox 的丢失代价形成少量直角折线。每侧保留图像短边 1.5% 的重叠带，不追求零重叠。
- **B2 第二轮（主对照 B）**：先尝试将矩形边向内吸附到明显投影边缘。单边最多移动图像短边 12% 或 ROI 对应边长 20%，取小者；边缘不明显则不动，已有内容 bbox 作为保守边界护栏。之后应用同一折线规则。四区总计 20 个顶点；R1/R2 为粗折线，R3/R4 保持矩形，形状复杂度由几何决定。
- **C 历史 SAM3 + 冲突消解**：原样读取 `region_grounding_conflict_resolution/round2_C_resolved` 的四个 Mask，未重新优化。它是上一轮的待审核候选，不能作为 GT。

B 的全部坐标来自输入窗口、缓存 bbox 和 RGB 投影边缘。没有按任务名、Region ID、语义名称指定坐标或区域优先级；所有相交对均基于同一不可变输入独立决定，最后合并约束。中心相同无法判断方向时保留重叠。倒置区域顺序的实际图像检查通过。

**这里验证的是缓存窗口到粗 ROI 的调整**。初始窗口和内容候选本身尚未获人工审核，历史视觉提示中含助手提供的参考侧 bbox；因此本轮不代表从任意新图完全自动完成语义定位。B 不读取 SAM 像素轮廓，只将缓存候选 bbox 作为可选定位线索。对新场景仍需要可靠的初始窗口/内容线索；通用代码和合成布局测试不等于跨场景质量验证。

## 候选几何统计

分母均为全图像素数；Overlap 表示至少两个 ROI 共同覆盖的像素比例。面积和重叠是几何统计，不是分割准确率。Δ 相对 A，单位为百分点。Global / Dense Patch 仍负责全图；本轮未实际运行这些评价。

| 方法 | ROI 数 | ROI 并集 | Overlap | Unassigned | Δ Overlap | Δ Unassigned | 几何/读取时间 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
'''+ '\n'.join(table)+'''

| Region | A 像素数 | B2 像素数 | C 像素数 |
| --- | ---: | ---: | ---: |
'''+ '\n'.join(geometry)+'''

## 原图静态检查（助手观察，未代替人工审核）

| Region | A / B1 的典型问题 | B2 主对照观察 | C 的典型问题 |
| --- | --- | --- | --- |
| R1 工作区 | A 包含较多左墙和地板，与书架大幅相交；B1 改善相交但左墙仍多 | 桌面、显示器、台灯、笔记本和透明椅保留；左侧收至桌边附近。仍含椅下地板、照明背板和少量右下邻区 | 分到 R1 的主要是显示器和椅子，桌面/灯具却混在 R2 的宽书架 Mask 内，不能代表完整工作设施组 |
| R2 展示书架 | A 的左下方吞入显示器和桌面；B1 的粗折线能保留右侧鱼缸内容 | 陈列书籍、地球仪、飞机图片、摆件和鱼缸可见内容保留；左下粗缺口明显减少工作区混入。显示器上缘附近仍有重叠带 | 工作台背板、桌面及下柜等混入；物体孔洞与书架大 Mask 不是稳定的粗区域边界 |
| R3 唱片与音响区 | A/B1 已保留设备，但左边跨入邻架、下边带入柜面 | 唱片、收录机和下方唱盘设备均在粗 ROI 内；边缘贴近架列/台面。最下沿设备阴影是否应多保留需人工确认 | 主要定位唱片，收录机/唱盘不属于其 R3 Mask，重要组成内容遗漏 |
| R4 沙发区 | A/B1 均有沙发上方柜面背景 | 保持整个沙发和靠垫，不逐靠垫拆分。缓存沙发 bbox 使边界护栏保守，因此与 A 相同；上方柜面、左上开放柜格仍被包含 | 边缘较贴近主体，但前景彩色织物出现孔洞；像素形状较精细不意味着语义内容更完整 |

这些观察支持 **B2 值得进入人工确认**，不证明它在其他图上稳定优于矩形或 SAM。没有审核 GT，不计算或声称 IoU、Boundary F1、物体完整率、背景准确率。ROI 数固定为既有四区；没有新增 Anchor 或 Relation。

每区大图：[R1](per_region/R1_comparison.png) · [R2](per_region/R2_comparison.png) · [R3](per_region/R3_comparison.png) · [R4](per_region/R4_comparison.png)。[HTML](comparison.html) 还展示 B1、Overlap 和 Unassigned。

## 未解决的问题与人工检查重点

1. 粗 ROI 自带上下文：R1 椅下地板、R4 后方柜面保留，没有为了美观人工修补。未来如确有评价价值，再按需借助 SAM/审核，不能默认改成实例 Mask。
2. R2 中桌面左缘的少量书籍缓存框与“工作设施组”有归属歧义。R1/R2 的边界代价只能作几何取舍，不能证明这些书籍应归哪组；完整丢失代价记录在各轮 `diagnostics.json`，并未隐藏困难内容。
3. R3 音响设备没有独立缓存 Mask，当前是由宽上下文和可见台面边缘保留；不能由唱片候选推断设备存在性/类别已获验证。R4 缓存矩形也没有区分柜面和沙发。
4. 只向内调整，不能补回原始窗口外已遗漏的内容；局部光影、书脊、架板强边缘可能吸附错误，复杂交错区域未验证。所有候选 `reviewed:false`、`mask_reviewed:false`、`reliability:0`，不进入正式评分。

以下内容词没有相应缓存 bbox，表示定位线索缺失，**不表示原图缺少物体**：

'''+ '\n'.join(missing)+'''

## 重叠的审计方案，暂不改变正式评分

本轮保留重叠，并保存独立的 `allocation_shares_NOT_FOR_SCORING.npz`：覆盖同一像素的 n 个 ROI 各分到 1/n；未覆盖像素为 0。数值逐像素求和在 ROI 并集上为 1，顺序无关。它是未来防止重复累计的**审计建议**，不属于可靠性 q，也没有接入指标或聚合器。

对于可加的像素统计，可在审核后用共享份额避免重复累计；对于 DINO、Semantic 等非线性区域测量，仅靠像素份额不能保证消除重复响应，仍应将共享部分单独归组计一次或在审核时确定归属。正式实现待确认，本轮不修改五类能量公式或实际评分权重。

## 成本、检查与复现

新增付费请求 0、Token 0、GPU 推理 0。B1/B2 上表时间仅为 ROI 几何计算；C 仅为缓存读取，不能用来比较 SAM3 实际模型速度。四种方案加可视化、Mask/JSON 输出和验证共约 '''+f"{validation['total_seconds']:.2f}"+''' 秒（不含报告整理与测试）。CPU 线程限制为 2。

已检查：原图尺寸 1258×855；4 个 ID 唯一；JSON 可由现有证据加载器读取；矩形/多边形坐标位于原图；多边形栅格化与保存 Mask 逐像素一致；全部候选未审核；倒序输入结果相同；份额不重复累计；C 与历史 Mask 逐像素一致；HTML 本地链接存在。轻量测试日志见 `tests.log`，最终检查见 `validation.json`。没有对原始 Run 或历史实验目录写入，也没有正式还原分数。

在项目根目录复现（选择不存在的新目录，禁止覆盖）：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \\
  /home/xymo/environments/relateanything-inference/bin/python \\
  scripts/coarse_roi_experiment.py --output results/coarse_evaluation_roi_bw0074_repeat
```

运行轻量检查：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONPATH=tests:. \\
  /home/xymo/environments/relateanything-inference/bin/python \\
  -m unittest test_region_hierarchy test_benchmark test_missing_evidence
```

改动仅为实验脚本 `scripts/coarse_roi_experiment.py` 与现有 `tests/test_region_hierarchy.py` 的 ROI 检查。本轮到此停止，供人工确认分区效果。
'''
    with (out/'report.md').open('x') as f: f.write(report)


def validate_presentation(out):
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def __init__(self): super().__init__(); self.targets = []
        def handle_starttag(self, tag, attrs):
            self.targets.extend(value for key, value in attrs if key in ('src', 'href'))
    parser = Links(); parser.feed((out/'comparison.html').read_text())
    for target in parser.targets:
        if not (out/target).is_file(): raise ValueError('Missing local HTML target: '+target)
    source = read(out/'source.json'); original = load_document(source['control_source'])
    control = load_document(out/'C_cached_SAM3/evidence.json')
    old = {row['id']:row for row in original['regions']}
    for row in control['regions']:
        np.testing.assert_array_equal(row['mask'], old[row['id']]['mask'])
    return dict(html_targets_checked=len(parser.targets), historical_control_pixels_unchanged=True)


def run(out, pilot, previous):
    out.mkdir(parents=True, exist_ok=False); started = time.perf_counter()
    plan_source = read(pilot/'vlm_plan.json')
    plan = validate_region_first_plan(dict(regions=[{k:r[k] for k in ('id','name','location','content')}
                                                   for r in plan_source['regions']]))
    regions = plan['regions']; info = read(pilot/'input.json'); original = Path(info['reference_rgb'])
    image = Image.open(original).convert('RGB'); rgb = np.asarray(image)
    if list(image.size) != info['image_size']: raise ValueError('Reference size mismatch')
    shutil.copyfile(original, out/('reference'+original.suffix)); save(out/'plan.json', plan_source)
    localized = {r['id']:r for r in read(pilot/'localized_regions.json')['regions']}
    boxes = [localized[r['id']]['bbox'] for r in regions]
    candidates = read(previous/'raw_candidates/candidates.json')['candidates']
    hints, records = content_hints(regions, candidates, rgb.shape[:2], boxes)
    save(out/'content_hints.json', dict(regions=records, usage='unreviewed cached bbox hints only; no SAM contours'))
    save(out/'source.json', dict(reference_rgb=str(original), original_metadata=str(pilot/'input.json'),
         rectangle_source=str(pilot/'localized_regions.json'), plan_source=str(pilot/'vlm_plan.json'),
         control_source=str(previous/'round2_C_resolved/evidence.json'), paid_vlm_calls=0,
         new_model_inferences=0, agent_render_used=False, gpu_used=False, reviewed=False))
    rows = []; methods = {}; timings = {}; polygons = {}
    configurations = [('A_rectangles', None), ('B1_coarse_notches', False), ('B2_edge_polygons', True), ('C_cached_SAM3', None)]
    for key, snap in configurations:
        t = time.perf_counter()
        if key.startswith('A'):
            masks = rectangles(rgb.shape[:2], boxes); diagnostic = dict(input_boxes=boxes)
        elif key.startswith('B'):
            masks, diagnostic = coarse_polygons(rgb, boxes, hints, snap=snap)
        else:
            document = read(previous/'round2_C_resolved/evidence.json')
            control = {r['id']:r for r in document['regions']}
            masks = np.stack([np.asarray(Image.open(previous/'round2_C_resolved'/control[r['id']]['mask'])) > 0 for r in regions])
            diagnostic = dict(historical_control=True, computation='read cached masks only')
        timings[key] = time.perf_counter()-t; methods[key] = masks
        stats = method(out, key, rgb, regions, masks, source=str(out/'source.json'))
        if key.startswith(('A', 'B')):
            evidence_path = out/key/'evidence.json'; evidence = read(evidence_path)
            for row in evidence['regions']:
                row.update(representation='coarse_evaluation_roi', semantic_mask_available=False,
                           localization_status='approximate_coarse_roi')
            evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        stats.update(geometry_seconds=timings[key], roi_count=len(regions), reviewed=False)
        if key.startswith('B') or key.startswith('A'):
            loops = [polygon_loops(mask) for mask in masks]
            polygons[key] = loops
            stats['polygon_vertex_count'] = sum(len(p['vertices']) for group in loops for p in group)
            save(out/key/'polygons.json', dict(image_size=list(image.size), coordinate_convention='pixel edges, xy; even-odd fill',
                 regions=[dict(id=r['id'], polygons=group, reviewed=False) for r, group in zip(regions, loops)]))
        else: stats['polygon_vertex_count'] = None
        save(out/key/'diagnostics.json', diagnostic)
        # Explicitly an audit artifact: not loaded by evidence loader or metrics.
        np.savez_compressed(out/key/'allocation_shares_NOT_FOR_SCORING.npz', shares=allocation_shares(masks))
        rows.append(stats)
    selected = [('A_rectangles','A: initial rectangles'), ('B2_edge_polygons','B: coarse edge polygons'),
                ('C_cached_SAM3','C: cached SAM3 + conflict resolution')]
    comparison(out, selected, image)
    columns = ['method','roi_count','region_union_fraction','overlap_fraction','unassigned_fraction',
               'per_region_pixels','polygon_vertex_count','geometry_seconds','reviewed']
    with (out/'summary.csv').open('x') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    body = ['<!doctype html><meta charset="utf-8"><title>Coarse Evaluation ROI — bw_0074</title>',
            '<style>body{font:16px sans-serif;background:#f4f5f7;margin:24px}img{max-width:100%}td{vertical-align:top}table{width:100%;table-layout:fixed}th,td{padding:8px}p{max-width:1100px}</style>',
            '<h1>bw_0074：粗 ROI 对照，全部待人工审核</h1>',
            '<p>只使用 Reference RGB 和缓存。洋红色为重叠；背景无需被 ROI 覆盖。B 不追踪 SAM 像素轮廓。Global / Dense Patch 继续覆盖全图。</p>',
            '<img src="comparison.png" alt="Reference / A / B / C comparison">',
            '<p><a href="report.md">实验报告</a> · <a href="summary.csv">候选统计</a> · <a href="content_hints.json">缓存线索与缺项</a></p>']
    all_folders = selected[:2]+[('B1_coarse_notches','B1: first bounded round')]+selected[2:]
    body.append('<table><tr><th>Region / VLM Plan</th>'+''.join('<th>'+html.escape(title)+'</th>' for _,title in all_folders)+'</tr>')
    for region in regions:
        body.append('<tr><td>'+html.escape(region['id']+' '+region['name'])+'<p>'+html.escape(region['content'])+'</p><p>reviewed: false</p></td>'+''.join(
            '<td><a href="'+folder+'/'+region['id']+'_overlay.png"><img src="'+folder+'/'+region['id']+'_overlay.png"></a></td>' for folder,_ in all_folders)+'</tr>')
    body.append('</table><h2>重叠与未分配区域</h2><table>')
    for folder,title in all_folders:
        body.append('<tr><td>'+html.escape(title)+'</td><td>Overlap<img src="'+folder+'/overlap.png"></td><td>Unassigned<img src="'+folder+'/unassigned_overlay.png"></td></tr>')
    body.append('</table><p>显示图仅供候选审核，不表示分割准确率或正式评分。未知或缺失的内容线索不能证明原图不存在该物体。</p>')
    (out/'comparison.html').write_text('\n'.join(body))
    checks = {}
    for key, masks in methods.items():
        doc = load_document(out/key/'evidence.json')
        assert len(doc['regions']) == len(regions)
        assert all(r['reviewed'] is False and r['reliability'] == 0 for r in doc['regions'])
        for row, mask in zip(doc['regions'], masks):
            np.testing.assert_array_equal(row['mask'], mask)
        if key in polygons:
            for mask, loops in zip(masks, polygons[key]):
                np.testing.assert_array_equal(mask, raster_polygons(rgb.shape[:2], loops))
                assert all(0 <= x <= image.width and 0 <= y <= image.height for p in loops for x,y in p['vertices'])
        shares = allocation_shares(masks)
        np.testing.assert_allclose(shares.sum(axis=0), masks.any(axis=0), atol=1e-6)
        checks[key] = dict(native_shape=True, loader=True, all_unreviewed=True, polygon_raster_matches=True if key in polygons else None,
                           allocation_shares_sum_one_on_union=True)
    # Reversing Region order cannot change results. No Region-ID ownership input.
    for snap in (False, True):
        reversed_masks, _ = coarse_polygons(rgb, boxes[::-1], hints[::-1], snap=snap)
        np.testing.assert_array_equal(reversed_masks[::-1], methods['B2_edge_polygons' if snap else 'B1_coarse_notches'])
    save(out/'validation.json', dict(checks=checks, order_invariance=True, new_api_calls=0, new_model_inferences=0,
         five_energy_formulas_modified=False, polygon_rounds=2, total_seconds=time.perf_counter()-started))
    review_materials(out)
    final_validation = read(out/'validation.json')
    final_validation.update(validate_presentation(out))
    (out/'validation.json').write_text(json.dumps(final_validation,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(output=str(out), statistics=rows, total_seconds=time.perf_counter()-started), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot', type=Path, default=ROOT/'results/region_first_pilot_bw0074')
    parser.add_argument('--previous', type=Path, default=ROOT/'results/region_grounding_conflict_resolution')
    args = parser.parse_args(); run(args.output, args.pilot, args.previous)
