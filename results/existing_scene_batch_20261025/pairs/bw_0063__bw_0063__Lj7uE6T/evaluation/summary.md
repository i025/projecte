# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.024595 | 0.444444 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.151894 | 0.500000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.041150 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.160695 | 0.500000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.094584; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 327327/329472; gradient-safe measurement pixels: 326898. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r_living | 0.187315 | 0.100768 | False |
| r_dining | 0.170637 | 0.210617 | False |
| r_background | 0.159860 | 0.209784 | False |

Named overlap pixels: 20480. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0063__bw_0063__Lj7uE6T/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r_living / N/A | Is a light-colored upholstered sofa visible in the living area? | yes | yes | satisfied |
| e2 / r_living / g_coffee_tables | How many low tables are visible in front of or beside the sofa? | 3 | 2 | candidate_violated |
| e3 / r_living / g_coffee_tables | Does the round wooden coffee table project below the sofa in the image? | yes | yes | satisfied |
| e4 / r_living / N/A | What type of wall decoration is visible above the sofa? | framed artwork | framed artwork | satisfied |
| e5 / r_living / N/A | Does a tall leafy plant project to the left of the wall artwork? | yes | yes | satisfied |
| e6 / r_dining / g_dining_chairs | What kind of backrest do the visible dining chairs have? | rounded upholstered | rounded upholstered | satisfied |
| e7 / r_dining / N/A | Are white plates and bowls visible on the dining table? | yes | yes | satisfied |
| e8 / r_background / N/A | What panel pattern is visible on the wooden doors? | horizontal glass panels | horizontal glass panels | satisfied |
| e9 / r_background / N/A | Does a narrow console table project to the left of the double doors? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
