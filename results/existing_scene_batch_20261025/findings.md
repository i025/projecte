# Actual batch findings — 2026-10-25

**All evidence unreviewed; provisional/debug. No formal Benchmark score or accuracy estimate.**

The independent Existing-Scene runner completed **13/13 saved Reference–Render
pairs from 10 Reference images**: 9 completed runs and 4 incomplete/failed
checkpoints. The two priority cases passed the actual integration gate before
expansion. All 25 native trials in the 29-row inventory were accounted for;
14 excluded records and two old imports with unproven autonomous-Agent origin
remain documented in [dataset_audit.json](dataset_audit.json). Continued
bw_0073 runs share lineage and are not independent Agents.

There were **33 real Codex CLI calls**, no retries: 10 Reference-only planning,
10 independent Reference VQA and 13 independent Render VQA. All returned valid
JSON. The requested model was gpt-6-sol; observed model snapshots were not
provided. CLI-reported usage was **379,036 input / 12,484 output tokens**,
including CLI platform context, not Ofox billing. Summed model latency was
**1,102.832 seconds**. No Ofox request or API-key access occurred.

The local pretrained DINOv2 performed **224 CPU forward calls / 448 image
inputs**, with two CPU threads, no GPU/download; recorded inference time was
**38.576 seconds**, excluding model initialization and other pipeline work.
These were actual paired image measurements, not an availability-only probe
or historical feature replay.

## What the new evidence adds

Reference-only planning produced 32 Regions, 15 Groups, 11 optional Anchors and
80 unique atomic facts: 44 Semantic, 28 Spatial and 8 Statistical. Reusing the
same frozen kitchen evidence across four Render checkpoints produced **107
pair-specific comparisons**: 91 satisfied, 13 candidate_violated, 3 unknown,
0 unavailable. These are not 13 independently confirmed reconstruction errors.

- bw_0073/bA358eg: VLM reported an arched-window presence difference and an
  island-top/veining attribute difference; stool count remained four and its
  row relationship remained satisfied. Two candidates, seven agreements.
- bw_0074/KcPDLD8: VLM reported a transparent-chair attribute difference; seven
  other coarse claims agreed. This plan contains **no Statistical atomic
  question**, despite two Groups. Group-aware planning is not guaranteed to
  cover group arrangement; questions were not supplemented after seeing Render.
- Other candidates concern hatch-window organization, visible people/tires/
  tables counts, cloud placement, and walkway banners. The banner-color answer
  was `red → absent`, while a banner-presence question also differed. These two
  claims may describe the **same underlying issue** and must not become two
  unconditional penalties.
- Three unknowns concern a person relationship, vehicle lights and kitchen
  surface appearance. They remain abstentions, not confirmed object absence.
- Two kitchen checkpoints have all nine broad claims satisfied. This does not
  establish good reconstruction, and no independent human visual GT was added.

The full [candidate list](candidate_findings.json), [human audit table](evidence_audit.md)
and raw per-pair JSON preserve each question and both actual answers. No answers
or questions were changed to obtain a candidate violation.

## Coverage and N/A

| Energy | Pairs with actual conditional numeric value | Valid / planned core metric records | Interpretation |
| --- | --- | --- | --- |
| Semantic | 0/13 | 0/17 | All semantic candidates unreviewed; VQA stays diagnostic |
| Spatial | 13/13 | 52/116 (44.83%) | Existing Dense image-edge proxy; not continuous object layout |
| Appearance | 13/13 | 65/129 (50.39%) | Existing RGB comparison; camera/light/visibility sensitive |
| Statistical | 13/13 | 104/198 (52.53%) | Existing texture/multiscale-edge proxies; not group density |
| Perceptual | 13/13 | 65/129 (50.39%) | Real local DINOv2; crop/fill/aspect confounds remain |
| Independent Structural | 0/13 | N/A | No reliable evaluated collision/support Geometry bound to these runs |

Atomic diagnostics use a separate denominator: Semantic usable 55/56,
Spatial 38/40, Statistical 11/11 paired questions. “Usable” means a schema-valid
non-abstaining comparison, **not** independently verified correctness. Neither
those ratios nor pair-level numeric availability imply full evidence coverage.
All formal-scored counts are zero.

Sixteen unique categorical questions freeze explicit `absent`/`other` options
under the separately named Reference-only policy; `unknown`/`ambiguous` remain
allowed. There was one actual `absent` answer, three `unknown` answers and no
`other` or `ambiguous` answer. This verifies format/flow availability, not the
accuracy or calibration of these categories. All original planner categories
and responses are retained separately from the augmented frozen candidate.

## What remains unresolved

Historical cameras are non-T0 or unverified, Reference cameras are unknown,
and saved PNG/blend synchronization is not attested. Projection differences
cannot be directly attributed to 3D reconstruction. There is no reliable
RGB-only object localization/correspondence for continuous Spatial measures.
bw_0074's Scene Graph and low-resolution Group-ID cache provide auxiliary
generated-side evidence but are not reviewed semantic or collision/support GT.

Independent human evidence/answer/ROI review is pending. Planning may omit
discriminative properties or generate compound claims; satisfied broad claims
can miss visible differences. CLI temporary cwd/read-only mode is not strict
filesystem isolation, and requested model names do not verify a remote snapshot.

**452 CPU tests passed**, including 16 new Existing-Scene tests, with network
and real subprocess launches denied during regression. Actual live requests
are recorded separately. No Agent code, Blender, SAM/SLIC, new scene or official
score was produced. Energy formulas/weights and Runtime blocked state remain
unchanged. Post-run coverage/table checks invoked no additional models.

Private server output: `results/existing_scene_batch_20261025/`. Per-pair
`evaluation/comparison.png`, RGBs and valid-pixel Masks are intentionally
withheld publicly until redistribution rights are established. See
[runner and reproduction](../../EXISTING_SCENE_BENCHMARK.md),
[integration checks](integration_checks.json), [CPU receipt](cpu_tests.json)
and [summary](summary.md).
