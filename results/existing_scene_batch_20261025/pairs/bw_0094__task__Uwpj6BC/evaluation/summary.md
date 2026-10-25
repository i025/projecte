# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.048640 | 0.444444 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.250914 | 0.500000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.097229 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.306774 | 0.500000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.175889; independent 3D Structural: N/A.

Camera: historical_camera. Recorded actual pose differs from prescribed T0 or conflicts with another pose; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 331776/347136; gradient-safe measurement pixels: 331008. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r1 | 0.256161 | 0.375178 | False |
| r2 | 0.248836 | 0.253486 | False |
| r3 | 0.260907 | 0.275247 | False |

Named overlap pixels: 14745. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0094__task__Uwpj6BC/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / N/A | Does the mural show a landscape with prominent white text? | yes | yes | satisfied |
| e2 / r1 / N/A | Is the mural left of the visible pair of windows on the brick building? | yes | yes | satisfied |
| e3 / r2 / N/A | Do the walkway's side boundaries converge toward the rear plaza in the image? | yes | yes | satisfied |
| e4 / r2 / g1 | What is the predominant color of the vertical walkway banners? | red | absent | candidate_violated |
| e5 / r2 / g1 | Are vertical banners visible on both sides of the central walkway? | yes | no | candidate_violated |
| e6 / r3 / N/A | Is an upward water jet visible at the fountain? | yes | yes | satisfied |
| e7 / r3 / g2 | What color are the blossoms on the trees around the rear plaza? | pink | pink | satisfied |
| e8 / r3 / g2 | Are flowering trees visible to both the left and right of the fountain? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
