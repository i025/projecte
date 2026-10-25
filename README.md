# Project e

Project e studies evaluation of Agentic Image-to-3D reconstruction without reference 3D ground truth. The current evidence organization is **Region-first, Group-aware, Anchor-on-demand**: Global/Dense Patch coverage, a few coarse functional Regions, meaningful Semantic Groups, and optional important Anchors.

**Start with [the latest experiments](results/LATEST.md)** or [the complete experiment index](results/README.md). They link original JSON/CSV and Markdown, and publication-permitted synthetic PNGs. Real-image comparison PNGs are withheld where redistribution rights are unconfirmed; their reports and actual outcomes remain visible. [Publication notes](results/PUBLICATION_NOTES.md) list withheld figures, consolidated files and historical links that cannot open in a public checkout.

The [Offline Evaluation MVP](OFFLINE_EVALUATION.md) provides one manifest-based entry for existing Reference/Render images, fixed ROI, optional evidence and camera checks. It emits auditable JSON, PNG and Markdown; external camera declarations and unreviewed Group/Structural answers do not create formal scores.

The [real-RGB batch v0.1](BENCHMARK_V01.md) freezes inputs and budgets, runs bounded Codex CLI planning/code generation/VQA, and retains failures across resume. Its actual run is **partial**: untrusted Blender execution remains blocked by missing qualified isolation, so no new Render or formal Benchmark score is claimed.

## Current findings

- Direct coarse Reference ROI is the experimental baseline. SAM/SLIC have not demonstrated consistent improvements in functional-region completeness.
- Group-level questions can describe contents and arrangements without per-instance matching, but agreement on broad questions does not establish reconstruction quality.
- Structural evidence can describe visible divisions independently of the displayed Group. In `bw_0073/R4`, independent observations identified a candidate difference between vertically stacked drawer-like fronts and side-by-side cabinet fronts.
- Comparability is proposition-specific: partial positive evidence can remain useful; absence requires sufficient local visibility. Unknown/N/A, extraction failures, camera differences and missing geometry corroboration are retained.
- These are small **provisional/debug** studies. Unreviewed evidence is not GT and does not create formal Benchmark scores.

## Source map

| Path | Responsibility |
| --- | --- |
| `e_harness/benchmark_evidence.py` | Reference candidates, review/reliability handling and shared evidence interfaces |
| `e_harness/benchmark_metrics.py` | Semantic, Spatial, Appearance, Statistical and Perceptual diagnostics and aggregation |
| `e_harness/benchmark_structure.py` | Independent 3D structural checks and unavailable/coverage handling |
| `e_harness/benchmark_config.py` | Existing fixed camera, provisional policies and weights |
| `scripts/` | Bounded experiments, parsers, offline replays and visualizations |
| `tests/` | Metric/verification contracts and orchestration checks; some older suites require Blender or local caches |
| `experiments/` | Existing supervised reconstruction drivers, not an authorization to execute Agent code |
| `SANDBOX_READINESS.md` | Runtime execution limits and unresolved isolation requirements |

The five Observation Energies and independent 3D Structural Energy remain separate. Semantic evidence is not replaced by DINO distance. The protocol retains fixed camera extrinsics and Agent-chosen intrinsics. The formal Runtime remains blocked under its existing safety gates.

## Reading and reproducing

Start with [the reproduction guide](REPRODUCING.md): it separates reading published results, offline tests and experiments requiring unavailable local inputs. Python dependencies are recorded in [requirements.txt](requirements.txt) and [requirements-lock.txt](requirements-lock.txt). The latter is a historical environment snapshot, not a complete portable lock for every optional experiment. The code currently reuses the sibling `../scene-benchmark` package and, for historical replays, local BlenderWorld data, masks, model caches or Codex sessions. Those dependencies and third-party images are not bundled. See [publication and reproduction limits](PUBLICATION.md).

On the existing server environment, the following checks are offline and do not launch Blender, models or API requests:

```bash
python -B -m unittest discover -s tests -p 'test_benchmark.py'
python -B -m unittest discover -s tests -p 'test_structural_visual_controls.py'
python -B -m unittest discover -s tests -p 'test_kitchen_structural_transfer.py'
```

Do not run `tests/run_tests.py` as a CPU-only check: it includes trusted Blender integration tests. Do not rerun historical live/request/render stages merely to inspect results. Where a report offers an offline replay, use a new destination and first confirm its local inputs exist.

## Public result policy

New work delivers PNG, JSON/CSV and Markdown by default. [PUBLICATION.md](PUBLICATION.md) explains why some visual assets are withheld, which first-party controls are included, and how to curate explicit paths. Original `reviewed` flags, provisional status, failures, raw answers and unresolved limitations are preserved.

The first public commit/push requires user confirmation. Published deliveries should state the actual GitHub commit SHA and experiment directory; do not substitute a date or fabricate a publication status. [AGENTS.md](AGENTS.md) records the agreed workflow.

Earlier server-side harness development and accounting are documented in [EXPERIMENT_HISTORY.md](EXPERIMENT_HISTORY.md); historical local paths in that document may intentionally be absent from the public checkout.
