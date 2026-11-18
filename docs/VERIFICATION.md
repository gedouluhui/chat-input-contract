# Verification record — 0.1.0

Observed locally on 2026-11-18 for the original 0.1.0 release. This record describes executed checks, not universal compatibility or adoption. Version 0.2 adds separate evidence; these historical results must not be treated as verification of newer code.

Execution-scope clarification: the unittest suite includes CLI subprocess tests that explicitly select the inspected source tree. A run in an installed-package venv therefore combines package/API checks with source-selected CLI checks; it is not exclusively a wheel test. Byte identity and separate real installed CLI runs provide additional release evidence.

## Executed

- Windows, Python 3.12.3: `python -m unittest discover -s tests -v` passed **53 tests**, including six in-memory known-bad controls.
- A separate venv installed the built wheel and the declared capture dependencies. Every installed Python source file was compared byte-for-byte with the release source; no differences remained. Its test run passed **53 tests**.
- The installed CLI executed the original demo: `safe=match, broken=drift, cases=3`. The safe path is a separate real execution, not an edited failure snapshot.
- A core-only wheel installation, without Transformers, executed a saved-snapshot comparison successfully. Core comparisons do not import the capture dependencies.
- `python -m build --no-isolation` produced wheel and source distribution. The final source archive includes its public documentation and tests; no virtual environment or generated private snapshots are intended for distribution.
- Real browser inspection of the self-authored HTML example: desktop 1280-pixel viewport and emulated 390-pixel viewport, no horizontal page overflow, all three cases visible, no resource requests. The final example highlights only the postprocessing stage for this failure. These are Chromium checks, not Safari/Firefox/mobile-device verification.

The pure suite includes case-union rather than intersection, vocabulary change with unchanged observed IDs, strict integers rather than bool/float, selected-route consistency, safe defaults, prefix-difference indices, input/output alias protection, and byte-budget checks on both sides of the threshold.

## Defects found and corrected before release

Independent review found a snapshot that could be captured successfully but exceeded the reader's byte limit. A real fixture of twelve 950,000-NUL renderings reproduced it: JSON escaping expands characters to six bytes. Capture and JSON publication now enforce the same 64 MiB serialized-byte limit as the reader. This is a size contract, not an allocation sandbox.

The same review identified an overly strict empty-special-token rejection and JSON numeric exponent overflow (`1e999` / `-1e999`). Both were reproduced, fixed and covered by regression tests. The report's stage highlight also needed a regression test: changed final spellings caused by an extra postprocessor must not blame the unchanged tokenizer stage.

Clean installation exposed a missing Jinja2 requirement. It is now explicit, pinned and fingerprinted with the other runtime versions. The minimal environment reports that PyTorch is absent; that is expected because this project does not run models.

A reinstall check caught another verification trap: pip kept the old 0.1.0 implementation while updating its extras. The exact rebuilt wheel was then force-reinstalled, source hashes were checked, and the installed demo and tests were rerun. The earlier same-version install was not counted as final verification.

A read-only scoped review subsequently marked all five submitted fixes addressed, with no evidenced new must-fix finding in that scope. Independent review is a useful check, not a proof that all possible bugs have been excluded.

## Not established

No live vLLM/llama.cpp parity, model quality, training behavior, GPU throughput, hard memory isolation, authenticated snapshot provenance, Safari/Firefox support, physical mobile-device behavior, real-user adoption or star-growth claim. Python 3.11 is the declared floor; the local executions above used 3.12. GitHub Actions has a separate public execution history and must not be inferred from these local results.

## Reproduce

```sh
python -m pip install ".[capture]" build
python -m unittest discover -s tests -v
chat-input-contract demo --out fresh-demo-directory
python -m build
```

Use a new demo directory; reusing a populated directory is deliberately refused. Before sharing any non-demo evidence, review its identifiers, fingerprints and content-export choice.
