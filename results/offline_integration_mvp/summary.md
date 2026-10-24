# Offline Integration MVP — 实际结果

运行日期：2026-10-24 UTC / 2026-10-25 Asia/Shanghai。基准 Commit：`2671c129ab66260f6658faf0f741137119836089`。
本轮源码尚未 Commit/Push；该 SHA 表示审计起点，不代表本轮修改已经发布。

**已跑通一条可重复、可审计的静态离线入口；尚不是正式成绩发布流程。** 所有真实场景输出均为 `provisional/debug`、`formal_eligible:false`，未审核语义候选保留 `reviewed:false`。

最终回放：[完整报告](bw0073_checked/report.json) · [数值摘要](bw0073_checked/summary.md) · [对照 PNG](bw0073_checked/comparison.png) · [接口检查](bw0073_checked/integration_checks.json) · [有效像素](bw0073_checked/valid_pixels.png)。
合成运行：[报告](synthetic_control/report.json) · [自制 PNG](synthetic_control/comparison.png)。
测试：[最终结果](test_results_final.json) · [此前完整测试日志](test_results.md) · [坐标缓存一致性](replay_checks.json)。

## 四项风险复核与最小修改

| 风险 | 基准源码实况 | 本轮处理 |
| --- | --- | --- |
| evaluate / CLI | evaluate 已调用 build_reference、compare、aggregate、structural_report；原 CLI 文件输入分散，没有 Manifest，旧 writer 总是产生 HTML | 保留已有函数及命令，增加 `offline --manifest --output` 薄适配；新入口仅输出 PNG/JSON/Markdown |
| T0 与 metadata | trusted camera 新建相机并保留 Agent 内参已实现，但只验证矩阵是刚体；静态 evaluate 仅凭 fixed_extrinsics_enforced=true 就置 valid | launcher / camera constructor 数值强制指定 T0；导出前与导出 metadata 检查实际位姿；静态 metadata 只能说明数值一致性，永不自行证明可信执行 |
| 坐标与有效像素 | compare 拒绝不同尺寸；bw_0073 实验脚本已有全帧 uniform fit + alpha valid，但核心 compare 未接该支持 | 原样提取共享 fit_render；Manifest 必须指定 identity/uniform_fit 和 basis，可要求历史 transform 全字段一致；增加 valid_mask，排除补边/透明像素及跨无效边界梯度 |
| Group / Structural Layout | 证据、真实回答及局部结构比较在独立实验中；不能直接转换为可信 Energy | 原样附入统一 report.diagnostics，不升级审核、不任意转 0/1；Optional Geometry 继续通过独立 structural_report |

五类 Energy 公式、POLICY 权重、匹配算法和 3D Structural 定义未改变。新增的是有效性/适用性门控及审计字段。

## 实际执行链

1. 读取真实配对记录、Run task path、input.json 和 artifact export 映射；Reference 与 Agent 当时收到的图片逐字节一致，不用哈希。
2. 原图 7952×4333 按已保存方式 thumbnail 至 1536×837，逐像素确认与历史 working Reference 一致。
3. 读取同一次重建的真实 1672×941 RGBA Render；复用既有 fit，得到 1487×837 内容，偏移 (24,0)。新适配得到的 RGB 和 valid mask 与历史缓存逐像素一致。
4. 四个 Direct Polygon Mask 与此前真实 Render 实验的冻结 Mask 一致。未重新检测、移动、裁切或优化 ROI。
5. `build_reference → compare → aggregate` 计算原有可用像素指标；`structural_report` 因没有审核 Geometry/Triage 返回 N/A。
6. 附入一个 R2 高脚椅 Group、三条 unavailable 集合验证、历史三条 satisfied 原子回答，以及 R4 四条结构候选/比较。它们没有形成新的有效 Energy。
7. 统一生成 report.json、summary.md、comparison.png、integration_checks.json 和 valid_pixels.png；没有 HTML。

## bw_0073 的实际数值与范围

| 项目 | 数值 | 能说明什么 |
| --- | --- | --- |
| Semantic | N/A | 未审核参考语义/无本轮有效语义验证；历史回答不是 GT |
| Spatial | 0.022815 | 既有 Dense Patch 边缘空间代理；不是岛台/柜体三维布局误差 |
| Appearance | 0.212317 | Global + Dense Patch 的既有层次条件 RGB L1 |
| Statistical | 0.058073 | 既有纹理与多尺度边缘分布代理；不是唱片/物体密度 |
| Perceptual | N/A | 本轮禁止 DINO 推理，也未把历史 DINO 数值冒充本次计算 |
| 独立 3D Structural | N/A | 未提供该 Run 的已审核 Geometry/Triage |
| 条件 Observation 调试值 | 0.097735 | 仅对可用核心记录按原有权重聚合，不是正式总分/排行榜成绩 |
| Evidence Coverage | 17/46 = 36.96% | 保留未审核、未知和模型不可用项，不补零 |

Global Appearance 为 0.212347；四个 Dense Patch 分别为 0.179951、0.185333、0.260111、0.223810。

| 固定候选 ROI | 单独 Appearance | 正式贡献 |
| --- | --- | --- |
| R1 | 0.297536 | 无；reviewed:false |
| R2 | 0.270866 | 无；reviewed:false |
| R3 | 0.318984 | 无；reviewed:false |
| R4 | 0.248873 | 无；reviewed:false |

候选 ROI 内的数值只表示固定图像域上的差异，不确认语义范围正确。所有 ROI 外移、相机与可见性因素仍存在。

## 相机、重叠与门控

- 保存的实际历史位姿 z=1.5 m，指定 T0 z=2 m；内参 K 和完整位姿保存在 report.json.render_metadata。Reference 相机 unknown，历史 PNG 与 .blend 当前状态同步未重新验证。
- 新入口明确 historical_camera，正式资格 false。即使外部 JSON 的实际矩阵与 T0 相同，也只标 pose_consistent_unverified；布尔声明无法使其 valid。
- 联合有效像素 1,244,619 / 1,285,632；梯度模板安全支持 1,243,782。无效补边没有贡献图像误差。
- 候选 Region 交叠支持 17,517 像素。它们 q=0，原本就不参与核心数值聚合，也不直接相加。
- 只有彼此重叠的有效/已审核 named Region 才触发 aggregation_eligible=false；保留真实测量及 q，不裁切 ROI、不重配权重。Global 和其他可用项继续运行。该保守处理会留下局部覆盖缺口，并如实记录。
- 开发复核发现初版保护将 q=0 候选也纳入触发；现已修正并新增测试，保证新增无效候选不能移除已有有效测量。初次回放保留在 bw0073/，最终在 bw0073_checked/；本真实配对的 Energy 数值两次完全相同，不掩盖记录变化。

## 测试、未执行项与限制

最终 **89 项 CPU 测试通过**：原 Benchmark 47 + 新集成 18 + Real Render 7 + Structural 13 + Kitchen Transfer 4。已验证合法非 T0 在启动 Blender 前拒绝；布尔伪造不能创建正式有效；缺 Group、坏可选结构/渲染证据不丢 RGB；unknown/null 不补零；尺寸无合法显式映射则拒绝；alpha/padding/梯度边界不计分；重叠与 q=0 门控；旧输出目录拒绝覆盖。最初测试命令将 tests 当 Python package 导致导入错误，改用 unittest discover 后通过，未将其隐瞒为执行成功。

真实配对只读离线回放约 2 秒（精确耗时见 report.json.elapsed_seconds）；没有 Ofox、GPT 子 Agent、SAM/SLIC/DINO、GPU 或 Blender 执行。未开展正式排行榜，也未更改 Runtime blocked 状态。实际 Blender 导出路径只修改并静态检查，没有在本轮运行验证；不能宣称渲染执行回归已完成。

仍需独立步骤：Reference Region Planning/Grounding、Group/结构证据提取及人工审核、真实验证器运行、受控可信渲染与几何导出。本入口消费已有结果，不自动触发它们。

成为正式 MVP 仍受以下条件限制：可信执行与 RGB/metadata 绑定尚未接入；未审核候选和相机差异不能构成正式 GT；有效的 Group 比较定义与定位/验证仍缺；重叠局部聚合目前保守暂缓；Perceptual/3D 缺少本轮可用输入；核心还依赖未随公开仓库提供的 sibling scene-benchmark，真实配对、Mask 及图像再分发许可也未齐备。

## 复现与交付

从项目根目录，使用既有兼容 Python 环境，不安装依赖、不推理模型：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B -m e_harness.benchmark offline --manifest results/offline_integration_mvp/inputs/bw0073_manifest.json --output /tmp/projecte-offline-bw0073-new
/home/xymo/environments/relateanything-inference/bin/python -B -m e_harness.benchmark offline --manifest results/offline_integration_mvp/inputs/synthetic_manifest.json --output /tmp/projecte-offline-synthetic-new
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_benchmark*.py'
```

输出目的地必须不存在，运行需要 Manifest 所指的本机原有数据。合成输入在 inputs/synthetic/，真实图像及衍生 PNG 仅留服务器，不新增公开授权。

源码接口及最小 Manifest 说明见 [OFFLINE_EVALUATION.md](../../OFFLINE_EVALUATION.md)。核心改动：benchmark.py、benchmark_config.py、benchmark_evidence.py、benchmark_metrics.py、runtime/benchmark_blender.py；新增 benchmark_offline.py 和 test_benchmark_offline.py；旧 region_real_render.py 仅改为复用同一 fit_render。README 与结果索引更新；没有 Commit/Push。完成后停止，待人工审核。
