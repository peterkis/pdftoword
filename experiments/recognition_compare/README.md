# Fixed three-arm recognition and Word comparison

This opt-in experiment does not register a production route or change model configuration.
A uses the existing reconstruction-v2 route; B/C use the explicitly authorized MinerU
v4 official pipeline/vlm service. Every uploaded file sets `files[].is_ocr=true`.
No local MinerU installation is needed. Authentication is read from an explicit
`--token-file` and is never passed to signed-storage requests or written to logs.

Use the existing Python 3.12 environment. `RUN` must be a new ignored directory under
`tmp/docx-demo`; `DATASET` is the provided batch3 package; `EDITS` is the exported owner
review JSON. `TOKEN_FILE` is the separately supplied private credential file.

```sh
.venv/bin/python experiments/recognition_compare/run_compare.py prepare \
  --dataset "$DATASET" --edits "$EDITS" --run-dir "$RUN"
.venv/bin/python experiments/recognition_compare/run_compare.py run \
  --run-dir "$RUN" --arm A --group G1
.venv/bin/python experiments/recognition_compare/run_compare.py run \
  --run-dir "$RUN" --arm B --group G1 --token-file "$TOKEN_FILE"
.venv/bin/python experiments/recognition_compare/run_compare.py run \
  --run-dir "$RUN" --arm C --group G1 --token-file "$TOKEN_FILE"
```

After G1 evidence is delivered, repeat the three commands for G2 through G6 in order.
There are six input groups, 29 source pages and at most 18 original DOCX outputs;
the online arms submit 12 files / 58 page instances. The three supermix groups keep
Russian separate (`cyrillic`); other groups use `ch`. Native source objects remain
intact for A. This is a system comparison, not an equal-input-image bare-model test.

A preparation freezes the complete region/page request budgets before inference.
A uses its existing no-retry ledger. Each experiment arm/group reserves a directory
exclusively and a run-wide lock serializes inference. A crash leaves the lock as a
visible unresolved condition; do not remove it until process/job state is inspected.
Online submissions are single attempts. Poll every 10 seconds up to 30 minutes;
`resume` polls the saved ID/download only, never re-uploads or resubmits:

```sh
.venv/bin/python experiments/recognition_compare/run_compare.py resume \
  --run-dir "$RUN" --arm B --group G1 --token-file "$TOKEN_FILE"
.venv/bin/python experiments/recognition_compare/run_compare.py evaluate \
  --run-dir "$RUN" --output "$RUN/evaluations/v1"
.venv/bin/python experiments/recognition_compare/run_compare.py report \
  --run-dir "$RUN" --evaluation "$RUN/evaluations/v1" --output "$RUN/reports/v1"
```

Evaluation/report do not import converters or make model calls. A Python socket guard
protects the offline path; this is not an operating-system sandbox. Results and frozen
inputs/reference files are hash-sealed. Each evaluation/report gets a fresh directory.
Source-tree drift blocks additional inference; evaluator corrections must be versioned
and historical scores retained. Source notes/images, responses, signed URLs, source
paths and credentials remain private. Do not commit the output directory or token file.

## Reference and quality boundaries

Owner edits are merged into copied references with before/after records. Per-item owner
confirmation is not global human coverage acceptance. Image-only and source-truncated
items are not expected to become editable text. Formula context records are not extra
equations. The owner confirmed scan page 9 has three logical columns; its old two-region
geometry is explicitly NOT a validated three-column grid, so automatic topology scoring
is withheld until source-aligned adjudication. The original selected PDFs are re-rendered
after lossless page copy and compared byte-for-byte at the pixel level.

mix page 4 is a derived-content diagnostic: its content scores are shown separately and
excluded from the primary aggregate to avoid double-counting native page 2; its page layout
remains part of the comparison. Full automatic semantic reconstruction of clipped/derived
annotation units is not attempted. Incomplete four-source macro averages are labeled.

Geometry determines recognition alignment. Repeated text, fused spans and overlapping
reference boxes remain explicit alignment-review items, not free passes. Unsupported
formula syntax or table topology is unscored with a reason. Actual missing units stay in
the denominator. Online discarded blocks are preserved but never counted as emitted text.
Relations absent from an output are not synthesized by the evaluator.

Word inspection reads the unchanged OOXML package and builds separate tentative alignment
records; it does not insert source bookmarks into official DOCX files. Word rendering,
representative editing, image preservation and relationship/geometry adjudication require
actual evidence and remain NOT_RUN until performed. Package counts are not accuracy.
The static report presents available renders from `renders/G*/A|B|C/page-*.png` and links
receipts, raw Word documents and per-unit evidence. It never manufactures a quality winner.

## Tests

```sh
.venv/bin/python -m pytest tests/experiments/test_recognition_compare.py -q
.venv/bin/python -m ruff check experiments/recognition_compare tests/experiments/test_recognition_compare.py
.venv/bin/python -m mypy experiments/recognition_compare tests/experiments/test_recognition_compare.py
```

Synthetic fixtures prove adapter safety and metric behavior only. Real runs, Word visual
observations and human acceptance are separate evidence levels.

## Authorized page-limit amendment

The application default remains three pages. An explicit `convert --page-limit N`
(or `convert(..., page_limit=N)`) allows a larger finite input and records the cap.
Duplicate/out-of-range pages remain rejected. This changes admission only, not routing,
prompts, inference retries, geometry or rendering algorithms.

For the owner-authorized batch3 amendment, `extend-page-limit` accepts only G2/G3
previously blocked by `MAX_THREE_PAGES`, with zero prior calls and no inference artifacts.
It creates a separate run, copies the other 16 immutable results, preserves the original
manifest identity, and prepares the 12-page/9-page routes before freezing new budgets.

```sh
.venv/bin/python experiments/recognition_compare/run_compare.py extend-page-limit \
  --previous-run "$PREVIOUS_RUN" --run-dir "$NEW_RUN"
.venv/bin/python experiments/recognition_compare/run_compare.py run \
  --run-dir "$NEW_RUN" --arm A --group G2
.venv/bin/python experiments/recognition_compare/run_compare.py run \
  --run-dir "$NEW_RUN" --arm A --group G3
```

Offline `analysis.comparison` produces paired common-reference text metrics;
`word_evidence.audit_word` audits actual Word PDF exports against original DOCX copies.
The viewer uses `word-render-pristine` for actual Word pages and keeps bundled renderer
images under `renders` as auxiliary evidence. Word Print-to-PDF can crop non-default
paper sizes: prefer local Save As PDF for those documents, retain the failed print export,
and never use Microsoft's online conversion option without separate authorization.
Open one inspection copy at a time and close it immediately after inspection.
