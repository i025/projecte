# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. No model, API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | N/A | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.000606 | 1.000000 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.005195 | 1.000000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.001045 | 1.000000 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | N/A | 0.000000 | N/A: no DINO inference in this entry |

Conditional Observation: 0.002282; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 630784/630784; gradient-safe measurement pixels: 630784. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |

Named overlap pixels: 0. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest results/vlm_adapter_integration/offline_manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| books_horizontal_stack / R_shelf / G_books | 图中是否存在至少两本水平叠放的书籍？ | yes | no | candidate_violated |
| books_upright_books / R_shelf / G_books | 图中是否存在竖直站立摆放的书籍？ | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
