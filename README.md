# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="180"/>
</p>

**Languages:** **English** | [Português](README.pt-BR.md) | [Español](README.es.md)

> Python library and command-line tool for organizing, vectorizing, and analyzing academic PDF articles with AI.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.1.2-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Public%20Preview-blue)
![CLI](https://img.shields.io/badge/Interface-CLI-informational)

**Tags:** systematic review, academic screening, scientific articles, generative AI, LLM, RAG, embeddings, PDF, LanceDB, Python, open science, academic research.

Lutz helps researchers, students, and literature review teams work with large sets of PDF articles. It creates a reproducible project structure, copies PDFs into the right place, performs basic security checks, extracts text, generates embeddings, stores everything in a local vector database, and uses a language model to answer analysis prompts.

Current package version: `0.1.2`.

The package is named after **Bertha Maria Julia Lutz**, an important Brazilian scientist, biologist, and researcher who contributed to biology and to the recognition of science in Brazil.

---

## Table of contents

- [What Lutz is for](#what-lutz-is-for)
- [How Lutz works](#how-lutz-works)
- [Before you start](#before-you-start)
- [Installation](#installation)
- [First use, step by step](#first-use-step-by-step)
- [Model configuration](#model-configuration)
- [Main commands](#main-commands)
- [Complete systematic review workflow](#complete-systematic-review-workflow)
- [How to write prompts](#how-to-write-prompts)
- [Where results are stored](#where-results-are-stored)
- [Security model](#security-model)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [How to cite](#how-to-cite)
- [License](#license)

---

## What Lutz is for

Use Lutz when you need to:

- Organize a folder of scientific articles in PDF format.
- Prepare a systematic review, narrative review, literature map, or initial study screening.
- Ask questions about a set of articles using a language model.
- Generate structured analysis from Markdown prompts.
- Keep files, prompts, vector data, and reports inside a reproducible project.

Lutz does not replace critical reading or methodological decisions by researchers. It is a support tool for accelerating organization, semantic search, and first-pass synthesis of texts.

---

## How Lutz works

```text
PDFs -> security check -> text extraction -> embeddings -> vector database -> LLM analysis -> JSON report
```

Basic flow:

1. `lutz init` creates a project folder with subfolders, prompt templates, and `.env.example`.
2. `lutz load` copies your PDFs into `articles/`.
3. `lutz vectorize` checks PDFs, extracts text, splits content into chunks, and creates embeddings.
4. `lutz analysis` uses a Markdown prompt to analyze the vectorized articles.
5. Results are stored in `analysis/execution_reports/`.

---

## Before you start

You will need:

- A computer running Windows, macOS, or Linux.
- Terminal access. On Windows, use PowerShell; on macOS and Linux, use Terminal.
- Python 3.10 or higher.
- A folder with your PDF articles.
- An AI model for analysis: self-hosted via Docker Model Runner, Ollama, or llama.cpp; OpenAI/OpenRouter; or Anthropic.

The recommended installation path uses the package published on PyPI.

---

## Installation

### From PyPI

1. Install Python 3.10 or higher.

Check your version:

```bash
python --version
```

On some systems, the command may be `python3 --version`.

2. Create and activate a virtual environment.

Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install Lutz.

```bash
python -m pip install --upgrade pip
pip install lutz-research
```

4. Test the installation.

```bash
lutz --help
lutz --version
```

### From source

Use this option if you want to contribute or run the latest code from the repository.

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
python -m pip install --upgrade pip
pip install -e .
```

---

## First use, step by step

The commands below assume that `lutz` already works in your terminal.

### 1. Create a folder for your review

```bash
mkdir my-review
cd my-review
lutz init
```

Lutz creates a structure similar to this:

```text
articles/                   research PDFs
prompts/                    prompt templates
analysis/execution_reports/ generated reports
.env.example                configuration example
README.md                   project notes
```

### 2. Configure AI models

Copy the example file:

Linux or macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor and choose one of the configurations from [Model configuration](#model-configuration).

### 3. Add PDFs to the project

You can manually copy files into `articles/` or use the `load` command.

Linux example:

```bash
lutz load --f ~/Downloads/my-articles --so linux
```

macOS example:

```bash
lutz load --f ~/Desktop/articles --so mac
```

Windows example:

```powershell
lutz load --f "C:\Users\Ana\Downloads\articles" --so windows
```

If the PDFs are already in `articles/`, you can skip this step.

### 4. Create the article vector index

```bash
lutz vectorize
```

This command may take time on the first run, especially if there are many PDFs or if a local model still needs to be downloaded.

### 5. Run an analysis

```bash
lutz analysis --p prompts/systematic_review.md
```

To analyze each article separately, use:

```bash
lutz analysis --p prompts/systematic_review.md --per-article
```

### 6. Open the result

Files are stored in:

```text
analysis/execution_reports/
```

Each run generates a `.json` file with metadata, articles used, token usage, and the model response.

---

## Model configuration

Configuration lives in `.env`, created from `.env.example`.

### Local/self-hosted option: Docker Model Runner

This option uses local models through Docker Model Runner and does not require an external API key.

1. Pull the models.

```bash
docker model pull nomic-embed-text
docker model pull ai/llama3.2
```

2. Configure `.env`.

```dotenv
EMBEDDING_PROVIDER=docker_model_runner
EMBEDDING_MODEL=nomic-embed-text

LLM_PROVIDER=docker_model_runner
LLM_MODEL=ai/llama3.2

DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
```

### Self-hosted option with Ollama or llama.cpp

Lutz can also use local servers compatible with the OpenAI API, including Ollama and llama.cpp server.

For local endpoints, `OPENAI_API_KEY` can be a dummy value when the server does not require authentication.

Example with Ollama:

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2
```

Example with llama.cpp server:

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:8080/v1
OPENAI_API_KEY=llama-cpp
LLM_MODEL=model-loaded-in-server
```

If the self-hosted server also provides embeddings through an OpenAI-compatible API, you can set `EMBEDDING_PROVIDER=openai` and use the corresponding embedding model.

### OpenRouter or OpenAI-compatible API

Use this option if you have an API key or want to use OpenRouter models.

1. Create an account at [https://openrouter.ai](https://openrouter.ai).
2. Generate a key at [https://openrouter.ai/keys](https://openrouter.ai/keys).
3. Configure `.env`.

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=your-key-here
LLM_MODEL=google/gemma-3-12b-it:free
```

Standard OpenAI also works:

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=your-key-here
LLM_MODEL=gpt-4o-mini
```

### Anthropic

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
LLM_MODEL=claude-haiku-4-5-20251001
```

### Useful variables

| Variable | Purpose |
|----------|---------|
| `EMBEDDING_PROVIDER` | Embedding provider: `docker_model_runner`, `openai`, or `sentence_transformers`. |
| `EMBEDDING_MODEL` | Embedding model name. |
| `LLM_PROVIDER` | Language model provider: `docker_model_runner`, `openai`, or `anthropic`. |
| `LLM_MODEL` | Model used for analysis. |
| `OPENAI_API_KEY` | Key for OpenAI or a compatible service. For unauthenticated local endpoints, it can be a dummy value. |
| `OPENAI_BASE_URL` | Alternative URL for OpenAI-compatible APIs. |
| `ANTHROPIC_API_KEY` | Anthropic API key. |
| `DOCKER_MODEL_HOST` | Docker Model Runner address when using a local Python installation. |
| `DOCKER_MODEL_API_KEY` | Key used by the OpenAI-compatible Docker Model Runner client. Usually does not need to be changed. |
| `LLM_MAX_TOKENS` | Maximum response size. Default: `4096`. |
| `LLM_TEMPERATURE` | Response variation. Default: `0.2`. |
| `HUGGINGFACE_TOKEN` | Optional token for gated models used through `sentence_transformers`. |

---

## Main commands

### `lutz init [PROJECT_NAME]`

Creates a new Lutz project.

```bash
lutz init
lutz init my-review
```

The command creates:

- `articles/`
- `prompts/`
- `analysis/execution_reports/`
- `.env.example`
- `.gitignore`
- project `README.md`
- local Git repository

### `lutz load --f FOLDER [--so OS] [--overwrite]`

Copies PDFs from a source folder into `articles/`.

| Option | Description | Default |
|--------|-------------|---------|
| `--f` | Path to the folder containing PDFs. | required |
| `--so` | Path operating system: `linux`, `windows`, or `mac`. | choose your system |
| `--overwrite` | Overwrite files that already exist in `articles/`. | disabled |

Examples:

```bash
lutz load --f ~/Downloads/articles --so linux
lutz load --f ~/Desktop/articles --so mac
```

Windows PowerShell:

```powershell
lutz load --f "C:\Users\Ana\Downloads\articles" --so windows
```

### `lutz vectorize [--skip-security] [--chunk-size N] [--chunk-overlap N] [--quarantine]`

Processes PDFs from `articles/` and creates the local vector database in `.lutz/vector_store/`.

| Option | Description | Default |
|--------|-------------|---------|
| `--skip-security` | Skip security checks. Not recommended. | disabled |
| `--chunk-size` | Text chunk size in words. | `512` |
| `--chunk-overlap` | Overlap between chunks. | `64` |
| `--quarantine` | Process files in `articles/_quarantine/`. | disabled |

Examples:

```bash
lutz vectorize
lutz vectorize --chunk-size 256 --chunk-overlap 32
```

### `lutz unvectorize`

Deletes the vector database, but does not delete your PDFs.

```bash
lutz unvectorize
```

Use it when you want to rebuild the index from scratch.

### `lutz analysis --p PROMPT [options]`

Analyzes vectorized articles using a Markdown prompt. Two modes are available.

**RAG mode (default)**

Embeds the prompt, retrieves the most relevant chunks from the full corpus, and makes one model call. Useful for general synthesis and semantic search.

**Per-article mode (`--per-article`)**

Makes a separate model call for each article in the vector database. Useful for systematic screening where you need an inclusion or exclusion decision per article.

| Option | Description | Default |
|--------|-------------|---------|
| `--p` | Path to the `.md` prompt. | required |
| `--top-k` | Chunks to retrieve in RAG mode. Use `'*'` for all. | `10` |
| `--per-article` | Analyze each article in a separate model call. | disabled |
| `--workers` | Parallel model calls in `--per-article` mode. | `1` |
| `--max-chunks-per-article` | Chunk limit per article in `--per-article` mode. | no limit |
| `--output-name` | Base output filename. | generated automatically |

Examples:

```bash
# Default RAG mode
lutz analysis --p prompts/systematic_review.md

# RAG retrieving more chunks
lutz analysis --p prompts/methodology_analysis.md --top-k 20

# RAG using all chunks in the corpus
lutz analysis --p prompts/systematic_review.md --top-k '*'

# Sequential per-article screening
lutz analysis --p prompts/screening.md --per-article

# Per-article screening with 4 parallel calls
lutz analysis --p prompts/screening.md --per-article --workers 4

# Per-article screening with a 10-chunk context limit per article
lutz analysis --p prompts/screening.md --per-article --workers 4 --max-chunks-per-article 10

# Custom output name
lutz analysis --p prompts/systematic_review.md --output-name my-analysis-v1
```

**Performance in `--per-article` mode**

With many articles, `--per-article` can take a long time because each article requires a model call. Use `--workers` to parallelize:

| Articles | `--workers 1` | `--workers 4` | `--workers 8` |
|----------|---------------|---------------|---------------|
| 52 articles at ~50s each | ~43 min | ~11 min | ~6 min |

The practical limit depends on the provider. Remote APIs such as OpenRouter have rate limits; self-hosted models may bottleneck on CPU, GPU, memory, or request queues. Tune `--workers` according to your service capacity.

Use `--max-chunks-per-article` to reduce context size per call, which lowers latency and cost. Chunks are sent in document order.

> **Context size note:** `--chunk-size` in `lutz vectorize` is measured in words, not model tokens. A 512-word chunk is roughly 680 tokens. With 23 chunks per article, a typical article can produce around 15,000 to 16,000 input tokens. Check that your configured model supports the required context window.

### `lutz citations --analysis FILE [options]`

Extracts structured citations from a report generated by `lutz analysis --per-article`.

| Option | Description | Default |
|--------|-------------|---------|
| `--analysis` | Path to the per-article analysis JSON. | required |
| `--workers` | Parallel model calls. | `1` |
| `--only-relevant` | Include only relevant articles in the report. | disabled |
| `--output-name` | Base output filename. | generated automatically |

**Internal flow:**

1. Reads the JSON produced by `lutz analysis --per-article`.
2. Classifies each article as relevant, not relevant, or unknown using the analysis text, without an LLM call.
3. For each relevant article, retrieves original chunks from the vector database and asks the LLM to extract the 3 to 5 passages that best justify the classification.
4. Saves a JSON report in `analysis/execution_reports/`.

The output filename follows `<analysis_name>_citations_<timestamp>.json`.

```bash
# Basic extraction
lutz citations --analysis analysis/execution_reports/screening_20260501.json

# Parallel calls and relevant articles only
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --workers 4 --only-relevant

# Custom output name
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --output-name review_citations_v1
```

> **Prerequisite:** the input report must have been generated with `lutz analysis --per-article`. The vector database must be available at `.lutz/vector_store/` because citations are extracted from original article chunks.

### `lutz vector-store [--summarize] [--export [FILE]]`

Inspects the local vector database.

| Option | Description |
|--------|-------------|
| `--summarize` | Display a summary in the terminal. |
| `--export` | Export the summary as JSON, with an automatic path in `.lutz/`. |
| `--export FILE` | Export to a specific path. Use `-` to print to stdout. |

The options can be combined.

```bash
# Display in terminal
lutz vector-store --summarize

# Export JSON with automatic path
lutz vector-store --export

# Export to a specific file
lutz vector-store --export summary.json

# Print JSON to stdout
lutz vector-store --export -

# Display and export at the same time
lutz vector-store --summarize --export summary.json
```

---

## How to write prompts

Prompts are Markdown files inside `prompts/`. They tell the model what you want to analyze.

A good prompt usually includes:

```markdown
# Analysis title

## Objective
Explain in a few lines what you want to discover.

## Questions
1. What is the main question?
2. What information should be extracted from the articles?
3. Which inclusion or exclusion criteria should be considered?

## Response format
Ask for a table, a list, or sections with clear headings.

## Research topic
Describe the topic or research question.
```

`lutz init` creates ready-to-edit prompt templates:

| File | Suggested use |
|------|---------------|
| `prompts/systematic_review.md` | Systematic review with evidence table. |
| `prompts/methodology_analysis.md` | Comparison of research methods. |
| `prompts/evidence_quality.md` | Quality and bias assessment. |
| `prompts/thematic_synthesis.md` | Thematic synthesis across articles. |

Before running `lutz analysis`, open the chosen prompt and replace example fields with your research question.

---

## Where results are stored

After `lutz analysis`, results are stored in:

```text
analysis/execution_reports/
```

The generated file is a `.json`. It includes:

- prompt used in the analysis;
- execution date and duration;
- analysis mode, such as `rag` or `per_article`;
- embedding model and language model used;
- token counts;
- covered articles;
- model response.

Example filename:

```text
systematic_review_20260501_153000.json
```

---

## Security model

Before vectorizing, Lutz can check PDFs to reduce common risks in malicious or unsuitable files.

| Check | What it looks for |
|-------|-------------------|
| Structural analysis | Embedded JavaScript, automatic actions, and XFA forms. |
| Prompt injection | Phrases that try to override model instructions. |
| Academic structure | Basic signs of academic articles, such as abstract, methodology, and references. |
| Corpus anomaly | When there are 5 or more documents, identifies possible statistical outliers. |

Suspicious files can be moved to:

```text
articles/_quarantine/
```

To process quarantined files after manual review:

```bash
lutz vectorize --quarantine
```

To skip security checks:

```bash
lutz vectorize --skip-security
```

Use `--skip-security` only if you trust the PDF source.

---

## Architecture

```text
lutz/
├── cli.py                    # main Click CLI entry point
├── commands/
│   ├── init.py               # lutz init
│   ├── load.py               # lutz load
│   ├── vectorize.py          # lutz vectorize / lutz unvectorize
│   ├── analysis.py           # lutz analysis
│   ├── citations.py          # lutz citations
│   └── vector_store.py       # lutz vector-store
├── core/
│   ├── security_checker.py   # PDF security checks
│   ├── pdf_processor.py      # text extraction and chunking
│   ├── vector_store.py       # LanceDB wrapper
│   ├── embedding_client.py   # embedding providers
│   └── llm_client.py         # LLM providers
└── utils/
    ├── pdf.py                # basic PDF validation
    ├── project.py            # project detection and .env loading
    └── templates.py          # files created by lutz init
```

The vector database uses [LanceDB](https://lancedb.github.io/lancedb/) and is stored in `.lutz/vector_store/` inside the project. This directory should not be committed to Git.

---

## Complete systematic review workflow

```bash
# 1. Create project
lutz init my-review && cd my-review

# 2. Add PDFs
lutz load --f ~/Downloads/articles --so linux

# 3. Vectorize with security checks
lutz vectorize

# 4. Per-article screening
lutz analysis --p prompts/screening.md --per-article --workers 4

# 5. Extract citations from relevant articles
lutz citations --analysis analysis/execution_reports/screening_<timestamp>.json \
  --workers 4 --only-relevant

# 6. Inspect the vector database
lutz vector-store --summarize
lutz vector-store --export
```

---

## Contributing

Contributions are welcome. To prepare a development environment:

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e ".[dev]"
pytest
```

Before proposing large changes, open an issue to discuss the idea.

---

## How to cite

If you use Lutz in your research, please cite it using the information below or refer to the [`CITATION.cff`](CITATION.cff) file.

**APA**

> Cabral, J. G. S., & Azevedo Farias, A. K. (2026). *Lutz: AI-powered academic article screening and analysis tool* (Version 0.1.2) [Software]. Zenodo. https://doi.org/10.5281/zenodo.19982571

**BibTeX**

```bibtex
@software{cabral2026lutz,
  author  = {Cabral, João Guilherme Silva and Azevedo Farias, Anna Karoline},
  title   = {{Lutz: AI-powered academic article screening and analysis tool}},
  year    = {2026},
  version = {0.1.2},
  doi     = {10.5281/zenodo.19982571},
  url     = {https://github.com/jooguilhermesc/lutz},
  license = {MIT}
}
```

---

## License

MIT
