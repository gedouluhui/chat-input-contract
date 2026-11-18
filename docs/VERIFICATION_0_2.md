# Verification — published 0.2.0

Observed on 2026-11-18, Windows / Python 3.12.3, with remote results read back on 2026-11-19. The 0.2.0 tag and assets are published. The independent whole-upgrade final review gap remains as described below.

## Executed checks

| Check | Observed result | Execution scope |
|---|---|---|
| Current source suite | 100 tests passed | Includes real captures, native panic/timeout controls, aliases, privacy, compatibility and nine in-memory known-bad controls. |
| Source-distribution replay | 100 tests passed | Tests from extracted sdist, parent API imports from installed wheel; some CLI tests explicitly select the byte-matched sdist source. Not exclusively a wheel test. |
| Core-only environment | 61 tests passed | No Transformers, tokenizers or Jinja2 installed. Pure comparison, explanations, reports, input validation and compatibility. |
| Real installed capture CLI | 9 scenarios matched expected return codes and artifacts | Executed outside the source and sdist trees, with PYTHONPATH removed by a Python subprocess launcher. All installed Python modules byte-match source. |
| Real installed core CLI | Match/0 and drift/1 | Same external directory, no capture dependencies, explanatory report v2. |
| Browser report | Desktop 1280px and emulated 390px | No horizontal overflow, three cases, six change windows, no external resources. Enter toggled the focused native case summary open→closed→open. |
| Published tag CI | success | [Run 44412198343](https://github.com/gedouluhui/chat-input-contract/actions/runs/44412198343) on commit `0f08489`; main and `improve-v0.2` runs also succeeded. |

The nine real installed CLI scenarios were original demo, live safe check, live broken check, legacy v1 compare, opt-in v2 explanation/content, baseline overwrite rejection, repeated-demo rejection, safe argument rejection and fresh capture. The golden baseline bytes remained unchanged. Negative return code 1 is expected for genuine drift; a runtime failure/2 is not counted as successful drift detection.

## Strengthened evidence

The real tokenizer matrix uses locally authored ByteLevel BPE and WordPiece models, no public/private model download. It checks literal Unicode/whitespace roundtrip, hand-calculated WordPiece IDs, direct/safe route agreement, actual extra-BOS/EOS insertion, same-render normalizer changes and assistant prefill. Synthetic tests are not real-user adoption or universal tokenizer compatibility.

The legacy fixture is an actual self-authored capture from the earlier 0.1.0 validation, SHA256 `74e4dd58f04809cc03b59be5904eb4bf4b4ef498ac0bebd09163eb59d9f8ffa6`. It is distinct from the separately hand-authored schema-compatibility control; neither is presented as third-party data.

Known-bad controls replace selected guards only in in-memory module copies, requiring a named behavioral assertion to fail and rejecting crashes as evidence. New controls cover alignment budget, visible window omissions and opt-in preview privacy. Repeated-sequence alignments are not promised unique/minimal; large changes are explicitly labelled as enclosing ranges.

## Review and corrections

Independent targeted reviewers reproduced and checked the fixes for stale protection paths from repeated manifest reads, a native panic escaping the exception boundary, unstable rendering being blamed on postprocessing, argument echoing and live-check alias handling. A reported version-field gap was corrected with explicit old/new producer acceptance and unknown-version rejection tests.

The final whole-upgrade independent reviewer could not start: the service returned a daily-quota 403 with no tool execution. It supplies **no review result**. The owner completed the integrated tests, installed-CLI probes and visual review described above; 0.2.0 was published with this gap disclosed rather than labelled universally approved.

Two test-launch attempts using a local PATH-provided `env` command returned success without running Python or creating test evidence. They were rejected as invalid measurements. Actual verification uses `subprocess.run` with an explicitly sanitized environment, requires an observed test count and `OK` in nonempty logs, and checks the artifact content. An exit code alone is insufficient.

## Reproduce

In a fresh environment, install the published 0.2.0 wheel with its capture extra, or install a reviewed source checkout:

```sh
python -m pip install ".[capture]"
python -m unittest discover -s tests -v
chat-input-contract demo --out fresh-demo
chat-input-contract check fresh-demo/safe-manifest.json --baseline fresh-demo/direct-snapshot.json
chat-input-contract check fresh-demo/broken-manifest.json --baseline fresh-demo/direct-snapshot.json --json broken.json --html broken.html
```

Expected final command exit: 1, with postprocessing evidence. Use fresh output paths, and do not auto-regenerate your baseline in CI. The default report contains no full prompt/token content; case names and fingerprints still require review before sharing.

## Unverified

The published Linux/Windows Python 3.11/3.12/3.13 matrix succeeded for tag commit `0f08489`; see the run linked above. No live vLLM/llama.cpp compatibility, slow/custom/multimodal tokenizer support, hard memory or OS privilege sandboxing, authenticated capture origin, model quality, physical-mobile/Safari/Firefox results, real users or star-growth claims are established.
