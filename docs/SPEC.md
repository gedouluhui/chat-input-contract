# Chat Input Contract — v0.1 contract

## Purpose

An offline CI tool for capturing and comparing chat preprocessing evidence. It is not a new tokenizer, a model evaluation system, a deployment parity guarantee, or a security scanner. The value is an installable capture → evidence → regression workflow, not the invention of token diffing. No model weights, API credentials, network requests or remote Python code are needed.

## Supported execution

Python >=3.11. First integration target: Transformers 5.8.0, tokenizers 0.22.2. Load an explicit local `tokenizer.json` using `PreTrainedTokenizerFast`, explicit Jinja template, string-valued special tokens. Do not use AutoTokenizer or load arbitrary custom classes. Only text system/user/assistant messages. No tools, multimodal content, padding, truncation, batches, slow tokenizers or arbitrary template kwargs. Generation and continuation are booleans and mutually exclusive. Templates are trusted local configuration, not a security sandbox.

## Manifest v1

JSON object with exactly `schema_version`, `tokenizer`, `template`, `special_tokens`, `options`, `cases`. Paths resolve relative to the manifest. No URLs. Existing input files are never modified. An output path must not resolve to an input path.

`schema_version` is integer 1 (not true/1.0). `tokenizer` and `template` are nonempty paths. `special_tokens` is an object with optional string values for `bos_token`, `eos_token`, `unk_token`, `pad_token`, `sep_token`, `cls_token`, `mask_token`; no unknown keys.

`options` has exactly `route`, `add_special_tokens`, `add_generation_prompt`, `continue_final_message`. `route` is `direct` or `render_then_encode`; other options are strict booleans. Direct route requires add_special_tokens=false. Both generation flags cannot be true.

`cases` is a nonempty array. Each item has exactly `id` and `messages`. IDs are nonempty strings up to 128 characters and unique. Messages is a nonempty list of objects with exactly `role` and `content`; role is system/user/assistant and content is a string (empty string permitted).

Budgets: manifest <=2 MiB; tokenizer <=64 MiB; template <=128 KiB; cases <=256; total message characters <=1,000,000; individual render <=1,000,000 characters; <=262,144 IDs per observed sequence; total selected IDs <=1,000,000. Serialized snapshots and JSON reports are limited to 64 MiB of actual UTF-8 bytes including indentation and escapes. Capture checks this before returning success; JSON writing and reading use the same limit, so a successful snapshot can be read back. Special-token strings may be empty and have a 4,096-character maximum. Token-spelling text is bounded to 1,000,000 characters per case. Check before reading/expanding when possible. Native tokenization, Jinja rendering and JSON serialization can allocate before result checks: these are workflow budgets, not hard RAM/CPU sandbox limits. No unbounded corpus scan.

## Capture API and observations

`capture_manifest(path: str | Path) -> dict`. Uses strictly decoded UTF-8 JSON with duplicate object keys and NaN/Infinity rejected. Metadata imports may be lazy so snapshot comparison needs no Transformers installed.

For each case, call the real library for:

1. `apply_chat_template(..., tokenize=False)` -> rendered text.
2. `apply_chat_template(..., tokenize=True, return_dict=False)` -> direct IDs.
3. `encode(rendered, add_special_tokens=False)` -> unprocessed IDs.
4. `encode(rendered, add_special_tokens=True)` -> postprocessed IDs.

Selected IDs are the direct sequence for direct route; otherwise the selected encode sequence. Record actual output, never fabricate a faulty snapshot to serve as a demo. `convert_ids_to_tokens(selected)` produces selected token spellings. Capture exact vocabulary identity from the full key→ID map and special-token mapping, not just the IDs observed in one case. Fingerprint tokenizer JSON bytes and template bytes separately. Include installed library versions, no local absolute paths or timestamps.

## Snapshot v1 (exact keys)

```
{
  "schema_version": 1,
  "producer": "chat-input-contract/0.1.0",
  "runtime": {"transformers": "5.8.0", "tokenizers": "0.22.2", "jinja2": "3.1.6"},
  "artifacts": {
    "tokenizer_sha256": "64 lowercase hex",
    "template_sha256": "64 lowercase hex",
    "vocabulary_sha256": "64 lowercase hex"
  },
  "options": {
    "route": "direct",
    "add_special_tokens": false,
    "add_generation_prompt": true,
    "continue_final_message": false
  },
  "cases": [{
    "id": "example",
    "messages_sha256": "64 lowercase hex",
    "rendered_text": "actual rendering",
    "input_ids": [1, 4, 2],
    "tokens": ["<bos>", "hello", "<eos>"],
    "direct_ids": [1, 4, 2],
    "unprocessed_ids": [1, 4, 2],
    "postprocessed_ids": [1, 1, 4, 2, 2]
  }]
}
```

Each ID is a strict nonnegative int <=2**32-1, not bool/float. Token strings count equals selected ID count. All object keys are exact; runtime contains exactly those three nonempty version strings, including the template runtime. Apply the manifest case-count limit, render limits, per-sequence limits and total selected-ID limit to loaded snapshots too. Hash format validated, not treated as cryptographic authentication. Selected sequence must agree with options and the corresponding stored observed sequence. Snapshot is self-reported evidence, not proof of origin; input and provenance hashes do not stop a malicious author fabricating a whole snapshot.

## Pure comparison API

`validate_snapshot(snapshot: dict) -> None`; raises `ContractError(code, message)` on invalid input.

`compare_snapshots(baseline: dict, candidate: dict, *, include_content: bool = False) -> dict` validates both. No input mutation, no filesystem, no Transformers import.

Report exact top-level keys:

- `schema_version`: 1
- `status`: `match`, `drift`, or `incomparable`
- `summary`: `total`, `match`, `drift`, `incomparable` integer case counts
- `provenance_changes`: list of `{field, baseline, candidate}` strings; include runtime, tokenizer/template/vocabulary hashes and options when changed. Artifact hash drift alone is informational, not behavioral regression.
- `case_results`: per union of case IDs, sorted lexically, with `id`, `status`, `stages` (list of codes), `first_char_difference`, `first_token_difference` (nonnegative index or null), `lengths` ({baseline_chars,candidate_chars,baseline_tokens,candidate_tokens}; missing side null).
- Each case MAY contain `content` ONLY if include_content=True: baseline/candidate each null or `{rendered_text,input_ids,tokens}`. Otherwise no prompt text, IDs or spellings enter a report.

Case IDs themselves may be sensitive; users must choose non-sensitive identifiers for sharing. Default reports contain only IDs, lengths, difference positions, fixed codes and fingerprints/version/options provenance. No source path or freeform exception text containing content.

Case rules:

- Missing side: incomparable, `MISSING_CASE`.
- Different messages_sha256: incomparable, `INPUT_CHANGED`.
- Different generation or continuation flags: incomparable, `INTENT_CHANGED` (do not guess whether this was intentional or correct).
- Otherwise different vocabulary hash: drift, `VOCABULARY_CHANGED`, even if same integer IDs.
- Different rendered_text: drift, `RENDER_CHANGED`.
- Different unprocessed_ids: drift, `TOKENIZATION_CHANGED`.
- Different selected IDs with equal rendered_text and unprocessed_ids: drift, `POSTPROCESSING_CHANGED`; if selected differ in other cases add `TOKENS_CHANGED`.
- Direct vs unprocessed mismatch within either snapshot: drift, `ROUTE_INCONSISTENCY` (observed evidence, no universal blame assignment).
- Different selected token spellings: drift, `TOKEN_SPELLING_CHANGED`.
- Otherwise match. Unknown intentional changes require user review, never automatic correction.

Stage codes are deterministic and unique. first differences computed on rendered Unicode code points and selected IDs separately; a strict prefix difference returns min length, equality returns null. Overall incomparable takes precedence over drift, then match; all results still reported. `summary.total` equals union case count and all buckets sum to total.

## Errors and CLI

`ContractError` extends ValueError and exposes code/message; use content-free diagnostics such as `INVALID_MANIFEST`, `INVALID_SNAPSHOT`, `BUDGET_EXCEEDED`, `CAPTURE_FAILED`, `OUTPUT_CONFLICT`.

Commands:

- `capture MANIFEST --out SNAPSHOT`
- `compare BASELINE CANDIDATE --json REPORT [--html REPORT] [--include-content]`
- `demo --out DIRECTORY`

Compare exits 0=match, 1=drift, 2=incomparable or rejected input/runtime failure. Capture exits 0 only with complete valid snapshot and successful write. Always produce a concise content-free stderr diagnostic on failure; no traceback or success artifact after invalid input. Write JSON atomically, ensure_ascii=False, UTF-8 LF, allow_nan=False; refuse overwriting existing files unless `--force` explicitly supplied. Even with force, never overwrite inputs; JSON and HTML outputs must be distinct. Demo uses a new or empty output directory and refuses reuse by default.

## Demo and evidence

Generate an original fixed WordLevel vocabulary, WhitespaceSplit pre-tokenizer and TemplateProcessing BOS/EOS postprocessor with the installed tokenizers library. Jinja template itself emits BOS/EOS with spaces. Run direct, safe two-stage, and unsafe two-stage captures through actual capture API. Exact small sequence has an independent hand-calculated assertion in tests. Direct vs safe must match; direct vs unsafe must drift with POSTPROCESSING_CHANGED. Do not insert faulty final snapshots by hand.

Demo writes source tokenizer/template/manifests, all three snapshots and safe/broken comparison reports. A successful demo command means both expected outcomes occurred, not that the broken path passed. Repair is shown by the safe two-stage real path. A restored flag alone without another execution is not verification.

## HTML

`render_html(report: dict) -> str` uses only report data. Dependency-free single HTML file with inline CSS, no JS required, no network/CDN/fonts. Responsive editorial/engineering style: pale background, dark ink, teal match, amber drift, red incomparable; clear privacy notice, overall status, stage counts, provenance changes and case evidence. Escape all supplied strings/HTML. Use CSP default-src 'none'; style-src 'unsafe-inline'; no external links based on untrusted values. No dark-pattern star prompts or fabricated benchmarks. Explicit details panel only for opted-in content.

## Verification and release

stdlib unittest to avoid altering global packages. Independent mutation controls must prove selected-ID, missing-case and vocabulary predicates matter. End-to-end tests execute real CLI, reload artifacts and check output bytes/return codes. Fresh wheel installation in a new isolated environment plus demo; don't treat editable install as clean-install evidence. Browser-open generated report at desktop and narrow viewport, check layout and no external requests. Independent read-only review, fix important issues, rerun relevant tests. Never include private handover, credentials, generated snapshots, environment directories or unrelated projects in Git. README English-first plus Chinese quick start, limitations, schema and tests, MIT for original code after dependency license review. GitHub publication only after checks; remote existence and CI state are separate from local commits. User's existing publication authorization applies; do not create credentials or alter account settings silently.
