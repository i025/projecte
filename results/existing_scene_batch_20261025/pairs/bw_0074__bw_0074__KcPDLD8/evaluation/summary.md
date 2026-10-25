# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.035222 | 0.444444 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.227628 | 0.500000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.056504 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.164145 | 0.500000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.120875; independent 3D Structural: N/A.

Camera: historical_camera. Recorded actual pose differs from prescribed T0 or conflicts with another pose; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 399360/400896; gradient-safe measurement pixels: 398592. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r1 | 0.246507 | 0.150259 | False |
| r2 | 0.233172 | 0.215541 | False |
| r3 | 0.194423 | 0.263689 | False |

Named overlap pixels: 77202. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0074__bw_0074__KcPDLD8/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / g1 | Are the record rows in the upper-right portion of the wall shelving? | yes | yes | satisfied |
| e2 / r1 / g2 | Are open rectangular compartments positioned above closed lower cabinets? | yes | yes | satisfied |
| e3 / r1 / N/A | Is a silver boombox on a shelf below the record rows? | yes | yes | satisfied |
| e4 / r1 / N/A | What type of audio equipment is visible on the lower-right shelf? | turntable | turntable | satisfied |
| e5 / r2 / N/A | Is the monitor positioned above the desk surface? | yes | yes | satisfied |
| e6 / r2 / N/A | Is the chair at the desk transparent? | yes | no | candidate_violated |
| e7 / r3 / N/A | What is the dominant color of the foreground sofa upholstery? | blue | blue | satisfied |
| e8 / r3 / N/A | Does the sofa overlap the lower portion of the wall unit in the image? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
