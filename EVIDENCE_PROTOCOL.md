# Existing-Scene VLM evidence protocol

`existing_scene_v1` is a new, diagnostic-only protocol. It does **not** rewrite
M2, Benchmark v0.1, or any frozen questions, raw answers, labels or review states.
No model requests were made to validate this revision.

## Planning and freezing

The actual System prompts live in
[reference_vlm_pilot.py](scripts/reference_vlm_pilot.py) (`PLANNING_SYSTEM`) and
[verification_adapter.py](e_harness/verification_adapter.py) (`VERIFICATION_SYSTEM`).
The [offline protocol review](results/existing_scene_protocol_v1/report.md)
includes a saved planning contract and CPU test receipt.

New planning permits 1–5 coarse evaluation Regions, optional Groups and a few
Anchors. The evidence budget defaults to 10 and accepts integers 1–10. It is a
maximum, not a quota: fewer or zero observable atomic facts are allowed. Group
creation and Energy types are not mandatory for every image or Region.

Only Reference RGB enters planning. No tested Render, scene/object names,
construction labels or expected changes enter its contract. The prompt asks for
discriminative visible facts, including arrangement, structural partitions,
relative layout and salient attributes, rather than existence/count alone.
This is a planning instruction, not proof of evidence quality; semantic review
and harder visual experiments remain necessary.

Each fact contains an ID, Region ID, optional Group/Anchor IDs, Energy type,
claim, neutral question, `answer_type` and `categories`. There is no expected
answer field. IDs, endpoint membership and boxes are checked before freezing.
Boxes use normalized 0–1000 xyxy in planning, converted once to Reference pixels.
New candidate files record:

```json
{
  "evidence_protocol": {
    "version": "existing_scene_v1",
    "evidence_budget": 10
  },
  "reviewed": false,
  "usage": "provisional/debug"
}
```

The candidate file is frozen before the live driver opens Changed RGB. Category
options are part of that Reference-only freeze; they are not the Reference VQA
answer. Do not edit an old freeze to migrate it to this protocol.

## Answers and verification

| answer_type | Frozen answer space |
| --- | --- |
| `yes_no_unknown` | `yes`, `no`, `unknown`; `categories: []` |
| `count_unknown` | Nonnegative integer or `unknown`; `categories: []` |
| `categorical_unknown` | 1–12 unique neutral labels in `categories`, plus `unknown` and `ambiguous` |

Reserved abstention labels are added by the adapter, not repeated in
`categories`. Empty, duplicate, invalid or unrecognized types/categories are
rejected rather than repaired. A missing or invalid individual answer does not
erase valid sibling answers.

Verification inputs explicitly allowlist neutral questions, frozen answer
spaces, IDs and fixed Region definitions. Claims, expected values and Reference
answers stay outside the model input. Prompts contain no filled-answer JSON
example. Both sides receive exactly the same System/User/schema contract,
Reference-coordinate Regions and image processing. The CLI independently
re-encodes each full input as RGB PNG without cropping, alignment or blackout;
paired callers must first use a valid common coordinate grid. A Region box is
an evaluation scope, not an object detector box. Continuous distances/areas
require reliable RGB localization and deterministic measurement, not guessed
VQA coordinates.

The existing CLI transport is retained: one image per call, JSON Schema, no
automatic retries, bounded attempts, temporary cwd, read-only sandbox and tools
disabled. These reduce exposure but do **not** establish strict filesystem
isolation or a verifiable remote model snapshot. No new calls are authorized
by selecting a protocol or running the offline tests.

`compare_answers()` requires identical frozen contracts and keeps exact raw
answer JSON. Each result contains `reference_verification` and
`render_verification`: raw field value, validation status, backend/source/model
and `human_review: {status: unreviewed, reviewed: false, notes: null}`. Import
validation reparses raw answers, recomputes comparisons and checks the new
answer-space metadata against the frozen schema. It never trusts an imported
verdict or claimed human approval.

Same usable answers yield `satisfied`; different usable answers yield
`candidate_violated`; either `unknown`/`ambiguous` yields `unknown`; invalid,
missing or failed responses yield `unavailable`. All values remain diagnostic,
`reviewed:false`, non-scorable and without Energy contribution. A candidate
difference is not confirmed reconstruction error, and detection failure is not
confirmed absence. Existing Energy formulas, weights and Runtime gates remain
unchanged.

## Selecting the version

The Python helpers retain `m2_legacy` defaults for existing callers. Legacy
contracts are regression-tested byte-for-byte as JSON structures. Select the
new version explicitly when preparing a new experiment:

```python
from scripts.reference_vlm_pilot import planning_protocol, evidence_from_plan, verification_protocol

settings = dict(protocol_version="existing_scene_v1", evidence_budget=10)
planning_input = planning_protocol(**settings)  # local construction; no call
# After a separately authorized Reference-only planning request:
# evidence = evidence_from_plan(planning_packet, reference_size, **settings)
# verification_input, questions = verification_protocol(evidence)
```

The existing M2 live driver now defaults to `existing_scene_v1` at its CLI
entry; `--protocol-version m2_legacy` selects the old protocol. Its Python
`run()` retains the legacy default for compatibility. That driver still takes
saved M1 fixture inputs; this revision does not turn it into a new framework.

For the actual Existing-Scene batch entry, use a **new** config/output and add:

```json
"planning": {
  "protocol_version": "existing_scene_v1",
  "evidence_budget": 10
}
```

Without `planning`, existing Batch configs keep `m2_legacy`. Both batch
preparation and execution use the selected contract, and frozen config/prompt
checks reject changing versions/budgets during resume. The original
`configs/benchmark_v01.yaml` and saved results were not migrated. Zero facts
skip VQA, retaining available RGB evaluation without manufacturing questions.

Offline regression (with the documented project dependencies):

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python3 -B -m unittest discover -s tests -p 'test_existing_scene_protocol.py'
python3 -B -m unittest discover -s tests
```

These tests use labelled Mock packets, not new real VLM answers. The revision
has not established better Region/Group coverage or detection accuracy.
