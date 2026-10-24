# bw_9064 Reference Evidence 候选摘要

准备时间：2026-10-20T15:00:02+08:00（Asia/Shanghai）。只准备参考证据与人工审核材料，无评分。

## 来源与对应

- 成功 Run：`scene_064-harbor-generation/scene_064/task__LY4dtPw`，task_name=`LocalCustom/BlenderWorld-bw_9064`，原生 exception_info=null。
- 原始 RGB：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/work/scene_064-harbor/task/environment/inputs/references/image_01.png`，1672×941，RGB。实际 Agent 分发输入清单：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/work/scene_064-harbor/task/environment/inputs/input.json`。
- 数据集原媒体副本：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/work/scene_064-blenderworld-custom/dataset/tasks/bw_9064/references/image_01.png`。输入清单、task metadata 和 Run config 给出对应链，不以文件名猜测，不做哈希验证。
- 已有 Agent Render：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/scene_064-harbor-generation/scene_064/task__LY4dtPw/artifacts/workspace/exports/final.png`，1672×941。仅用于 HTML 对照；候选 JSON 写完并通过加载检查后才读取该图元数据，没有用它确定候选内容。
- 任务为给定原始 RGB 重建完整、可编辑三维场景，关注对象、布局、尺度、材质和视图一致性；没有指定对象清单。任务说明存于 `/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/work/scene_064-harbor/task/environment/inputs/query.txt`，JSON provenance 保留可核对文件。
- 原始模型/接口记录为 claude-code 2.1.220 / gpt-6-sol (anthropic)。这是本地 scene_064 → bw_9064 适配，与官方雪山 bw_0064 和旧 scene_064 导入评测均有区别。历史相机结果不认定为当前 Fixed-T0 合规。

## 候选内容

- **1 个 Global、3 个 Region、5 个 Anchor、4 条 Relation**。所有节点 ID 唯一，document/global/region/anchor/relation 均 reviewed=false，inventory_complete=false。
- Region：后墙内部 `[260,125,1120,490]`；顶棚内部 `[300,12,1370,92]`；前景木地板 `[440,825,1540,930]`。采用避开物体和交界线的局部采样框，不宣称完整平面分割或完整图像覆盖。
- Anchor：圆桌、画面左椅、画面右椅、冰箱、盆栽（花盆+叶簇整体）。使用可见物体范围 bbox；均沿用 importance=1.0，没有改变 Benchmark 聚合规则或评价权重。
- Relation：左椅 left_of 圆桌；圆桌 left_of 右椅；圆桌 left_of 冰箱；盆栽 on 圆桌。前三条仅声明二维投影左右，后一条 status=inferred、candidate_assessment=uncertain，不把接触线索认定为已证实三维支撑。未增加冗余逆关系或前后关系。
- 候选来自本轮对原始 RGB 的视觉检查与坐标草拟；不是人工审核结果，也没有复用历史 GT、Blender 对象名称或 Judge 判词。没有执行检测/分割模型、VLM 或任何 API，没有下载依赖。

## 能量建议与限制

- 后墙、顶棚主要适合 Appearance 与 Perceptual；后者需未来已有合规特征可用。低纹理墙顶不优先作为元素分布样本。框是采样位置，不是 Spatial 几何边界。
- **木地板适合 Statistical**：板缝和木纹可以比较纹理与多尺度边缘分布；也适合 Appearance 和 Perceptual。它只是前景局部纹理/边缘代理，没有重复物体占据图，不声称真实物体密度、板材数量或三维尺度分布。
- Semantic 的候选依据在五个 Anchor 的类别与存在性；本轮全未审核。没有 DINO 距离冒充语义。Spatial 可研究审核后的位置/左右关系；on 仍需明确语义判断，现有接口支持但本轮未调用。
- 整体明暗、曝光、材质、阴影和相机视角存在混杂。Render 不作为原图证据，原图不提供真实尺度、相机真值、隐藏几何或精确物理材质。

## 不确定性与 Mask 建议

- 墙/顶/地区域是保守内部矩形，整面边界、踢脚线与交线尚未标。应先确认每个区域内部是否纯净，再决定是否扩大。
- 两把椅子的细腿、桌子与椅子的重叠、盆栽小叶和冰箱脚/投影界限需要人工放大审核。不可把框里的背景当成物体，不补齐不可见构件。
- 优先精细 Mask：两把椅子（细腿、空隙与交叠）、圆桌（桌面/立柱/底座与遮挡）和盆栽（叶间背景、尺度小）。冰箱轮廓较简单，后续可补，注意投影与脚。当前没有为此原图建立可用的已审核分割结果，因此不生成 Mask；所有 anchor.mask_reviewed=false。
- 盆栽 on 圆桌保留 uncertain；三维支撑、真实深度顺序、准确植物品种/叶片数量不在此图可确认范围内。未提出 behind / in_front_of。

## 格式与审核状态

- 直接复用 `e_harness.benchmark_evidence.load_document` 读取 JSON，`area_mask` 检查 bbox，`reliability` 检查审核门控。保持现有 image_size=[width,height]、regions/anchors/relations、subject/predicate/object 字段和谓词 Taxonomy。
- 所有 reliability=0.0 表示尚未指定审核后的可用权重，不是模型置信度或正确概率；人工仅选择 Correct 不会自动分配可靠性。所有 effective reliability 为0，尚未形成参与评分的参考证据。
- **没有调用 build_reference**：现有函数会补充 reviewed=true 的确定性网格与 Global。此次交付直接保存并加载原始候选，未触发该补充过程；不能把加载成功当作冻结或正式评测资格。冻结审核与未来评测前必须再明确入口和审核范围。本轮未改其代码、数学公式或权重。

## 检查结果

- 环境：项目 `.venv` 的首次加载尝试因缺少 NumPy 失败，未生成产物；随后复用 README 已记录的 `/home/xymo/environments/relateanything-inference/bin/python` 完成 CPU 检查，没有安装依赖、加载模型或启动 GPU。
- 已通过：JSON 被现有 loader 读取且未修改其审核状态；9 个 bbox（Global+3 Region+5 Anchor）均在 1672×941 范围、面积非零；13 个节点/关系 ID 唯一；4 条 Relation 端点存在且谓词属于现有 Taxonomy。
- 已通过：全部 reviewed 和 mask_reviewed 均为 false；所有 effective reliability 为0；未提供任何实例 Mask 或分割真值；两个 Overlay 保持原图尺寸。
- HTML 图片/文档链接已做文件存在性检查，原图/已有 Render 不作重复拷贝；页面4种审核决定默认不选、不自动写回 JSON。Markdown 提供持久记录入口。
- Overlay 已按原图网格绘制，仍需人工决定最终边界；绘图正确不等于标注已被人工认可。
- 未执行：五能量计算、最终分数、Blender 载入/渲染、Agent Python、GPU、VLM/API 或正式 Runtime；历史数据和审核状态未改。

## 查看与必要的轻量复现检查

在本机文件系统打开 [review.html](review.html)；逐项记录到 [review_checklist.md](review_checklist.md)。候选数据：[candidate_evidence.json](candidate_evidence.json)；可视化：[Region](region_overlay.png)、[Anchor](anchor_overlay.png)。HTML 引用现存原图/Render，需要保留当前目录布局。

```bash
cd /srv/lab-disks/disk2/users/xymo/projects/e-harness
PYTHONDONTWRITEBYTECODE=1 /home/xymo/environments/relateanything-inference/bin/python - <<'PY'
from e_harness.benchmark_evidence import load_document, area_mask, reliability
p = '/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/bw_9064_evidence_review/candidate_evidence.json'
d = load_document(p)
w, h = d['image_size']
rows = [d['global_evidence']] + d['regions'] + d['anchors'] + d['relations']
assert d['reviewed'] is False and d['inventory_complete'] is False
assert len({r['id'] for r in rows}) == len(rows)
ids = {r['id'] for r in d['regions'] + d['anchors']}
for r in rows:
    assert r['reviewed'] is False and reliability(r) == 0
    if 'bbox' in r: assert area_mask(r, (h, w)).sum() > 0
    if 'predicate' in r: assert r['subject'] in ids and r['object'] in ids
print('candidate format and review gates: PASS; no scoring')
PY
```

最终审核人、逐项决定、修订坐标、可靠性规则和是否完整的 inventory 仍待人工决定；本轮没有正式 GT 或冻结产物。
