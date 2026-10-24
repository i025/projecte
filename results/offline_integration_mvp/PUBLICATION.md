# Offline Integration MVP: public subset

This is a publication note, not a rewrite of the original experiment.
Original server files, review states, failures and numerical values remain
unchanged. The original summary and delivery receipts describe their creation
time, when no commit or push had occurred. They are historical snapshots, not
the publication status of this review branch.

## Included

- Integration code, tests and documentation; no new Energy or policy weights.
- Final bw_0073 report JSON, integration checks and Markdown; fixed candidate
  coordinates, actual camera metadata, unavailable evidence and old answers
  remain provisional/debug and reviewed:false. They contain annotations and
  project-owner provenance paths, without photographic/image payloads.
- bw_0073's earlier integration-check JSON as a small failure/audit record.
  The duplicate early full report is retained on the server, not republished.
- The original integration test receipts, including the 89-test subset.
  The release review separately records the initial 318-test run with two
  compatibility errors and the final 319-test passing full suite.
- Authored synthetic RGB inputs, evidence and output PNGs. The inputs are
  128×96 primitive pixel drawings: RGB(120,120,120) background;
  xyxy [20,24,64,70] in RGB(220,55,35); xyxy [78,30,110,64] in
  RGB(35,90,205), changed to RGB(80,170,205) on the second image. Pixel equality
  to these authored arrays was checked; no third-party pixels are used.
  The existing generic figure calls its right panel “Saved Agent Render”;
  **for this Synthetic Oracle fixture it is a programmed color change, not
  an actual Agent output**. The fixture is not a visual-verifier accuracy test.
- Three existing first-party Python snapshots required by CPU legacy tests:
  `../region_first_generalization_checked/source_snapshot/benchmark_evidence.py`,
  `../region_first_generalization_checked/source_snapshot/coarse_roi_experiment.py`,
  `../vlm_direct_grounding_bw0073/source_snapshot/vlm_direct_grounding.py`.
  Their original bytes are preserved. They are necessary test inputs, not a new
  version-management system or a bundled model/dependency.

## Withheld

The following local paths are **not public download links**:

| Local path | Reason |
| --- | --- |
| `bw0073/comparison.png` | Third-party Reference/Render pixels and derivatives not cleared for redistribution |
| `bw0073/valid_pixels.png` | Conservative exclusion of real-image-derived supports/masks |
| `bw0073_checked/comparison.png` | Same unresolved image redistribution rights |
| `bw0073_checked/valid_pixels.png` | Same conservative mask exclusion |
| Native Reference, historical Render, all original ROI masks, `.blend` and caches | Not part of this publication; provenance paths in JSON do not distribute the assets |

Consequently, original Markdown links to these four PNGs do not open in a public
checkout. No substitute image or invented mask is supplied. Replaying the real
case requires authorized local inputs at the manifest paths; it is not portable
from GitHub alone. The synthetic manifest is relative and its own inputs are
provided, but the core still requires the compatible sibling scene-benchmark
dependency described in the project reproduction guide.

No API credentials, authentication headers, raw image request bodies, other
users' data, model weights, environments or Blender assets are included.
The complete exact file list and scan receipt are recorded under
[`release_review/publication.json`](release_review/publication.json).
No new source-code license or third-party image permission is asserted.
