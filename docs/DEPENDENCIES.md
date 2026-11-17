# Dependency and license boundaries

Original Chat Input Contract code and self-authored example data are MIT-licensed. No third-party source tree, model weights, tokenizer assets from a model publisher, fonts or browser libraries are vendored into the project.

The core comparison, JSON I/O, report and CLI use the Python standard library only. The optional capture extra requests these exact tested packages:

| Package | Version | License evidence inspected |
|---|---|---|
| transformers | 5.8.0 | Installed distribution metadata declares Apache 2.0 License; the clean wheel contains its LICENSE. |
| tokenizers | 0.22.2 | Installed distribution classifier declares Apache Software License. The inspected wheel does not contain a license file; consult upstream licensing when redistributing it. |
| Jinja2 | 3.1.6 | Installed LICENSE.txt is the three-clause BSD license, copyright Pallets. |

The extra installs these packages and their transitive dependencies separately; it does not relicense them as MIT or embed them in this project's wheel. A bundled application or redistributed environment would require its own complete dependency/license review. Build tooling setuptools/wheel is not a runtime dependency.

Jinja2 is explicitly declared because Transformers installation alone did not install it in the clean environment used for this release. The initial clean demo failed for that reason before the declaration was corrected. Capture fingerprints all three runtime versions.

Sources: [Transformers package](https://pypi.org/project/transformers/5.8.0/), [tokenizers package](https://pypi.org/project/tokenizers/0.22.2/), [Jinja documentation](https://jinja.palletsprojects.com/en/stable/). Metadata and installed license evidence are described above, not a claim that every upstream repository or transitive dependency was exhaustively audited.
