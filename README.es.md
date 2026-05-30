# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="160"/>
</p>

**Idiomas:** [English](README.md) | [Português](README.pt-BR.md) | **Español**

> Herramienta con IA para triaje y análisis de artículos académicos en PDF — interfaz web y línea de comandos.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.3.1-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Instalación

```bash
pip install lutz-research
```

Requiere Python 3.10+. Se recomienda usar un entorno virtual:

```bash
python -m venv .venv && source .venv/bin/activate
pip install lutz-research
```

---

## Inicio rápido

```bash
# Crear un proyecto
mkdir mi-revision && cd mi-revision
lutz init

# Configurar el modelo de IA (ver sección .env abajo)
cp .env.example .env

# Agregar PDFs
lutz load --f ~/Downloads/articulos --so linux

# Abrir la interfaz web
lutz web
```

La interfaz se abre en `http://localhost:8765`. Desde allí puedes vectorizar artículos, ejecutar análisis y generar reportes.

---

## Configurar el modelo (.env)

Edita el archivo `.env` en la raíz del proyecto. Elige un proveedor:

**OpenRouter** (recomendado — acceso a cientos de modelos)
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

También puedes configurar todo desde la página **Configuraciones** en la interfaz web.

---

## Documentación

Guías completas, referencia del CLI y capturas de pantalla en **[jooguilhermesc.github.io/lutz](https://jooguilhermesc.github.io/lutz/)**.

---

## Cómo citar

```bibtex
@software{cabral2026lutz,
  author  = {Cabral, João Guilherme Silva and Azevedo Farias, Anna Karoline},
  title   = {{Lutz: AI-powered academic article screening and analysis tool}},
  year    = {2026},
  version = {0.3.1},
  doi     = {10.5281/zenodo.19982571},
  url     = {https://github.com/jooguilhermesc/lutz}
}
```

---

## Licencia

MIT
