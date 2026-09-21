# P2W-U1-01: isolated MinerU public DOCX experiment

Status: **BLOCKED for real inference / B.docx**. Local CLI and synthetic contract
tests exist; no new runtime, weights, service, remote request or real MinerU
render has been executed. This directory is opt-in and has no production route.
The existing Layout IR pipeline and DocVortex 0.4.9 environment remain unchanged.
This direct upstream comparison is explicitly scoped to U1-01; it is not a new
production exception to the repository's Layout IR boundary.

## Public contract and versions

- MinerU **4.0.4**, public source snapshot
  [`45ba9d1`](https://github.com/opendatalab/MinerU/tree/45ba9d1502eb1f35477894492d80d35e8f14aa24).
- DocVortex **0.4.17** satisfies that snapshot's declared `>=0.4.15,<1` range.
  This is metadata compatibility, **not an installed/runtime compatibility test**.
- [`parse`](https://github.com/opendatalab/MinerU/blob/45ba9d1502eb1f35477894492d80d35e8f14aa24/mineru/parser/__init__.py)
  returns `ParseResult`; its public `save(writer)` writes the materialized complete
  package (MiddleJson, Markdown, structured content, original images and optional
  model output). `BundleWriter` implements the documented DataWriter interface
  with stronger path confinement; it does not copy an upstream algorithm.
- [`render_docx`](https://github.com/opendatalab/MinerU/blob/45ba9d1502eb1f35477894492d80d35e8f14aa24/mineru/render/docx.py)
  takes typed MiddleJson and a bytes-returning asset resolver. There is no
  Markdown/Pandoc conversion, custom document layout algorithm or CLI DOCX flag.

## After installation and model-processing authorization only

Run on the authorized model host, with its existing Python 3.12 and `uv`.
Choose a **new private path**, represented below by `$EXPERIMENT_ENV`, and a new
private evidence directory `$RUN_ROOT`. Do not reuse the repository `.venv` or
its `tmp/docx-demo/docvortex-runtime/.venv`. Commands below have **NOT_RUN** status.

First save a read-only host snapshot privately: timestamp, `nvidia-smi` GPU count,
UUID/name/free memory, `/proc/meminfo`, `ss -ltn` and current GPU processes. Do not
stop existing services or assume either GPU is free. Select backend/device only
from that evidence; installing additional backend extras requires authorization.

```sh
# Installation/download authorization required; existing Python only.
UV_PYTHON_DOWNLOADS=never uv venv --python 3.12 "$EXPERIMENT_ENV"
uv pip compile experiments/mineru_replacement/requirements.in \
  --python "$EXPERIMENT_ENV/bin/python" --generate-hashes \
  -o "$RUN_ROOT/requirements.lock"
uv pip sync --python "$EXPERIMENT_ENV/bin/python" "$RUN_ROOT/requirements.lock"
"$EXPERIMENT_ENV/bin/python" experiments/mineru_replacement/run_direct.py inspect-env
```

`requirements.in` pins the two direct dependencies only. No transitive lock or
installed dependency receipt is claimed yet. Actual run receipts enumerate all
installed distributions. Weight provisioning is separate: verify and record the
actual backend, tier, GPU/device, model revision and file hashes before inference;
unknown fields remain `unknown`. Do not copy the old environment or automatically
share its vLLM/CUDA dependencies. This full SDK is not a lightweight Mac client.

```sh
# Explicit authorization for this input and local model processing required.
# INPUT is a local original PDF; physical page is one-based. No file is uploaded.
"$EXPERIMENT_ENV/bin/python" experiments/mineru_replacement/run_direct.py parse \
  --input "$INPUT" --page 4 --tier standard --evidence-kind real \
  --allow-local-parse --output "$RUN_ROOT/first"

# Uses only sealed saved results. No parser import, parse call, upload or retry.
"$EXPERIMENT_ENV/bin/python" experiments/mineru_replacement/run_direct.py export \
  --bundle "$RUN_ROOT/first/bundle" --output "$RUN_ROOT/offline-reexport"
```

The input page number must match the selected source receipt; an image accepts
only page 1. `--tier flash` is an explicit alternative and is recorded as flash;
it does not establish standard quality. No self-hosted HTTP adapter is included:
this first bounded implementation selects the public **local SDK** route. A Mac
client or new V1 service/FRP mapping is not necessary to run it on a model host.

The local inference command sets hub offline flags and denies Python sockets.
Weights must already be provisioned; it will not intentionally download them.
The socket guard is **not an OS sandbox for native code or subprocesses**. Use a
network-disabled worker/container for the actual disconnected acceptance test.
Only explicitly authorized installation may use the network. Do not rerun a
failed parse automatically; retain the run and investigate. For this local route
there is no remote job ID to poll. No timeout becomes a successful result.

## Evidence and error behavior

Each command reserves a new output directory; it refuses to overwrite evidence
or export into its own source bundle. On success: `B.docx`, `run-receipt.json`, and
(for `parse`) `bundle/bundle-manifest.json` plus `bundle/result/` containing all
upstream saved files. On failure: nonzero exit and a sanitized receipt; partial
bundles remain for diagnosis. No failed bundle is silently treated as a complete
result. Do not use human-corrected/golden data as a real automatic parse result.

The seal checks every file and asset hash. Absolute paths, traversal, symlinks,
external image URLs, unregistered assets, missing images and wrong schema are
rejected. Upstream public typed validation and materialized-asset validation run
before DOCX rendering; error codes preserve failure without exposing source text.
Upstream Python/native stdout/stderr is discarded because it may contain private
content. Bundle files themselves are sensitive and must stay in ignored/private
storage. Never commit raw bundles, logs, local paths, PDFs, fonts or DOCX files.

The receipt records SHA-256, source physical page, requested/actual tier, producer,
runtime packages, parser entry calls, renderer and ZIP/XML/object inventory.
Internal native model request counts are **not instrumented**. Unknown backend,
weights or device are not fabricated. Word opening, visual quality and local
image/formula fallback verification remain `NOT_RUN` / `NOT_REVIEWED` until
actually checked. Object counts do not establish correctness or editability of
all source content. This experiment does not rewrite already-selected native
text in the production pipeline, and does not assert that MinerU preserved it.

After actual B exists, open it in Word, record version/open result and inspect
content/order/source page, image integrity, formula/table fallbacks. Re-export
with the OS network disabled from the same bundle; record zero new parse calls
and output hashes. Preserve both files if DOCX metadata makes bytes differ.

## Local verification (no installation / no model)

```sh
.venv/bin/python -m pytest tests/experiments/test_mineru_direct.py -q
.venv/bin/python -m ruff check experiments/mineru_replacement tests/experiments/test_mineru_direct.py
.venv/bin/python -m mypy experiments/mineru_replacement tests/experiments/test_mineru_direct.py
.venv/bin/python experiments/mineru_replacement/run_direct.py inspect-env
```

The tests use explicit public-API doubles and synthetic DOCX files. They prove
adapter behavior, safe paths, sealed persistence, sanitized failures and no parser
import during repeat export. They do **not** prove MinerU/DocVortex 0.4.17 runtime
compatibility, actual disconnected inference, real B quality or Word acceptance.
Use Python 3.12; the host's unqualified `python3` may still select Python 3.9.
