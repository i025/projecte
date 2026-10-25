# 最近的重要实验

整理日期：2026-10-25（Asia/Shanghai）。这是公开阅读入口，不是正式成绩。以下候选均为 `reviewed:false`、`provisional/debug`；原始回答、失败、Unknown/N/A 和相机限制不改写。公开修订以实际 Git Commit SHA 为准。

日期按原报告的文件时间（mtime，Asia/Shanghai）分组，不冒充无法核实的实际推理日期。完整历史见 [实验索引](README.md)；缺图和历史链接说明见 [公开内容说明](PUBLICATION_NOTES.md)。

## M2 Reference Evidence + Real VLM End-to-End（2026-10-25；审核分支，未合并 main）

| 实验 | 已获得的结论 | 图像 | 报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| 保存的 M1 RGB → Reference-only 规划 → 真实 VQA → Offline | 三次真实 Codex CLI 调用无重试；自动规划 1 区、2 条命题，两侧均回答数量2、左右关系yes，均satisfied；已知位移被粗命题漏检，图像Appearance仍响应。373项CPU测试通过，新增20项。 | [自制 comparison.png](m2_reference_vlm_e2e/comparison.png) | [总结与复现](m2_reference_vlm_e2e/summary.md) · [冻结证据](m2_reference_vlm_e2e/reference_evidence.json) · [真实回答](m2_reference_vlm_e2e/verification_results.json) · [完整报告](m2_reference_vlm_e2e/report.json) · [检查](m2_reference_vlm_e2e/validation_checks.json) | reviewed=false、provisional/debug；VLM仅诊断，条件Energy与M1一致。Group/Anchor为空，相关接口仅CPU测试。0次新Blender执行，不将回放升级可信执行；模型快照和强文件隔离未核实。Semantic/Perceptual/Structural N/A，Runtime仍blocked。 |

## Trusted Blender End-to-End Pilot（2026-10-25；审核分支，未合并 main）

| 实验 | 已获得的结论 | 图像 | 报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| 实际受控 CPU Blender → Offline | 两次真实串行渲染，实际T0/K/设置相同；RGB、Depth、Object-ID和9组件Geometry同次导出，进入完整离线报告。Baseline有效图像误差0，移动红色主体后Appearance为0.03928318，固定局部0.17462874。 | [自制 comparison.png](trusted_blender_e2e_pilot/comparison.png) | [总结与复现](trusted_blender_e2e_pilot/summary.md) · [完整报告](trusted_blender_e2e_pilot/report.json) · [执行检查](trusted_blender_e2e_pilot/integration_checks.json) · [CPU测试](trusted_blender_e2e_pilot/cpu_tests.json) | 353项CPU回归通过，新增15项；0次VLM调用。已实际观察可信Fixture执行，不是正式Agent成绩。Semantic/Perceptual/Structural N/A，Spatial/Statistical仍是图像代理。旧VLM回答缺配对信息时拒配；静态布尔/匹配相机不授予正式资格；reviewed=false、provisional/debug，Runtime仍blocked。 |

## VLM Verification Adapter 集成（2026-10-25；审核分支，未合并 main）

| 实验 | 已获得的结论 | 图像 | 报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| Codex CLI · 书籍清晰正负对照 | Python通过codex exec图片输入获得两次合法JSON；横放yes→no、竖放yes→yes；统一Manifest只附加诊断。新增19项Adapter测试，完整CPU回归338项通过。 | [自制 comparison.png](vlm_adapter_integration/comparison.png) | [报告](vlm_adapter_integration/report.md) · [真实回答](vlm_adapter_integration/verification_results.json) · [集成检查](vlm_adapter_integration/integration_checks.json) | reviewed=false、provisional/debug；仅两张清晰合成图。请求gpt-6-sol，远端快照未知；临时cwd/只读并非强文件隔离。不将VQA回答转成Energy，不与Desktop Subagent或Ofox混同；公开副本仅路径脱敏，源码Diff以审核分支提交为准。 |

## Offline Evaluation Integration MVP（2026-10-25；审核分支，未合并 main）

| 实验 | 已获得的结论 | 图像 | 报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| Manifest 离线集成 · bw_0073 + CPU Synthetic | 复用四个核心函数跑通固定 ROI 与有效像素比较；阻止非 T0/外部布尔声明产生正式有效状态；Group/结构候选统一附入但不评分。发布回归完整 319 项通过，其中集成专用 19 项；原实验的 89 项记录保留。 | [自制 Synthetic PNG](offline_integration_mvp/synthetic_control/comparison.png)；真实比较 PNG/Mask 仅留服务器，第三方原图/衍生图许可未确认。 | [发布审查](offline_integration_mvp/release_review/report.md) · [集成报告](offline_integration_mvp/summary.md) · [真实 JSON](offline_integration_mvp/bw0073_checked/report.json) · [接口检查](offline_integration_mvp/bw0073_checked/integration_checks.json) · [全量测试](offline_integration_mvp/release_review/cpu_tests_final.json) · [公开边界](offline_integration_mvp/PUBLICATION.md) | 审核分支 feat/offline-integration-mvp；不合并 main。历史相机不合规；Semantic/Perceptual/3D N/A，Spatial/Statistical 仅既有图像代理。保留首次全量回归的两项冻结校验失败及最小兼容修复；原始结果不改写。可信执行绑定仍缺。 |

## 结构证据与跨场景验证（2026-10-24）

| 实验 | 已获得的结论 | 图像 | 原报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| Kitchen Structural Transfer · bw_0073/R4 | 两侧独立回答得到三条粗一致、一条“上下抽屉样前面板 / 并排竖向门板”差异候选。 | `comparison.png` 在服务器，未公开：含许可未确认的 Reference/Render 像素。 | [报告](kitchen_structural_transfer_bw0073/report.md) · [逐条结构证据](kitchen_structural_transfer_bw0073/structural_evidence.json) | 未审核；历史相机不同，Reference 相机未知；对象级几何佐证 N/A，不认定为正式三维错误。 |
| Structural Layout · bw_0074/R3 | 纯视觉提取受局部裁切及 Reference 第二层疑似漏检影响；几何只支持有条件的结构差异候选。 | `comparison.png` 在服务器，未公开：第三方图片及衍生图再分发许可未确认。 | [报告](structural_layout_bw0074/report.md) · [Reference 拓扑](structural_layout_bw0074/topology_reference.json) · [Render 拓扑](structural_layout_bw0074/topology_render.json) · [比较](structural_layout_bw0074/topology_comparison.json) | 未审核；柜体外框、内部隔板和封套边缘须区分；不以柜格数简单相减评分。 |
| 局部结构可比较性 · bw_0074/R3 | 三条层板一致、两条几何条件性差异假设可独立保留；第二层冲突等命题继续 Unknown。 | 真实图 `comparison.png` 未公开；可读自制 [present](structural_local_comparability_bw0074/synthetic_present.png)、[absent](structural_local_comparability_bw0074/synthetic_absent.png)、[cropped](structural_local_comparability_bw0074/synthetic_cropped.png)。 | [报告](structural_local_comparability_bw0074/report.md) · [结构证据](structural_local_comparability_bw0074/structural_evidence.json) | Oracle 合成测试验证比较逻辑，不验证 VLM 识别；精确对应及 Reference 第二层待人工审核。 |
| Structural Visual Verifier · 自制合成 | 三次单图实际回答为 present / absent / unknown。 | [自制 comparison.png](structural_visual_verifier_controls/comparison.png) | [报告](structural_visual_verifier_controls/report.md) · [真实回答](structural_visual_verifier_controls/verification_results.json) | Codex Subagent 后端；遮挡标签未独立审核，不计算准确率；简单合成结果不证明真实图泛化。 |
| Group Spatial Distribution · bw_0074/R3 | Reference 六个清晰柜格候选及一个不确定单元；生成侧有三层可见支持，但两种单元定义不等价。 | `comparison.png` 在服务器，未公开：含未获图片再分发确认的原图/衍生图。 | [报告](group_spatial_distribution_bw0074/report.md) · [空间分布](group_spatial_distribution_bw0074/distribution.json) | 不能用 7−3 作为错误数；连续密度/分布误差 N/A，未将世界 Z 层架当作 Reference 柜格 GT。 |

## 生成侧几何与可见性（2026-10-23）

| 实验 | 已获得的结论 | 图像 | 原报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| Group Visibility · bw_0074/R3 | 已有低分辨率 IndexOB Pass 为候选主体提供考虑遮挡的像素支持；228/241 个候选 Mesh 在该次采样有像素。 | `comparison.png`、`visibility_mask.png` 均在服务器，因衍生内容许可未确认而未公开。 | [报告](blender_group_visibility_bw0074/report.md) · [可见性与成本记录](blender_group_visibility_bw0074/visibility.json) | 不是唱片数量，也不是历史 PNG 的精确 Mask；读取器版本、透明度、薄片采样和边缘均有限制。 |
| Reference–Blender Group Evidence | Group 支持中约 12.51% 位于固定 R3 左缘之外；生成侧层分布可重算。 | `comparison.png` 在服务器，未公开：Reference/Render 及衍生图许可未确认。 | [报告](reference_blender_group_evidence_bw0074/report.md) · [属性对照](reference_blender_group_evidence_bw0074/group_evidence_comparison.json) · [Scene Graph](blender_scene_graph_audit_bw0074/scene_graph.json) | 名称、几何、可见像素与 VLM 类别回答不能互作 GT；Reference 无同定义 Mask，相机不同，跨侧误差 N/A。 |

## 固定 ROI 与真实 Render（2026-10-22）

| 实验 | 已获得的结论 | 图像 | 原报告与数据 | 审核状态及局限 |
| --- | --- | --- | --- | --- |
| Real Render Comparison · bw_0073 | 一个真实配对、37 个固定范围的 Appearance/Perceptual 诊断。Region 按功能组织局部差异，但未证明数值上优于普通 ROI。 | `comparison.png` 和 `details/` 局部 PNG 在服务器，因真实图片及衍生图许可未确认而未公开；原报告链接的 HTML 也不上传。 | [报告](region_first_real_render_bw0073/report.md) · [实际数值](region_first_real_render_bw0073/metrics.csv) · [配对/相机](region_first_real_render_bw0073/pair_audit.json) · [重叠](region_first_real_render_bw0073/overlaps.json) | 没有正式总分；历史相机与固定 T0 不一致，Semantic/Spatial/Statistical N/A。Polygon 存在内容移出范围和 DINO 黑色填充问题。 |

任何 `candidate_*` 只是待审核诊断。下一步需要独立人工审核、局部对应和统一相机条件；本索引不授权重跑模型、Blender 或付费请求。公开图像缺失不等于实验没有执行，也不表示可以从数字替代人工视觉审核。
