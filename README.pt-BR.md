# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="160"/>
</p>

**Idiomas:** [English](README.md) | **Português** | [Español](README.es.md)

> Ferramenta com IA para triagem e análise de artigos acadêmicos em PDF — interface web e linha de comando.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.5.4-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Instalação

```bash
pip install lutz-research
```

Requer Python 3.10+. Recomenda-se usar um ambiente virtual:

```bash
python -m venv .venv && source .venv/bin/activate
pip install lutz-research
```

---

## Início rápido

```bash
# Criar um projeto
mkdir minha-revisao && cd minha-revisao
lutz init

# Configurar o modelo de IA (veja a seção .env abaixo)
cp .env.example .env

# Adicionar PDFs
lutz load --f ~/Downloads/artigos --so linux

# Abrir a interface web
lutz web
```

A interface abre em `http://localhost:8765`. Por lá você vetoriza artigos, executa análises e gera relatórios.

---

## Configurar o modelo (.env)

Edite o arquivo `.env` na raiz do projeto. Escolha um provedor:

**OpenRouter** (recomendado — acesso a centenas de modelos)
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

Você também pode configurar tudo pela página **Configurações** na interface web.

---

## Documentação

Guias completos, referência do CLI e capturas de tela em **[jooguilhermesc.github.io/lutz](https://jooguilhermesc.github.io/lutz/)**.

---

## Como citar

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

## Licença

MIT
