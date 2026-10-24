# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. No model, API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | N/A | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.002285 | 0.666667 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.039283 | 0.714286 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.003342 | 0.666667 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | N/A | 0.000000 | N/A: no DINO inference in this entry |

Conditional Observation: 0.014970; independent 3D Structural: N/A.

Camera: pose_consistent_unverified. Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 65536/65536; gradient-safe measurement pixels: 65536. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| R_anchor_neighbourhood | 0.174629 | N/A | False |
| R_large_primitives | 0.094275 | N/A | False |

Named overlap pixels: 9408. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest results/trusted_blender_e2e_pilot/changed_manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.
