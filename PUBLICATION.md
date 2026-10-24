# Public repository content and reproduction

This repository is a curated publication of Project e source and existing experiment records. Raw server artifacts remain in place. Publication does not approve evidence, certify a segmentation, repair failed experiments, or create official Benchmark scores.

## Included

- `e_harness/`, `scripts/`, necessary `tests/` and trusted experiment drivers.
- Existing scientific Markdown, selected JSON/CSV, original answers and failure/Unknown/N/A records.
- First-party synthetic book and shelf controls, their comparison PNGs and selected input images. The controls use authored primitive geometry/materials or Pillow drawings; they contain no BlenderWorld reference photos.
- Small trusted Runtime calibration summaries required by existing code. Their historical states are retained; they are not new sandbox acceptance results.

## Withheld visual material

The [BlenderWorld dataset card](https://huggingface.co/datasets/Qwen/BlenderWorld) says its MIT license covers adapter/evaluator code. The locally available MIT software license does not establish permission to redistribute each third-party reference image.

Until image-specific permission or a suitable redistribution license is established, publication excludes downloaded originals, photographic reference/render comparison sheets, crops, overlays, segmentation/mask PNGs derived from those images, and historical Agent renders whose reuse rights have not been established. Files stay untouched on the server. Experiment Markdown and numerical/annotation JSON remain available; the result index identifies withheld PNGs. This is a publication scope decision, not evidence that an experiment was omitted or succeeded.

No third-party model weights, virtual environments, Blender files, EXR arrays, caches, raw session JSONL, archives, secret configuration or other users' data are published. There is no Base64 image request body in the curated JSON.

No new source-code license is assigned by this preparation. Dependencies retain their own terms; the current code imports the separately maintained local `../scene-benchmark` evaluator instead of copying it into this repository.

## Historical paths and limits

Original reports and JSON retain their original paths and states. Absolute `/home/...`, `/srv/...`, `/tmp/...`, `runs/...`, and missing-image references are provenance, not publicly downloadable assets. Do not interpret such references as files contained in this checkout. Original reports may discuss historical HTML, paid API attempts, images, or local resources that are deliberately not published. [Publication notes](results/PUBLICATION_NOTES.md) enumerate unavailable historical Markdown links instead of silently rewriting the original reports or adding substitute images.

The complete server-run inventory CSVs are withheld: they contain verbatim third-party task briefs and a broad server directory listing. A new, explicitly labelled [publication inventory excerpt](results/blenderworld_runs_inventory/publication_inventory.json) retains selected task/run identifiers, eligibility and protocol flags without copying the briefs or file listings. Other numerical/annotation provenance contains only the project owner's paths; those paths are not credentials. No unrelated user's directory contents are included.

The Scene Graph JSON contains stored object bounds, transforms, names and camera metadata, with no vertices, embedded text scripts, drivers or external libraries. Names remain Agent claims, not semantic GT. Existing provider response records were inspected, including nested serialized JSON: the retained records contain model answers, usage and request identifiers, with no authentication headers or image payloads. Reconstructed request examples retain their original designation as reconstructions, not wire captures.

Reading the code and published records requires no server credentials. Replaying many old experiments requires local data/caches, the sibling evaluator, Blender, optional model installations or original Codex session files. A fresh clone is **not** claimed to reproduce all historical experiments in one command. [REPRODUCING.md](REPRODUCING.md) records the missing dependency and data-acquisition steps without inventing a package URL or redistributing private data. Replays must use new output directories and must not make model requests or execute historical Agent code without fresh task authorization.

The original server README was retained locally in `runs/github_publication_preparation_20261024/original_README.md` before the public README was organized. No historic experiment result was edited.

## Git workflow

`results/` is opt-in through `.gitignore`. Review each new file for provenance, secrets, embedded images and size, then stage explicit paths. For an ignored result file use `git add -f -- results/<experiment>/<checked-file>` only after that review; do not use a blanket force-add.

1. Inspect branch, remote refs and working tree; retain existing remotes/history.
2. Curate source, report, data and permitted PNGs; keep actual failures and review states.
3. Update `results/README.md` with date source, research question, finding, links and limitations.
4. Scan the precise candidate files for credentials, image payloads and forbidden/large artifacts; inspect the staged diff and file list.
5. For the first publication, wait for the user's confirmation before commit/push. Later authorized publications still require explicit file review and a non-force push; obey any task-specific instruction prohibiting Git changes.
6. After a successful push, report the actual commit SHA and experiment path. A SHA from a local-only commit does not prove remote publication.

The pending first-publication review list and scan receipt are local files under `runs/github_publication_preparation_20261024/`; they are not credentials and are not a synchronization system.
