# VLM Adapter publication subset

This is the authorized publication to `feat/offline-integration-mvp`, without merging main. The original experiment report and raw server files remain unchanged locally. Public JSON is a curated copy: project-private absolute paths become repository-relative provenance, the manifest uses paths relative to itself, and ephemeral CLI/test directories are redacted. These transformations do not alter raw model answers, frozen prompts/schema, counts, tokens, timing, comparison statuses, review flags, Energy values, failures or limitations.

Included PNGs are first-party primitive shelf/book synthetic controls, their comparison, and the all-valid synthetic pixel-support mask. The published two input PNGs have EXIF and renderer text chunks removed; decoded pixels and color/image data chunks are unchanged. They contain no BlenderWorld reference photos, historical Agent Render pixels, third-party masks or Blender assets. No full CLI session JSONL, authentication information, environments, weights or external users' files are included. The saved `argv` and prompt are relevant invocation metadata, not a full session log; ephemeral path arguments are marked `<VERIFIER_TEMP>`.

The real results remain two serial Codex CLI invocations, no retry: T1 yes/yes; T2 no/yes. The original CPU regression was 338/338; the publication regression also passed 338/338 with network/process denial. Unreviewed answers are diagnostics only. Remote model snapshot and strict context/filesystem isolation remain unverified. Historical subagent imports and explicit Mock transport tests remain separate from these two live CLI calls.

## Withheld from this publication

- `code_changes.patch`: redundant with the GitHub Commit Diff.
- `change_review.json`: local directory/patch inventory; this document and `release_checks.json` provide the curated publication review.
- `attempt_started.json`: local run reservation, unnecessary for reviewing completed results.
- `cpu_tests_initial.json`: superseded successful 336-test intermediate; the final 338-test record remains included.
- `offline_replay/`: duplicate report/PNG/mask outputs; `offline_modes_checks.json` and the original integration checks preserve the successful no-model replay result.
- `offline_report/comparison.png`: redundant synthetic overview; the main `comparison.png`, original two synthetic images, numerical report and valid-pixel mask remain included.
- Original server absolute paths, private home paths and ephemeral directories: omitted/redacted from public copies; kept only in the local original artifacts.

No experiment or model request was added for publication. Original report statements describing the pre-publication state remain historical snapshots, not the current GitHub upload status. A public clone still needs the documented sibling `scene-benchmark` dependency for evaluator execution. `offline_manifest.json` supports saved-answer replay with the two included images; reproducing the original historical subagent sessions is neither required nor claimed.

To run the existing offline replay after supplying the compatible sibling dependency, from the project root:

```bash
python3 -B -m e_harness.benchmark offline --manifest results/vlm_adapter_integration/offline_manifest.json --output /tmp/projecte-public-replay-new
python3 -B -m unittest discover -s tests -p 'test_verification_adapter.py'
```

These commands do not call a model. Do not select a live backend without a new explicit request budget.

Public copies were staged separately so the server originals stay intact. Local result files may therefore retain unstaged differences from the committed sanitized metadata/PNGs. These are intentional raw/public differences, not new experiments; do not indiscriminately stage them.
