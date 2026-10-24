# Offline Evaluation Integration MVP

This entry evaluates existing images, using `build_reference()`, `compare()`,
`aggregate()` and independent `structural_report()`. It does not run a model,
VLM client, Agent or Blender. The five Energy definitions and policy weights
are unchanged. The existing `evaluate`, `render`, `pilot` commands remain
available; the new entry writes PNG/JSON/Markdown without HTML.

```bash
python3 -B -m e_harness.benchmark offline \
  --manifest /absolute/path/manifest.json \
  --output /absolute/path/new-output-directory
```

Use the existing compatible environment; no extra dependencies are introduced.
The sibling `scene-benchmark` import dependency and dataset permissions described
in [REPRODUCING.md](REPRODUCING.md) still apply. This MVP does not make a public
checkout self-contained.

Release review and public-file boundaries are recorded in
[the release review](results/offline_integration_mvp/release_review/report.md)
and [the publication subset](results/offline_integration_mvp/PUBLICATION.md).

## Manifest

Paths are relative to the manifest file, or absolute. Only the two RGB paths
and explicit coordinates are required. Reference Evidence may be omitted for
Global/Dense RGB diagnostics. If supplied, invalid Reference Evidence stops the
run; missing/malformed optional evidence is recorded as unavailable.

```json
{
  "reference_rgb": "reference.png",
  "render_rgb": "saved_render.png",
  "reference_evidence": "reference_evidence.json",
  "render_evidence": null,
  "geometry": null,
  "triage": null,
  "rules": null,
  "render_metadata": "camera.json",
  "vlm_verification": "verification_results.json",
  "diagnostics": {
    "groups": "group_verification.json",
    "structural_layout": "structural_evidence.json"
  },
  "coordinates": {
    "convention": "reference_pixel_xyxy",
    "render_mapping": "identity",
    "basis": "Both images use the same documented full-frame pixel grid"
  },
  "camera_comparability": "unknown",
  "evidence_category": "historical_diagnostic"
}
```

- Coordinates are Reference pixel edges, top-left origin, x right and y down.
  Evidence `image_size` and masks must already match the Reference input. The
  adapter does not silently rescale Reference Evidence or re-detect any ROI.
- `identity` requires equal image sizes. `uniform_fit` explicitly opts into the
  existing `bw_0073` full-frame uniform resize with centered letterbox, integer
  rounding and Lanczos RGB/alpha sampling. It is display-grid conversion, not
  pose alignment or perspective correction. ROI remains fixed on the Reference.
- A previous `coordinates.expected_transform` object can be supplied; each
  recorded field must match the applied transform exactly, otherwise the run
  fails. `basis` is an explicit provenance declaration, not proof of alignment.
- Opaque alpha support from both images is intersected. An optional top-level
  `valid_pixels` binary 0/255 PNG can further restrict support. Padding and
  transparency never count as observation. Existing right/down gradient
  stencils must also lie entirely on valid support. The stricter shared support
  is recorded in the report; it does not change a metric's formula.
- Partial support conservatively withholds Semantic and Anchor-level Spatial
  verdicts that have not been revalidated for the partial image. They remain N/A.

## Camera trust and execution

`render_cpu()` and the trusted Blender camera constructor now reject even a legal
rigid matrix when it differs from the prescribed T0. The renderer checks the
actual camera pose before export and in the exported camera metadata.

Static evaluation checks actual pose fields (`camera.matrix_world`, `T_c2w`,
or `matrix_world`) numerically. `fixed_T0` is only a declaration and
`fixed_extrinsics_enforced=true` is not execution evidence. A matching external
pose remains `pose_consistent_unverified`; a different pose is
`historical_camera`. **Every static manifest report is provisional/debug and
`formal_eligible=false`**, including a numerically matching pose. No file-based
authentication or attestation system is invented here.

Before formal results can be issued, a trusted in-process render/evaluation
execution must bind the actual camera, image and evidence. This task does not
open the Runtime, rerender historical scenes or claim that binding exists.

## Group, structure and overlap

Group verification and Structural Layout JSON are attached verbatim under
`report.diagnostics`. This is a diagnostic bridge, not a numerical adapter:
yes/no/unknown and candidate mismatches never become arbitrary 0/1 Energy.
Original review states are preserved. Group membership is not inferred from ROI.

Unreviewed named ROI can still have a fixed-domain Appearance measurement under
`diagnostics.fixed_region_measurements`. That measures RGB differences within a
candidate domain, without approving its semantics or contributing its candidate
measurement to Energy. Perceptual stays N/A because this entry never runs DINO.

The existing fractional pixel support does not by itself deduplicate an average
of normalized overlapping Region losses. In this entry, overlapping eligible
(reviewed, positive-reliability) named Region records are retained but flagged `aggregation_eligible=false`; their
local aggregate stays N/A. Their reliability is not altered. Other eligible
Global/Dense or disjoint reviewed records retain the original aggregation rules
and weights. Coverage records withheld measurements. No ROI is cropped to remove
overlap, and no missing content is silently treated as correct. Reviewed named
ROI continue to exclude their pixels from fallback Dense Patch as before; an
overlap guard can therefore leave local gaps, which the report preserves rather
than optimizing away. Global retains its original full valid support.
Unreviewed/q=0 candidates cannot trigger this guard against an existing valid
measurement. Their overlaps remain visible in diagnostic statistics.

3D Structural Energy remains separate from image Structural Layout diagnostics.
Unavailable geometry/triage/rules do not discard available image measurements.
Unknown/N/A is serialized as JSON null, never zero. Spatial and Statistical
image-edge/texture proxies keep their existing meanings; they do not certify
object layout, density or geometry.

## Optional visual Verification Adapter

`vlm_verification` is an optional **already-produced** adapter result JSON. The
offline command imports it into `report.diagnostics.vlm_verification`, validates
raw answers again and recomputes the deterministic comparisons. It never starts
Codex, Ofox or another model. Missing/malformed results stay unavailable without
discarding RGB metrics. Failed requests cannot reuse an apparent answer; a
missing field preserves other valid fields. `unknown` and `unavailable` remain
non-numeric. Every imported result stays unreviewed, debug-only and excluded
from Energy, even if its supplied verdict or review flag claims otherwise.

New result bundles must include `image_pair` with `reference_rgb` and
`render_rgb`, relative to the verification JSON or absolute. They must resolve
to the current Manifest images; recorded per-side `image_binding.source_rgb`
must also agree when supplied. CLI packets now record their source image path.
Old unbound answers and wrong/swapped pairs are retained as `unmatched_evidence`
with `status=unavailable`, never attributed to the current pair. Explicitly
bound Mock/replay packets remain labelled as such. This is association checking,
not authentication against replacing image contents at the same path. Original
historical JSON is not retroactively given a binding.

The small Python adapter in `e_harness.verification_adapter` supports:

- `codex_answer(image, contract, ledger=..., model='gpt-6-sol')`: one independent
  `codex exec --image` invocation with JSON Schema, a temporary input directory,
  read-only sandbox, disabled execution/image-reader/MCP/plugin/memory tools,
  timeout and no HTTP/stream retries. Share one ledger across a pair; at most
  two attempts, no repeated image. It uses existing ChatGPT CLI login, not API keys.
- `import_subagent(record, contract)`: imports an existing Desktop subagent's
  exact raw answer and recorded prompt/model/usage. This launches no subagent.
- `replay(raw, contract, source_kind='historical_real' or 'mock')`: no model or
  network. Mock provenance remains explicit.

The present pilot intentionally supports the existing two-field book answer
schema only; this is not a general object verifier. The transport can later be
reused with an explicitly validated schema for another frozen question set.
The contract allowlist is `system`, `user`, `schema`; expectations and other-side
answers belong to the coordinator and must never be added to that contract.
No `ModelClient` provider API route is changed. Existing book parsing/comparison
and `model_client.token_counts()` are reused.

**Isolation limit:** read-only does not restrict reading to the temporary cwd.
The CLI retains its global system context and login state; disabling its tools
reduces exposure but is not a filesystem access guarantee or strict blind test.
The local preflight checks one decoded image and the exact prompt without
persisting Base64. A CLI-selected model name does not prove the remote model
snapshot; if no observed identifier is returned, it stays null. CLI token usage
includes platform context and is not equivalent to Ofox billing.

The audited server uses CLI 0.163.0. It rejects overrides to its built-in
`openai` provider, so the adapter uses a per-process provider definition pointing
to the official ChatGPT Codex endpoint with zero request/stream retries. No
shared config or credentials are written. An installation with different CLI
capabilities should fail preflight, not silently enable execution or retry.

The existing two-image fixture can be replayed without any inference:

```bash
python3 -B scripts/vlm_adapter_pilot.py prepare --output /tmp/projecte-adapter-new
python3 -B scripts/vlm_adapter_pilot.py finish --backend replay --output /tmp/projecte-adapter-new
python3 -B -m unittest discover -s tests -p 'test_verification_adapter.py'
```

It requires the authorized existing synthetic images and the saved calibration
records on the server. `--backend subagent_import` imports those same original
sessions. `--backend codex_cli` is a separate, explicitly selected live operation
and requires request authorization; never run it as an installation test. The
pilot reserves its run before inference and refuses to resume/retry a started
run. See [this integration experiment](results/vlm_adapter_integration/report.md).

## Trusted Blender fixture closure

The separate bounded controller accepts only a new output directory and uses
the existing source-controlled `baseline` and `moved` fixtures. It never accepts
Agent Python, arbitrary scene paths or a saved execution receipt as trusted:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python3 -B -m e_harness.benchmark_trusted \
  --output /tmp/projecte-trusted-fixture-new
```

This command **actually launches two serial CPU Blender jobs** with the existing
namespace launcher, two render threads/two-CPU affinity, 8 samples, 256×256 and
existing time/memory/cleanup limits. Check server resources first. It validates
actual same-run source/config, camera before/after export, T0, K, RGB/Depth/ID
grid correspondence, binary ID masks and evaluated Geometry components before
calling the unchanged offline metrics. Reference candidate ROI is frozen from
Baseline before Changed exists. The actual renderer is still the whitelisted
`e_harness/runtime/benchmark_blender.py`; it now additionally exports execution
metadata without changing scene generation or metric definitions.

`execution_chain.json` is an audit trail produced by this controller. It is not
a certificate that can be imported to upgrade a static replay. The controller
can report observed trusted synthetic execution while the standalone evaluator
remains `pose_consistent_unverified` and `formal_eligible=false`. The launcher's
legacy `scene_validity=valid` means successful render execution only. No matching
camera matrix, boolean or arbitrary receipt confers formal Benchmark status.
Unreviewed Group/semantic/structural evidence remains excluded from Energy.

Outputs include `comparison.png`, `report.json`, `integration_checks.json`,
`summary.md`, both per-scene exports and fixed-coordinate Manifest evaluations.
No HTML, VLM, GPU, SAM/SLIC/DINO or Agent execution is involved. See the
[actual synthetic pilot](results/trusted_blender_e2e_pilot/summary.md). Formal
Runtime stays blocked. The sibling evaluator/Blender dependencies and real
Reference evidence/verification limitations still apply.

## Outputs and tests

Each new output directory contains `report.json`, `summary.md`,
`comparison.png`, `integration_checks.json` and `valid_pixels.png`.
The JSON retains every planned core metric, actual participating weights,
coverage, sources, attached diagnostic evidence and camera limitations.

```bash
python3 -B -m unittest discover -s tests -p 'test_benchmark*.py'
python3 -B -m unittest discover -s tests -p 'test_real_render.py'
python3 -B -m unittest discover -s tests -p 'test_structural*.py'
python3 -B -m unittest discover -s tests -p 'test_kitchen_structural_transfer.py'
```

These tests use deterministic pixels/Oracle evidence and existing JSON only;
they do not establish real visual-verifier quality or Blender runtime safety.
The new integration experiment is in
[`results/offline_integration_mvp/`](results/offline_integration_mvp/summary.md).
Do not run `tests/run_tests.py` as a CPU-only check.

The release review also ran the complete `tests/test_*.py` suite: 319 tests,
including 19 integration-specific tests. All passed with real network and
subprocess execution blocked. The three existing first-party source snapshots
needed by legacy freeze tests are included as test inputs, without changing
their bytes or bypassing their checks. `benchmark_evidence.py` remains identical
to the baseline; shared `fit_render` lives in `benchmark_offline.py` and remains
importable through the historical `scripts.region_real_render` binding.
The new keyword arguments default to legacy behavior; camera validation is
deliberately stricter. The release fix also treats wrong-shaped optional Render
Evidence JSON as unavailable instead of discarding RGB measurements.
