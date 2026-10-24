# agentic_smoke_cpu_final：公开整理说明

本文件为2026-10-24新增的发布索引说明，不是新实验或重新审核。原有JSON/CSV和执行结果未修改；历史HTML和二进制中间文件不纳入公开版。

以下字段直接摘录自原 summary.json，不重新计算分数或修改失败状态：

```json
{
  "success": true,
  "checks": {
    "baseline_fixed_T0": true,
    "baseline_intrinsics": true,
    "baseline_data_passes": true,
    "baseline_reprojection": true,
    "baseline_vlm_unavailable": true,
    "deleted_fixed_T0": true,
    "deleted_intrinsics": true,
    "deleted_data_passes": true,
    "deleted_reprojection": true,
    "deleted_vlm_unavailable": true,
    "moved_fixed_T0": true,
    "moved_intrinsics": true,
    "moved_data_passes": true,
    "moved_reprojection": true,
    "moved_vlm_unavailable": true,
    "color_fixed_T0": true,
    "color_intrinsics": true,
    "color_data_passes": true,
    "color_reprojection": true,
    "color_vlm_unavailable": true,
    "distribution_fixed_T0": true,
    "distribution_intrinsics": true,
    "distribution_data_passes": true,
    "distribution_reprojection": true,
    "distribution_vlm_unavailable": true,
    "penetration_fixed_T0": true,
    "penetration_intrinsics": true,
    "penetration_data_passes": true,
    "penetration_reprojection": true,
    "penetration_vlm_unavailable": true,
    "billboard_fixed_T0": true,
    "billboard_intrinsics": true,
    "billboard_data_passes": true,
    "billboard_reprojection": true,
    "billboard_vlm_unavailable": true,
    "ortho_fixed_T0": true,
    "ortho_intrinsics": true,
    "ortho_data_passes": true,
    "ortho_reprojection": true,
    "ortho_projection": true,
    "identity_zero": true,
    "deletion_semantic": true,
    "movement_spatial": true,
    "color_appearance": true,
    "distribution_statistics": true,
    "penetration_detected": true,
    "billboard_detected": true,
    "vlm_unavailable_safe": true,
    "five_energies_numeric": true,
    "dino_responds_to_deletion": true
  },
  "api_calls": 0,
  "gpu_used": false,
  "skipped": [
    "GPU unavailable/not requested",
    "Live VLM: no authorized verified model",
    "Real Agent replay: human approval required"
  ],
  "scope": "Synthetic pipeline/perturbation checks; not calibrated reconstruction accuracy"
}
```

公开数据：

- [baseline/reference_evidence.json](baseline/reference_evidence.json)
- [baseline/report.json](baseline/report.json)
- [billboard/reference_evidence.json](billboard/reference_evidence.json)
- [billboard/report.json](billboard/report.json)
- [color/reference_evidence.json](color/reference_evidence.json)
- [color/report.json](color/report.json)
- [deleted/reference_evidence.json](deleted/reference_evidence.json)
- [deleted/report.json](deleted/report.json)
- [distribution/reference_evidence.json](distribution/reference_evidence.json)
- [distribution/report.json](distribution/report.json)
- [moved/reference_evidence.json](moved/reference_evidence.json)
- [moved/report.json](moved/report.json)
- [penetration/reference_evidence.json](penetration/reference_evidence.json)
- [penetration/report.json](penetration/report.json)
- [reference.json](reference.json)
- [summary.json](summary.json)

图片和本机运行依赖的公开范围见 [PUBLICATION.md](../../PUBLICATION.md)。
