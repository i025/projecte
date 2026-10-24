# Supervised contrast reconstruction

This is an opt-in, assistant-reviewed experiment, not the formal unattended Runtime.
The latter remains blocked. No filesystem sandbox or aggregate task quota is claimed.

`run.py --image <id> --request --live` makes one request and stops after saving it.
It saves the actual incremental prompt and uses the same tool schemas and full conversation history.
The user-authorized batch ceiling is 10 USD and each image permits at most 8 requests.
Requests have no automatic retries and max_tokens=4096. Every request uses the exact
configured `requests.Session.post()` through BlenderWorld's reviewed `OfoxTunnel`:
only loopback is bound, original OFox hostname/SNI and certificate verification remain.
The BlenderWorld project is read-only and no alternate provider is contacted.

`run.py --image <id> --apply --review-note '...'` processes only the last saved call.
An execute submission requires a separate assistant review of the complete source,
with a note and byte comparison to the original provider response. It cannot be
automatically approved by the request loop. The reviewed immutable bytes enter
Blender through stdin. No static filter is treated as a security boundary.

A schema-valid execute call with a Python syntax error receives a failed tool result
without constructing a Runtime or launching Blender. The original code is retained;
the error line and unchanged scene version enter the next normal model request.
The model can revise within the remaining request/fee budget; no repair call or
transport retry is added. Already processed calls cannot be applied again.
Each image's `issues.jsonl` and each round's trajectory record syntax errors,
tool failures and API/protocol failures with references to their complete saved details.
Origins distinguish model output, tool execution and API/protocol outcomes; a tool
failure is not automatically attributed to the model. Historical runs are not rewritten.

The supervised adapter subclasses the existing Blender Runtime and retains its
replace/update commits, scene snapshots and failure retention. Only its process
launcher is overridden with the calibrated namespace/CPU/resource-monitored launcher.
Execution, rendering, custom views, inspection and reopening all use that launcher.
Model keys do not enter the sanitized Blender environment. Autoexec is disabled.
Empty-scene World normalization is the previously tested, explicitly enabled policy.
Input-camera observations occur only when requested by the agent or required to finish.

The standalone request path deliberately does not use the old SDK transport: this
server requires the configured session. It records the raw response and actual usage,
without changing the provider model identifier or adding provider-specific prompting.

Balance differences are account-wide and may settle late. They are not SDK-confirmed
costs. The budget guard also considers twice the uncached estimate at cached supplier
prices (2 USD/M input, 10 USD/M output), and reserves 1 USD before each request.
These are labelled estimates, not guaranteed future prices. If balances or a previous
charge cannot be verified, no further request is made. No search/tool add-ons are requested.

132 existing non-Blender offline tests passed; three Blender integration classes were
intentionally skipped because their launchers do not use the supervised resource profile.
The transport/review/profile tests passed separately (3 tests).
The trusted CPU fixture saved/reopened/inspected and rendered input/custom views,
while preserving the original blend bytes. The first fixture exposed a missing log-file
interface in the adapter; the correction and failed fixture are preserved in run artifacts.

The supervised profile is explicitly authorized at 32 GiB RSS, 64 GiB virtual address
space, 1200 cumulative CPU seconds and 600 wall seconds. CPU affinity/render threads
remain 2, the process monitor 4 and thread monitor 128. Original launcher defaults are
unchanged; optional limits are passed only by this experiment. GPU use requires a
successful trusted render, a currently idle device, 1 GiB VRAM headroom, and a watcher
that stops our task if a foreign process appears. No other task is terminated.
All trusted probe attempts and stop snapshots remain in the batch artifacts.

Final per-object joining is separate postprocessing: retain original part-level scenes,
do not repair geometry, and do not use reference annotations to decide model revisions.

`diagnostic_render.py --image <id>` separately renders the last saved scene with its
unchanged camera, a 512-pixel longest edge, the reference aspect ratio, 64 samples and
CPU denoising. It uses the same monitored launcher and idle-GPU policy. The source
blend is not saved, original feedback images are retained, and the diagnostic never
enters Agent messages. It changes presentation settings, not model geometry or the
batch's 256×256 / 8-sample observation protocol.
