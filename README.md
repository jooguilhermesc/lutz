# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="160"/>
</p>

**Languages:** **English** | [Português](README.pt-BR.md) | [Español](README.es.md)

> Validated data extraction for systematic reviews: every cell of the extraction table comes with its quote, its page and a measured confidence level, plus a reliability report for the Methods section and the PRISMA 2020 checklist.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-1.0.0a1-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)

Lutz 1.0 is a rewrite. It does not read 0.5.x projects; see [upgrading from 0.5](docs/upgrade-0.5-para-1.0.md). To keep 0.5: `pip install "lutz-research<1"`.

## How it works

1. **Import PDFs.** Lutz keeps the visible text of every page (hidden text is discarded), fixes the reading order of two-column pages, reads tables row by row and gives every sentence and table row a citable id.
2. **Write the codebook** (the extraction form), with an Assistant, a deterministic lint and a quick test on a few articles.
3. **Autonomous mode.** Three independent extractors (ideally from different vendors) fill every cell with a value, a verbatim quote and a page. The quote is checked against the page text without an LLM, an independent verifier judges whether the quote supports the value, and codebook rules act as a gate. Each cell gets a level: High, Medium or Low. Krippendorff's alpha per field measures agreement among extractors.
4. **Calibrated mode (optional).** A blind pilot with one or two human raters: Cohen's kappa, weighted kappa or ICC per field with bootstrap CIs, a per-field decision, and the measured accuracy of each confidence level.
5. **Adjudication and audit.** Low cells go to a human decision; a random sample of High cells is checked by hand.
6. **Report.** Seven parts in Portuguese and English (Markdown and PDF): run identification, process, reliability by field, level calibration, adjudication, ready-to-paste Methods text, PRISMA 2020 map, RAISE AI-use statement, and annexes with the full log.

## Install

```bash
pip install --pre lutz-research
```

Python 3.10+. Windows installer: see the releases page.

**Windows with `pip`:** PyMuPDF, which reads the PDFs, needs the [Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe). Most machines already have it; on a fresh Windows install it with `winget install --id Microsoft.VCRedist.2015+.x64 -e`. If it is missing, `lutz doctor` says so. The `lutz.exe` from the releases page carries these DLLs and needs nothing else.

## Quick start

```bash
lutz init my-review --pergunta "Do LLM tutors improve student engagement?"
cd my-review
lutz config set OPENROUTER_API_KEY sk-or-...   # one key for every model (https://openrouter.ai/keys)
# choose E1, E2, E3 (extractors) and V (verifier) in lutz web > Settings, or in lutz.yaml
lutz doctor --chamar
lutz load ~/papers/
lutz codebook new                 # or: lutz codebook import codebook.yaml
lutz codebook test --campo sample_size
lutz codebook freeze
lutz extract                      # cost estimate, confirmation, run
lutz adjudicate export            # then: lutz adjudicate import <file>
lutz audit sample                 # then: lutz audit import <file>
lutz report
lutz web                          # the same flow in the browser
```

Every model runs through [OpenRouter](https://openrouter.ai): one key, the whole catalog, prices and usage in the Settings screen; see [configuration](docs/configuracao.md).

## Interfaces

* **CLI** `lutz` — [reference](docs/referencia-cli.md).
* **Web** — `lutz web` (127.0.0.1 only): Library, Codebook, Pilot, Extraction, Results, Adjudication, Report, API & MCP, Settings.
* **REST API** — OpenAPI at `/api/docs` while `lutz web` runs.
* **MCP server** — `lutz mcp --projeto .` (stdio, read-only) for Claude Desktop, Cursor and VS Code.

## Documentation

* [System specification](docs/spec-1.0.md)
* [Statistical methods](docs/metodos-estatisticos.md)
* [Configuration](docs/configuracao.md)
* [End-to-end validation with a real article](docs/validacao-e2e.md)
* Site: [jooguilhermesc.github.io/lutz](https://jooguilhermesc.github.io/lutz/)

## How to cite

```bibtex
@software{cabral2026lutz,
  author  = {Cabral, João Guilherme Silva and Azevedo Farias, Anna Karoline},
  title   = {{Lutz: validated data extraction for systematic reviews}},
  year    = {2026},
  version = {1.0.0a1},
  doi     = {10.5281/zenodo.19982571},
  url     = {https://github.com/jooguilhermesc/lutz}
}
```

## License

MIT
