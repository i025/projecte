# Project e：Region Segmentation 与 Missing Evidence 实验

时间：2026-10-20T16:09:42+08:00（Asia/Shanghai）。仅对 bw_9064 原始 RGB 生成分割候选，并用可信 CPU 合成 raster 验证 Missing 机制；未对该真实 Agent 样本做正式五能量评分。

## 实际完成与资源

- 原始 RGB：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/work/scene_064-harbor/task/environment/inputs/references/image_01.png`（1672×941）。以已核实的 selected.csv 和 bw_9064 候选草稿定位；没有读取 Agent Render 来决定区域或物体标签。
- 保留旧 `results/bw_9064_evidence_review` 的3个 ROI、5个 bbox 和审核材料。旧 ROI 并集覆盖率约 **32.73%**，本次用实际非矩形 Mask 补充，不将旧框扩大冒充新分割。
- SLIC 使用 scikit-image 0.26.0，100/200/400三档，参数 compactness=10、sigma=1、10轮、Lab距离与连通性约束。实际得到 **92 / 199 / 384** 个区域，各档计算约1.4–1.5秒；原图网格完整划分，不给超像素自动贴语义标签。
- SLIC 依赖最初未预装。自动审批曾因旧约束拒绝联网安装；随后用户明确授权“允许临时安装 SLIC 依赖”。仅在 `/tmp/project_e_slic_deps_rlhjhcvv` 安装 scikit-image、lazy-loader、imageio、tifffile；共享环境未改，没有下载模型。
- GPU 推理最初也因旧任务约束被自动审批拒绝；补充本轮附件的条件授权与空闲检查后获准。仅使用 GPU 2（UUID `GPU-158426a4-6684-7863-8cbe-ed6595f97683`），启动前为3MiB/0%，1次串行 SAM2 推理 **3.62秒，峰值688.59MiB**，CPU限制2线程、GPU分配上限12%、外层150秒超时。结束后GPU2回到3MiB/0%。没有占用其他GPU。
- 复用 `sam2_box_masks` 与 `/home/xymo/models/sam2` 的既有官方权重，10个 box prompts：5个重要物体、5个表面候选。不重写分割模型，不尝试新的自动 Mask 生成器。
- 既有权重 model_type=sam2_video，复用项目静态 Sam2Model 适配；Transformers 类型提示保留于日志。实际加载 missing/unexpected/mismatched/error 列表均为空。头分数只原样保留，不用作语义正确概率或可靠性。

## 覆盖率与方法对照

| 方法 | Region数 | Dense Pixel | Candidate Region | Candidate Semantic（未审核） | Reviewed Semantic |
| --- | ---: | ---: | ---: | ---: | ---: |
| SLIC（200档） | 199 | 100.00% | 100.00% | 0.00% | 0.00% |
| SAM2 + Unknown网格 | 9 | 100.00% | 100.00% | 84.86% | 0.00% |
| SLIC + SAM2 | 376 | 100.00% | 100.00% | 84.86% | 0.00% |

- Candidate Region 包含 Unknown；Dense 表示某个基础单元对像素有分配，不表示理解正确。SAM2 原始5个表面 Mask 只覆盖 **84.86%**；其余 **15.14%（238242像素）**由显式 Unknown 网格补齐，而非宣称 SAM2 全图分割成功。
- Region 覆盖按 Mask 并集统计，不重复计算重叠；每种方法本次 Region 重叠像素均为0，未分配像素均为0。候选类别只是 RGB 提示，全部 reviewed=false、mask_reviewed=false、reliability=0，故审核语义覆盖率必须为0。
- SAM2 提取了5个非空 Anchor Mask：圆桌、左右椅、冰箱、盆栽。它们的并集为159663像素；有 **209个重叠像素**：桌/盆栽124，桌/左椅85，其余对为0。没有自动消除这些冲突或确定归属，也没有已审核 GT 来计算 Mask IoU 准确率。
- SLIC 比较图使用200档作为固定展示设置，不是最终方法选择。该档全部199个区域为非矩形，面积中位数7707像素，bbox填充率中位数0.734；详细大小分布与边界比例见 segmentation_summary.json。
- 组合方法用 `(SLIC label, SAM2各Mask成员位)` 简单拆分。跨候选 Anchor 边界单元从 **30降为0**；这是算法一致性检查，不是边界准确率。Region 数由199增至376；其中23片不足16像素，共122像素，未为提高报告覆盖而丢弃。Anchor Mask 原样沿用，候选语义覆盖仍是84.86%，无新增语义证据。
- 静态观察：SAM2 的墙顶大面和物体整体边界比独立 SLIC 单元更贴合可见结构；但桌/盆栽接触、椅腿空隙、冰箱底脚与踢脚线仍需人工复核。SLIC 对平滑墙顶和地板纹理明显过分割；组合又保留了这些分割并引入小片，不能声称整体优于 SAM2。

## Evidence 与可视化

- `candidate_regions.json` 保留 **584条**不同方法的候选（199 SLIC + 9 SAM2/Unknown + 376组合），通过 method 字段区分；不是将三种重复覆盖当作一个最终评分参考。`region_masks.npz` 存储原始网格布尔 Mask，已有 load_document 可直接加载。
- `candidate_anchors.json` 保留5个物体的默认 importance=1.0 和未审核状态；mask 指向 SAM2 PNG，prompt_bbox 保留旧提示框，bbox/position 仅表示新候选 Mask 的辅助范围。所有改动只在新目录，不修改旧 Evidence。
- 每种方法提供 labels.npy、彩色分割图、原图叠加、Anchor叠加、未被原始候选覆盖的区域图。SAM2 的红色未覆盖诊断仍展示原始表面候选遗漏，没有被补全网格隐藏。SLIC 本身没有 Anchor 实例 Mask，图中仅有提示框，未伪称 SLIC 完成实例分割。
- [并排对照页面](comparison.html) 包含三种方法、三档 SLIC、小区域/重叠/静态失败说明及旧审核材料入口。本轮不自动选择最终方法或冻结 GT。

## Missing / Mismatch / Misplaced / Unknown 机制

1. 保留全局 Hungarian 对应和既有加权实例 F1。相同类别可跨大位移、低IoU匹配；每轴中心偏移超过预设5%图幅时诊断为 Misplaced，Semantic 仍视为存在，Spatial 保留连续偏移公式。没有精细 Mask 也可保守匹配。
2. 不同类别只有足够位置重叠，或明确且已审核的对应结论，才作为 Semantic Mismatch；远处无关类别不自动充当替代物。对应权重使用有效证据可靠性，importance 独立于 [0,1] 可靠性字段。
3. 完整且已审核的 Render Inventory 仍可确认缺失，且必须是输入视图可见内容；场景对象清单、Mesh名称或 visible_in_input_view=false 不构成成功对应。
4. 新增最小 `anchor_verdicts` 列表。Confirmed Missing 使用 reference_id，Confirmed Extra 使用 rendered_id，明确对应使用两者及 status=matched。只接受 reviewed=true、正可靠性、非空来源、evidence_scope=input_view、verification_type=human 或 synthetic_oracle 的结论。本轮没有校准自动缺失验证器；VLM、检测器未检出、candidate_missing、自评confidence均不会获此资格。冲突结论返回 Unknown；非法/未审核结论也保留诊断。
5. 不完整清单时，已验证结论形成现有 F1 的条件误差；每个 Unknown 仍保留预期记录与 Coverage，不伪造0误差或自动扣 Missing 分。新增不参与计算的q=0候选不改变有效条件分数。
6. Confirmed Extra 需要逐项可靠确认，或完整且经过审核的参考清单。参考提取器可能漏掉的未匹配渲染物体为 Unknown Extra，并计入未确认报告与 Coverage；不因渲染清单完整就自动扣 Extra 分。
7. 为兼容旧报告，旧 status=missing 保留，但仅表示可靠确认；新 verification_status 明确写 confirmed_missing。完整状态诊断与 Extra 记录均可从 error_diagnostics 读取。

## Region Missing 与重复响应

- 对审核后参考 Region 设置 `presence_evidence=true`、category；渲染同 ID 区域须提供审核后的同类别 `occupancy_category`、`element_occupancy` 和 occupancy_reviewed=true，才计算 Semantic 的 `1-sum(M_I*P_R)/sum(M_I)`。P_R 是可靠内容占据，不是未经校准的 SAM2 头分数。
- 没有可靠 P_R、渲染区域漏检、类别范围不对应时，此 Semantic 子项为 N/A。Appearance 和可用的 Perceptual 始终在原参考 Mask 坐标比较，不因渲染侧未找到 Region 就消失。现有 Anchor 排除与层次权重继续生效。
- 确认缺失只在 Semantic 实例 F1 中扣缺失分。该 Anchor 的 Spatial、Appearance、Perceptual 以及涉及缺失端点的关系都保留记录、返回 N/A，避免把同一不存在的对象再判为最坏位置和最坏材质。
- Global/固定 Region 的真实 RGB、边缘、外观变化仍会响应删除，这是不同可观察内容的响应，不能声称五能量完全独立。Texture/边缘分布仍是 Proxy；未修改五类能量或层次聚合权重，也未新增 Observation Energy。
- 同一受控删除场景的前后结果：Semantic 保持 0.333333；Spatial 从 0.167643 降到 0.000977，Appearance 从 0.049571 降到 0.000551，正是去除了缺失 Anchor 的重复局部惩罚。完整矩阵保留在 [既有回归结果](controlled_regression/response_matrix.csv)。这些是合成 fixture，非 bw_9064 分数。

## 实际测试

- 修改前47项单测：全部通过；修改后 **75项**：全部通过（含26项缺失/coverage测试与2项GPU资源门控测试，门控测试不启动GPU）。
- [missing_tests.json](missing_tests.json)：12个真实实现计算的 raster 场景，**15个检查全部通过**，保留每项能量、Coverage、诊断和实际参与/未参与记录；Perceptual 无本地特征时为N/A。
- 原有 `--validate-metrics` 回归：16个扰动场景、6个各自Baseline、**12个检查全部通过**，同像素/同证据保留修改前后比较。身份零误差、颜色不改变类别、空间强度响应、分布响应、q=0不变性、importance、不可用项等均通过。
- Region 替换的 Perceptual 网关另以实际像素均值向量作单测，仅验证公式路径与固定坐标响应，不当成真实 DINO 质量实验。没有运行真实 DINO 或 VLM，本轮没有必要重复模型评测。
- 真实 Agent 重放、未经审核 Blender、正式 bw_9064评分均未执行；Blender端到端未重复启动，已有CPU raster回归覆盖本次指标修改。SAM2/GPU没有因资源问题跳过，实际运行记录可查。

| 控制场景 | 实际状态 | Semantic | Appearance | Coverage |
| --- | --- | ---: | ---: | ---: |
| matched | a: matched | 0.0 | 0.000000 | 0.7692 |
| misplaced | a: misplaced | 0.0 | 0.108660 | 0.7692 |
| semantic_mismatch | a: semantic_mismatch | 1.0 | 0.043905 | 0.7692 |
| confirmed_missing_oracle | a: confirmed_missing | 1.0 | 0.005719 | 0.6923 |
| detector_false_negative | a: unknown | N/A | 0.000000 | 0.6667 |
| single_anchor_human_absence | a: confirmed_missing | 1.0 | 0.005719 | 0.6923 |
| confirmed_extra | a: matched | 0.33333333333333337 | 0.012868 | 0.7692 |
| unknown_extra | a: matched | 0.0 | 0.012868 | 0.7407 |
| region_content_replaced | Region 固定位置比较 | 1.0 | 0.127088 | 0.7333 |
| region_detector_failed | Region 固定位置比较 | N/A | 0.127088 | 0.6667 |
| color_error_baseline | a: matched | 0.0 | 0.153952 | 0.7692 |
| add_q_zero | a: matched | 0.0 | 0.153952 | 0.6667 |

## 代码修改与复用

| 文件 | 修改目的 |
| --- | --- |
| e_harness/benchmark_evidence.py | 新增并集型 coverage_audit；保留现有 Mask加载与审核门控。 |
| e_harness/benchmark_metrics.py | 逐Anchor可信结论、错位/替换门控、Extra与Unknown、条件F1、Region内容缺失以及不重复扣缺失分。 |
| e_harness/benchmark_config.py | 仅增加5%位移诊断阈值；能量/层次/结构权重不变。 |
| scripts/compare_region_segmentation.py | 复用 scikit-image SLIC、现有SAM2适配器；资源门控、简单边界拆分、候选JSON和可视化。 |
| scripts/smoke_benchmark.py | 增加 --validate-missing 的可信CPU raster控制。 |
| tests/test_missing_evidence.py | 新增机制/coverage/资源门控测试。 |
| tests/test_benchmark.py | 原Extra用例补上原本缺少的“完整参考清单”条件。 |
| README.md | 新字段契约、限制与复现说明。 |

直接复用 SciPy Hungarian、现有 F1/aggregation、area_mask/load_document、sam2_box_masks、本地 SAM2、既有 smoke controls 与 Pillow。未重写分割/检测模块，未新增复杂类、注册表、版本或哈希机制，没有提交/推送Git；正式 Runtime blocked 状态未改。

## 最简复现

所有输出必须选不存在的新目录。临时 SLIC 目录只增加 PYTHONPATH，未修改共享环境；将来清理该目录后需重新取得依赖，不能假设所有机器已经安装。

```bash
cd /home/xymo/projects/e-harness
EVAL_PY=/home/xymo/environments/relateanything-inference/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
"$EVAL_PY" -B -m unittest discover -s tests -p 'test_*.py' -v
"$EVAL_PY" -B scripts/smoke_benchmark.py --validate-missing --output results/missing_controls_new
"$EVAL_PY" -B scripts/smoke_benchmark.py --validate-metrics --output results/region_metrics_regression_new
# CPU复现全部分割；本地模型，不下载
PYTHONPATH=/tmp/project_e_slic_deps_rlhjhcvv timeout 180 "$EVAL_PY" -B scripts/compare_region_segmentation.py \
  --sam-device cpu --output results/region_segmentation_new
```

若使用已获授权的空闲 GPU，先查询资源，用一个实际空闲的 GPU UUID 设置 CUDA_VISIBLE_DEVICES，再将 --sam-device 改为 cuda:0。脚本拒绝占用设备；没有默认抢占或自动多GPU行为。

打开 [comparison.html](comparison.html) 查看图像；Region/Anchor候选分别为 [candidate_regions.json](candidate_regions.json)、[candidate_anchors.json](candidate_anchors.json)。旧人工审核材料保持原状。下一步仍是人工逐项审 Mask/语义/接触区，不是自动冻结。
