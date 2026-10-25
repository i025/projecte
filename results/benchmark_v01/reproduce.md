# Reproduce / resume

Use the declared Python dependencies, compatible sibling scene-benchmark, local input RGB at dataset_manifest paths and locally authenticated Codex CLI. Do not copy credentials.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -B -m e_harness.benchmark batch --config configs/benchmark_v01.yaml
```

This command makes real model requests only for never-reserved stages. Same frozen output resumes without retries; changed config/prompts are rejected. All reserved interruptions remain unavailable. For a new model experiment choose a new output and freeze it first. No model-generated Python is executed by this entry without a qualified executor; currently execution is blocked. No model request is made by the legacy offline/replay entry.
