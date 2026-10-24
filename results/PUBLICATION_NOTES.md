# 公开内容、缺图与历史链接说明

本文件是 2026-10-24 新增的发布说明，不是新实验或重新审核。原始实验 JSON/CSV/报告不回写，原始文件也未从服务器删除。所有未审核候选保持其原状态。最近研究见 [LATEST.md](LATEST.md)，全部实验见 [README.md](README.md)，复现前提见 [REPRODUCING.md](../REPRODUCING.md)。

## 近期核心实验图片核对

Offline Integration MVP 的后续审核分支材料见[公开子集说明](offline_integration_mvp/PUBLICATION.md)及[发布审查](offline_integration_mvp/release_review/report.md)。其真实比较图和 valid-pixel Mask 仍排除，只有自制合成 PNG 纳入。为运行历史 CPU 冻结回归，本轮补入三个已有的第一方源码快照；原副本未改动，不包含模型或第三方像素。原实验与本轮测试记录分别保留，不能把旧的本地未发布快照当作当前 GitHub 状态。

这些真实场景图片已存在，不是实验漏做。现有 BlenderWorld 软件 MIT 说明不足以确认每张参考图片及衍生内容的再分发权，因此不补传、不替换、不人工重画它们。原始图片、Mask 和 HTML 仍在服务器。

| 项目内路径（非公开下载链接） | 服务器状态 | 公开状态 / 原因 |
| --- | --- | --- |
| `structural_layout_bw0074/comparison.png` | 存在，[2400, 1770] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `structural_local_comparability_bw0074/comparison.png` | 存在，[2040, 1930] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `structural_local_comparability_bw0074/reference_row2_review.png` | 存在，[1660, 860] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `structural_visual_verifier_controls/comparison.png` | 存在，[3120, 1250] | 已纳入：本项目自制合成图 |
| `blender_group_visibility_bw0074/comparison.png` | 存在，[3120, 1225] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `blender_group_visibility_bw0074/visibility_mask.png` | 存在，[512, 347] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `group_spatial_distribution_bw0074/comparison.png` | 存在，[2490, 1850] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `kitchen_structural_transfer_bw0073/comparison.png` | 存在，[2460, 1860] | 未公开：第三方参考/Render 或衍生内容许可未确认 |
| `region_first_real_render_bw0073/comparison.png` | 存在，[1700, 1010] | 未公开：第三方参考/Render 或衍生内容许可未确认 |

许可依据：[BlenderWorld 数据集说明](https://huggingface.co/datasets/Qwen/BlenderWorld) 限定 MIT 声明为 adapter/evaluator 代码；没有据此推定图片再分发获准。其软件许可见 [官方 LICENSE](https://github.com/QwenLM/BlenderWorld/blob/main/LICENSE)。需要逐项确认 Reference、历史 Agent Render 及衍生图的公开范围。

## 精简与保留

仅从待提交清单移除下列文件，服务器原件不删改。相同答案若来自不同的实际请求，或相同图片作为另一实验的固定对照，均保留；不能把科学上有意义的重复当成冗余。旧/checked 敏感性矩阵有真实数值差异，也继续保留。

| 未纳入路径 | 原因 | 保留的公开记录 |
| --- | --- | --- |
| `vlm_region_hierarchy_review/records/bw_9064/vlm_plan.json` | 重复审查副本，原始记录仍保留 | [vlm_region_hierarchy/bw_9064/vlm_plan.json](vlm_region_hierarchy/bw_9064/vlm_plan.json) |
| `vlm_region_hierarchy_review/records/report.md` | 重复审查副本，原始记录仍保留 | [vlm_region_hierarchy/report.md](vlm_region_hierarchy/report.md) |
| `vlm_region_hierarchy/bw_0074/evidence.json` | 层级候选的中间 benchmark 导出；保留合并层级、Plan、回答和失败 | [vlm_region_hierarchy/hierarchy.json](vlm_region_hierarchy/hierarchy.json) |
| `vlm_region_hierarchy/bw_9064/evidence.json` | 层级候选的中间 benchmark 导出；保留合并层级、Plan、回答和失败 | [vlm_region_hierarchy/hierarchy.json](vlm_region_hierarchy/hierarchy.json) |
| `multiscene_region_extraction/post_exit_resources.json` | 服务器资源/进程状态快照，不是必要科学结果 | 相关原报告及成本记录保留 |
| `region_grounding_conflict_resolution/resource_checks.json` | 服务器资源/进程状态快照，不是必要科学结果 | 相关原报告及成本记录保留 |
| `vlm_region_hierarchy/resource_checks.json` | 服务器资源/进程状态快照，不是必要科学结果 | 相关原报告及成本记录保留 |
| `blenderworld_runs_inventory/inventory.csv` | 含完整第三方任务原文及服务器运行目录清单；公开范围未确认，改为事实字段摘录 | [blenderworld_runs_inventory/publication_inventory.json](blenderworld_runs_inventory/publication_inventory.json) |
| `blenderworld_runs_inventory/selected.csv` | 含完整第三方任务原文及服务器运行目录清单；公开范围未确认，改为事实字段摘录 | [blenderworld_runs_inventory/publication_inventory.json](blenderworld_runs_inventory/publication_inventory.json) |

新增的 `publication_inventory.json` 只是原清单的事实字段摘录，不是重新筛选或新 GT，不含原任务全文、图片或宽泛的服务器路径列表。

## 所有原报告的不可公开/缺失链接

原报告保留当时的链接和相机、失败声明，未为了 GitHub 可读性改写历史文件。下表是逐文件检查 Markdown 实际链接得到的遗漏清单；新索引不将这些路径伪装为可下载资产。代码块里的历史命令和 JSON 中的本地 provenance 路径也不能直接在公开 clone 上运行，参见复现说明。

| 原文档及行号 | 原链接（非公开下载链接） | 原因 |
| --- | --- | --- |
| [EXPERIMENT_HISTORY.md:5](../EXPERIMENT_HISTORY.md) | `runs/scene_064_gpt6_sol_20261014/final_report.md` | 历史路径在服务器也已缺失，不补造 |
| [results/atomic_evidence_discriminability_bw0073/report.md:5](atomic_evidence_discriminability_bw0073/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/blenderworld_runs_inventory/report.md:59](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/scene_064-harbor/task/environment/inputs/references/image_01.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:59](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/scene_064-harbor-generation/scene_064/task__LY4dtPw/artifacts/workspace/exports/final.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:59](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/scene_064-harbor-generation/scene_064/task__LY4dtPw/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:75](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0074/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:75](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/modern_living_room.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:75](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:91](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/codex-fixed-camera-v1-reference-pair/bw_0073/task/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:91](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:91](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:107](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/bw_0073-codex-fixed-camera-v1-official-query/task/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:107](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-official-query-generation/bw_0073/task__Dpf9tyA/artifacts/workspace/exports/final.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:107](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-official-query-generation/bw_0073/task__Dpf9tyA/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:123](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/bw_0073-official-harbor/task/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:123](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/bw_0073-official-harbor-continued/bw_0073/task__qtzUWks/artifacts/workspace/exports/render.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:123](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/bw_0073-official-harbor-continued/bw_0073/task__qtzUWks/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:139](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0063/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:139](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0063/bw_0063__Lj7uE6T/artifacts/workspace/exports/coastal_living_dining.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:139](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0063/bw_0063__Lj7uE6T/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:155](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0043/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:155](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0043/bw_0043__p7isE6U/artifacts/workspace/exports/final.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:155](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0043/bw_0043__p7isE6U/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:171](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0006/environment/inputs/references/image_01.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:171](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0006/bw_0006__gfHGhky/artifacts/workspace/exports/final.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:171](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0006/bw_0006__gfHGhky/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/blenderworld_runs_inventory/report.md:187](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0075/environment/inputs/references/image_01.jpg` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:187](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0075/bw_0075__nVjEut5/artifacts/workspace/exports/mountain_blue_oil_painting.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/blenderworld_runs_inventory/report.md:187](blenderworld_runs_inventory/report.md) | `../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0075/bw_0075__nVjEut5/artifacts/workspace/exports/final.blend` | 源场景/数据位于仓库外，未随项目发布 |
| [results/bw_9064_evidence_review/summary.md:53](bw_9064_evidence_review/summary.md) | `review.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/bw_9064_evidence_review/summary.md:53](bw_9064_evidence_review/summary.md) | `region_overlay.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/bw_9064_evidence_review/summary.md:53](bw_9064_evidence_review/summary.md) | `anchor_overlay.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/coarse_evaluation_roi_bw0074/report.md:5](coarse_evaluation_roi_bw0074/report.md) | `comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/coarse_evaluation_roi_bw0074/report.md:47](coarse_evaluation_roi_bw0074/report.md) | `per_region/R1_comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/coarse_evaluation_roi_bw0074/report.md:47](coarse_evaluation_roi_bw0074/report.md) | `per_region/R2_comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/coarse_evaluation_roi_bw0074/report.md:47](coarse_evaluation_roi_bw0074/report.md) | `per_region/R3_comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/coarse_evaluation_roi_bw0074/report.md:47](coarse_evaluation_roi_bw0074/report.md) | `per_region/R4_comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/coarse_evaluation_roi_bw0074/report.md:47](coarse_evaluation_roi_bw0074/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/group_books_review_bw0074/report.md:16](group_books_review_bw0074/report.md) | `books_region_detail.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:17](group_books_review_bw0074/report.md) | `orientation_details.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:18](group_books_review_bw0074/report.md) | `r2_r3_edge.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:19](group_books_review_bw0074/report.md) | `distribution_grid_proposal.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:21](group_books_review_bw0074/report.md) | `books_region_detail.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:23](group_books_review_bw0074/report.md) | `orientation_details.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:25](group_books_review_bw0074/report.md) | `r2_r3_edge.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/group_books_review_bw0074/report.md:64](group_books_review_bw0074/report.md) | `distribution_grid_proposal.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/multiscene_region_extraction/report.md:156](multiscene_region_extraction/report.md) | `post_exit_resources.json` | 重复/中间记录已精简，见规范文件映射 |
| [results/region_atomic_verification_bw0073/report.md:5](region_atomic_verification_bw0073/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/region_atomic_vlm_r2_bw0073/report.md:5](region_atomic_vlm_r2_bw0073/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/region_first_e2e_generalization/report.md:37](region_first_e2e_generalization/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/region_first_real_render_bw0073/report.md:5](region_first_real_render_bw0073/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/region_first_real_render_bw0073/report.md:5](region_first_real_render_bw0073/report.md) | `failure_cases.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/region_segmentation_experiment/report.md:35](region_segmentation_experiment/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/region_segmentation_experiment/report.md:112](region_segmentation_experiment/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_box_sam_hybrid_bw0073/report.md:7](vlm_box_sam_hybrid_bw0073/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_box_sam_hybrid_bw0073/report.md:7](vlm_box_sam_hybrid_bw0073/report.md) | `comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/vlm_direct_grounding_bw0073/report.md:5](vlm_direct_grounding_bw0073/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_direct_grounding_bw0073/report.md:5](vlm_direct_grounding_bw0073/report.md) | `comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/vlm_direct_grounding_cross_scene/bw_0074/report.md:7](vlm_direct_grounding_cross_scene/bw_0074/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_direct_grounding_cross_scene/bw_9064/report.md:7](vlm_direct_grounding_cross_scene/bw_9064/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_direct_grounding_cross_scene/report.md:5](vlm_direct_grounding_cross_scene/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_direct_grounding_cross_scene/report.md:5](vlm_direct_grounding_cross_scene/report.md) | `bw_0074/comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_direct_grounding_cross_scene/report.md:5](vlm_direct_grounding_cross_scene/report.md) | `bw_9064/comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_guided_slic_grounding/report.md:7](vlm_guided_slic_grounding/report.md) | `comparison.html` | 旧 HTML 不发布，不生成替代页面 |
| [results/vlm_guided_slic_grounding/report.md:7](vlm_guided_slic_grounding/report.md) | `comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/vlm_guided_slic_grounding/report.md:7](vlm_guided_slic_grounding/report.md) | `slic_200/comparison.png` | 图片及衍生内容许可未确认，保留服务器原件 |
| [results/vlm_guided_slic_grounding/report.md:7](vlm_guided_slic_grounding/report.md) | `failure_cases/index.html` | 旧 HTML 不发布，不生成替代页面 |

新 README / LATEST / 公开说明中的实际本地链接应全部指向明确纳入清单的文件；上述原报告的历史缺口单独保留，不声称所有历史超链接都已修复。无图片许可时不会生成伪造的 comparison.png。

## 内容与复现边界

已审查完整待提交内容，包括嵌套序列化的 Provider Response、脱敏请求构造、Scene Graph、路径和清单元数据。保留的请求记录不含认证 Header、凭据或 Base64 图片正文；离线重构的请求仍标为重构，不伪称真实线缆抓包。Scene Graph 没有嵌入脚本、驱动或外部库，也未导出顶点；对象名不作 GT。

源报告保留项目所有者本机路径作为来源证据，不代表这些路径下的数据已发布。完整服务器清单、账号快照、其他用户文件、模型、运行会话及 Blend/EXR/数组缓存不发布。已知复现阻塞包括未公开分发的 sibling evaluator、合法原图和历史 Agent 输出、Mask/ID 数组及原会话；没有虚构公开下载入口或通过重新运行模型补齐。
