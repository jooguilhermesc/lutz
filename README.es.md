# Lutz

**Idiomas:** [English](README.md) | [Português](README.pt-BR.md) | **Español**

> Biblioteca y herramienta de línea de comandos para organizar, vectorizar y analizar artículos académicos en PDF con IA.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.1.2-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Public%20Preview-blue)
![CLI](https://img.shields.io/badge/Interface-CLI-informational)

**Etiquetas:** revisión sistemática, cribado académico, artículos científicos, IA generativa, LLM, RAG, embeddings, PDF, LanceDB, Python, ciencia abierta, investigación académica.

Lutz ayuda a investigadores, estudiantes y equipos de revisión bibliográfica a trabajar con grandes conjuntos de artículos en PDF. Crea una estructura reproducible de proyecto, copia los PDFs al lugar correcto, realiza verificaciones básicas de seguridad, extrae texto, genera embeddings, guarda todo en una base vectorial local y usa un modelo de lenguaje para responder prompts de análisis.

Versión actual del paquete: `0.1.2`.

El paquete lleva el nombre de **Bertha Maria Julia Lutz**, importante científica brasileña, bióloga e investigadora que contribuyó a la biología y al reconocimiento de la ciencia en Brasil.

---

## Índice

- [Para qué sirve](#para-qué-sirve)
- [Cómo funciona Lutz](#cómo-funciona-lutz)
- [Antes de empezar](#antes-de-empezar)
- [Instalación](#instalación)
- [Primer uso paso a paso](#primer-uso-paso-a-paso)
- [Configuración de modelos](#configuración-de-modelos)
- [Comandos principales](#comandos-principales)
- [Interfaz visual](#interfaz-visual)
- [Flujo completo de revisión sistemática](#flujo-completo-de-revisión-sistemática)
- [Cómo escribir prompts](#cómo-escribir-prompts)
- [Dónde se guardan los resultados](#dónde-se-guardan-los-resultados)
- [Modelo de seguridad](#modelo-de-seguridad)
- [Arquitectura](#arquitectura)
- [Contribuir](#contribuir)
- [Cómo citar](#cómo-citar)
- [Licencia](#licencia)

---

## Para qué sirve

Usa Lutz cuando necesites:

- Organizar una carpeta de artículos científicos en PDF.
- Preparar una revisión sistemática, revisión narrativa, mapa de literatura o cribado inicial de estudios.
- Hacer preguntas sobre un conjunto de artículos usando un modelo de lenguaje.
- Generar un análisis estructurado a partir de prompts en Markdown.
- Mantener archivos, prompts, base vectorial e informes dentro de un proyecto reproducible.

Lutz no sustituye la lectura crítica ni las decisiones metodológicas de investigadores. Es una herramienta de apoyo para acelerar organización, búsqueda semántica y primera síntesis de textos.

---

## Cómo funciona Lutz

```text
PDFs -> verificación de seguridad -> extracción de texto -> [análisis de secciones] -> embeddings -> base vectorial -> análisis con LLM -> informe JSON
```

Flujo básico:

1. `lutz init` crea una carpeta de proyecto con subcarpetas, plantillas de prompts y `.env.example`.
2. `lutz load` copia tus PDFs en `articles/`.
3. `lutz vectorize` verifica los PDFs, extrae texto, opcionalmente divide los artículos en secciones etiquetadas (resumen, introducción, metodología…), fragmenta el contenido y crea embeddings.
4. `lutz analysis` usa un prompt en Markdown para analizar los artículos vectorizados.
5. Los resultados se guardan en `analysis/execution_reports/`.

---

## Antes de empezar

Necesitarás:

- Un computador con Windows, macOS o Linux.
- Acceso a la terminal. En Windows, puedes usar PowerShell; en macOS y Linux, Terminal.
- Python 3.10 o superior.
- Una carpeta con tus artículos en PDF.
- Un modelo de IA para el análisis: autohospedado con Docker Model Runner, Ollama o llama.cpp; OpenAI/OpenRouter; o Anthropic.

La ruta recomendada de instalación usa el paquete publicado en PyPI.

---

## Instalación

### Desde PyPI

1. Instala Python 3.10 o superior.

Verifica la versión:

```bash
python --version
```

En algunos sistemas, el comando puede ser `python3 --version`.

2. Crea y activa un entorno virtual.

Linux o macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Instala Lutz.

```bash
python -m pip install --upgrade pip
pip install lutz-research
```

4. Prueba la instalación.

```bash
lutz --help
lutz --version
```

### Desde el código fuente

Usa esta opción si quieres contribuir o ejecutar el código más reciente del repositorio.

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
python -m pip install --upgrade pip
pip install -e .
```

---

## Primer uso paso a paso

Los comandos siguientes asumen que `lutz` ya funciona en tu terminal.

### 1. Crea una carpeta para tu revisión

```bash
mkdir mi-revision
cd mi-revision
lutz init
```

Lutz crea una estructura parecida a esta:

```text
articles/                   PDFs de la investigación
prompts/                    plantillas de prompts
analysis/execution_reports/ informes generados
.env.example                ejemplo de configuración
README.md                   notas del proyecto
```

### 2. Configura los modelos de IA

Copia el archivo de ejemplo:

Linux o macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Abre `.env` en un editor de texto y elige una de las configuraciones de [Configuración de modelos](#configuración-de-modelos).

### 3. Agrega PDFs al proyecto

Puedes copiar los archivos manualmente a `articles/` o usar el comando `load`.

Ejemplo en Linux:

```bash
lutz load --f ~/Downloads/mis-articulos --so linux
```

Ejemplo en macOS:

```bash
lutz load --f ~/Desktop/articulos --so mac
```

Ejemplo en Windows:

```powershell
lutz load --f "C:\Users\Ana\Downloads\articulos" --so windows
```

Si los PDFs ya están en `articles/`, puedes omitir este paso.

### 4. Crea el índice vectorial de artículos

```bash
lutz vectorize
```

Este comando puede tardar en la primera ejecución, especialmente si hay muchos PDFs o si todavía falta descargar un modelo local.

### 5. Ejecuta un análisis

```bash
lutz analysis --p prompts/systematic_review.md
```

Para analizar cada artículo por separado, usa:

```bash
lutz analysis --p prompts/systematic_review.md --per-article
```

### 6. Abre el resultado

Los archivos se guardan en:

```text
analysis/execution_reports/
```

Cada ejecución genera un archivo `.json` con metadatos, artículos usados, tokens y respuesta del modelo.

---

## Configuración de modelos

La configuración está en `.env`, creado a partir de `.env.example`.

### Opción local/autohospedada: Docker Model Runner

Esta opción usa modelos locales mediante Docker Model Runner y no requiere una clave de API externa.

1. Descarga los modelos.

```bash
docker model pull nomic-embed-text
docker model pull ai/llama3.2
```

2. Configura `.env`.

```dotenv
EMBEDDING_PROVIDER=docker_model_runner
EMBEDDING_MODEL=nomic-embed-text

LLM_PROVIDER=docker_model_runner
LLM_MODEL=ai/llama3.2

DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
```

### Opción autohospedada con Ollama o llama.cpp

Lutz también puede usar servidores locales compatibles con la API de OpenAI, incluidos Ollama y llama.cpp server.

Para endpoints locales, `OPENAI_API_KEY` puede ser un valor ficticio cuando el servidor no requiere autenticación.

Ejemplo con Ollama:

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2
```

Ejemplo con llama.cpp server:

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:8080/v1
OPENAI_API_KEY=llama-cpp
LLM_MODEL=modelo-cargado-en-el-servidor
```

Si el servidor autohospedado también ofrece embeddings mediante una API compatible con OpenAI, puedes configurar `EMBEDDING_PROVIDER=openai` y usar el modelo de embeddings correspondiente.

### OpenRouter o API compatible con OpenAI

Usa esta opción si tienes una clave de API o quieres usar modelos de OpenRouter.

1. Crea una cuenta en [https://openrouter.ai](https://openrouter.ai).
2. Genera una clave en [https://openrouter.ai/keys](https://openrouter.ai/keys).
3. Configura `.env`.

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=tu-clave-aqui
LLM_MODEL=google/gemma-3-12b-it:free
```

También funciona con OpenAI estándar:

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=tu-clave-aqui
LLM_MODEL=gpt-4o-mini
```

### Anthropic

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=tu-clave-aqui
LLM_MODEL=claude-haiku-4-5-20251001
```

### Variables útiles

| Variable | Para qué sirve |
|----------|----------------|
| `EMBEDDING_PROVIDER` | Proveedor de embeddings: `docker_model_runner`, `openai` o `sentence_transformers`. |
| `EMBEDDING_MODEL` | Nombre del modelo de embeddings. |
| `LLM_PROVIDER` | Proveedor del modelo de lenguaje: `docker_model_runner`, `openai` o `anthropic`. |
| `LLM_MODEL` | Modelo usado para el análisis. |
| `OPENAI_API_KEY` | Clave para OpenAI o un servicio compatible. En endpoints locales sin autenticación, puede ser un valor ficticio. |
| `OPENAI_BASE_URL` | URL alternativa para APIs compatibles con OpenAI. |
| `ANTHROPIC_API_KEY` | Clave de Anthropic. |
| `DOCKER_MODEL_HOST` | Dirección de Docker Model Runner cuando se usa instalación Python local. |
| `DOCKER_MODEL_API_KEY` | Clave usada por el cliente compatible con OpenAI de Docker Model Runner. Normalmente no hace falta cambiarla. |
| `LLM_MAX_TOKENS` | Tamaño máximo de la respuesta. Predeterminado: `4096`. |
| `LLM_TEMPERATURE` | Variación de la respuesta. Predeterminado: `0.2`. |
| `HUGGINGFACE_TOKEN` | Token opcional para modelos restringidos usados mediante `sentence_transformers`. |

---

## Comandos principales

### `lutz init [PROJECT_NAME]`

Crea un nuevo proyecto Lutz.

```bash
lutz init
lutz init mi-revision
```

El comando crea:

- `articles/`
- `prompts/`
- `analysis/execution_reports/`
- `.env.example`
- `.gitignore`
- `README.md` del proyecto
- repositorio Git local

### `lutz load --f FOLDER [--so OS] [--overwrite]`

Copia PDFs desde una carpeta de origen a `articles/`.

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--f` | Ruta de la carpeta que contiene los PDFs. | obligatoria |
| `--so` | Sistema de la ruta: `linux`, `windows` o `mac`. | elige tu sistema |
| `--overwrite` | Sobrescribe archivos ya existentes en `articles/`. | desactivado |

Ejemplos:

```bash
lutz load --f ~/Downloads/articulos --so linux
lutz load --f ~/Desktop/articulos --so mac
```

Windows PowerShell:

```powershell
lutz load --f "C:\Users\Ana\Downloads\articulos" --so windows
```

### `lutz vectorize [opciones]`

Procesa los PDFs de `articles/` y crea la base vectorial local en `.lutz/vector_store/`.

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--skip-security` | Omite las verificaciones de seguridad. No recomendado. | desactivado |
| `--chunk-size` | Tamaño de los fragmentos de texto en palabras. | `512` |
| `--chunk-overlap` | Superposición entre fragmentos. | `64` |
| `--quarantine` | Procesa archivos en `articles/_quarantine/`. | desactivado |
| `--extraction` | Backend de extracción: `pymupdf`, `marker` o `auto` (ver abajo). | `pymupdf` |
| `--section-parse` | Divide cada artículo en secciones etiquetadas (resumen, introducción, metodología, resultados, discusión, conclusión, referencias…) antes de fragmentar. Cada fragmento queda marcado con el nombre de su sección. Los fragmentos nunca cruzan límites de sección. | desactivado |
| `--layout-parse` / `--no-layout-parse` | Cuando `--section-parse` está activo, usa layout-parser para detectar secciones visualmente. Requiere `pip install "lutz-research[layout]"` (obsoleto — usar `--extraction marker`). | activado |

Ejemplos:

```bash
lutz vectorize
lutz vectorize --chunk-size 256 --chunk-overlap 32

# Vectorización por sección
lutz vectorize --section-parse

# OCR y layout multi-columna con marker
pip install "lutz-research[marker]"
lutz vectorize --extraction marker
lutz vectorize --extraction marker --section-parse

# Detección automática de PDFs escaneados
lutz vectorize --extraction auto
```

**Backends de extracción de texto**

| Tipo de documento | Backend recomendado | Motivo |
|---|---|---|
| Artículo digital, 1 columna | `pymupdf` (predeterminado) | Rápido, sin dependencias extra |
| Artículo digital, 2+ columnas (IEEE, Elsevier, ACM) | `marker` | Detección de layout |
| Libro o artículo escaneado | `marker` | OCR con surya |
| Corpus mixto | `auto` | Detecta y adapta por archivo |

El backend `marker` gestiona layouts multi-columna y PDFs escaneados sin Poppler ni Tesseract. Cuando `--section-parse` se combina con `--extraction marker`, las secciones se extraen directamente de los encabezados Markdown que genera marker — sin layoutparser.

```bash
# Pesos de los modelos (~500 MB), descargados automáticamente una sola vez
pip install "lutz-research[marker]"
```

**Backend `[layout]` (obsoleto)**

El `layoutparser` (extra `[layout]`) está obsoleto y será eliminado en la v0.5.0. Usa `--extraction marker` como reemplazo — sin dependencias de sistema (Poppler) y con soporte OCR.

### `lutz unvectorize`

Elimina la base vectorial, pero no elimina tus PDFs.

```bash
lutz unvectorize
```

Úsalo cuando quieras reconstruir el índice desde cero.

### `lutz analysis --p PROMPT [opciones]`

Analiza los artículos vectorizados usando un prompt en Markdown. Hay dos modos disponibles.

**Modo RAG (predeterminado)**

Convierte el prompt en un vector, recupera los fragmentos más relevantes del corpus completo y realiza una única llamada al modelo. Es útil para síntesis general y búsqueda semántica.

**Modo por artículo (`--per-article`)**

Realiza una llamada separada al modelo para cada artículo de la base vectorial. Es útil para cribado sistemático, donde necesitas una decisión de inclusión o exclusión por artículo.

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--p` | Ruta del prompt `.md`. | obligatoria |
| `--top-k` | Fragmentos que se recuperan en modo RAG. Usa `'*'` para todos. | `10` |
| `--per-article` | Analiza cada artículo en una llamada separada al modelo. | desactivado |
| `--workers` | Llamadas paralelas al modelo en modo `--per-article`. | `1` |
| `--max-chunks-per-article` | Límite de fragmentos por artículo en modo `--per-article`. | sin límite |
| `--filter-sections` | Lista de secciones separadas por comas a incluir en el análisis (ej: `abstract,methodology,results`). Solo se recuperan fragmentos cuya etiqueta de sección coincida. Requiere artículos vectorizados con `--section-parse`. Usa `lutz vector-store --sections` para verificar qué hay disponible. | sin filtro |
| `--output-name` | Nombre base del archivo de salida. | generado automáticamente |
| `--multiple` | Ruta a un archivo YAML con múltiples experimentos para ejecutar en secuencia. Cuando se usa, todas las demás flags se ignoran — cada experimento define sus propios parámetros en el YAML. | no usado |

Ejemplos:

```bash
# Modo RAG predeterminado
lutz analysis --p prompts/systematic_review.md

# RAG recuperando más fragmentos
lutz analysis --p prompts/methodology_analysis.md --top-k 20

# RAG usando todos los fragmentos del corpus
lutz analysis --p prompts/systematic_review.md --top-k '*'

# Cribado por artículo, secuencial
lutz analysis --p prompts/screening.md --per-article

# Cribado por artículo con 4 llamadas paralelas
lutz analysis --p prompts/screening.md --per-article --workers 4

# Cribado por artículo limitando el contexto a 10 fragmentos por artículo
lutz analysis --p prompts/screening.md --per-article --workers 4 --max-chunks-per-article 10

# Analizar solo metodología y resultados (modo RAG)
lutz analysis --p prompts/methodology_analysis.md \
  --filter-sections methodology,results

# Cribar artículos usando solo el resumen (por artículo, paralelo)
lutz analysis --p prompts/screening.md --per-article --workers 4 \
  --filter-sections abstract

# Salida con nombre personalizado
lutz analysis --p prompts/systematic_review.md --output-name mi-analisis-v1

# Ejecutar múltiples experimentos desde un archivo YAML
lutz analysis --multiple experimentos/piloto.yaml
```

**Múltiples experimentos (`--multiple`)**

Ejecuta varios experimentos en secuencia usando un único archivo YAML. Cada experimento define su propio prompt, modo y parámetros. Un JSON consolidado se produce junto con los informes individuales.

```yaml
# experimentos/piloto.yaml
cribado_resumen:
  prompt: prompts/screening.md
  mode: per_article
  workers: 4
  filter_sections:
    - abstract

analisis_metodologia:
  prompt: prompts/methodology_analysis.md
  mode: top_k
  top_k: 20
  main_model: claude-haiku-4-5      # opcional: sobreescribe LLM_MODEL del .env
```

**Veredicto de relevancia en modo por artículo**

Al ejecutar `--per-article`, Lutz instruye al modelo para añadir un bloque de veredicto estructurado al final de cada análisis:

```
---VERDICT---
RELEVANCE: INCLUDE
```

El veredicto se extrae automáticamente y se guarda como campo `relevance` en el JSON. Las etiquetas válidas son:

| Etiqueta | Significado |
|----------|-------------|
| `INCLUDE` | El artículo cumple el criterio de relevancia definido en el prompt. |
| `EXCLUDE` | El artículo no cumple el criterio. |
| `UNCERTAIN` | Los fragmentos disponibles no son suficientes para decidir. |
| `UNKNOWN` | No se encontró bloque de veredicto en la respuesta del modelo. |

Para que el veredicto sea confiable, el prompt debe definir un criterio claro de inclusión o exclusión. Lutz emite una advertencia en tiempo de ejecución si no se detectan palabras clave de criterio.

**Filtro de secciones (`--filter-sections`)**

Cuando los artículos han sido vectorizados con `--section-parse`, cada fragmento lleva una etiqueta de sección (`abstract`, `introduction`, `background`, `methodology`, `results`, `discussion`, `conclusion`, `references`, `acknowledgements`, `appendix`). El flag `--filter-sections` restringe el análisis solo a esas secciones, reduciendo el tamaño del contexto y enfocando la atención del modelo.

- En **modo RAG** la búsqueda por similitud se ejecuta solo sobre las secciones especificadas, luego se ordena por relevancia normalmente.
- En **modo por artículo** cada artículo recibe solo los fragmentos de las secciones especificadas. Los artículos sin fragmentos en esas secciones aparecen con `chunks_used: 0` en el informe.
- Los artículos vectorizados sin `--section-parse` no tienen etiqueta de sección y son **excluidos** cuando el filtro está activo.
- Ejecuta `lutz vector-store --sections` primero para confirmar qué secciones están presentes en la base.

**Rendimiento en modo `--per-article`**

Con muchos artículos, `--per-article` puede tardar porque cada artículo requiere una llamada al modelo. Usa `--workers` para paralelizar:

| Artículos | `--workers 1` | `--workers 4` | `--workers 8` |
|-----------|---------------|---------------|---------------|
| 52 artículos a ~50s cada uno | ~43 min | ~11 min | ~6 min |

El límite práctico depende del proveedor. APIs remotas como OpenRouter tienen límites de solicitudes por minuto; modelos autohospedados pueden tener cuellos de botella de CPU, GPU, memoria o cola de solicitudes. Ajusta `--workers` según la capacidad del servicio usado.

Usa `--max-chunks-per-article` para reducir el tamaño del contexto por llamada, lo que disminuye la latencia y el costo. Los fragmentos se envían en el orden del documento.

> **Nota sobre tamaño de contexto:** `--chunk-size` en `lutz vectorize` se mide en palabras, no en tokens del modelo. Un fragmento de 512 palabras equivale aproximadamente a 680 tokens. Con 23 fragmentos por artículo, un artículo típico puede producir cerca de 15.000 a 16.000 tokens de entrada. Verifica que el modelo configurado soporte esa ventana de contexto.

### `lutz citations --analysis FILE [opciones]`

Extrae citas estructuradas de un informe generado por `lutz analysis --per-article`.

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--analysis` | Ruta del JSON de análisis por artículo. | obligatoria |
| `--workers` | Llamadas paralelas al modelo. | `1` |
| `--only-relevant` | Incluye solo artículos relevantes en el informe. | desactivado |
| `--output-name` | Nombre base del archivo de salida. | generado automáticamente |

**Flujo interno:**

1. Lee el JSON producido por `lutz analysis --per-article`.
2. Clasifica cada artículo como relevante, no relevante o desconocido usando el texto del análisis, sin llamada al LLM.
3. Para cada artículo relevante, recupera los fragmentos originales de la base vectorial y pide al LLM que extraiga los 3 a 5 pasajes que mejor justifican la clasificación.
4. Guarda un informe JSON en `analysis/execution_reports/`.

El nombre del archivo de salida sigue el patrón `<nombre_del_analisis>_citations_<timestamp>.json`.

```bash
# Extracción básica
lutz citations --analysis analysis/execution_reports/screening_20260501.json

# Con paralelismo y solo artículos relevantes
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --workers 4 --only-relevant

# Con nombre de salida personalizado
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --output-name revision_citas_v1
```

> **Prerequisito:** el informe de entrada debe haber sido generado con `lutz analysis --per-article`. La base vectorial debe estar disponible en `.lutz/vector_store/`, porque las citas se extraen de los fragmentos originales de los artículos.

### `lutz vector-store [--summarize] [--sections] [--export [FILE]]`

Inspecciona la base vectorial local.

| Opción | Descripción |
|--------|-------------|
| `--summarize` | Muestra el resumen en la terminal. |
| `--sections` | Muestra el desglose de secciones por artículo (resumen, introducción, metodología…). Los artículos vectorizados sin `--section-parse` aparecen bajo `(no section)`. |
| `--export` | Exporta el resumen como JSON, con ruta automática en `.lutz/`. |
| `--export FILE` | Exporta a una ruta específica. Usa `-` para imprimir en stdout. |

Las opciones se pueden combinar.

```bash
# Mostrar resumen
lutz vector-store --summarize

# Ver qué secciones se detectaron por artículo
lutz vector-store --sections

# Resumen + desglose de secciones juntos
lutz vector-store --summarize --sections

# Exportar JSON con ruta automática
lutz vector-store --export

# Exportar a un archivo específico
lutz vector-store --export summary.json

# Imprimir JSON en stdout
lutz vector-store --export -
```

---

## Cómo escribir prompts

Los prompts son archivos Markdown dentro de `prompts/`. Le dicen al modelo qué quieres analizar.

Un buen prompt suele incluir:

```markdown
# Título del análisis

## Objetivo
Explica en pocas líneas qué quieres descubrir.

## Preguntas
1. ¿Cuál es la pregunta principal?
2. ¿Qué información debe extraerse de los artículos?
3. ¿Qué criterios de inclusión o exclusión deben considerarse?

## Formato de respuesta
Pide una tabla, una lista o secciones con títulos claros.

## Tema de investigación
Describe el tema o la pregunta de investigación.
```

`lutz init` crea plantillas listas para editar:

| Archivo | Uso sugerido |
|---------|--------------|
| `prompts/systematic_review.md` | Revisión sistemática con tabla de evidencias. |
| `prompts/methodology_analysis.md` | Comparación de métodos de investigación. |
| `prompts/evidence_quality.md` | Evaluación de calidad y sesgos. |
| `prompts/thematic_synthesis.md` | Síntesis temática entre artículos. |

Antes de ejecutar `lutz analysis`, abre el prompt elegido y reemplaza los campos de ejemplo con tu pregunta de investigación.

---

## Dónde se guardan los resultados

Después de `lutz analysis`, los resultados se guardan en:

```text
analysis/execution_reports/
```

El archivo generado es un `.json`. Incluye:

- prompt usado en el análisis;
- fecha y duración de la ejecución;
- modo de análisis, como `rag` o `per_article`;
- modelo de embeddings y modelo de lenguaje usados;
- conteo de tokens;
- artículos cubiertos;
- respuesta producida por el modelo.

En **modo por artículo**, también se genera un informe `.html` junto al JSON, con una tabla formateada de resultados, veredictos de relevancia y texto de análisis expandible por artículo.

Ejemplos de nombres de archivo:

```text
screening_20260501_153000.json
screening_20260501_153000.html
```

---

## Modelo de seguridad

Antes de vectorizar, Lutz puede verificar PDFs para reducir riesgos comunes en archivos maliciosos o inadecuados.

| Verificación | Qué busca |
|--------------|-----------|
| Análisis estructural | JavaScript incrustado, acciones automáticas y formularios XFA. |
| Prompt injection | Frases que intentan sobrescribir instrucciones del modelo. |
| Estructura académica | Señales básicas de artículo académico, como resumen, metodología y referencias. |
| Anomalía en el corpus | Cuando hay 5 o más documentos, identifica posibles outliers estadísticos. |

Los archivos sospechosos pueden moverse a:

```text
articles/_quarantine/
```

Para procesar archivos en cuarentena después de revisarlos manualmente:

```bash
lutz vectorize --quarantine
```

Para omitir la verificación de seguridad:

```bash
lutz vectorize --skip-security
```

Usa `--skip-security` solo si confías en el origen de los PDFs.

---

## Arquitectura

```text
lutz/
├── cli.py                    # entrada principal de la CLI Click
├── commands/
│   ├── init.py               # lutz init
│   ├── load.py               # lutz load
│   ├── vectorize.py          # lutz vectorize / lutz unvectorize
│   ├── analysis.py           # lutz analysis (modos RAG y por artículo)
│   ├── experiments.py        # lutz analysis --multiple (ejecutor de experimentos YAML)
│   ├── citations.py          # lutz citations
│   ├── vector_store.py       # lutz vector-store
│   └── web.py                # lutz web (lanzador de Streamlit)
├── core/
│   ├── security_checker.py   # verificaciones de seguridad en PDF
│   ├── pdf_processor.py      # extracción de texto y división en fragmentos
│   ├── section_parser.py     # detección de secciones (layout-parser o heurísticas de texto)
│   ├── vector_store.py       # wrapper de LanceDB
│   ├── embedding_client.py   # proveedores de embeddings
│   └── llm_client.py         # proveedores de LLM
└── utils/
    ├── html_report.py        # generación de informe HTML para modo por artículo
    ├── pdf.py                # validación básica de PDF
    ├── project.py            # detección del proyecto y lectura de .env
    └── templates.py          # archivos creados por lutz init
```

La base vectorial usa [LanceDB](https://lancedb.github.io/lancedb/) y se guarda en `.lutz/vector_store/` dentro del proyecto. Este directorio no debe versionarse en Git.

### `lutz web [opciones]`

Inicia la interfaz visual de investigación en el navegador.

```bash
lutz web
lutz web --port 8080
lutz web --host 0.0.0.0 --port 8888   # expone en la red local
lutz web --no-browser                  # inicia el servidor sin abrir el navegador
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--port` | Puerto del servidor Streamlit. | `8501` |
| `--host` | Dirección de red a la que se vincula el servidor. | `localhost` |
| `--browser` / `--no-browser` | Abrir el navegador automáticamente al iniciar. | activado |

---

## Interfaz visual

Lutz incluye una interfaz visual basada en Streamlit, diseñada para investigadores que prefieren no usar la línea de comandos. Cubre el flujo de trabajo completo a través del navegador.

**Para iniciar:**

```bash
lutz web
```

**Páginas:**

| Página | Qué hace |
|--------|----------|
| Home | Panel del proyecto: conteo de PDFs, fragmentos vectorizados y análisis ejecutados. |
| Vetorização | Sube PDFs, ve los artículos en `articles/` y ejecuta la vectorización con opciones configurables. |
| Vector Store | Inspecciona artículos indexados, conteo de fragmentos, modelo de embeddings y desglose de secciones. Incluye acción segura de unvectorize. |
| Análise | Escribe o carga un prompt Markdown, elige el modo RAG o por artículo, configura los parámetros y ejecuta un análisis simple o un lote de experimentos vía YAML. |
| Relatórios | Visualiza todos los análisis anteriores en una tabla, expande resultados por artículo y descarga informes JSON o HTML. |
| Citações | Selecciona un informe por artículo, ejecuta la extracción de citas y visualiza los pasajes extraídos con confianza y razonamiento. |
| Configurações | Configura proveedores de LLM y embeddings, claves de API (enmascaradas) y URLs base — guardado directamente en `.env`. |

La interfaz lee el mismo `.env` y estructura de proyecto que la CLI. Todas las operaciones se ejecutan contra la raíz del proyecto detectada desde el directorio de trabajo.

---

## Flujo completo de revisión sistemática

```bash
# 1. Crear proyecto
lutz init mi-revision && cd mi-revision

# 2. Agregar PDFs
lutz load --f ~/Downloads/articulos --so linux

# 3. Vectorizar con división por secciones (opcional pero recomendado)
lutz vectorize --section-parse

# 4. Inspeccionar el desglose de secciones para confirmar la detección
lutz vector-store --sections

# 5. Cribado por artículo (solo resumen — más rápido y más económico)
lutz analysis --p prompts/screening.md --per-article --workers 4 \
  --filter-sections abstract

# 6. Análisis profundo sobre metodología y resultados
lutz analysis --p prompts/methodology_analysis.md \
  --filter-sections methodology,results

# 7. Extraer citas de los artículos relevantes
lutz citations --analysis analysis/execution_reports/screening_<timestamp>.json \
  --workers 4 --only-relevant

# 8. Inspeccionar la base vectorial
lutz vector-store --summarize
lutz vector-store --export
```

---

## Contribuir

Las contribuciones son bienvenidas. Para preparar un entorno de desarrollo:

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e ".[dev]"
pytest
```

Antes de proponer cambios grandes, abre una issue para discutir la idea.

---

## Cómo citar

Si utilizas Lutz en tu investigación, por favor cítalo usando la información a continuación o consulta el archivo [`CITATION.cff`](CITATION.cff).

**APA**

> Cabral, J. G. S., & Azevedo Farias, A. K. (2026). *Lutz: AI-powered academic article screening and analysis tool* (Versión 0.1.2) [Software]. Zenodo. https://doi.org/10.5281/zenodo.19982571

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

## Licencia

MIT
