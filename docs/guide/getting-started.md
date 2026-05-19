# Primeiros passos

Lutz é uma ferramenta de linha de comando e interface web para triagem e análise de artigos acadêmicos em PDF usando IA. Este guia cobre a instalação e os primeiros comandos para colocar o projeto em funcionamento.

## Pré-requisitos

- Python **3.10** ou superior
- Terminal (PowerShell no Windows, Terminal no macOS/Linux)
- Uma pasta com PDFs de artigos científicos
- Um modelo de IA: Docker Model Runner, Ollama, OpenAI, OpenRouter ou Anthropic

## Instalação

### Via PyPI (recomendado)

::: code-group

```bash [Linux / macOS]
python -m venv .venv
source .venv/bin/activate
pip install lutz-research
```

```powershell [Windows PowerShell]
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install lutz-research
```

:::

Para instalar com a interface web:

```bash
pip install "lutz-research[ui]"
```

Verifique a instalação:

```bash
lutz --version
lutz --help
```

### A partir do código-fonte

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e .
```

---

## Criando um projeto

```bash
mkdir minha-revisao
cd minha-revisao
lutz init
```

O comando `lutz init` cria a estrutura de diretórios e arquivos de configuração:

```
minha-revisao/
├── articles/                   → PDFs dos artigos
├── prompts/                    → templates de prompt prontos para editar
│   ├── systematic_review.md
│   ├── methodology_analysis.md
│   ├── evidence_quality.md
│   └── thematic_synthesis.md
├── analysis/
│   └── execution_reports/      → relatórios gerados pelas análises
├── .env.example                → exemplo de configuração de modelos
├── .gitignore
└── README.md
```

::: tip
Você pode passar um nome de projeto: `lutz init minha-revisao`. Se omitido, o nome da pasta atual é usado.
:::

---

## Adicionando PDFs

Copie os arquivos manualmente para `articles/` ou use o comando `load`:

::: code-group

```bash [Linux]
lutz load --f ~/Downloads/artigos --so linux
```

```bash [macOS]
lutz load --f ~/Desktop/artigos --so mac
```

```powershell [Windows]
lutz load --f "C:\Users\Ana\Downloads\artigos" --so windows
```

:::

---

## Vetorizando os artigos

```bash
lutz vectorize
```

Este comando executa três fases:

1. **Verificação de segurança** — analisa cada PDF em busca de JavaScript embutido, XFA, ações automáticas e padrões de prompt injection.
2. **Extração de texto** — usa `pdfplumber` (com fallback para `pypdf`) e divide o conteúdo em chunks de palavras.
3. **Embedding e indexação** — gera vetores de embedding e armazena no banco LanceDB em `.lutz/vector_store/`.

Para vetorização com detecção de seções (abstract, metodologia, resultados…):

```bash
lutz vectorize --section-parse
```

---

## Rodando uma análise

```bash
lutz analysis --p prompts/systematic_review.md
```

**Modo RAG (padrão):** embeds do prompt recuperam os chunks mais relevantes do corpus inteiro e fazem uma única chamada ao LLM.

**Modo por artigo:** cada artigo recebe uma chamada separada, útil para triagem com veredicto INCLUDE/EXCLUDE:

```bash
lutz analysis --p prompts/screening.md --per-article --workers 4
```

---

## Abrindo a interface web

```bash
lutz web
```

Isso inicia o servidor Streamlit em `http://localhost:8501` e abre o navegador automaticamente.

Veja a seção [Interface Web](/guide/interface/home) para uma descrição completa de cada página.

---

## Fluxo completo de revisão sistemática

```bash
# 1. Criar projeto
lutz init minha-revisao && cd minha-revisao

# 2. Adicionar PDFs
lutz load --f ~/Downloads/artigos --so linux

# 3. Vetorizar com detecção de seções
lutz vectorize --section-parse

# 4. Conferir seções detectadas
lutz vector-store --sections

# 5. Triagem por abstract (rápido e econômico)
lutz analysis --p prompts/screening.md --per-article --workers 4 \
  --filter-sections abstract

# 6. Análise de metodologia e resultados
lutz analysis --p prompts/methodology_analysis.md \
  --filter-sections methodology,results

# 7. Extrair citações dos artigos relevantes
lutz citations \
  --analysis analysis/execution_reports/screening_<timestamp>.json \
  --workers 4 --only-relevant
```
