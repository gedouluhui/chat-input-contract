# Chat Input Contract

**Catch chat-preprocessing drift before you blame the model.**

An offline capture → compare → evidence workflow for local chat templates and fast tokenizers. It tells you whether a change happened in the input, rendered prompt, tokenizer vocabulary, tokenization, or special-token postprocessing.

No model weights. No GPU. No API key. No runtime network requests. Comparing saved snapshots has **zero third-party dependencies**.

[中文快速开始](README.zh-CN.md) · [Exact contract](docs/SPEC.md) · [Example HTML report](docs/example.html)

## The bug you can reproduce in one command

A chat template already adds BOS/EOS. A second tokenization call adds them again. The rendered text looks right, but the model receives a different sequence.

From a source checkout with Python 3.11+:

```sh
python -m pip install ".[capture]"
chat-input-contract demo --out demo-output
```

Actual demo outcome:

```text
Demo verified: safe=match, broken=drift, cases=3.
```

Open `demo-output/broken-report.html`. The example uses an original tiny WordLevel vocabulary and **real Transformers/tokenizers calls**, not a prewritten failure report. It also runs the repaired two-stage path and verifies that it matches direct tokenization.

For the single-turn case:

```text
Direct / repaired:  [1,    3, 5, 6, 2, 4, 5]
Extra postprocess: [1, 1, 3, 5, 6, 2, 4, 5, 2]
                      ^ first difference: token 1 (zero-based)
```

A working CI check must fail on the broken path, not merely generate an attractive report.

## Capture your configuration

Create a manifest relative to your own local files:

```json
{
  "schema_version": 1,
  "tokenizer": "tokenizer.json",
  "template": "chat.jinja",
  "special_tokens": {"bos_token": "<bos>", "eos_token": "<eos>", "unk_token": "<unk>"},
  "options": {
    "route": "direct",
    "add_special_tokens": false,
    "add_generation_prompt": true,
    "continue_final_message": false
  },
  "cases": [
    {"id": "single-turn", "messages": [{"role": "user", "content": "hello"}]}
  ]
}
```

Use the **actual special-token strings and template for your tokenizer**; the example strings are not universal model defaults. This tool deliberately does not infer a model class or silently use a remote template.

```sh
chat-input-contract capture manifest.json --out baseline.json
# Change your local configuration, then capture again:
chat-input-contract capture manifest.json --out candidate.json
chat-input-contract compare baseline.json candidate.json --json result.json --html result.html
```

Capture records four observations per case: rendered text, direct template tokenization, encoding without extra special tokens, and encoding with extra special tokens. `route` chooses the tested output; the other observations provide evidence for interpreting a difference.

For a two-stage deployment path, choose `"route": "render_then_encode"` and explicitly declare `add_special_tokens`. The ordinary safe choice when the template supplies special tokens is `false`, as explained in the [HF documentation](https://huggingface.co/docs/transformers/en/chat_templating). Whether a different configuration is appropriate remains your decision.

## CI verdicts, without false reassurance

| Exit | Status | Meaning |
|---|---|---|
| 0 | `match` | All named cases agree under the recorded input contract. |
| 1 | `drift` | Comparable cases differ; inspect the stage evidence. |
| 2 | `incomparable` / rejected | Inputs/intent/case coverage differ, or input/runtime/output validation failed. |

Missing cases are not silently dropped. Changing the vocabulary is detected even if the particular examples still produce identical integer IDs. Runtime/file fingerprint changes are reported as provenance; they are **not automatically called behavioral regressions**.

The overall result is `incomparable` if any case cannot be compared, even when other cases drift. The report retains every case. A passing capture command only means a complete snapshot was recorded; run `compare` to enforce a baseline.

No automatic fix or baseline blessing is performed. Intentional changes need review. Different tokens do not, by themselves, establish worse model quality.

## Privacy and output safety

**Snapshots contain rendered prompts and reversible token information. Treat them as sensitive.** Nothing is uploaded by this tool.

JSON comparison reports and HTML hide prompt text, IDs and token spellings by default. They still contain case identifiers, lengths, fingerprints and configuration/version metadata; choose non-sensitive case names and review reports before sharing. SHA-256 fingerprints are not anonymization or authentication.

`--include-content` explicitly exports the sensitive details into both comparison outputs. HTML is escaped, has no scripts/CDN/fonts/telemetry, and can be opened offline. Existing outputs are refused unless `--force` is supplied; inputs are protected even under force. Each output file is published atomically; a JSON+HTML pair is not a filesystem transaction, so an I/O failure can leave the already-completed first file.

## Scope, honestly

**Supported first:** explicit local HF fast-tokenizer JSON; text `system`/`user`/`assistant` messages; boolean generation/continuation options; strict versioned snapshots; Python API and CLI. Capture dependencies are pinned to the first tested integration, Transformers **5.8.0**, tokenizers **0.22.2**, and Jinja2 **3.1.6**. Newer versions are not implicitly certified.

**Not supported:** AutoTokenizer model discovery, custom Python tokenizer classes, slow tokenizers, model inference, multimodal/tool-call inputs, arbitrary template kwargs, batching/padding/truncation policies, live vLLM/llama.cpp service parity, or model-quality evaluation. Loading a local tokenizer JSON is not equivalent to reproducing every option of its serving environment.

Jinja templates are trusted local configuration. File/character/token budgets limit ordinary workflow size, but native tokenization/rendering may allocate before result checks. This is **not a hostile-code sandbox or a hard RAM/CPU limiter**. A snapshot is self-reported evidence, not a signed proof of execution.

## Python API

```python
from chat_input_contract import compare_snapshots, validate_snapshot
from chat_input_contract.capture import capture_manifest  # requires [capture]
from chat_input_contract.io import load_json
from chat_input_contract.report import render_html

baseline = capture_manifest("baseline-manifest.json")
candidate = load_json("candidate.json")
report = compare_snapshots(baseline, candidate)
assert report["status"] == "match", report["summary"]
html = render_html(report)
```

`capture` is optional. `python -m pip install .` installs only the pure compare/report CLI.

## Verification

```sh
python -m pip install ".[capture]"
python -m unittest discover -s tests -v
python -m build
```

For source-only testing, install the package or add `src` to `PYTHONPATH`. Tests use original local fixtures and real library calls. They cover strict inputs, coverage/vocabulary checks, actual duplicate-special-token drift and repair, output preservation, privacy and HTML escaping. Known-bad controls mutate **in-memory copies** of guard code and require named behavioral assertions to fail; the active source tree is never mutated.

See [verification notes](docs/VERIFICATION.md) for what was actually run and what remains unverified. Test counts and passing checks are engineering evidence, not user adoption, statistical model accuracy or future stars.

## Why another tool?

HF already implements template rendering. llama.cpp already has strong tokenizer differential tests. This project does **not** invent token comparison or replace them. It packages local preprocessing observations into strict transferable snapshots, case-coverage-aware CI results, and small offline evidence reports. For backend tokenizer implementation correctness, use the backend's own upstream tests.

If you find a useful missing case, include a **minimal self-authored fixture**, the library versions, expected intent and a redacted report. Never post private prompts or credentials. Contributions should add a failing test before changing a contract rule.

Original code: MIT. Third-party dependencies retain their own licenses; see [dependency notes](docs/DEPENDENCIES.md).
