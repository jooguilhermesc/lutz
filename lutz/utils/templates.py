"""Static template strings used by lutz init."""

from __future__ import annotations


def get_gitignore_template() -> str:
    return """\
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
dist/
build/
eggs/
parts/
var/
sdist/
develop-eggs/
.installed.cfg
lib/
lib64/

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Distribution / packaging
.Python
pip-log.txt
pip-delete-this-directory.txt

# Testing
.tox/
.nox/
.coverage
.coverage.*
htmlcov/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# IDEs
.idea/
.vscode/
*.swp
*.swo
*~

# lutz — do NOT commit articles or the vector store
articles/*
!articles/.gitkeep
.lutz/

# OS
.DS_Store
Thumbs.db
"""


def get_env_example_template() -> str:
    return """\
# =============================================================================
# Lutz — environment configuration
# Copy this file to .env and fill in the values.
# Never commit .env to version control.
# =============================================================================

# -----------------------------------------------------------------------------
# Embedding model
# Provider options: docker_model_runner | openai | sentence_transformers
# -----------------------------------------------------------------------------
EMBEDDING_PROVIDER=docker_model_runner

# Model to use for generating embeddings.
#   docker_model_runner  -> nomic-embed-text  (pull with: docker model pull nomic-embed-text)
#   openai               -> text-embedding-3-small  (low cost, good quality)
#   sentence_transformers-> all-MiniLM-L6-v2  (local, no API key required)
EMBEDDING_MODEL=nomic-embed-text

# -----------------------------------------------------------------------------
# LLM for analysis
# Provider options: docker_model_runner | openai | anthropic
# -----------------------------------------------------------------------------
LLM_PROVIDER=docker_model_runner

# Model identifier.
#   docker_model_runner  -> ai/llama3.2  (pull with: docker model pull ai/llama3.2)
#   openai               -> gpt-4o-mini  (cheap, capable)
#   anthropic            -> claude-haiku-4-5-20251001  (fast and affordable)
LLM_MODEL=ai/llama3.2

# Max tokens in the LLM response (default: 4096)
LLM_MAX_TOKENS=4096

# Temperature: 0.0 = deterministic, 1.0 = creative (default: 0.2)
LLM_TEMPERATURE=0.2

# -----------------------------------------------------------------------------
# Docker Model Runner (used when PROVIDER=docker_model_runner)
# Leave blank to use the default Docker-internal URL.
# When running lutz OUTSIDE Docker on your local machine, set:
#   DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
# -----------------------------------------------------------------------------
DOCKER_MODEL_HOST=

# -----------------------------------------------------------------------------
# OpenAI / OpenAI-compatible API
# Used when EMBEDDING_PROVIDER=openai or LLM_PROVIDER=openai.
# Also works with OpenRouter: set OPENAI_BASE_URL=https://openrouter.ai/api/v1
# and OPENAI_API_KEY to your OpenRouter key.
# -----------------------------------------------------------------------------
OPENAI_API_KEY=
OPENAI_BASE_URL=

# -----------------------------------------------------------------------------
# Anthropic API
# Used when LLM_PROVIDER=anthropic.
# Get a free-tier key at https://console.anthropic.com
# -----------------------------------------------------------------------------
ANTHROPIC_API_KEY=

# -----------------------------------------------------------------------------
# Optional: HuggingFace Hub token
# Required only if you use gated models via sentence-transformers.
# Get one at https://huggingface.co/settings/tokens
# -----------------------------------------------------------------------------
HUGGINGFACE_TOKEN=

# -----------------------------------------------------------------------------
# PDF extraction backend  (lutz vectorize --extraction)
# Options: pymupdf (default) | marker | auto
#   pymupdf  — fast, no extra deps; fails silently on scanned PDFs.
#   marker   — OCR + multi-column layout (requires pip install "lutz-research[marker]").
#   auto     — pymupdf first; switches to marker for scanned PDFs when available.
# This value is overridden by the --extraction CLI flag.
# -----------------------------------------------------------------------------
EXTRACTION_BACKEND=pymupdf

# Languages for marker OCR (comma-separated BCP-47 codes, e.g. "pt,en").
# Leave blank to use marker's default (English).
MARKER_LANGUAGES=

# Device for marker model inference: cpu | cuda  (leave blank for auto-detect).
MARKER_DEVICE=
"""


def get_readme_template(project_name: str) -> str:
    return f"""\
# {project_name}

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
"""


def get_prompt_templates() -> dict[str, str]:
    return {
        "systematic_review.md": _PROMPT_SYSTEMATIC_REVIEW,
        "methodology_analysis.md": _PROMPT_METHODOLOGY,
        "evidence_quality.md": _PROMPT_EVIDENCE_QUALITY,
        "thematic_synthesis.md": _PROMPT_THEMATIC_SYNTHESIS,
    }


_PROMPT_SYSTEMATIC_REVIEW = """\
# Systematic Literature Review

## Objective
Conduct a systematic review of the provided articles to synthesise evidence on the research topic.

## Relevance Criterion
<!-- Define your inclusion/exclusion rule. The LLM will use this to emit a structured RELEVANCE verdict. -->
*[Enter your relevance criterion here — e.g. "Studies must report empirical data on X in context Y"]*

## Instructions

1. **Identification**: List all articles by filename and provide a one-sentence summary of each.

2. **Inclusion/Exclusion**: Based on the excerpts provided, indicate which articles are directly
   relevant to the research question and which are tangential. Justify each decision with reference
   to the eligibility criteria stated above.

3. **Data extraction**: For each included article extract:
   - Study design (RCT, cohort, case study, review, etc.)
   - Population / sample
   - Main intervention or variable of interest
   - Key findings / results
   - Limitations reported by the authors

4. **Synthesis**: Identify common themes, patterns, or contradictions across the included studies.

5. **Evidence table**: Produce a Markdown table with columns:
   `Article | Design | Sample | Key Finding | Quality`

6. **Conclusion**: Summarise the overall body of evidence in 3–5 sentences.

## Research question
<!-- Replace this placeholder with your specific research question -->
*[Enter your research question here]*
"""

_PROMPT_METHODOLOGY = """\
# Methodology Analysis

## Objective
Critically analyse the research methodologies employed in the provided articles.

## Relevance Criterion
<!-- Define what makes an article eligible for methodology analysis. -->
*[Enter your eligibility criterion — e.g. "Articles must describe a primary research study with an explicit methodology section"]*

## Instructions

For each article:

1. **Design**: Identify the research design (quantitative, qualitative, mixed-methods).

2. **Data collection**: Describe the data collection methods (surveys, interviews, experiments,
   secondary data, etc.).

3. **Sample / dataset**: Describe the sample size, selection criteria, and representativeness.

4. **Analysis approach**: Describe the statistical or qualitative analysis methods used.

5. **Validity & reliability**: Comment on how the authors address threats to validity and
   reliability.

6. **Comparison**: After analysing each article individually, compare methodological approaches
   across the corpus — note similarities, differences, and gaps.

## Focus area
<!-- Specify the methodological aspect you want to highlight -->
*[Enter specific methodological focus, e.g., "sampling strategies in urban health studies"]*
"""

_PROMPT_EVIDENCE_QUALITY = """\
# Evidence Quality and Bias Assessment

## Objective
Assess the quality of evidence and potential sources of bias in each article.

## Relevance Criterion
<!-- Define what qualifies an article for quality assessment. -->
*[Enter your eligibility criterion — e.g. "Articles must present original empirical findings with a defined study design"]*

## Assessment criteria

For each article, rate the following dimensions on a scale of Low / Medium / High:

| Dimension | Description |
|-----------|-------------|
| **Internal validity** | Did the study design control for confounders? |
| **External validity** | Are findings generalisable beyond the study context? |
| **Measurement quality** | Are constructs clearly defined and measured consistently? |
| **Reporting completeness** | Is enough detail provided to evaluate the study? |
| **Conflict of interest** | Are funding sources disclosed? Any apparent conflicts? |

## Bias checklist

For each article, check for:
- [ ] Selection bias
- [ ] Information / measurement bias
- [ ] Confounding
- [ ] Publication bias (if a review)
- [ ] Attrition bias

## Summary table

Produce a table: `Article | Internal Validity | External Validity | Main Bias Risk | Overall Quality`

## Additional notes
<!-- Any context-specific quality criteria for your field -->
*[Enter field-specific quality standards if relevant]*
"""

_PROMPT_THEMATIC_SYNTHESIS = """\
# Thematic Synthesis

## Objective
Identify and synthesise recurring themes, concepts, and theoretical frameworks across the articles.

## Relevance Criterion
<!-- Define what makes an article eligible for thematic synthesis. -->
*[Enter your eligibility criterion — e.g. "Articles must address the topic of X and present qualitative or mixed-methods findings"]*

## Instructions

1. **Line-by-line coding**: From the excerpts, extract key concepts, terms, and arguments.
   Group them into initial codes.

2. **Descriptive themes**: Cluster the initial codes into descriptive themes — themes that
   directly reflect the content.

3. **Analytical themes**: Generate analytical (interpretive) themes that go beyond description
   to explain patterns and relationships.

4. **Concept map outline**: Describe the relationships between the main themes — which themes
   are central, which are peripheral, and how they relate to each other.

5. **Contradictions**: Note any articles that challenge or contradict the dominant themes and
   explain how they fit into the synthesis.

6. **Implications**: What are the practical or theoretical implications of the synthesised themes?

## Guiding concept or theory
<!-- Optionally anchor the synthesis in a specific theoretical framework -->
*[Enter your theoretical lens, e.g., "Social Cognitive Theory", "Institutional Theory", or leave blank]*
"""
