# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.010689 | 0.444444 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.271275 | 0.500000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.035838 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.276207 | 0.500000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.148502; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 264600/483840; gradient-safe measurement pixels: 263970. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r1 | 0.234698 | 0.284656 | False |
| r2 | 0.293901 | 0.283941 | False |
| r3 | 0.255978 | 0.299245 | False |

Named overlap pixels: 9240. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0006__bw_0006__gfHGhky/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / N/A | Is the tall left panel predominantly red? | yes | yes | satisfied |
| e2 / r1 / N/A | Are white star shaped graphics visible on the red panel? | yes | yes | satisfied |
| e3 / r2 / N/A | What type of feature occupies the central wall? | electronic display | electronic display | satisfied |
| e4 / r2 / N/A | Is a red maple leaf emblem visible near the upper center of the display? | yes | yes | satisfied |
| e5 / r2 / N/A | Is the display above the lower horizontal wall trim? | yes | yes | satisfied |
| e6 / r3 / N/A | Does a light colored polygonal frame surround the dark hatch openings? | yes | yes | satisfied |
| e7 / r3 / g1 | How many dark window areas are visible within the hatch? | 2 | 1 | candidate_violated |
| e8 / r3 / g1 | Are the hatch windows arranged one above the other? | yes | no | candidate_violated |
| e9 / r3 / N/A | Is the hatch to the right of the central display? | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
