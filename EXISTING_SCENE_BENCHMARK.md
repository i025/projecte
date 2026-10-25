# Existing-Scene Batch Runner

`python3 -B -m e_harness.benchmark_existing --config <private.json> --output <new-directory>`
evaluates saved Reference/Agent Render pairs. This is independent of
`benchmark_batch` and has no Agent generation or Blender execution path.

The config contains `pairs` with `pair_id`, `task_id`, `run_id`,
`reference_rgb`, `render_rgb`, `completion`, and optional `camera_metadata`,
`geometry`, `scene_graph_cache`, `group_visibility_cache`, `provenance`.
Use actual task/input/export manifests to establish pair identity; a similar
filename is insufficient. The live controller defaults to `existing_scene_v1`,
10 maximum atomic questions, 768-pixel longest Reference edge and gpt-6-sol.
`dino_model` must be an existing local DINOv2 directory. No weights download.

Process:

1. Decode/thumbnail Reference RGB only; independently plan and save raw JSON.
2. Freeze Reference Regions/Groups/Anchors/questions before opening the Render.
   The separately named `reference_only_missing_other_v1` category policy saves
   raw planner categories and adds neutral `absent`/`other` options before
   freezing. Unknown/ambiguous remain abstentions. The historical v1 contracts
   and answers are unchanged. Up to twelve substantive category labels plus
   these two fallbacks are accepted; the planner schema still permits twelve.
3. Independent Reference and Render VQA use identical questions/schema/Region
   definitions and full RGB PNG preprocessing. Render undergoes a single
   declared full-frame fit on the Reference grid, with invalid letterbox/alpha
   pixels excluded from metrics. No camera optimization or registration.
4. Reuse a shared task's frozen Reference plan/VQA; each saved Agent Render has
   its own VQA. Stage reservations prevent automatic retry on resume, including
   interruption/failure. Zero observable questions skip VQA without invention.
5. Reuse `benchmark_offline.run_manifest()` with one explicitly loaded local
   CPU DINOv2 model (two threads) across the batch. Existing Global/Dense and
   candidate Region diagnostics remain distinct; overlapping ROI losses are
   never summed. No Energy definitions, weights or Runtime gates change.
6. The first two pairs must pass real planning/verification, Perceptual and
   Appearance measurement, diagnostic binding and provisional-eligibility
   checks before the controller expands to the remaining pairs. Unknowns are
   allowed; passing the gate is an integration check, not semantic accuracy.

The bounded call budget is two calls per unique Reference plus one per Render.
A new output directory entails actual model inference and requires task
authorization. Resume requires the exact frozen config and never retries a
reserved call. Raw answers and frozen evidence are immutable; derived tables
can be recomputed. Use the existing Codex CLI login, never Ofox credentials.

Outputs include root `report.json`, `per_pair_results.csv`, `evidence_audit.md`,
`summary.md`, per-reference planning and VQA packets, per-pair Render VQA and
`evaluation/{report.json,integration_checks.json,summary.md,comparison.png}`.
`valid_pixels.png`, private prepared RGBs, source size/transform records and
raw/frozen categories support audit. No HTML is created.

Coverage is reported in separate terms: actual numerical image measurements,
usable/unknown/unavailable VQA diagnostics, reviewed evidence, and formal
scores. Spatial/Statistical image proxies are not object-level layout/density
measurements. Unreviewed semantics and structural candidates remain N/A for
Energy; no categorical answer becomes an arbitrary 0/1 penalty.

Historical camera metadata is retained, with native and prepared-image domains
explicitly separated. Even matching T0 numbers cannot attest trusted execution
or PNG/blend synchronization. All historical results stay `provisional/debug`,
`reviewed:false`, and formally ineligible. Scene Graph names and bounding boxes
are auxiliary generated-side evidence, not evaluated support/collision Geometry
or Reference GT. Missing reliable geometry remains N/A; no scene is opened.

The CLI uses a temporary cwd, fixed prompt/schema, read-only sandbox and disabled
tools, but filesystem confinement and remote model snapshot are not guaranteed.
Model answers require independent human review. A `candidate_violated` status
may reflect camera, occlusion or recognition error; `satisfied` does not certify
reconstruction quality. Completed runs and failed/incomplete checkpoints must
be analysed separately, and continued runs are not independent Agents.

All third-party RGBs, crops, Masks and comparison PNGs remain server-only until
redistribution rights are established. Only curated code, tests, scientific
JSON/CSV and Markdown are published. A public clone lacks these private inputs,
local model weights and complete server inventory; it is not a standalone
reproduction of the historical dataset.

Offline tests, no actual models:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python3 -B -m unittest discover -s tests -p 'test_benchmark_existing.py'
```
