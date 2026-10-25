# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.024361 | 0.363636 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.185632 | 0.416667 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.044614 | 0.444444 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.171205 | 0.416667 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.106453; independent 3D Structural: N/A.

Camera: historical_camera. Recorded actual pose differs from prescribed T0 or conflicts with another pose; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 310574/321024; gradient-safe measurement pixels: 310156. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r1 | 0.213568 | 0.177790 | False |
| r2 | 0.180566 | 0.252170 | False |
| r3 | 0.241710 | 0.180312 | False |
| r4 | 0.201141 | 0.190289 | False |
| r5 | 0.157590 | 0.208098 | False |

Named overlap pixels: 25323. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0073__task__Dpf9tyA/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / N/A | Is a large arched-top window visible on the left wall? | yes | yes | satisfied |
| e2 / r1 / N/A | Are open shelves positioned above the left countertop? | yes | yes | satisfied |
| e3 / r1 / N/A | What is the dominant color of the left lower cabinet fronts? | dark gray | dark gray | satisfied |
| e4 / r2 / N/A | Does the central island have a white stone top with dark veining? | yes | unknown | unknown |
| e5 / r2 / g1 | How many stools are visible along the near side of the island? | 4 | 4 | satisfied |
| e6 / r2 / g1 | Do the stools form a horizontal row along the island's near side? | yes | yes | satisfied |
| e7 / r3 / N/A | Is the glazed doorway to the right of the rear cooking area in the image? | yes | yes | satisfied |
| e8 / r4 / g2 | Are the tall dark cabinet faces bordered by light wood cabinetry? | yes | no | candidate_violated |
| e9 / r5 / N/A | Is a gold sculptural pendant visible above the island? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
