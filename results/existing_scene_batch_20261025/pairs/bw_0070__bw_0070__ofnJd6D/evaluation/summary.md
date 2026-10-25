# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | N/A | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.023292 | 0.571429 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.273465 | 0.625000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.043730 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.322109 | 0.625000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.165649; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 312664/496128; gradient-safe measurement pixels: 312018. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r1 | 0.274081 | 0.310060 | False |
| r2 | 0.279340 | 0.311325 | False |
| r3 | 0.319844 | 0.325737 | False |

Named overlap pixels: 153928. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0070__bw_0070__ofnJd6D/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / N/A | Is the main vehicle body predominantly yellow? | yes | yes | satisfied |
| e2 / r1 / g1 | How many large tires are visible beneath the chassis? | 2 | 0 | candidate_violated |
| e3 / r1 / g2 | Is there a pair of square lights on each side of the central gray compartment? | yes | unknown | unknown |
| e4 / r2 / N/A | Is the glazed cabin to the right of the central gray compartment in the image? | yes | no | candidate_violated |
| e5 / r2 / N/A | Does the central gray compartment have a large rectangular door panel? | yes | yes | satisfied |
| e6 / r3 / N/A | What is the predominant color of the articulated equipment above the central gray compartment? | red | red | satisfied |
| e7 / r1 / N/A | Does a yellow frame extend across the top and down both sides of the central compartment? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
