# Project e collaboration and publication

- Keep the five Observation Energies, independent 3D Structural Energy, camera protocol, aggregation weights, and Runtime execution gates unchanged unless a task explicitly authorizes changes.
- New experiments deliver PNG, JSON/CSV, and Markdown. Do not create new HTML review pages by default.
- Keep original evidence, raw model answers, `reviewed` states, `provisional/debug`, Unknown/N/A, failures and unresolved cases. Never rewrite old results to make publication appear successful.
- Read [PUBLICATION.md](PUBLICATION.md) before staging results. Reference dataset images, their crops/overlays and other image-bearing derivatives are withheld until redistribution rights are established.
- Do not stage environments, models, datasets, raw sessions, credentials, unrelated users' files, or large Blender/GPU intermediates. Never use unchecked `git add .` or `git add -A`.
- Update [results/LATEST.md](results/LATEST.md) and [results/README.md](results/README.md) after an experiment, linking the report, data and publication-permitted PNGs. State missing visual assets and historical broken links explicitly; do not rewrite frozen results to repair publication links.
- The first public commit/push requires the user's explicit confirmation of the prepared file list, size, security review and staged diff. Preparation alone does not authorize that first commit or push.
- After the first publication is approved, the user authorizes normal curated commits and non-force pushes following experiments, unless the current task prohibits Git changes. Recheck the remote, review explicit paths and credentials/rights before publishing; preserve existing remote work and never force-push.
- Report the actual GitHub commit SHA and experiment directory after a successful publication. If publication is pending or fails, say so; never invent a SHA or claim files were uploaded.
- Keep publication a simple Git workflow. Do not add synchronization services, registries, custom version systems or automatic model calls.
