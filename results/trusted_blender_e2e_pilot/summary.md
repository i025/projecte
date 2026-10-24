# Trusted Blender End-to-End Pilot

Trusted source-controlled synthetic execution closure; **reviewed=false, provisional/debug, formal_eligible=false**. This is not proof of real Agent Benchmark validity. Runtime remains blocked for unattended Agent execution.

## Executed chain

Built-in baseline fixture → bounded CPU Blender → RGB + same-render Object-ID/Depth/Normal export → evaluated Geometry → fixed Reference-only ROI → Offline Manifest → build_reference → compare → aggregate + independent structural_report. Two real Blender processes, strictly serial; no Agent source, VLM, SAM, SLIC, DINO, GPU or extra simulation engine.

Both renders used 256×256, 8 samples, fixed T0 (camera height 2 m), identical actual intrinsics (42 mm lens with shift_x=0.05), and identical CPU/color settings. The red cuboid moved from x=-1 to x=-0.1; geometry independently reports the same ~0.9 world-X change. The control also changes occlusion/shadows, not just object pixels.

Reference scopes were generated once from Baseline visible Object-ID support with a fixed 15% bounds margin, written read-only before Changed existed, then used at exactly the same coordinates. They are unreviewed coarse scopes, not semantic GT or object Masks. The narrow frozen scope clips the moved object as expected; it was not relocated to improve the response.

## Actual measurements (lower is better; no formal score)

| Existing Energy | Baseline self | Changed | Delta from Baseline |
| --- | --- | --- | --- |
| semantic | N/A | N/A | N/A |
| spatial | 0.00000000 | 0.00228500 | 0.00228500 |
| appearance | 0.00000000 | 0.03928318 | 0.03928318 |
| statistical | 0.00000000 | 0.00334170 | 0.00334170 |
| perceptual | N/A | N/A | N/A |

Spatial is the existing image-edge proxy and Statistical the existing texture/multiscale-edge proxy; these values do not measure true 3D layout or object density. Semantic has no reviewed verifier, Perceptual has no DINO inference, and 3D Structural has no reviewed triage/rules, so they remain N/A. Geometry still enters structural_report as nine components and 36 candidate pairs per scene; unreviewed contacts are never scored as confirmed errors.

| Fixed Region diagnostic | Baseline Appearance | Changed Appearance |
| --- | --- | --- |
| R_anchor_neighbourhood | 0.00000000 | 0.17462874 |
| R_large_primitives | 0.00000000 | 0.09427483 |

Global and the existing four Dense grid scopes remain available. The two unreviewed named scopes overlap on 9,408 pixels; q=0, no local total, and neither contributes an additional Energy penalty. The overlap is retained for audit, not cropped away.

## Execution provenance and trust boundary

The controller calls the existing whitelisted render_cpu entry itself; it does not import a saved receipt as trusted execution. Each output directory is new. It checks the returned launcher command/exit/cleanup, actual job fixture/config, camera before/after export, actual CPU render settings, RGB/array dimensions, positive camera-Z depth support, per-unit Mask equality to the same-render ID array, and Geometry component identities. The approved fixture helper bytes stayed unchanged during the executions; no signature, hash, registry or external attestation was introduced.

execution_chain.json records each launch, actual camera/K, RGB/Depth/Mask/Geometry paths, software identity and checks. Depth/ID/Normal NPY and intermediate EXR files are retained locally; their measured summaries and same-render Mask PNGs are public. Depth is camera-axis Z, not Euclidean ray distance; empty/background Depth is NaN. Object-ID uses an unfiltered pass at alpha threshold 0.5, without antialiasing guarantees; masks are not general semantic or transparent-surface GT.

The standalone Offline Evaluator deliberately remains pose_consistent_unverified even for these matching JSON matrices. Its formal_eligible flag never becomes true from fixed_extrinsics_enforced, trusted_execution or receipt files. The parent controller separately records that it observed this trusted synthetic execution chain. Later static replays have only a saved audit trail, not proof that files were never edited. No formal Agent score or Runtime unlock follows.

## VLM and optional evidence

No VLM ran, because this fixture is not a book arrangement task. No VLM result is required for RGB/Geometry diagnostics. New verification packets bind source image paths; Offline checks the exact Reference/Render pair and any recorded model source. Legacy answers without binding, swapped pairs or answers from other images remain unavailable with unmatched evidence preserved, not attributed to this fixture. Matching mocked pairs are tested only as interface contracts, never as visual success. Path binding is not content authentication: replacing a file at the same path is outside this guarantee.

## Resources

Existing CPU launcher: two render threads and two-CPU affinity, 120 s wall timeout, 60 CPU-seconds, 8 GiB address-space cap, 1 GiB sampled RSS stop, four-process stop, 128-thread stop; nice +10, isolated user/net/pid/mount namespaces, autoexec disabled. These are bounded trusted-code controls, not aggregate kernel quotas or an arbitrary-code sandbox. Additional library/control threads can exist; their measured counts/affinity are recorded.

| Case | Launcher seconds | Peak RSS MiB | Sampled processes / threads | Render seconds |
| --- | --- | --- | --- |
| baseline | 0.737 | 290.59 | 2 / 11 | 0.214 |
| changed | 0.733 | 289.89 | 2 / 11 | 0.222 |

Both launches exited 0 and cleanup completed. All sampled threads stayed within the two-CPU affinity. Initial controller syntax validation found and fixed an unmatched parenthesis before Blender started; the actual experiment comprises exactly two successful render launches, with no render retry. CPU unit tests use explicit synthetic Oracle files/mocks and do not validate Blender rendering or VLM visual recognition. Final test results are recorded separately in cpu_tests.json.

## Reproduce

With the documented sibling scene-benchmark dependency and the existing Blender binary/namespace support available:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python3 -B -m e_harness.benchmark_trusted --output /tmp/projecte-trusted-fixture-new
python3 -B -m unittest discover -s tests -p "test_benchmark_trusted.py"
```

The first command actually launches two bounded CPU Blender jobs and must use a new output directory on a server with resources available. Static no-render replay instead uses baseline_manifest.json / changed_manifest.json with the offline entry and a new evaluation directory. Neither replay certifies trusted execution; neither calls a VLM.

## Remaining blockers

Reference evidence review, reliable real-image Semantic/Spatial/Statistical verification, calibrated abstention, correspondence/visibility under the official protocol, safe actual Agent execution and clean-install distribution of the sibling evaluator remain unresolved. This pilot uses known first-party primitives, not real Agent reconstruction. Formal Runtime remains blocked; no formulas or weights changed.

## Validation results

Full CPU regression: **353/353 passed**, 0 failures/errors/skips; 15 new trusted-artifact/pairing tests, 19 existing Adapter and 19 Offline tests. Network connections and external subprocesses were denied during the unit suite. These Oracle tests are separate from the two successful real Blender runs.

Four additional no-render checks on the actual saved RGB passed: missing Geometry preserves image Energies; real old book answers without image binding remain unavailable; forged matching-camera/trusted-execution booleans grant no formal status; a synthetic 1.5 m camera-metadata fault is flagged historical_camera. The latter is metadata fault injection, not a new historical-camera rendering. None caused model calls or extra Blender launches. See [integration_checks.json](integration_checks.json).

Baseline self-comparison uses the same actual generated RGB on both sides; zero error verifies the evaluator path, not independent re-render determinism. Larger local errors reflect both localization and ROI area normalization, and do not prove semantic ROI superiority. The frozen ROI was not modified after Changed.

Files: [comparison.png](comparison.png), [report.json](report.json), [execution_chain.json](execution_chain.json), [cpu_tests.json](cpu_tests.json), [Reference Evidence](reference_evidence.json), [Baseline Manifest](baseline_manifest.json), [Changed Manifest](changed_manifest.json).
