# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | 0.000000 | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.007296 | 0.571429 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.178899 | 0.625000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.022825 | 0.666667 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.155306 | 0.625000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.091082; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 331776/355584; gradient-safe measurement pixels: 331008. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r_flower | 0.223505 | 0.147577 | False |
| r_background | 0.178885 | 0.133520 | False |

Named overlap pixels: 184464. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0043__bw_0043__p7isE6U/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r_flower / N/A | 中央主体是否为一朵开放的花？ | yes | yes | satisfied |
| e2 / r_flower / N/A | 这朵花可见多少片主要的白色花被片？ | 6 | 6 | satisfied |
| e3 / r_flower / N/A | 花被片的主要颜色是什么？ | 白色 | 白色 | satisfied |
| e4 / r_flower / N/A | 花朵中心的主要颜色是什么？ | 绿色 | 绿色 | satisfied |
| e5 / r_flower / N/A | 花朵中心是否可见黄色花药？ | yes | yes | satisfied |
| e6 / r_background / N/A | 花朵周围是否可见绿色狭长叶片？ | yes | yes | satisfied |
| e7 / r_background / N/A | 花朵周围的地面是否可见褐色落叶或枯枝？ | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
