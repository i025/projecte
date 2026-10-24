# VLM Direct Grounding：跨场景验证

**本轮没有证明 Direct Polygon 已能稳定跨场景工作。** `bw_9064` 的两个功能区得到合法、内容大致完整的粗 ROI；`bw_0074` 返回的 R1 Polygon 有 10 个顶点，违反冻结的 3–8 点要求，整份响应被拒收。没有删点、重试、接受部分结果或伪造 Mask。Polygon 可作为优先研究的简化候选路线，当前证据不足以将其替换为无需审核的正式默认方法。

[双场景审核入口](comparison.html) · [bw_0074 对照与失败原文](bw_0074/comparison.html) · [bw_9064 完整对照](bw_9064/comparison.html) · [几何统计](summary.csv) · [请求成本](request_costs.json)

所有自动候选和诊断均为 `reviewed:false`；“合理定位”等分类只是助手根据参考 RGB 的静态初审，不等于人工审核通过、像素 GT 或分割准确率。本轮没有正式重建评分。

## 冻结内容与真实来源

复用 `results/vlm_direct_grounding_bw0073/source_snapshot/vlm_direct_grounding.py`。测试逐字比较以下实现：`SYSTEM`、`prompt_for`、`schema_for`、`cross`、`intersects`、`validate_direct`、`native_coordinates`、`masks_for`、`request_payload`。它们全部不变。没有修改 B2、类别词表、五类 Observation Energy 或 3D Structural Energy。

源码只进行了输入路径、任务标签与离线 replay 的最小泛化，增加“整份坐标拒收时仅展示 N/A”的失败页面。没有新增依赖、复杂抽象或图片专属坐标、区域名称、边界规则。

| 输入 | 既有真实 Plan | 既有 A Historical | 原图尺寸 | 请求尺寸 |
| --- | --- | --- | --- | --- |
| bw_0074 | `results/region_first_pilot_bw0074/vlm_plan.json`，4 区 | `results/coarse_evaluation_roi_bw0074/B2_edge_polygons/evidence.json` | 1258×855 | 1024×696 |
| bw_9064 | `results/region_first_e2e_generalization/bw_9064/vlm_plan.json`，2 区 | `results/region_first_e2e_generalization/bw_9064/B2_frozen/evidence.json` | 1672×941 | 1024×576 |

每图 `input.json` 保存原始 RGB 绝对路径、任务元数据来源和历史证据路径。Plan 与原文件逐字相同，其名称、位置、内容与历史 VLM 实际响应一致；请求图片与原始 RGB 按原流程缩小后的像素一致。每次只发送一张原始参考图的整图缩小版和对应历史 Plan，不发送 Agent Render、历史 Overlay、人工框或评分结果。

**冻结模板的已知限制：** 原模板末尾仍有“全部四个 Region”字样，而 bw_9064 的真实 Plan 是两区。按本轮要求没有改动模板、补造区域或重新规划；Schema/校验器始终要求真实 Plan 的准确 ID 集合。本次 bw_9064 实际返回正确的两个 ID 并通过。该模板矛盾仍需后续单独处理，不能把它推断为 bw_0074 顶点违规的原因。

## 实际调用与停止条件

| 图片 | 请求次数 | HTTP / finish_reason | 输入 Token | 输出 Token | 总 Token | 请求耗时 | 最终状态 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| bw_0074 | 1 | 200 / stop | 1422 | 699 | 2121 | 22.467 s | Schema 拒收，Direct 结果 N/A |
| bw_9064 | 1 | 200 / stop | 1170 | 887 | 2057 | 17.074 s | 坐标合法，2 区非空候选 |
| 合计 | **2** | 无重试、无额外调用 | 2592 | 1586 | **4178** | **39.540 s** | 一图通过、一图失败 |

模型为 `openai/gpt-6-sol`，复用现有 OfoxTunnel 和 VLMClient，temperature=0.1、输出上限 2200 Token、不启用 JSON Mode、不要求解释推理。上述耗时为两次请求耗时之和，不是整个实验墙钟时间。供应商未返回费用金额，记为 unknown，没有另查余额或估算账单。原始响应仅有要求的 JSON。

`provider_response.json` 保存脱敏供应商响应；`vlm_response.json` 保存原始回答文本、解析结果与精确校验错误；不保存请求认证 Header 或密钥。

### bw_0074：明确的输出契约失败

精确错误：`Expected 3–8 vertices`。

出错位置：`regions[0].polygons[0]`，ID 为 R1，实际 **10** 个顶点，冻结上限 **8**。全部四个 ID、Box 字段及其他 Polygon 都确实由模型返回，但整份文档未通过同一校验器。因此 B/C 整体 N/A，没有独立收用 Box，也没有把其他三个局部合法结果包装成成功实验。

[拒收坐标原文](bw_0074/rejected_regions.json) 保留实际归一化值，并明确 `accepted_as_roi:false`；它不是可评分的 Evidence。该图没有 `direct_regions.json`、`native_coordinates.json` 或 Direct Mask 目录。仅保留历史 A 的图像及原分辨率 Mask，并生成明确标为 N/A 的 Direct 对照位。

这是 **Schema / Coordinate Contract Failure**，不是重新规划失败。现有四区语义 Plan 没有改变；本轮无法据此判断该图 Direct Polygon 的内容质量。失败后的工作仅整理历史对照和诊断材料，没有再次请求或修补坐标。

## 逐 Region 静态诊断

分类含义：“合理定位”仅表示主要可见内容在粗 ROI 中大致保留；“部分定位”表示已有明确漏项；“定位失败”包含无法接受的输出契约错误；“无法判断”表示没有可接受的新 ROI 或缺乏审核依据。

| 图片 / Region | A Historical | B Direct Box | C Direct Polygon | 主要问题 / Uncertain |
| --- | --- | --- | --- | --- |
| bw_0074 R1 工作区 | 合理定位 | 无法判断 | 定位失败：10 顶点违规 | A 保留桌面、显示器、台灯与椅子，但墙面/地板混入；新 Box 随整份响应拒收 |
| bw_0074 R2 展示书架 | 合理定位 | 无法判断 | 无法判断 | A 陈列内容大致保留；与工作区交界略重叠；新结果未收用 |
| bw_0074 R3 唱片与音响区 | 合理定位 | 无法判断 | 无法判断 | A 含唱片、收录机和下方唱盘设备；新结果未收用 |
| bw_0074 R4 沙发区 | 合理定位 | 无法判断 | 无法判断 | A 沙发及抱枕保留，邻近抽屉柜混入；新结果未收用 |
| bw_9064 R1 桌椅区 | **部分定位** | 合理定位 | 合理定位，边缘待审 | A 遗漏盆栽叶冠；B/C 保留桌、两椅和盆栽。C 减少墙面/部分地板，但不能声称更完整 |
| bw_9064 R2 冰箱区 | 合理定位 | 合理定位 | 合理定位，边缘待审 | B 有少量外围背景；C 较贴近柜体整体形状。柜脚、阴影和边缘仍不确定 |

bw_9064 的具体观察：

- **R1 完整性：** Direct Box 与 Polygon 都明显改善了历史 A 的盆栽遗漏，同时保留两把椅子及圆桌。Polygon 用两块相交的粗多边形取并集，减少桌椅上方墙面与部分地板，没有逐椅腿或逐叶片分割。两块并不是彼此分离的实例 Mask；其内部交集只计一次。
- **R1 限制：** 细椅腿、左椅座外缘、盆栽叶尖和物体间空隙没有人工像素 GT，不能确认精确完整性。不能因为 C 面积较小就认为优于 B。
- **R2 完整性：** B/C 均保留冰箱主体，Polygon 的粗斜边减少周围背景。没有把两扇门拆成 Anchor。底脚、接触阴影仍需人工检查。
- **R2 语义范围：** Plan 提到“周围可见浅色墙面和木地板”，但没有规定应纳入多少上下文。Polygon 比 Box 更窄不自动意味着更符合语义范围，需人工决定评价 ROI 的上下文宽度。

每个 Region 都有独立四面板图，原图始终保留，Overlay 沿用原有轻量显示。详细文字见各图 `initial_review.json` 和 HTML。

## 几何统计，仅作诊断

全部统计在原始分辨率上计算。ROI 覆盖、非空数量和重叠都不是准确率；N/A 不能记成零误差或零覆盖。

| 图片 / 方法 | 合法非空 ROI | ROI 并集 / 全图 | Region 重叠 / 全图 | 未分配 / 全图 |
| --- | ---: | ---: | ---: | ---: |
| bw_0074 A Historical | 4/4 | 81.33% | 1.33% | 18.67% |
| bw_0074 B Direct Box | N/A | N/A | N/A | N/A |
| bw_0074 C Direct Polygon | N/A | N/A | N/A | N/A |
| bw_9064 A Historical | 2/2 | 16.73% | 0.00% | 83.27% |
| bw_9064 B Direct Box | 2/2 | 20.35% | 0.00% | 79.65% |
| bw_9064 C Direct Polygon | 2/2 | 15.89% | 0.00% | 84.11% |

bw_9064 的两个 Region 在三种方法下都不相交；没有重复覆盖可用于宣称 C 优于 B。C 的实际收益是保留主要内容时减少部分背景。没有为提高覆盖率强制分配其余墙面、顶棚或地板；它们留给后续 Global/Dense。

bw_9064 两个独立 Box 均与 Polygon 外接矩形不同，见 `geometry_audit.json`。例如 R1 的实际 Box 为 `[120,535,420,910]`，Polygon 包络为 `[123,540,417,908]`；代码只用前者生成 B。没有将包络冒充模型的独立 Box。

归一化坐标保持原样，按 `(x×width/1000,y×height/1000)` 映射到原图连续像素边界，再以像素中心采样。Box 左上含、右下不含；Polygon 扫描线填充并取并集。没有钳位、删点、平滑、冲突裁剪或人工修补。

## 与 bw_0073 的对照及最终判断

1. **所有 Region 是否成功定位？** bw_9064 为 2/2 合法非空、主要内容大致保留。bw_0074 的模型确实返回四区，但整份输出拒收，不能宣称 4/4 成功。本轮整图契约通过为 1/2，这个极小样本统计不能当成未来成功概率。
2. **Polygon 是否比 Box 更保留内容？** 没有这样的普遍证据。bw_9064 两者都保留主要内容，Polygon 的收益主要是减少背景；bw_0074 无可接受结果可比较。此前 bw_0073 的 R1 壁灯遗漏也说明 Polygon 可能更不完整。
3. **是否出现相似遗漏/误覆盖？** bw_9064 未发现 bw_0073 那种明显的跨功能区冲突，但细部边缘仍不确定；仍存在功能区域间空隙背景。历史 A 的盆栽遗漏由本次 Direct 候选明显改善。bw_0074 新增了输出契约失败，不能推断其视觉质量成功或失败。
4. **能否取代复杂词表与 Mask 拼接成为默认实验方法？** 可优先研究这条更简单的候选入口；**当前还不适合替换为稳定、无需审核的默认路径**。原因包括本轮一次 Schema 失败、一次场景通过、缺少像素 GT，以及此前已出现重要内容漏项。复杂缓存 Grounding 不必作为粗 ROI 的强制前置，但仍可保留按需辅助。本轮不改变任何正式默认配置。
5. **哪些还需 Grounding / 人工审核？** bw_0074 全部 Direct ROI 均不可用，尤其 R1 需要未来独立批准的重新获取或其他 Grounding；本轮不执行。bw_9064 两区均需人工确认主体完整性和上下文范围，特别是 R1 细腿/叶尖、R2 柜脚/阴影。不能自动设置 reviewed=true。

## 当前 ROI 与 benchmark_metrics.py 的最小接入

**格式已兼容，当前候选尚未获准参与正式评分。** bw_9064 的 `B_direct_box_native/evidence.json` 与 `C_direct_polygon_native/evidence.json` 已包含原始 `image_size`、Region ID、相对 PNG Mask 路径和审核字段，可直接由现有 `benchmark_evidence.load_document()` 读取，再由 `area_mask()` 检查。加载后的原分辨率二值 Mask 与文件像素相同。原分辨率文件未显式填写 metrics，现有构造器会采用默认的 Appearance/Spatial/Statistical/Perceptual；逐项适用性应在下一阶段人工审核时确认，不能照搬预览文件的五指标列表作为有效语义证据。

下一阶段最小接线是：人工审核并在独立审核产物中冻结 Reference ROI 和适用指标/可靠性；通过 `load_document()`、`build_reference(reference_rgb, supplied)` 构造 Reference；将 Reference 与符合相同视野/坐标协议的 Render 放到同一 RGB 网格，再交给现有 `compare()`。两张图使用同一组 Reference Mask，不对 Agent Render 重新规划或 Grounding。本轮没有执行这些评分调用。

- 当前 `reviewed:false` 和 `reliability:0` 会使 ROI 条件指标保持 N/A。不能只为了产生成绩把它们改成已审核；模型分数不是真实正确概率。
- 审核的是“粗评价 ROI 可用性”，不自动意味着精确语义实例 Mask 或像素 GT，也不自动批准 `mask_reviewed`。
- 现有 `build_reference` 保留 Global，并以确定性 Dense Patch 覆盖未被有效 Region 覆盖的内容；`compare` 已对有效 Region 间的重叠使用 multiplicity 分摊，不需要本轮新增零重叠裁剪或修改公式。
- Region 名称和边界本身不足以生成 Semantic 正确性；仍需有效、经审核的语义证据或明确授权的验证。没有类别/存在性证据时 Semantic 继续 N/A。
- Spatial 的图像空间代理、Statistical 的梯度分布代理和 Perceptual 的特征需求仍按现有实现执行，不因新 ROI 自动变为物体密度或几何 GT。3D Structural Energy 完全独立。
- bw_0074 的 `rejected_regions.json` **不可**走上述评分接线；不能将 N/A 对照位当作空 Mask 输入。

## 实际检查与限制

- 付费请求前 **127 项 CPU 测试通过**。加入“契约失败不能生成 Direct Mask 或接受部分输出”的回归测试后，最终 **128 项全部通过**。
- 两图历史 Plan、原始图片来源、缩放后请求像素、精确 ID、坐标范围、顶点数、退化和自交检查已执行；bw_0074 的真实违规被拒收并完整保留。
- 原分辨率共有 **10 张可用二值 ROI Mask**：bw_0074 历史 A 四张，bw_9064 A/B/C 各两张。没有为失败的 Direct 方法创建假空 Mask。
- 离线 replay 不联网，10 张原分辨率 Mask 逐像素一致；失败图重放后仍无 Direct Mask。HTML、本地图像、现有 Evidence 加载器、原始坐标保留、冻结源码及凭证缺失检查见 `validation.json`。
- CPU 线程限制为 2；没有 GPU、SAM3、DINO、SLIC 推理，没有 Blender、Agent、VLM 自我验证、局部扰动、正式五能量或结构评分。没有下载依赖、修改共享环境或自动提交 Git。
- 没有人工 GT，因此不计算 IoU、Boundary F1 或真实分割准确率。两次独立响应也不足以估计随机稳定性。

## 离线复现：不产生新付费请求

在 Project e 根目录执行，输出目录必须尚不存在：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /home/xymo/environments/relateanything-inference/bin/python \
  scripts/vlm_direct_grounding.py replay \
  --source results/vlm_direct_grounding_cross_scene/bw_0074 \
  --output results/vlm_direct_grounding_cross_scene_replay/bw_0074

OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /home/xymo/environments/relateanything-inference/bin/python \
  scripts/vlm_direct_grounding.py replay \
  --source results/vlm_direct_grounding_cross_scene/bw_9064 \
  --output results/vlm_direct_grounding_cross_scene_replay/bw_9064
```

replay 读取保存的实际响应/既有 Plan，不调用 API；失败图仍显示 N/A。各图 `report.md` 提供本地说明，源码快照见 `source_snapshot/`，离线与最终测试日志均在本目录。本轮预算已用完，完成后停止等待人工审核。
