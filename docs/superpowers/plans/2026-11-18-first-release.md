# Chat Input Contract First Release Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development with isolated file ownership and test-first execution. The owner performs integration and final verification.

**Goal:** Installable offline chat-input capture and evidence-based regression checking, with a real duplicate-special-token failure and repair demo.

**Architecture:** A strict JSON contract joins a pure comparison module, an optional real HF capture adapter, CLI/filesystem operations, and a static HTML renderer. Core comparisons never import HF or execute templates.

**Tech Stack:** Python >=3.11; stdlib unittest; optional transformers 5.8.0 / tokenizers 0.22.2; static HTML/CSS.

**Spec:** `docs/SPEC.md` is authoritative for exact formats, limits and semantics.

## Global Constraints

- Offline: no API calls, AutoTokenizer, remote code, model weights or telemetry.
- Only this new repository; never read parent private documents into project outputs.
- Snapshot v1 and report v1 keys, codes and budgets are specified exactly in SPEC.
- Capture observes real library outputs; errors are not invented in completed snapshots.
- `match` is contract agreement, never model quality or universal serving compatibility.
- Default reports omit text/IDs/spellings; snapshots are explicitly sensitive local data.
- Test-first, actual execution, independently checked negative controls; no fabricated pass counts.
- Each implementation worker owns disjoint named files and must not commit or launch agents.
- The owner chooses implementation details; no further user design prompts are required.

## Task 1: Strict snapshots and pure comparison

**Files:** `src/chat_input_contract/errors.py`, `src/chat_input_contract/core.py`, `tests/test_core.py`.

**Produces:** `ContractError(code: str, message: str)`; `validate_snapshot(snapshot: dict) -> None`; `compare_snapshots(baseline: dict, candidate: dict, *, include_content=False) -> dict`.

- [ ] Write minimal hand-built valid snapshots in test helpers; assert a copied baseline matches, is not mutated, and has no `content`.
- [ ] Run `PYTHONPATH=src python -m unittest discover -s tests -p test_core.py -v`; observe named assertion failure before implementation, then implement the smallest contract.
- [ ] Add one red test group at a time: first differences/prefix, actual vocabulary mismatch despite equal IDs, exact case coverage, input/intent incomparability, stage attribution, provenance-only changes, privacy.
- [ ] Add strict-input tests for booleans/floats posing as IDs/version, unknown keys, invalid hashes, empty cases, duplicate case IDs, inconsistent selected trace and each budget.
- [ ] Require real behavior in tests, e.g.:

```python
candidate = copy.deepcopy(baseline)
candidate['artifacts']['vocabulary_sha256'] = 'b' * 64
result = compare_snapshots(baseline, candidate)
self.assertEqual(result['status'], 'drift')
self.assertIn('VOCABULARY_CHANGED', result['case_results'][0]['stages'])
```

- [ ] Rerun only owned tests, report exact command/result and tests' mutation sensitivity. Owner reviews code and reruns the integrated suite before committing.

## Task 2: Offline real capture and evidence demo

**Files:** `src/chat_input_contract/io.py`, `capture.py`, `demo.py`; `tests/test_capture.py`, `tests/test_io.py`.

**Consumes:** errors and pure snapshot validation from Task 1.
**Produces:** `load_json(path, max_bytes=...) -> dict`; `write_json(path, obj, *, force=False, protected=()) -> None`; `capture_manifest(path) -> dict`; `run_demo(directory) -> dict`.

- [ ] Write red tests using a self-authored WordLevel vocab and real tokenizers TemplateProcessing, with an independent manually listed expected sequence.
- [ ] Implement UTF-8 strict JSON reader, duplicate-key rejection, finite values and bounded read. Atomic exclusive output writes; no overwrite of input even under force. Test bad JSON, byte limits, NaN, duplicate keys, existing output and identical/symlink-resolved input/output.
- [ ] Validate all manifest fields before constructing a tokenizer; convert each library exception to a content-free `ContractError`. Test unsupported role/content/options and missing dependency failures.
- [ ] Call the four real observation paths in SPEC; explicitly set return_dict=False. Hash canonical messages/vocab and raw artifacts; omit local paths/timestamps. Test same inputs produce equal captures.
- [ ] Test direct and safe encode path agreement and true double-BOS/EOS failure:

```python
safe = capture_manifest(safe_manifest)
broken = capture_manifest(broken_manifest)
self.assertEqual(safe['cases'][0]['input_ids'], expected_ids)
self.assertNotEqual(safe['cases'][0]['input_ids'], broken['cases'][0]['input_ids'])
self.assertEqual(compare_snapshots(safe, broken)['status'], 'drift')
```

- [ ] Implement demo sources then call actual capture/comparison; fail the demo if expected good/bad results do not occur. No manual writes to produced snapshots before comparisons.
- [ ] Test invalid files do not produce partial success output and snapshots' data sensitivity is documented.

## Task 3: Static evidence report

**Files:** `src/chat_input_contract/report.py`, `tests/test_report.py`.
**Consumes:** SPEC report v1; no import of capture or library dependencies.
**Produces:** `render_html(report: dict) -> str`.

- [ ] Write red tests for overall/case states, empty provenance list and clear first-difference indexing.
- [ ] Implement self-contained accessible HTML/CSS. Test raw injected strings such as `</script><img src=x onerror=alert(1)>` do not occur as markup:

```python
html = render_html(report_with_hostile_id)
self.assertNotIn('<img src=x', html)
self.assertIn('&lt;img', html)
```

- [ ] Add tests: CSP/no scripts/external resources; privacy notice; absent content never synthesized; present explicit content escaped; long values wrap; narrow-screen media query.
- [ ] Owner opens a real generated report and checks mobile/desktop layout, content and network behavior. Unit markup checks alone are not visual verification.

## Task 4: CLI, packaging, reproducibility and public material

**Files:** `__init__.py`, `__main__.py`, `cli.py`, `pyproject.toml`, `.gitignore`, `README.md`, `README.zh-CN.md`, `LICENSE`, `.github/workflows/ci.yml`, `tests/test_cli.py`, `tests/test_mutations.py`.

- [ ] Test subprocess CLI help, unknown command, capture completion, compare return codes 0/1/2, redacted output and opt-in content. Test output collisions before any writes; JSON/HTML must not overwrite sources or one another.
- [ ] Implement argparse CLI with safe diagnostics. Core-only install supports compare/report; optional `[capture]` extra installs fixed tested dependencies.
- [ ] Test demo through the installed CLI. Unit scripts use `unittest discover`; network-independent test data generated locally.
- [ ] Inject isolated-copy mutants of vocabulary check, missing-case rule and selected-ID comparison. Assert the designated tests fail by named assertions, not syntax/import errors; never mutate the active repository or run file-mutating sweeps concurrently.
- [ ] Build wheel/sdist, inspect archive file allowlist, install wheel in fresh venv and run demo. Fresh venv may access dependency downloads only as install operations, not demo runtime.
- [ ] English-first README includes quickstart, real output, API/schema, intentional differences, unsupported scope, privacy, upstream alternatives and tested versions. Chinese quickstart mirrors capabilities. No claimed user/star/performance numbers.
- [ ] Check original MIT license and dependency notices, scan explicit publish files/history for secrets and local private paths. Initialize only this new repository; stage explicit files, create initial commit with user identity already configured, never modify git config.
- [ ] Independent review, fix important findings, final local verification. Coordinate authorized GitHub publishing without racing other sessions or credentials; distinguish local ready from uploaded and CI passed.

## Interface/self-review

| Boundary | Producer / consumer | Check |
|---|---|---|
| 1 → 2 | ContractError, validate_snapshot | exact names and v1 shapes shared |
| 1 → 3 | report dict | privacy optional content key identical |
| 1/2/3 → 4 | capture/compare/render | return-code mapping owned by CLI |
| 1/3 parallel ownership | no shared edited files | safe; owner integrates only after return |
| All tasks | SPEC budgets and supported scope | no automatic downloads or model claims |

Decision: use a new independent directory rather than a linked worktree because there is no source repository or existing branch to protect. Final git init is restricted to this directory. Agent model selection is inherited because the available tool has no model parameter. No commits are delegated, preventing staging races. This plan and public SPEC contain no private handover content.
