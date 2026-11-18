# 0.2.0 — Check the current configuration, explain the difference

## Practical workflow

- `check MANIFEST --baseline SNAPSHOT` captures current inputs in memory and compares them without automatically writing candidates or changing baselines.
- Optional explanatory JSON/HTML report v2 adds bounded change windows, clipped opt-in previews, conservative first-observed-stage interpretation and indexed, content-free terminal output.
- Small head/tail edits remain separate; large alignments use a labelled enclosing range rather than an unbounded diff algorithm.
- Native expandable report sections keep passing cases compact, with explicit partial/incomparable states rather than misleading green stages.

## Correctness and safety

- One frozen input payload ties preflight and capture to the same manifest/tokenizer/template bytes; no stale protected-file list from a second manifest read.
- Native capture runs behind a subprocess stderr boundary with a 60-second wall-clock timeout. Malformed native configurations no longer leak panic tracebacks through the public capture path.
- Observed disagreement between direct and separately rendered IDs rejects new captures; old inconsistent snapshots no longer imply a postprocessing cause.
- Invalid argument diagnostics no longer echo arbitrary supplied values.
- Real local ByteLevel BPE and WordPiece tests cover Unicode, whitespace, normalizer changes, extra tokens and assistant continuation.

## Compatibility

- Snapshot schema remains v1. Both actual v0.1.0 and new v0.2.0 producer identifiers are accepted.
- Existing compare API/CLI retain report v1 by default. `compare --explain` and the new check workflow use report v2.
- Report v2 opt-in content is bounded previews, not v1 full-content export. Consumers must inspect schema_version.
- Core comparison/reporting still require no third-party runtime packages. Capture dependencies remain explicitly pinned.

## Limits unchanged

This is not a model-quality evaluator, live-serving parity certificate, malicious-template sandbox, hard memory isolation tool or authenticated proof of capture. Multi-backend service integrations and real-user adoption remain unverified. The new CI matrix is a configuration until independently executed by the publishing workflow.
