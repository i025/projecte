# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | N/A | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.010762 | 0.571429 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.089248 | 0.625000 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.022517 | 0.571429 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.213145 | 0.625000 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.083918; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 393216/393216; gradient-safe measurement pixels: 393216. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r_sky | 0.093120 | 0.160447 | False |
| r_ridges | 0.090125 | 0.233765 | False |
| r_foreground | 0.077325 | 0.124683 | False |

Named overlap pixels: 67584. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0075__bw_0075__nVjEut5/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r_sky / N/A | 天空的主要颜色属于哪一类？ | 蓝色 | 蓝色 | satisfied |
| e2 / r_sky / g_clouds | 天空中是否可见浅色云层？ | yes | yes | satisfied |
| e3 / r_sky / g_clouds | 浅色云层是否主要分布在天空的中下部？ | yes | no | candidate_violated |
| e4 / r_ridges / g_ridges | 画面中是否可见至少三层上下分布的山岭轮廓？ | yes | yes | satisfied |
| e5 / r_ridges / g_ridges | 较浅色的山岭轮廓是否位于较深色的山岭轮廓上方？ | yes | yes | satisfied |
| e6 / r_ridges / g_ridges | 山岭顶部轮廓主要属于哪种形状？ | 起伏曲线 | 起伏曲线 | satisfied |
| e7 / r_foreground / N/A | 画面最下方山脊的主要颜色属于哪一类？ | 深蓝色 | 深蓝色 | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
