# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="160"/>
</p>

**Languages:** **English** | [Português](README.pt-BR.md) | [Español](README.es.md)

> AI-powered tool for screening and analyzing academic PDF articles — browser interface and CLI.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.5.4-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Install

```bash
pip install lutz-research
```

Requires Python 3.10+. A virtual environment is recommended:

```bash
python -m venv .venv && source .venv/bin/activate
pip install lutz-research
```

---

## Quick start

```bash
# Create a project
mkdir my-review && cd my-review
lutz init

# Configure your AI model (see .env section below)
cp .env.example .env

# Add PDFs
lutz load --f ~/Downloads/articles --so linux

# Open the browser interface
lutz web
```

The interface opens at `http://localhost:8765`. From there you can vectorize articles, run analyses, and generate reports.

---

## Configure your model (.env)

Edit `.env` in the project root. Choose one provider:

**OpenRouter** (recommended — access to hundreds of models)
```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=openai/text-embedding-3-small
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-...

LLM_PROVIDER=openai
LLM_MODEL=google/gemini-flash-1.5-8b
```

**OpenAI**
```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

**Anthropic**
```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001
```

**Local — Ollama**
```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2
```

You can also configure everything from the **Settings** page inside the web interface.

---

## Documentation

Full guides, CLI reference, and screenshots at **[jooguilhermesc.github.io/lutz](https://jooguilhermesc.github.io/lutz/)**.

---

## How to cite

```bibtex
@software{cabral2026lutz,
  author  = {Cabral, João Guilherme Silva and Azevedo Farias, Anna Karoline},
  title   = {{Lutz: AI-powered academic article screening and analysis tool}},
  year    = {2026},
  version = {0.5.4},
  doi     = {10.5281/zenodo.19982571},
  url     = {https://github.com/jooguilhermesc/lutz}
}
```

---

## License

MIT
