# 0.2 design: actionable, local CI checks

## Scope and compatibility

Upgrade the existing offline tool rather than creating a platform. The public 0.1.0 tag and artifacts are immutable. Work on improve-v0.2; publishing is coordinated separately after verification. Capture remains explicit local HF fast-tokenizer JSON with trusted text-only templates, no model, no remote code or downloads. Core-only compare remains dependency-free. Python >=3.11; tested capture versions remain Transformers 5.8.0, tokenizers 0.22.2, Jinja2 3.1.6.

Snapshot schema stays v1 and accepts producers chat-input-contract/0.1.0 and chat-input-contract/0.2.0. Captures use the new producer. Legacy compare_snapshots and default compare CLI keep report v1, preserving its observational stage codes. Observations are not causal claims; a changed rendering can explain downstream token changes. Existing genuine v0.1.0 self-authored snapshots are used as compatibility controls.

## Capture hardening from reproduced defects

Capture preflight and execution share one immutable `PreparedCapture` payload. Manifest, tokenizer and template are read once; exact bytes are sent over stdin to a private subprocess. Protected paths refer to those actual consumed inputs, not a later manifest revision. Public API and CLI both use this boundary. The worker returns complete JSON or a fixed error code; native panic text and stderr are not forwarded. Raw inputs are not placed in argv, temporary files or environment variables.

A 60-second worker wall-clock timeout aborts capture and publishes no success snapshot. This is a duration/error boundary, not an OS privilege, network or hard-memory sandbox. Native runtime diagnostics are deliberately unavailable in the default report because they can expose source paths/content. Direct and separately rendered IDs must agree in each new capture; observed inconsistency returns CAPTURE_INCONSISTENT. A finite agreeing observation is not proof that a random/time-dependent template is deterministic. Use stable templates. Existing v1 snapshots with route inconsistency remain readable and report drift, but no longer assign POSTPROCESSING_CHANGED solely from their differing selected IDs; that correction replaces an overconfident v1 inference.

## One-command workflow

`check MANIFEST --baseline SNAPSHOT [--json REPORT] [--html REPORT] [--include-content] [--force]` loads and validates the baseline before capture, validates the manifest, preflights every output alias against baseline/manifest/tokenizer/template and other outputs, captures actual current inputs in memory, compares, renders requested evidence, and prints bounded diagnostics. No default output file, no implicit candidate snapshot, no baseline writes. `--force` permits only already-existing reports, not inputs. Missing/corrupt baselines abort before tokenizer work; output preflight aborts before capture too.

Python API `check_manifest(manifest_path, baseline_path, *, include_content=False) -> dict` has no writes and returns explanatory report v2. CLI owns filesystem publication and return codes 0/1/2. Existing capture/compare commands remain. `compare --explain` opts into v2; default remains v1. `--version` reports package version. Argument-parser errors use fixed safe diagnostics, never echo arbitrary supplied values. Terminal case identifiers are indices in report order, not user-controlled text; at most 10 nonmatching cases are printed, with an explicit omitted count. Terminal never emits raw prompt/IDs/spellings, even with content export enabled.

## Explanation report v2

`explain_snapshots(baseline, candidate, *, include_content=False) -> dict` starts from validated v1 comparison semantics but sets schema_version=2 and adds top-level `content_included` boolean. It does not include legacy full-content blobs. Each case adds `analysis` with:

- `earliest_stage`: inputs, vocabulary, rendering, tokenization, postprocessing, consistency, token_spelling, or null. This is the first observed divergence under explicit criteria, not a proven root cause. Incomparable cases use inputs and do not align content.
- `notes`: static explanatory sentences, never supplied prompt strings. Vocabulary differences precede ID comparisons; different renderings make downstream token differences expected rather than proof of tokenizer failure. Same-render/unprocessed but different selected output supports a postprocessing-path observation.
- `character_change`, `token_change`: null for incomparable cases; otherwise bounded change summaries.

`sequence_changes(a,b,*,include_content=False,kind='tokens')` trims equal prefix/suffix in O(n). The remaining middles use difflib.SequenceMatcher(autojunk=False) only when product length <=65,536 and sum length <=4,096. Larger middles use one exact enclosing window, explicitly `alignment='enclosing'`, not approximate edit-distance claims. Small alignments are deterministic but not necessarily unique/minimal. Empty or equal sequences are valid controls.

Summary: `alignment` (equal/bounded/enclosing), `total_windows`, `omitted_windows`, `windows` (first two and last if more than three; otherwise all). Windows contain zero-based half-open `baseline_start/end`, `candidate_start/end`, `removed_count`, `added_count`. Raw content appears only with include_content=true in `baseline_preview` / `candidate_preview`: before, changed, after, omitted_items. Token preview: context 4, changed segment at most32; character preview: context24, changed segment at most160. Large changes are visibly clipped. Output limits do not claim hard RAM isolation; inputs retain v1 budgets.

## Report experience

Render v1 and v2; v2 groups cases in native details elements and adds human-readable interpretation, change ranges and optional bounded highlighted previews. Match cases are collapsed, nonmatches open; native keyboard navigation remains. Avoid false green pipeline labels when cases are incomparable: use 'Not comparable', not 'No reported difference'. Stage highlighting uses earliest_stage for v2, observational codes for v1 with explicit downstream caveats. No script/CDN/font/network addition. Escape all supplied content. Explicit export warning stays visible; even redacted case IDs/fingerprints may be sensitive.

## Verification and improvement gates

- Genuine released snapshot remains readable; same baseline/candidate v1 result unchanged except strengthened rejection of invalid evidence.
- Live check detects actual broken extra-token processing, repaired path matches, missing cases remain incomparable and can never overwrite baseline. No-write mode produces no files.
- Prefix/suffix/two-ended inserts, repeated tokens, middle edits, empty sequences, overflow alignment fallback, preview/window clipping, input immutability, text escaping and redaction get independent controls. Small deterministic random sequences use a reconstruction invariant rather than precomputed diff answers.
- Test actual ByteLevel BPE and WordPiece local toy tokenizers, Unicode/whitespace/multi-turn/assistant prefill. No paid models or unlicensed corpora.
- Any independently reproduced v0.1 defect gets a regression first, then minimal correction and documented compatibility impact.
- CI validates core-only installs and supported Python versions on Linux/Windows, plus pinned capture dependencies. Configured matrix is not counted as executed until the coordinator publishes and actual runs succeed.
- Verify new wheel in a fresh environment, source bytes vs installed files, sdist replay, HTML desktop/mobile, tests and named in-memory mutation controls. Use new logs/artifact directories, never overwrite 0.1 evidence.
- Independent review and owner verification precede fixed-commit handoff. No 'world-leading', user adoption or star-growth claims without evidence.
