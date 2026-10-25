# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | N/A | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.002530 | 0.571429 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.089860 | 0.625000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.011680 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.082283 | 0.625000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.046588; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 331776/331776; gradient-safe measurement pixels: 331776. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r1 | 0.089860 | 0.080898 | False |
| r2 | 0.119773 | 0.082100 | False |
| r3 | 0.292209 | 0.061723 | False |

Named overlap pixels: 65857. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_9064__task__LY4dtPw/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / N/A | Does the floor have a wood plank appearance? | yes | yes | satisfied |
| e2 / r1 / N/A | Are white baseboards visible along the wall-floor boundary? | yes | yes | satisfied |
| e3 / r2 / g1 | How many chairs are visible in the dining area? | 2 | 2 | satisfied |
| e4 / r2 / g1 | Is the table positioned between the two chairs in the image? | yes | yes | satisfied |
| e5 / r2 / g1 | Which visible support structure does the table have? | central pedestal | central pedestal | satisfied |
| e6 / r2 / N/A | Is a small potted plant visible on the tabletop? | yes | yes | satisfied |
| e7 / r3 / N/A | How many vertically stacked door sections are visible on the refrigerator? | 2 | 2 | satisfied |
| e8 / r3 / N/A | Is the refrigerator to the right of the dining furniture in the image? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
