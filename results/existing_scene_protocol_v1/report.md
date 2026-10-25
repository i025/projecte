# Existing-Scene evidence protocol v1 — offline revision

2026-10-25 (Asia/Shanghai). `reviewed:false`; `provisional/debug`.

This revision changes future planning/verification contracts, not historical
questions or answers. No real VLM, Ofox, Blender, GPU or Agent execution occurred.

- New protocol: `existing_scene_v1`; legacy `m2_legacy` remains byte-for-byte
  compatible in planning and verification regression fixtures.
- Planning: 1–5 coarse Regions, optional Groups/Anchors, configurable maximum
  1–10 atomic facts (default 10). Zero observable facts are permitted and skip
  VQA while retaining available RGB evaluation.
- Types: `yes_no_unknown`, `count_unknown`, `categorical_unknown`. Categories
  freeze during Reference-only planning. No expected answers or filled-answer
  JSON examples enter verification prompts.
- Both sides receive identical neutral questions, answer spaces and fixed
  Region definitions through the unchanged full-image RGB PNG CLI transport.
  Claims and Reference answers are excluded from verification input.
- `ambiguous`/`unknown` abstain; bad/missing fields remain unavailable without
  discarding valid siblings. Each answer retains exact raw JSON, validation,
  source/model and unreviewed human-review fields. Import comparisons are
  recomputed and answer-space metadata is checked against the frozen schema.
- New CLI driver invocations default to the new protocol. The Python helper
  default and Batch configs without `planning` preserve legacy operation.
  New Batch configs explicitly select version/budget; frozen resume rejects a
  changed contract. Existing v0.1 config/results are unchanged.
- No Energy formula, weight, aggregation policy or Runtime gate changed.
  Automatic evidence retains reliability zero; comparisons have no formal
  Energy contribution.

[CPU receipt](checks.json): **436 tests passed**, including **24 new protocol
tests**; zero failures/errors/skips. Network connections and real subprocesses
were denied during this suite. Transport calls in tests are explicitly Mock.
Tests cover legacy compatibility, categorical/Unknown/partial failures,
version and budget association, raw-answer audit, reference-answer exclusion,
fixed dual-side input, Batch selection/freeze, zero evidence, and Offline
diagnostics remaining outside formal Energy.

The [planning contract](planning_protocol.json) is a local construction snapshot,
not a model response. The [verification contract example](verification_protocol_example.json)
uses one manually authored, neutral question only to expose the new input
format; it is not Reference GT or a real visual result.

Reproduce with documented dependencies:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python3 -B -m unittest discover -s tests -p 'test_existing_scene_protocol.py'
python3 -B -m unittest discover -s tests
```

See [protocol selection and semantics](../../EVIDENCE_PROTOCOL.md) and
[source tests](../../tests/test_existing_scene_protocol.py). This change has
not demonstrated improved model evidence quality, actual Group coverage or
visual detection accuracy. Prompt wording alone cannot establish independence;
the CLI's filesystem isolation and remote model snapshot remain unverified.
Historical answers and unreviewed states remain unchanged.
