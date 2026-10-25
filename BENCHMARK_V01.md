# Real-RGB batch v0.1

This is an **actual partial run, not a completed or formally validated Benchmark**.
See [the batch report](results/benchmark_v01/benchmark_report.md),
[all selected samples](results/benchmark_v01/dataset_manifest.json),
[per-scene results](results/benchmark_v01/per_scene_results.csv), and
[one batch audit packet](results/benchmark_v01/audit_packet.md).

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 CUDA_VISIBLE_DEVICES= \
python -B -m e_harness.benchmark batch --config configs/benchmark_v01.yaml
```

The `.yaml` file uses JSON syntax, a YAML subset, to avoid a new parser dependency.
It freezes eight external RGB inputs, the existing five-Energy policy and T0,
the model, image preprocessing, and one generation with zero repairs/feedback.
The controller writes the config, selection and actual prompts before any model
request. Each scene can make at most four calls: Reference planning, independent
scene-code generation, Reference VQA, and Render VQA. The last requires a new
qualified execution, which is currently unavailable. Stages run serially.

Required local resources: the existing Python requirements, compatible sibling
`scene-benchmark`, authenticated Codex CLI, the local dataset, and local DINOv2
weights. Input/weight paths are not bundled assets. The published input list
does not grant redistribution rights or establish image-specific copyright
clearance. It is a user-authorized local research selection, not eight independently
rights-cleared photographs. Some benchmark references may be artwork or renders.

Every model task receives a freshly re-encoded, randomly named RGB in a temporary
working directory. Code generation sees only that RGB and the common reconstruction
task, never the Reference plan, answers or evaluator feedback. The CLI has tools
disabled. Global CLI context and broader filesystem readability remain limitations;
this is not strict filesystem confinement or a pure base-model evaluation.

Call reservations are written before subprocess launch. Resume never retries a
reserved call, including an interrupted attempt. Raw replies are retained locally;
syntax validation only parses Python, without importing or executing it. Failed
planning does not prevent independent generation. A failure stays in the selected
denominator. N/A values have zero availability and no fabricated zero error.

The existing supervised CPU renderer is **not** an untrusted-code sandbox. The
batch checks available execution capabilities but never interprets a boolean,
matching camera, or namespace smoke test as execution authorization. No qualified
container/VM executor is installed/configured here. Generated scene source and
pending jobs are retained; Blender, Render VQA, pairwise Energies and Structural
remain blocked/N/A. No host-only or historical-render fallback is provided.
Connecting a validated isolated executor and same-execution artifact export is
still required to complete the batch. This incomplete path is recorded, not
presented as a working render backend.

The pure offline CLI stays model-free. A trusted calling controller may explicitly
load the existing extractor and pass it to `run_manifest(..., extract=...,
extract_provenance=...)`; this reuses `compare()`'s unchanged DINO metric. A JSON
manifest cannot enable inference. The batch separately checks the real local
model on a Reference RGB; that availability check is not a pairwise Perceptual
Energy. Crop, padding and viewpoint limitations remain.

All automatic evidence stays `reviewed:false`. VQA answers are diagnostic, never
arbitrary Semantic/Spatial/Statistical penalties. Structural candidates require
triage; Agent names are claims. Fixed output T0 does not recover the unknown real
Reference camera. Human review and an eligible execution are still prerequisites
for affected formal results. No Energy formula, weight, Runtime gate or previous
experiment is changed.

Public results exclude third-party images, crops, masks, renders, generated
Blender assets, code-bearing raw Agent replies and full CLI sessions. Local
artifacts remain intact. Publication contains code, factual status/usage records,
annotation JSON and Markdown, with private paths redacted where necessary.
