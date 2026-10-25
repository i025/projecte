# Public projection of the actual Existing-Scene batch

This public view retains actual model questions/raw answers, numerical results,
Unknown/N/A, failures, review states and camera limitations. Server originals
are unchanged. Owner-specific absolute paths and temporary CLI state locations
are replaced by repository-relative references or explicit placeholders. They
are provenance, not downloadable inputs or a runnable replacement frozen config.
Raw answer strings, prompts and scientific values are not rewritten.

All third-party Reference/Render/comparison PNGs and valid-pixel Masks remain
server-only. The frozen private input config and full input audit (task briefs
and broad server metadata) are withheld; dataset_audit.json exposes selection
and exclusions without those briefs. Stage reservations remain on the server;
call status/budget are retained in report.json and the raw response packets.
The initial execution report is retained privately; public report.json has a
zero-inference deterministic coverage/table refresh. Historical visibility-cache
host UID/PID/CPU binding and execution commands are omitted from public projections;
scientific pass/measurement/limitations fields remain.

There are no model weights, environments, Blender assets, Agent source code,
credentials, full CLI sessions or Base64 image bodies in this publication.
No published result is independent human GT or a formal Benchmark score.
