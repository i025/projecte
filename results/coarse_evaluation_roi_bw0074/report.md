# bw_0074：Coarse Evaluation ROI 有界探索

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
| A_rectangles | 4 | 87.34% | 15.49% | 12.66% | +0.00 pp | +0.00 pp | 0.0009 s |
| B1_coarse_notches | 4 | 87.34% | 3.54% | 12.66% | -11.95 pp | +0.00 pp | 0.0704 s |
| B2_edge_polygons | 4 | 81.33% | 1.33% | 18.67% | -14.15 pp | +6.00 pp | 0.0828 s |
| C_cached_SAM3 | 4 | 64.17% | 0.00% | 35.83% | -15.49 pp | +23.16 pp | 0.0211 s |

| Region | A 像素数 | B2 像素数 | C 像素数 |
| --- | ---: | ---: | ---: |
| R1 工作区 | 259077 | 172032 | 51760 |
| R2 展示书架 | 386856 | 300162 | 387777 |
| R3 唱片与音响区 | 203765 | 158250 | 64489 |
| R4 沙发区 | 258704 | 258704 | 186204 |

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

- R1：desk, lamp
- R2：decorative objects, picture
- R3：boombox, turntable
- R4：cushions, pillows

## 重叠的审计方案，暂不改变正式评分

本轮保留重叠，并保存独立的 `allocation_shares_NOT_FOR_SCORING.npz`：覆盖同一像素的 n 个 ROI 各分到 1/n；未覆盖像素为 0。数值逐像素求和在 ROI 并集上为 1，顺序无关。它是未来防止重复累计的**审计建议**，不属于可靠性 q，也没有接入指标或聚合器。

对于可加的像素统计，可在审核后用共享份额避免重复累计；对于 DINO、Semantic 等非线性区域测量，仅靠像素份额不能保证消除重复响应，仍应将共享部分单独归组计一次或在审核时确定归属。正式实现待确认，本轮不修改五类能量公式或实际评分权重。

## 成本、检查与复现

新增付费请求 0、Token 0、GPU 推理 0。B1/B2 上表时间仅为 ROI 几何计算；C 仅为缓存读取，不能用来比较 SAM3 实际模型速度。四种方案加可视化、Mask/JSON 输出和验证共约 14.25 秒（不含报告整理与测试）。CPU 线程限制为 2。

已检查：原图尺寸 1258×855；4 个 ID 唯一；JSON 可由现有证据加载器读取；矩形/多边形坐标位于原图；多边形栅格化与保存 Mask 逐像素一致；全部候选未审核；倒序输入结果相同；份额不重复累计；C 与历史 Mask 逐像素一致；HTML 本地链接存在。轻量测试日志见 `tests.log`，最终检查见 `validation.json`。没有对原始 Run 或历史实验目录写入，也没有正式还原分数。

在项目根目录复现（选择不存在的新目录，禁止覆盖）：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /home/xymo/environments/relateanything-inference/bin/python \
  scripts/coarse_roi_experiment.py --output results/coarse_evaluation_roi_bw0074_repeat
```

运行轻量检查：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONPATH=tests:. \
  /home/xymo/environments/relateanything-inference/bin/python \
  -m unittest test_region_hierarchy test_benchmark test_missing_evidence
```

改动仅为实验脚本 `scripts/coarse_roi_experiment.py` 与现有 `tests/test_region_hierarchy.py` 的 ROI 检查。本轮到此停止，供人工确认分区效果。
