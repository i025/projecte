# Offline Evaluation Integration

**provisional/debug — no formal Benchmark score.**

The entry reuses build_reference → compare → aggregate and independent structural_report. An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.

| Energy | Conditional value | Coverage | Interpretation |
| --- | --- | --- | --- |
| semantic | N/A | N/A | Reviewed evidence only; attached Group/Structural answers never become scores |
| spatial | 0.036460 | 0.500000 | Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness |
| appearance | 0.279944 | 0.555556 | Actual RGB L1; affected by camera, lighting and visibility |
| statistical | 0.058881 | 0.500000 | Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density |
| perceptual | 0.311227 | 0.555556 | Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness |

Conditional Observation: 0.171628; independent 3D Structural: N/A.

Camera: unknown. Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient; Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding

Valid pixels: 235776/294912; gradient-safe measurement pixels: 235392. Explicit mapping: identity; no alignment search.

## Fixed Region diagnostics

| Region | Appearance | Perceptual | Reviewed |
| --- | --- | --- | --- |
| r_pool | 0.279004 | 0.331866 | False |
| r_lawn | 0.258700 | 0.275295 | False |
| r_patio | 0.268592 | 0.269669 | False |
| r_people | 0.257638 | 0.402935 | False |

Named overlap pixels: 117542. Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.

Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.

Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.

## Reproduce offline

From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:

```bash
python3 -B -m e_harness.benchmark offline --manifest ./results/existing_scene_batch_20261025/pairs/bw_0009__bw_0009__X9GcF9r/manifest.json --output /tmp/projecte-offline-new-output
```

The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.

## Imported VLM Verification (unreviewed, no Energy contribution)

| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r_pool / N/A | 泳池是否呈长方形且水面为浅蓝色？ | yes | yes | satisfied |
| e2 / r_lawn / N/A | 草坪上方是否有带弧形遮篷的圆形休闲床？ | yes | yes | satisfied |
| e3 / r_lawn / g_loungers | 右侧躺椅之一是否铺有橙白条纹织物？ | yes | yes | satisfied |
| e4 / r_patio / N/A | 左侧露台的圆形火盆中央是否为深色填料？ | yes | yes | satisfied |
| e5 / r_patio / N/A | 从当前视角看，白色圆形火盆是否位于两张浅色座椅之间？ | yes | yes | satisfied |
| e6 / r_people / N/A | 泳池上缘附近可见几个人？ | 2 | 0 | candidate_violated |
| e7 / r_people / N/A | 从当前视角看，深色上衣的人是否位于浅色上衣的人的左侧？ | yes | unknown | unknown |
| e8 / r_pool / N/A | 泳池右上侧池缘是否有一段凸出的浅色平台？ | yes | yes | satisfied |

Backends: codex_cli / codex_cli. Raw answers, frozen prompt, model provenance and request failures remain in report.json.
