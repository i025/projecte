# metric_corrections_20261020：公开整理说明

本文件为2026-10-24新增的发布索引说明，不是新实验或重新审核。原有JSON/CSV和执行结果未修改；历史HTML和二进制中间文件不纳入公开版。

以下字段直接摘录自原 summary.json，不重新计算分数或修改失败状态：

```json
{
  "success": true,
  "tests": {
    "unit": 47,
    "controlled_dino": 15,
    "controlled_without_model": 12,
    "blender": 52
  },
  "unresolved_failures": 0,
  "gpu_used": false,
  "skipped": {
    "gpu": "nvidia-smi failed to communicate with driver in two observations",
    "vlm": "No paid API or live VLM invoked; semantic oracles validate metric logic only",
    "agent": "No real Agent code replay; Runtime remains blocked"
  },
  "limitations": [
    "Synthetic occupancy is an oracle, not real-image object-density accuracy.",
    "Gradient-only distribution remains an edge proxy; texture responds to brightness.",
    "DINO is not a monotonic displacement ruler; appearances saturate after leaving the reference bbox.",
    "No calibrated weights, probabilities, rankings or real-world accuracy conclusions."
  ]
}
```

公开数据：

- [blender_before_after.json](blender_before_after.json)
- [blender_smoke/baseline/reference_evidence.json](blender_smoke/baseline/reference_evidence.json)
- [blender_smoke/billboard/reference_evidence.json](blender_smoke/billboard/reference_evidence.json)
- [blender_smoke/color/reference_evidence.json](blender_smoke/color/reference_evidence.json)
- [blender_smoke/deleted/reference_evidence.json](blender_smoke/deleted/reference_evidence.json)
- [blender_smoke/distribution/reference_evidence.json](blender_smoke/distribution/reference_evidence.json)
- [blender_smoke/moved/reference_evidence.json](blender_smoke/moved/reference_evidence.json)
- [blender_smoke/penetration/reference_evidence.json](blender_smoke/penetration/reference_evidence.json)
- [blender_smoke/summary.json](blender_smoke/summary.json)
- [controlled/response_matrix.csv](controlled/response_matrix.csv)
- [controlled/summary.json](controlled/summary.json)
- [controlled_cpu_only/response_matrix.csv](controlled_cpu_only/response_matrix.csv)
- [controlled_cpu_only/summary.json](controlled_cpu_only/summary.json)
- [summary.json](summary.json)

图片和本机运行依赖的公开范围见 [PUBLICATION.md](../../PUBLICATION.md)。
