# Benchmark v0.1 — actual partial run

**reviewed:false; provisional/debug; NOT a completed end-to-end Benchmark or formal score.**

Selected 8/8 real RGB inputs; 8 syntax-valid new scene programs; 24 real CLI attempts; 0 Blender executions. No historical Render or fixture substituted.

## Per-scene status

| Sample | Planning | Agent code | Reference VQA | Execution |
| --- | --- | --- | --- | --- |
| bw_9064 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0043 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0006 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0063 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0073 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0074 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0075 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |
| bw_0022 | valid | valid_python_unexecuted | valid | blocked_unqualified_isolation |

All five pairwise Energies and independent Structural are N/A (valid sample count 0). No safe new Render/geometry exists; availability Coverage is 0, not a zero error. No VQA comparison is invented from Reference answers alone.

Actual CLI attempts: 24; Agent generation attempts: 8; reported input/output tokens: {'input_tokens': 242672, 'output_tokens': 30040}; CLI elapsed sum: 841.401s. Currency cost unavailable. No remote model snapshot claimed; model_requested=gpt-6-sol, backend=Codex CLI.

## Reference planning coverage

Nodes: {'regions': 19, 'groups': 0, 'anchors': 3}. Atomic evidence types: {'statistical': 2, 'spatial': 3, 'semantic': 19}. These are automatic candidates, not GT. If no Group is proposed, the Group-aware path has not been exercised. Presence/count-heavy questions do not establish arrangement or continuous-layout sensitivity. No missing Group/question is added after seeing results.

## Actual boundary

- No qualified, adversarially checked untrusted-code executor is installed/configured.
- Existing CPU launcher has no filesystem confinement or per-job storage/process quota.
- No configured remote container/VM executor; no new cloud service/account is assumed.
- Namespace smoke success and resource monitoring alone do not meet the execution contract.

DINO: valid. Real Reference-only availability inference, not a pairwise Perceptual score

## Limitations

Codex CLI tools are disabled and cwd/images are isolated per call, but filesystem read confinement and exact remote model snapshot are not established. This is not a strict blind/base-model test. No scene-specific prompt edits, repairs, retries or render feedback. Reference evidence was frozen before Agent generation; the Agent receives only its RGB and common T0 task.

Local evaluation uses user-authorized existing benchmark images. The distribution documents evaluation use; image-specific copyright clearance is not established. No third-party visual/Blender asset is published. These are eight existing external RGB inputs, not eight verified real-world photographs: the selection includes artwork and potentially rendered references. These remain selected, with their scope limitation, rather than being discarded after model generation. Reference viewpoint is unknown; enforcing output T0 alone would not remove camera/reconstruction ambiguity.

## To finish

Provide and validate an unprivileged container/VM executor with the recorded hard resource and isolation requirements, then connect its same-execution exports to the existing Offline Evaluator. This batch deliberately has no unvalidated executor fallback. Resume does not rerun reserved model calls. Review all Reference candidates and subsequent VQA/Structural candidates independently before formal scores.

[Dataset](dataset_manifest.json) · [All calls/statuses](run_manifest.json) · [Per scene](per_scene_results.csv) · [Aggregate](aggregate_results.json) · [Execution checks](execution_checks.json) · [Human audit](audit_packet.md) · [Reproduce](reproduce.md)

## Validation and audit

412/412 CPU tests passed, including 17 batch-specific tests; network and subprocess execution were denied in the regression suite. No Blender/GPU or generated Python execution was tested. The separate real DINO check and 24 CLI tasks are live observations, not unit-test mocks.

The completed-stage resume/finalization was checked with model/DINO calls forbidden: 0 new calls. All 24 Render-side comparisons remain unavailable, with no penalty. See [batch validation](batch_validation.json), [CPU results](cpu_tests_final.json), and [publication limits](PUBLICATION.md).
