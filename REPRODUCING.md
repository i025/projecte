# Reading and reproducing Project e

This publication contains source and selected historical records. It is not a self-contained release of all data, models or server environments. No API call, model inference, Blender run or dependency installation was performed for this publication review.

## What works from the public files

Clone `https://github.com/i025/projecte.git` after its first approved publication. Read [recent experiments](results/LATEST.md), the [complete index](results/README.md), and [publication omissions](results/PUBLICATION_NOTES.md). JSON/CSV/Markdown can be inspected without credentials or model installations. First-party synthetic comparison PNGs can be opened directly.

For example, this uses only Python's standard library to read an actual saved result; it does not run a verifier or recalculate an Energy:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('results/structural_visual_verifier_controls/verification_results.json')
record = json.loads(p.read_text())
print('backend:', record['backend'])
print('model:', record['model'])
print('sessions:', record['actual_verifier_sessions'])
print('reviewed:', record['reviewed'])
print('formal energy:', record['formal_energy'])
PY
```

This checks record accessibility, not verifier accuracy. Model sessions are historical observations and are not reproduced by reading their JSON.

## Core CPU tests need one additional local package

Use Python 3.10+ on Linux; the code uses recent Python syntax and Linux process controls. [requirements.txt](requirements.txt) declares the main Python dependencies. [requirements-lock.txt](requirements-lock.txt) records an older server environment, but omits NumPy/SciPy and optional vision packages. Do not treat it as a full cross-platform or hardware-specific lock. On a machine you administer, create an isolated environment and install the declared main dependencies; do not alter a shared environment just to inspect results.

The core currently imports `benchmark.metrics`, `benchmark.evidence` and `benchmark.background` from a **sibling checkout** named `scene-benchmark`, configured in [benchmark_config.py](e_harness/benchmark_config.py):

```text
parent/
  projecte/          # this checkout; directory name may differ
  scene-benchmark/
    benchmark/
      metrics.py
      evidence.py
      background.py
```

That sibling code is not bundled and no verified public distribution URL is available in this publication. Obtain the compatible source and its redistribution terms from the maintainer before running core tests. Do not install an unrelated package named `benchmark` as a substitute. Until this dependency is supplied, a clean clone cannot import the full evaluator; that is a known reproduction blocker, not a test failure hidden by the documentation.

With that dependency and the declared Python dependencies already available, these bounded unit tests do not invoke models, APIs or Blender:

```bash
python3 -B -m unittest discover -s tests -p 'test_benchmark.py'
python3 -B -m unittest discover -s tests -p 'test_structural*.py'
python3 -B -m unittest discover -s tests -p 'test_kitchen_structural_transfer.py'
```

Those patterns previously ran 64 tests in the prepared server environment. They do not establish clean-install portability or the quality of a real visual verifier. Do not run every script as an installation check: some historical scripts contain live request/render stages or generate legacy HTML.

## Reference data and historical Render pairs

Acquire BlenderWorld inputs from its [official dataset card](https://huggingface.co/datasets/Qwen/BlenderWorld) or [official repository](https://github.com/QwenLM/BlenderWorld), under the applicable data terms. Its MIT software statement alone does not confirm redistribution rights for each reference photo. This publication neither downloads data nor republishes the photos.

The [selected-run excerpt](results/blenderworld_runs_inventory/publication_inventory.json) provides original task/run identifiers. Pair audits in each experiment describe which Reference, historical Agent Render and `.blend` were associated. Downloading a reference task alone does **not** provide that historical Agent output; request the matching Run from its owner if access is permitted. Never substitute a same-named scene or a different Render. Keep all path, image-size, camera and comparison-transform checks from the relevant original report.

Frozen Region Plans and ROI coordinates describe the original Reference pixel coordinates. Use the saved original image size and saved Render transform; do not re-ground or align ROI to make the Render look better. Reference cameras may be unknown, and historical Render cameras do not establish Project e's fixed-T0 contract. Results remain `provisional/debug`.

Some ROI masks and all real-image comparison PNGs are withheld. Their file paths in the original JSON are provenance, not download links. Recreating them requires authorized source data and the documented original processing; no placeholder mask is supplied here.

## Optional experiments and unsatisfied dependencies

| Workflow | Additional requirements | Current publication limit |
| --- | --- | --- |
| Read answers / deterministic comparison | Published JSON and the matching parser | No new visual verification occurs |
| Appearance / texture diagnostics | Correct Reference–Render pair, fixed ROI and main dependencies | Real images/masks require authorized access |
| DINO Perceptual | Matching local checkpoint and vision environment | Weights/environment not bundled; N/A remains valid |
| SAM/SLIC experiments | Matching optional packages, local weights/caches as applicable | Not part of this publication run; no automatic download |
| Scene Graph / Group-ID | Matching reviewed `.blend`, historical camera and reviewed CPU launcher | Source scene and visible Mask not publicly supplied; do not execute Agent code |
| Historical Codex Subagent observations | Original isolated inputs and session records | JSON replay is not a fixed-API reproduction or new blind test |

See the report for the exact experiment's input and failure conditions. Scripts often have server-local defaults and caches. Do not assume `--help` is the only precondition or execute a historical command blindly. Any new experiment must use a new output directory and obtain authorization for paid requests or unreviewed scene access. Formal Runtime remains blocked; no publication step changes that state.
