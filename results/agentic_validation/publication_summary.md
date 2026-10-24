# agentic_validation：公开整理说明

本文件为2026-10-24新增的发布索引说明，不是新实验或重新审核。原有JSON/CSV和执行结果未修改；历史HTML和二进制中间文件不纳入公开版。

以下字段直接摘录自原 summary.json，不重新计算分数或修改失败状态：

```json
{
  "client_date": "2026-10-20",
  "real_api_calls": 0,
  "gpu_used": false,
  "skipped": {
    "gpu": "nvidia-smi could not communicate with NVIDIA driver on two observations",
    "vlm": "No authorized verified VLM; unavailable paths tested with no API calls",
    "sam2_relations": "Existing candidates reused; no new model inference requested",
    "real_agent_replay": "Requires per-submission human review/approval; unattended runtime remains blocked"
  },
  "limitations": [
    "Provisional weights/thresholds, feature/texture proxies; no statistical calibration or calibrated confidence.",
    "Synthetic oracles validate implementation, not real-image reconstruction accuracy.",
    "Structural coverage is incomplete; valid checks do not establish a globally correct scene."
  ]
}
```

公开数据：

- [cli_evaluation/reference_evidence.json](cli_evaluation/reference_evidence.json)
- [cli_evaluation/report.json](cli_evaluation/report.json)
- [data_pass_checks.json](data_pass_checks.json)
- [summary.json](summary.json)

图片和本机运行依赖的公开范围见 [PUBLICATION.md](../../PUBLICATION.md)。
