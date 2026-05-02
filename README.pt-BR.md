# Lutz

**Idiomas:** [English](README.md) | **Português** | [Español](README.es.md)

> Biblioteca e ferramenta de linha de comando para organizar, vetorizar e analisar artigos academicos em PDF com IA.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.1.1-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Alpha-orange)
![CLI](https://img.shields.io/badge/Interface-CLI-informational)

**Tags:** revisão sistemática, triagem acadêmica, artigos científicos, IA generativa, LLM, RAG, embeddings, PDF, LanceDB, Python, ciencia aberta, pesquisa acadêmica.

Lutz ajuda pesquisadores, estudantes e equipes de revisão bibliográfica a lidar com um grande volume de artigos em PDF. O pacote cria uma estrutura de projeto, copia os PDFs para o local correto, faz uma verificação básica de segurança, extrai o texto, gera embeddings, salva tudo em um banco vetorial local e usa um modelo de linguagem para responder a prompts de análise.

Versão atual do pacote: `0.1.1`.

O nome do pacote é inspirado em **Bertha Maria Julia Lutz**, importante cientista brasileira, bióloga e pesquisadora que contribuiu para a biologia e para a valorização da ciência no Brasil.

---

## Sumário

- [Para que serve](#para-que-serve)
- [Como o Lutz funciona](#como-o-lutz-funciona)
- [Antes de comecar](#antes-de-comecar)
- [Instalação](#instalacao)
- [Primeiro uso passo a passo](#primeiro-uso-passo-a-passo)
- [Configuracao dos modelos](#configuracao-dos-modelos)
- [Comandos principais](#comandos-principais)
- [Fluxo completo de revisão sistemática](#fluxo-completo-de-revisao-sistematica)
- [Como escrever prompts](#como-escrever-prompts)
- [Onde ficam os resultados](#onde-ficam-os-resultados)
- [Modelo de seguranca](#modelo-de-seguranca)
- [Arquitetura](#arquitetura)
- [Contribuindo](#contribuindo)
- [Licença](#licenca)

---

## Para que serve

Use o Lutz quando você precisa:

- Organizar uma pasta de artigos cientificos em PDF.
- Preparar uma revisão sistemática, revisão narrativa, mapeamento de literatura ou triagem inicial de estudos.
- Fazer perguntas sobre um conjunto de artigos usando um modelo de linguagem.
- Gerar uma análise estruturada a partir de prompts em Markdown.
- Manter os arquivos, prompts, banco vetorial e relatórios dentro de um projeto reprodutível.

O Lutz não substitui a leitura crítica nem a decisão metodológica de pesquisadores. Ele é uma ferramenta de apoio para otimizar a organização, busca semântica e primeira sintese dos textos.

---

## Como o Lutz funciona

```text
PDFs -> verificação de segurança -> extração de texto -> embeddings -> banco vetorial -> análise com LLM -> relatório JSON
```

Fluxo basico:

1. `lutz init` cria uma pasta de projeto com subpastas, prompts prontos e `.env.example`.
2. `lutz load` copia seus PDFs para a pasta `articles/`.
3. `lutz vectorize` verifica os PDFs, extrai texto, divide o conteudo em trechos e cria embeddings.
4. `lutz analysis` usa um prompt em Markdown para analisar os artigos vetorizados.
5. Os resultados ficam em `analysis/execution_reports/`.

---

## Antes de começar

Você vai precisar de:

- Um computador com Windows, macOS ou Linux.
- Acesso ao terminal. No Windows, pode ser PowerShell; no macOS e Linux, Terminal.
- Python 3.10 ou superior.
- Uma pasta com seus artigos em PDF.
- Um modelo de IA para a análise: autohospedado via Docker Model Runner, Ollama ou llama.cpp; OpenAI/OpenRouter; ou Anthropic.

O caminho recomendado de instalação usa o pacote publicado no PyPI.

---

## Instalação

### Pelo PyPI

1. Instale Python 3.10 ou superior.

Verifique a versão:

```bash
python --version
```

Em alguns sistemas, o comando pode ser `python3 --version`.

2. Crie e ative um ambiente virtual.

Linux ou macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Instale o Lutz.

```bash
python -m pip install --upgrade pip
pip install lutz-research
```

4. Teste a instalação.

```bash
lutz --help
lutz --version
```

### Pelo codigo-fonte

Use esta opção se você quer contribuir ou executar o código mais recente do repositório.

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
python -m pip install --upgrade pip
pip install -e .
```

---

## Primeiro uso passo a passo

Os comandos abaixo assumem que o comando `lutz` já funciona no seu terminal.

### 1. Crie uma pasta para sua revisao

```bash
mkdir minha-revisao
cd minha-revisao
lutz init
```

O Lutz criara uma estrutura parecida com esta:

```text
articles/                  PDFs da pesquisa
prompts/                   modelos de prompts
analysis/execution_reports/ relatórios gerados
.env.example               exemplo de configuracao
README.md                  anotações do projeto
```

### 2. Configure os modelos de IA

Copie o arquivo de exemplo:

Linux ou macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Abra o arquivo `.env` em um editor de texto e escolha uma das configuracoes da seção [Configuracao dos modelos](#configuracao-dos-modelos).

### 3. Coloque seus PDFs no projeto

Voce pode copiar os arquivos manualmente para a pasta `articles/` ou usar o comando `load`.

Exemplo no Linux ou macOS:

```bash
lutz load --f ~/Downloads/meus-artigos --so linux
```

Exemplo no macOS:

```bash
lutz load --f ~/Desktop/artigos --so mac
```

Exemplo no Windows:

```powershell
lutz load --f "C:\Users\Ana\Downloads\artigos" --so windows
```

Se os PDFs ja estiverem em `articles/`, voce pode pular este passo.

### 4. Crie o indice vetorial dos artigos

```bash
lutz vectorize
```

Esse comando pode demorar na primeira execução, principalmente se houver muitos PDFs ou se o modelo local ainda precisar ser baixado.

### 5. Rode uma analise

```bash
lutz analysis --p prompts/systematic_review.md
```

Para analisar cada artigo separadamente, use:

```bash
lutz analysis --p prompts/systematic_review.md --per-article
```

### 6. Abra o resultado

Os arquivos ficam em:

```text
analysis/execution_reports/
```

Cada execução gera um arquivo `.json` com metadados, artigos usados, tokens e resposta do modelo.

---

## Configuração dos modelos

As configurações ficam no arquivo `.env`, criado a partir de `.env.example`.

### Opção local/autohospedada: Docker Model Runner

Esta opção usa modelos locais pelo Docker Model Runner e não exige chave de API externa.

1. Baixe os modelos.

```bash
docker model pull nomic-embed-text
docker model pull ai/llama3.2
```

2. Configure o `.env`.

```dotenv
EMBEDDING_PROVIDER=docker_model_runner
EMBEDDING_MODEL=nomic-embed-text

LLM_PROVIDER=docker_model_runner
LLM_MODEL=ai/llama3.2

DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
```

### Opção autohospedada com Ollama ou llama.cpp

O Lutz também pode usar servidores locais compatíveis com a API da OpenAI. Isso inclui Ollama e llama.cpp server.

Para endpoints locais, `OPENAI_API_KEY` pode ser um valor fictício quando o servidor não exige autenticação.

Exemplo com Ollama:

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2
```

Exemplo com llama.cpp server:

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:8080/v1
OPENAI_API_KEY=llama-cpp
LLM_MODEL=modelo-carregado-no-servidor
```

Se o servidor autohospedado também oferecer embeddings pela API compatível com OpenAI, você pode configurar `EMBEDDING_PROVIDER=openai` e usar o modelo de embeddings correspondente.

### Opção com OpenRouter ou API compativel com OpenAI

Use esta opção se voce tem uma chave de API ou quer usar modelos gratuitos do OpenRouter.

1. Crie uma conta em [https://openrouter.ai](https://openrouter.ai).
2. Gere uma chave em [https://openrouter.ai/keys](https://openrouter.ai/keys).
3. Configure o `.env`.

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sua-chave-aqui
LLM_MODEL=google/gemma-3-12b-it:free
```

Também funciona com OpenAI padrão:

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave-aqui
LLM_MODEL=gpt-4o-mini
```

### Opção com Anthropic

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sua-chave-aqui
LLM_MODEL=claude-haiku-4-5-20251001
```

### Variáveis úteis

| Variável | Para que serve |
|----------|----------------|
| `EMBEDDING_PROVIDER` | Define quem gera embeddings: `docker_model_runner`, `openai` ou `sentence_transformers`. |
| `EMBEDDING_MODEL` | Nome do modelo de embeddings. |
| `LLM_PROVIDER` | Define o provedor do modelo de linguagem: `docker_model_runner`, `openai` ou `anthropic`. |
| `LLM_MODEL` | Nome do modelo usado na análise. |
| `OPENAI_API_KEY` | Chave para OpenAI ou serviço compatível. Em endpoints locais sem autenticação, pode ser um valor fictício. |
| `OPENAI_BASE_URL` | URL alternativa para APIs compatíveis com OpenAI. |
| `ANTHROPIC_API_KEY` | Chave da Anthropic. |
| `DOCKER_MODEL_HOST` | Endereco do Docker Model Runner quando usado com instalação Python local. |
| `DOCKER_MODEL_API_KEY` | Chave usada pelo cliente compatível com OpenAI do Docker Model Runner. Normalmente não precisa ser alterada. |
| `LLM_MAX_TOKENS` | Tamanho máximo da resposta do modelo. Padrão: `4096`. |
| `LLM_TEMPERATURE` | Grau de variação da resposta. Padrão: `0.2`. |
| `HUGGINGFACE_TOKEN` | Token opcional para modelos protegidos usados via `sentence_transformers`. |

---

## Comandos principais

### `lutz init [PROJECT_NAME]`

Cria um novo projeto Lutz.

```bash
lutz init
lutz init minha-revisao
```

O comando cria:

- `articles/`
- `prompts/`
- `analysis/execution_reports/`
- `.env.example`
- `.gitignore`
- `README.md` do projeto
- repositorio Git local

### `lutz load --f FOLDER [--so OS] [--overwrite]`

Copia PDFs de uma pasta de origem para `articles/`.

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--f` | Caminho da pasta onde estão os PDFs. | obrigatória |
| `--so` | Sistema do caminho informado: `linux`, `windows` ou `mac`. | informe conforme seu sistema |
| `--overwrite` | Sobrescreve arquivos já existentes em `articles/`. | desativado |

Exemplos:

```bash
lutz load --f ~/Downloads/artigos --so linux
lutz load --f ~/Desktop/artigos --so mac
```

Windows PowerShell:

```powershell
lutz load --f "C:\Users\Ana\Downloads\artigos" --so windows
```

### `lutz vectorize [--skip-security] [--chunk-size N] [--chunk-overlap N] [--quarantine]`

Processa os PDFs de `articles/` e cria o banco vetorial local em `.lutz/vector_store/`.

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--skip-security` | Pula a verificação de segurança. Não recomendado. | desativado |
| `--chunk-size` | Tamanho dos trechos de texto. | `512` |
| `--chunk-overlap` | Sobreposição entre trechos. | `64` |
| `--quarantine` | Processa arquivos em `articles/_quarantine/`. | desativado |

Exemplos:

```bash
lutz vectorize
lutz vectorize --chunk-size 256 --chunk-overlap 32
```

### `lutz unvectorize`

Apaga o banco vetorial, mas não apaga seus PDFs.

```bash
lutz unvectorize
```

Use quando quiser reconstruir o índice do zero.

### `lutz analysis --p PROMPT [opcoes]`

Analisa os artigos vetorizados usando um prompt em Markdown. Dois modos estão disponíveis.

**Modo RAG (padrão)**

Incorpora o prompt em um vetor, busca os trechos mais relevantes do corpus inteiro e faz uma única chamada ao modelo. Útil para síntese geral e busca semântica.

**Modo por artigo (`--per-article`)**

Faz uma chamada separada ao modelo para cada artigo no banco vetorial. Útil para triagem sistemática, onde você precisa de uma decisão de inclusão ou exclusão por artigo.

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--p` | Caminho do prompt `.md`. | obrigatoria |
| `--top-k` | Trechos a recuperar no modo RAG. Use `'*'` para todos. | `10` |
| `--per-article` | Analisa cada artigo em uma chamada separada ao modelo. | desativado |
| `--workers` | Chamadas paralelas ao modelo no modo `--per-article`. | `1` |
| `--max-chunks-per-article` | Limite de trechos enviados por artigo no modo `--per-article`. | sem limite |
| `--output-name` | Nome base do arquivo de saída. | gerado automaticamente |

Exemplos:

```bash
# Modo RAG padrão
lutz analysis --p prompts/systematic_review.md

# RAG recuperando mais trechos
lutz analysis --p prompts/methodology_analysis.md --top-k 20

# RAG com todos os trechos do corpus
lutz analysis --p prompts/systematic_review.md --top-k '*'

# Triagem por artigo, sequencial
lutz analysis --p prompts/screening.md --per-article

# Triagem por artigo com 4 chamadas paralelas
lutz analysis --p prompts/screening.md --per-article --workers 4

# Triagem por artigo limitando o contexto a 10 trechos por artigo
lutz analysis --p prompts/screening.md --per-article --workers 4 --max-chunks-per-article 10

# Saida com nome personalizado
lutz analysis --p prompts/systematic_review.md --output-name minha-analise-v1
```

**Desempenho no modo `--per-article`**

Com muitos artigos, o modo `--per-article` pode demorar porque cada chamada ao modelo espera a anterior terminar. Use `--workers` para paralelizar:

| Artigos | `--workers 1` | `--workers 4` | `--workers 8` |
|---------|--------------|--------------|--------------|
| 52 artigos a ~50s cada | ~43 min | ~11 min | ~6 min |

O limite prático depende do provedor: APIs remotas como OpenRouter tem limites de requisições por minuto; modelos autohospedados podem ter gargalos de CPU, GPU, memória ou fila de requisições. Ajuste `--workers` conforme a capacidade do serviço usado.

Use `--max-chunks-per-article` para reduzir o tamanho do contexto por chamada, o que diminui a latência e o custo por artigo. Os trechos são enviados na ordem do documento.

> **Nota sobre tamanho de contexto:** o parâmetro `--chunk-size` do `lutz vectorize` é em palavras, não em tokens do modelo. Um chunk de 512 palavras equivale a aproximadamente 680 tokens. Com 23 chunks por artigo (média de um corpus tipico), o contexto de entrada por chamada é de cerca de 15.000 a 16.000 tokens. Verifique se o modelo configurado suporta esse tamanho de janela.

### `lutz citations --analysis FILE [opcoes]`

Extrai citações estruturadas de um relatório produzido por `lutz analysis --per-article`.

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--analysis` | Caminho do JSON de análise por artigo. | obrigatoria |
| `--workers` | Chamadas paralelas ao modelo. | `1` |
| `--only-relevant` | Inclui no relatório apenas artigos relevantes. | desativado |
| `--output-name` | Nome base do arquivo de saida. | gerado automaticamente |

**Fluxo interno:**
1. Lê o JSON produzido por `lutz analysis --per-article`.
2. Classifica cada artigo como relevante, não relevante ou desconhecido usando o texto da análise (sem custo de LLM).
3. Para cada artigo relevante, recupera os trechos originais do banco vetorial e chama o LLM para extrair as 3 a 5 passagens que melhor justificam a classificação.
4. Salva um relatório JSON em `analysis/execution_reports/`.

O nome do arquivo de saída segue o padrão `<nome_da_analise>_citations_<timestamp>.json`.

```bash
# Extração básica
lutz citations --analysis analysis/execution_reports/screening_20260501.json

# Com paralelismo e apenas artigos relevantes
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --workers 4 --only-relevant

# Com nome de saída personalizado
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --output-name revisao_citacoes_v1
```

> **Prérequisito:** o relatório de entrada deve ter sido gerado com `lutz analysis --per-article`. O banco vetorial precisa estar disponível (`.lutz/vector_store/`), pois as citações são extraídas dos trechos originais dos artigos.

---

### `lutz vector-store [--summarize] [--export [FILE]]`

Inspeciona o banco vetorial local.

| Opção | Descrição |
|-------|-----------|
| `--summarize` | Exibe o resumo no terminal. |
| `--export` | Exporta o resumo como JSON (caminho gerado automaticamente em `.lutz/`). |
| `--export FILE` | Exporta para o caminho informado. Use `-` para imprimir no stdout. |

As duas opções podem ser combinadas na mesma execução.

```bash
# Exibir no terminal
lutz vector-store --summarize

# Exportar JSON com caminho automático
lutz vector-store --export

# Exportar para um arquivo específico
lutz vector-store --export summary.json

# Imprimir JSON no stdout
lutz vector-store --export -

# Exibir e exportar ao mesmo tempo
lutz vector-store --summarize --export summary.json
```

---

## Como escrever prompts

Prompts são arquivos Markdown dentro da pasta `prompts/`. Eles dizem ao modelo o que você quer analisar.

Um bom prompt costuma ter:

```markdown
# Título da análise

## Objetivo
Explique em poucas linhas o que você quer investigar.

## Perguntas
1. Qual é a pergunta principal?
2. Quais informações devem ser extraídas dos artigos?
3. Que critérios de inclusão ou exclusão devem ser considerados?

## Formato da resposta
Peça uma tabela, uma lista ou seções com títulos claros.

## Tema da pesquisa
Descreva o tema ou a pergunta de pesquisa.
```

O `lutz init` já cria alguns modelos prontos:

| Arquivo | Uso sugerido |
|---------|--------------|
| `prompts/systematic_review.md` | Revisão sistemática com tabela de evidências. |
| `prompts/methodology_analysis.md` | Comparação de métodos de pesquisa. |
| `prompts/evidence_quality.md` | Avaliação de qualidade e vieses. |
| `prompts/thematic_synthesis.md` | Síntese temática entre artigos. |

Antes de rodar `lutz analysis`, abra o prompt escolhido e substitua os campos de exemplo pela sua pergunta de pesquisa.

---

## Onde ficam os resultados

Depois de `lutz analysis`, os resultados aparecem em:

```text
analysis/execution_reports/
```

O arquivo gerado e um `.json`. Ele inclui:

- prompt usado na análise;
- data e tempo de execução;
- modo de análise, como `rag` ou `per_article`;
- modelo de embedding e modelo de linguagem usados;
- quantidade de tokens;
- artigos cobertos;
- resposta produzida pelo modelo.

Exemplo de nome de arquivo:

```text
systematic_review_20260501_153000.json
```

---

## Modelo de segurança

Antes de vetorizar, o Lutz pode verificar os PDFs para reduzir riscos comuns em arquivos maliciosos ou inadequados.

| Verificação | O que procura |
|-------------|---------------|
| Análise estrutural | JavaScript embutido, ações automáticas e formulários XFA. |
| Prompt injection | Frases que tentam sobrescrever instruções do modelo. |
| Estrutura acadêmica | Sinais básicos de artigo acadêmico, como resumo, metodologia e referências. |
| Anomalia no corpus | Quando há 5 ou mais documentos, identifica possíveis outliers estatísticos. |

Arquivos suspeitos podem ser movidos para:

```text
articles/_quarantine/
```

Para processar arquivos em quarentena depois de revisá-los manualmente:

```bash
lutz vectorize --quarantine
```

Para pular a verificação de segurança:

```bash
lutz vectorize --skip-security
```

Use `--skip-security` apenas se você confia na origem dos PDFs.

---

## Arquitetura

```text
lutz/
├── cli.py                    # entrada principal da CLI Click
├── commands/
│   ├── init.py               # lutz init
│   ├── load.py               # lutz load
│   ├── vectorize.py          # lutz vectorize / lutz unvectorize
│   ├── analysis.py           # lutz analysis
│   ├── citations.py          # lutz citations
│   └── vector_store.py       # lutz vector-store
├── core/
│   ├── security_checker.py   # verificações de seguranca em PDF
│   ├── pdf_processor.py      # extração de texto e divisão em chunks
│   ├── vector_store.py       # wrapper do LanceDB
│   ├── embedding_client.py   # provedores de embeddings
│   └── llm_client.py         # provedores de LLM
└── utils/
    ├── pdf.py                # validação básica de PDF
    ├── project.py            # detecção do projeto e leitura de .env
    └── templates.py          # arquivos criados pelo lutz init
```

O banco vetorial usa [LanceDB](https://lancedb.github.io/lancedb/) e fica em `.lutz/vector_store/` dentro do projeto. Esse diretório não deve ser versionado no Git.

---

## Fluxo completo de revisão sistemática

```bash
# 1. Criar projeto
lutz init minha-revisao && cd minha-revisao

# 2. Adicionar PDFs
lutz load --f ~/Downloads/artigos --so linux

# 3. Vetorizar (com verificação de segurança)
lutz vectorize

# 4. Triagem por artigo
lutz analysis --p prompts/screening.md --per-article --workers 4

# 5. Extrair citações dos artigos relevantes
lutz citations --analysis analysis/execution_reports/screening_<timestamp>.json \
  --workers 4 --only-relevant

# 6. Inspecionar o banco vetorial
lutz vector-store --summarize
lutz vector-store --export
```

---

## Contribuindo

Contribuições são bem-vindas. Para preparar o ambiente de desenvolvimento:

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e ".[dev]"
pytest
```

Antes de propor mudanças grandes, abra uma issue para discutir a ideia.

---

## Licenca

MIT
