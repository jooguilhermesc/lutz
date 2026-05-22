# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="180"/>
</p>

**Languages:** **English** | [Português](README.pt-BR.md) | [Español](README.es.md)

> AI-powered tool for organizing, screening, and analyzing academic PDF articles — with a full browser interface and command-line access.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.3.0-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Public%20Preview-blue)
![Interface](https://img.shields.io/badge/Interface-Web%20%7C%20CLI-informational)

**Tags:** systematic review, academic screening, scientific articles, generative AI, LLM, RAG, embeddings, PDF, LanceDB, Python, open science, academic research.

Lutz helps researchers, students, and literature review teams work with large sets of PDF articles. It creates a reproducible project structure, processes and embeds PDFs into a local vector database, and uses language models to screen, analyze, and chat about your articles — all through a browser interface or the command line.

The package is named after **Bertha Maria Julia Lutz**, an important Brazilian scientist, biologist, and researcher who contributed to biology and to the recognition of science in Brazil.

---

## What's new in v0.3.0

- **React web interface** — full browser UI replacing the previous Streamlit prototype. Faster, more responsive, works on any device on the local network.
- **Background jobs** — vectorize, analyze, and extract citations while freely navigating the interface. A notification bell tracks every job.
- **Chat with sessions** — conversation history persisted on disk, automatic memory extraction, and support for context files alongside articles.
- **Reading roadmap** — LLM-generated staged reading plan that groups and orders relevant articles by dependency.
- **Inline PDF viewer** — open any article directly in the browser without leaving the interface.
- **Smart rename** — suggest a clean filename from the article's own content with one click, no vectorization required.
- **Multi-provider LLM/embedding** — OpenAI, Anthropic, Docker Model Runner, Ollama, llama.cpp — configurable from the Settings page.
- **Windows installer** — one-click setup wizard with license, shortcuts, and uninstaller; no Python or Node required.

---

## Table of contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Web interface](#web-interface)
- [Model configuration](#model-configuration)
- [CLI reference](#cli-reference)
- [Complete systematic review workflow](#complete-systematic-review-workflow)
- [How to write prompts](#how-to-write-prompts)
- [Security model](#security-model)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [How to cite](#how-to-cite)
- [License](#license)

---

## Installation

### Windows — installer (recommended for non-technical users)

Download `lutz-setup-windows-x64.exe` from the [latest release](https://github.com/jooguilhermesc/lutz/releases/latest) and run it. The wizard will:

- Show the MIT license agreement
- Let you choose the install directory
- Create a Start Menu entry and optional Desktop shortcut
- Register an uninstaller in Windows Settings → Apps

After installation, open **Lutz Research** from the Start Menu. The browser interface opens automatically.

> **No Python or Node.js required.** Everything is bundled in the installer.

---

### pip (Python users)

```bash
pip install lutz-research
lutz web
```

Requires Python 3.10+. A virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.\.venv\Scripts\Activate.ps1   # Windows PowerShell

pip install lutz-research
lutz web
```

---

### uv (fast, isolated — recommended for Linux / macOS)

[uv](https://docs.astral.sh/uv/) installs and runs the tool in a fully isolated environment with a single command:

```bash
uv tool install lutz-research
lutz web
```

To update later:

```bash
uv tool upgrade lutz-research
```

---

### Docker

Ideal for servers, shared environments, or Linux users who prefer containers:

```bash
# Start the server, mounting your project directory
docker run -v $(pwd):/project -p 8765:8765 ghcr.io/jooguilhermesc/lutz

# Then open http://localhost:8765 in your browser
```

The container bundles the full stack (Python, dependencies, React UI). Your article files and reports live in the mounted `/project` directory and are never copied into the image.

---

### From source

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e ".[dev]"
```

Build the React frontend to use the web interface from source:

```bash
cd web && npm ci && npm run build
cd ..
lutz web
```

---

## Quick start

```bash
# 1. Create a new project
mkdir my-review && cd my-review
lutz init

# 2. Copy your PDFs into articles/  (or upload via the web interface)
lutz load --f ~/Downloads/pdfs --so linux

# 3. Open the web interface
lutz web
```

The browser opens at `http://localhost:8765`. From there you can vectorize articles, run analyses, chat with your corpus, and generate reports — no more command line needed.

---

## Web interface

`lutz web` starts a local FastAPI server and opens the browser automatically.

```bash
lutz web                              # default: localhost:8765
lutz web --port 8080                  # custom port
lutz web --host 0.0.0.0               # expose on local network
lutz web --no-browser                 # server only, no auto-open
lutz web --project /path/to/project   # explicit project directory
```

### Pages

#### Home
Project dashboard showing article count, vectorized chunks, analyses run, and quick-action buttons. Entry point for first-time setup.

#### Library (Vetorização)
Upload PDFs via drag-and-drop or file picker. View all articles with size, vectorization status, and a one-click rename suggestion. Start vectorization as a background job and navigate freely while it runs.

#### Vector Store
Inspect the LanceDB index: total chunks, unique documents, embedding model, last update. Query the index directly with DuckDB SQL. Reset the store when you need to rebuild from scratch.

#### Analysis
Write or upload a Markdown prompt, choose RAG or per-article mode, set workers and chunk limits, and dispatch the analysis as a background job. A live log panel appears on the page if you return while the job is still running.

#### Citations
Select a per-article analysis report and extract the 3–5 passages that best justify each article's classification. Runs as a background job with real-time progress.

#### Roadmap
Generate a staged reading plan from your relevant articles. The LLM groups articles by conceptual dependency and suggests an order for reading.

#### Reports
Table of all past analyses. Click any row to expand the full results, including per-article verdicts, analysis text, token usage, and model metadata. Download JSON reports.

#### Chat
Conversational interface over your corpus. Each conversation is a persistent session saved to disk. The assistant can search the article vector store, attached context files, or use only its own knowledge — configurable per message. Memories pinned manually or extracted automatically from conversations are shown in a sidebar panel.

#### Settings
Configure LLM and embedding providers, API keys (write-only — never displayed after saving), base URLs, response language, and model parameters. Changes are saved to `.env` immediately.

### Background jobs and notifications

Long-running operations (vectorize, analysis, citations, roadmap) run as server-side background tasks. A bell icon in the top bar shows a badge when jobs are running or completed. Clicking it opens a panel with status, elapsed time, and the option to cancel in-progress jobs. If you navigate away from a page while a job is running, an **Active Job** panel appears when you return, allowing you to reconnect to the live log stream.

---

## Model configuration

Configuration lives in `.env` at the project root, created from `.env.example` by `lutz init`. It can also be edited from the Settings page in the web interface.

### Docker Model Runner (local, no API key)

```dotenv
EMBEDDING_PROVIDER=docker_model_runner
EMBEDDING_MODEL=nomic-embed-text

LLM_PROVIDER=docker_model_runner
LLM_MODEL=ai/llama3.2

DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
```

Pull models first:

```bash
docker model pull nomic-embed-text
docker model pull ai/llama3.2
```

### Ollama (local, no API key)

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2
```

### OpenAI

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=your-key-here
LLM_MODEL=gpt-4o-mini
```

### OpenRouter (free models available)

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=your-key-here
LLM_MODEL=google/gemma-3-12b-it:free
```

### Anthropic

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
LLM_MODEL=claude-haiku-4-5-20251001
```

### Configuration reference

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | `openai`, `anthropic`, or `docker_model_runner` | — |
| `LLM_MODEL` | Model name for analysis and chat | — |
| `LLM_MAX_TOKENS` | Maximum response size | `4096` |
| `LLM_TEMPERATURE` | Response variation | `0.2` |
| `EMBEDDING_PROVIDER` | `openai`, `sentence_transformers`, or `docker_model_runner` | — |
| `EMBEDDING_MODEL` | Embedding model name | — |
| `OPENAI_API_KEY` | Key for OpenAI or compatible services | — |
| `OPENAI_BASE_URL` | Alternative base URL for OpenAI-compatible APIs | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `DOCKER_MODEL_HOST` | Docker Model Runner address | — |
| `REPORT_LANGUAGE` | Language for generated reports | `português` |

---

## CLI reference

The full workflow is also available from the command line. The CLI and the web interface share the same project structure and `.env`.

### `lutz init [PROJECT_NAME]`

Creates a new project with `articles/`, `prompts/`, `analysis/execution_reports/`, `.env.example`, `.gitignore`, and a local Git repository.

```bash
lutz init
lutz init my-review
```

### `lutz load --f FOLDER [--so OS] [--overwrite]`

Copies PDFs from a source folder into `articles/`.

```bash
lutz load --f ~/Downloads/articles --so linux
lutz load --f "C:\Users\Ana\Downloads\articles" --so windows
```

### `lutz vectorize [options]`

Processes PDFs and creates the vector index in `.lutz/vector_store/`.

| Option | Description | Default |
|---|---|---|
| `--chunk-size` | Chunk size in words | `512` |
| `--chunk-overlap` | Overlap between chunks | `64` |
| `--section-parse` | Split articles into labeled sections before chunking | disabled |
| `--skip-security` | Skip PDF security checks | disabled |
| `--quarantine` | Process files in `articles/_quarantine/` | disabled |

```bash
lutz vectorize
lutz vectorize --section-parse          # section-aware (recommended)
lutz vectorize --chunk-size 256 --chunk-overlap 32
```

### `lutz analysis --p PROMPT [options]`

Analyzes vectorized articles using a Markdown prompt.

| Option | Description | Default |
|---|---|---|
| `--p` | Path to the `.md` prompt | required |
| `--per-article` | One model call per article | disabled (RAG mode) |
| `--workers` | Parallel calls in per-article mode | `1` |
| `--top-k` | Chunks to retrieve in RAG mode | `10` |
| `--max-chunks-per-article` | Chunk limit per article | no limit |
| `--filter-sections` | Restrict to specific sections | no filter |
| `--multiple` | Path to a YAML multi-experiment file | — |

```bash
lutz analysis --p prompts/screening.md --per-article --workers 4
lutz analysis --p prompts/methodology.md --filter-sections methodology,results
```

### `lutz citations --analysis FILE [options]`

Extracts the key passages that justify each article's classification.

```bash
lutz citations --analysis analysis/execution_reports/screening_<ts>.json \
  --workers 4 --only-relevant
```

### `lutz vector-store [options]`

Inspects the vector index.

```bash
lutz vector-store --summarize
lutz vector-store --sections      # section breakdown per article
lutz vector-store --export        # JSON export
```

### `lutz unvectorize`

Deletes the vector index. PDFs are not affected.

---

## Complete systematic review workflow

```bash
# 1. Create project
lutz init my-review && cd my-review

# 2. Configure AI model (.env or Settings page in the web UI)
cp .env.example .env

# 3. Add PDFs
lutz load --f ~/Downloads/articles --so linux

# 4. Vectorize with section-aware parsing
lutz vectorize --section-parse

# 5. Screen articles by abstract (fast and cheap)
lutz analysis --p prompts/screening.md --per-article --workers 4 \
  --filter-sections abstract

# 6. Deep analysis on methodology and results
lutz analysis --p prompts/methodology_analysis.md \
  --filter-sections methodology,results

# 7. Extract citations from relevant articles
lutz citations \
  --analysis analysis/execution_reports/screening_<timestamp>.json \
  --workers 4 --only-relevant

# 8. Inspect the index
lutz vector-store --summarize --sections
```

Or open `lutz web` and do all of the above from the browser.

---

## How to write prompts

Prompts are Markdown files inside `prompts/`. They tell the model what to analyze.

```markdown
# Screening prompt

## Objective
Determine whether each article describes a study that applies machine learning
to predict clinical outcomes in ICU patients.

## Inclusion criterion
Include articles that: use supervised or unsupervised ML; analyze ICU patient data;
report a clinical outcome (mortality, length of stay, readmission).

## Exclusion criterion
Exclude: review articles without original data; studies outside the ICU context;
studies using only statistical methods without ML.

## Response format
1. Summary of the article's approach (2–3 sentences).
2. Evidence for or against inclusion.
3. Verdict: INCLUDE, EXCLUDE, or UNCERTAIN.
```

`lutz init` creates ready-to-edit templates: `systematic_review.md`, `methodology_analysis.md`, `evidence_quality.md`, `thematic_synthesis.md`.

---

## Security model

Before vectorizing, Lutz checks PDFs to reduce common risks.

| Check | What it detects |
|---|---|
| Structural analysis | Embedded JavaScript, automatic actions, XFA forms |
| Prompt injection | Phrases attempting to override model instructions |
| Academic structure | Basic signs of academic articles (abstract, methodology, references) |
| Corpus anomaly | Statistical outliers when 5 or more documents are present |

Suspicious files are moved to `articles/_quarantine/`. To process them after manual review:

```bash
lutz vectorize --quarantine
```

---

## Architecture

```text
lutz/
├── cli.py                        # Click CLI entry point
├── commands/
│   ├── init.py                   # lutz init
│   ├── load.py                   # lutz load
│   ├── vectorize.py              # lutz vectorize / unvectorize
│   ├── analysis.py               # lutz analysis
│   ├── experiments.py            # --multiple YAML runner
│   ├── citations.py              # lutz citations
│   ├── vector_store.py           # lutz vector-store
│   └── web.py                    # lutz web (FastAPI launcher)
├── core/
│   ├── security_checker.py       # PDF security checks
│   ├── pdf_processor.py          # text extraction and chunking
│   ├── section_parser.py         # section detection
│   ├── vector_store.py           # LanceDB wrapper
│   ├── context_store.py          # chat context file store
│   ├── embedding_client.py       # embedding providers
│   └── llm_client.py             # LLM providers
├── server/
│   └── app.py                    # FastAPI server (REST + SSE + WebSocket)
├── web/                          # pre-built React SPA (bundled in wheel)
└── utils/
    ├── html_report.py            # HTML report generation
    ├── document_reader.py        # multi-format extraction (PDF, DOCX, XLSX…)
    ├── project.py                # project detection and .env loading
    └── templates.py              # files created by lutz init

web/src/                          # React 18 + Vite + Tailwind (source)
├── pages/                        # one component per page
├── components/                   # shared UI components
│   ├── ActiveJobPanel.tsx        # reconnects to running job log on page return
│   ├── NotificationsPanel.tsx    # bell icon + job status dropdown
│   └── ConfirmDialog.tsx         # delete confirmation dialogs
└── contexts/
    ├── NotificationsContext.tsx  # WebSocket job state (global)
    └── LanguageContext.tsx       # i18n (pt / en / es)
```

The vector index lives in `.lutz/vector_store/` inside the project (LanceDB format). Chat sessions and memory are stored in `.lutz/chat/`. Neither should be committed to Git.

---

## Contributing

Contributions are welcome. To set up a development environment:

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e ".[dev]"

# Build the React frontend
cd web && npm ci && npm run build && cd ..

lutz web
```

Before proposing large changes, open an issue to discuss the idea.

---

## How to cite

If you use Lutz in your research, please cite it using the information below or refer to the [`CITATION.cff`](CITATION.cff) file.

**APA**

> Cabral, J. G. S., & Azevedo Farias, A. K. (2026). *Lutz: AI-powered academic article screening and analysis tool* (Version 0.3.0) [Software]. Zenodo. https://doi.org/10.5281/zenodo.19982571

**BibTeX**

```bibtex
@software{cabral2026lutz,
  author  = {Cabral, João Guilherme Silva and Azevedo Farias, Anna Karoline},
  title   = {{Lutz: AI-powered academic article screening and analysis tool}},
  year    = {2026},
  version = {0.3.0},
  doi     = {10.5281/zenodo.19982571},
  url     = {https://github.com/jooguilhermesc/lutz},
  license = {MIT}
}
```

---

## License

MIT
