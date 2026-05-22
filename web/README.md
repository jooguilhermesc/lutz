# web

> Research project managed with [**lutz**](https://github.com/your-org/lutz) — AI-powered academic article screening.

## Project structure

```
articles/               ← Drop your PDF articles here (or use `lutz load`)
prompts/                ← Prompt templates for analysis
analysis/
  execution_reports/    ← CSV metadata + Markdown analysis outputs
.env                    ← Your environment config (not committed)
```

## Quickstart

```bash
# 1. Configure your models
cp .env.example .env
# Edit .env with your preferred model provider

# 2. Add articles
lutz load --f /path/to/papers

# 3. Index articles
lutz vectorize

# 4. Run analysis
lutz analysis --p prompts/systematic_review.md
```

## Available prompts

| File | Purpose |
|------|---------|
| `prompts/systematic_review.md` | Systematic literature review |
| `prompts/methodology_analysis.md` | Research methodology analysis |
| `prompts/evidence_quality.md` | Evidence quality and bias assessment |
| `prompts/thematic_synthesis.md` | Thematic synthesis across articles |

## Re-indexing

```bash
# Remove existing index and re-vectorize
lutz unvectorize
lutz vectorize
```
