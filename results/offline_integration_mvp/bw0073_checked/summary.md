# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. No model, API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.022815 | 0.500000 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.212317 | 0.555556 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.058073 | 0.500000 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | N/A | 0.000000 | N/A: no DINO inference in this entry |

Conditional Observation: 0.097735; independent 3D Structural: N/A.

Camera: historical_camera. Recorded actual pose differs from prescribed T0 or conflicts with another pose; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 1244619/1285632; gradient-safe measurement pixels: 1243782. Explicit mapping: uniform_fit; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| R1 | 0.297536 | N/A | False |
| R2 | 0.270866 | N/A | False |
| R3 | 0.318984 | N/A | False |
| R4 | 0.248873 | N/A | False |

Named overlap pixels: 17517. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest /srv/lab-disks/disk2/users/xymo/projects/e-harness/results/offline_integration_mvp/inputs/bw0073_manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.
