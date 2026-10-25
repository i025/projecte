# Existing-Scene Benchmark — actual historical pairs

**reviewed:false; provisional/debug; no formal score.**

Evaluated 13/13 pairs from 10 Reference images.
Saved Agent scenes were not executed, generated, rendered or realigned. Incomplete checkpoints remain labelled. Reference-only plans were frozen before independent Render VQA; each shared Reference plan/VQA is reused without using another Render answer.

| Energy | Measured pairs | Selected pairs | Pair availability | Metric-record coverage | Formal scored |
| --- | --- | --- | --- | --- | --- |
| semantic | 0 | 13 | 0.0000 | 0.0000 | 0 |
| spatial | 13 | 13 | 1.0000 | 0.4483 | 0 |
| appearance | 13 | 13 | 1.0000 | 0.5039 | 0 |
| statistical | 13 | 13 | 1.0000 | 0.5253 | 0 |
| perceptual | 13 | 13 | 1.0000 | 0.5039 | 0 |
| structural | 0 | 13 | 0.0000 | N/A | 0 |

Spatial/Statistical numbers above are existing image-edge/texture proxies, not verified object layout, density or group arrangement. Semantic and Structural require reviewed compatible evidence and remain N/A where unavailable. DINO is real local CPU inference, not semantic evidence.

## Real VLM diagnostics

{
  "semantic": {
    "planned": 56,
    "usable": 55,
    "unknown": 1,
    "unavailable": 0,
    "states": {
      "candidate_violated": 5,
      "satisfied": 50,
      "unknown": 1
    },
    "formal_scored": 0
  },
  "spatial": {
    "planned": 40,
    "usable": 38,
    "unknown": 2,
    "unavailable": 0,
    "states": {
      "satisfied": 34,
      "candidate_violated": 4,
      "unknown": 2
    },
    "formal_scored": 0
  },
  "statistical": {
    "planned": 11,
    "usable": 11,
    "unknown": 0,
    "unavailable": 0,
    "states": {
      "satisfied": 7,
      "candidate_violated": 4
    },
    "formal_scored": 0
  }
}

Attempts: 33 / maximum 33; automatic retries: 0. Reported input/output tokens: 379036 / 12484; summed model seconds: 1102.832.

Requested gpt-6-sol via existing Codex CLI. Observed snapshots may be unavailable. CLI usage includes platform context, not Ofox billing. Temporary cwd and disabled tools do not establish strict filesystem isolation. Planning, Reference and each Render are separate calls with the exact recorded neutral contract. No Reference answers, scene/task briefs or Blender names enter a Render prompt.

Category spaces retain raw planner choices and freeze explicit absent/other options before any Render read. Unknown/ambiguous are abstentions. Unreviewed answers never enter formal Energy. Continuous object-level distances remain N/A without reliable RGB-only localization/correspondence.

## Review and reproduction

[Per-pair measurements](per_pair_results.csv) · [Evidence audit](evidence_audit.md) · [Full batch data](report.json). Individual pairs/<pair_id>/evaluation/report.json and raw VQA JSON retain failures, reason strings, fixed ROI, overlaps and source/coordinate checks. Server-only PNG/Mask derivatives are withheld until redistribution is authorized.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 python3 -B -m e_harness.benchmark_existing --config /path/to/private-pairs-config.json --output /path/to/new-results
```

Requires existing local data, DINO weights, sibling scene-benchmark and Codex CLI login. A new output entails real model requests and requires authorization. An unchanged output may resume saved stages without retrying reservations; no raw packet or frozen evidence is overwritten. The public checkout contains no third-party images or complete server run inventory. Historical camera/PNG-blend synchronization, independent review and validated RGB grounding still block official Benchmark scores. Runtime stays blocked.
