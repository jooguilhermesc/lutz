# Lutz

**Idiomas:** [English](README.md) | **Português** | [Español](README.es.md)

> Biblioteca e ferramenta de linha de comando para organizar, vetorizar e analisar artigos academicos em PDF com IA.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-0.1.2-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Public%20Preview-blue)
![CLI](https://img.shields.io/badge/Interface-CLI-informational)

**Tags:** revisao sistematica, triagem academica, artigos cientificos, IA generativa, LLM, RAG, embeddings, PDF, LanceDB, Python, ciencia aberta, pesquisa academica.

Lutz ajuda pesquisadores, estudantes e equipes de revisao bibliografica a lidar com muitos artigos em PDF. O pacote cria uma estrutura de projeto, copia os PDFs para o lugar correto, faz uma verificacao basica de seguranca, extrai o texto, gera embeddings, salva tudo em um banco vetorial local e usa um modelo de linguagem para responder a prompts de analise.

Versao atual do pacote: `0.1.2`.

O nome do pacote e inspirado em **Bertha Maria Julia Lutz**, importante cientista brasileira, biologa e pesquisadora que contribuiu para a biologia e para a valorizacao da ciencia no Brasil.

---

## Sumario

- [Para que serve](#para-que-serve)
- [Como o Lutz funciona](#como-o-lutz-funciona)
- [Antes de comecar](#antes-de-comecar)
- [Instalacao](#instalacao)
- [Primeiro uso passo a passo](#primeiro-uso-passo-a-passo)
- [Configuracao dos modelos](#configuracao-dos-modelos)
- [Comandos principais](#comandos-principais)
- [Fluxo completo de revisao sistematica](#fluxo-completo-de-revisao-sistematica)
- [Como escrever prompts](#como-escrever-prompts)
- [Onde ficam os resultados](#onde-ficam-os-resultados)
- [Modelo de seguranca](#modelo-de-seguranca)
- [Arquitetura](#arquitetura)
- [Contribuindo](#contribuindo)
- [Como citar](#como-citar)
- [Licenca](#licenca)

---

## Para que serve

Use o Lutz quando voce precisa:

- Organizar uma pasta de artigos cientificos em PDF.
- Preparar uma revisao sistematica, revisao narrativa, mapeamento de literatura ou triagem inicial de estudos.
- Fazer perguntas sobre um conjunto de artigos usando um modelo de linguagem.
- Gerar uma analise estruturada a partir de prompts em Markdown.
- Manter os arquivos, prompts, banco vetorial e relatorios dentro de um projeto reproduzivel.

O Lutz nao substitui a leitura critica nem a decisao metodologica de pesquisadores. Ele e uma ferramenta de apoio para acelerar organizacao, busca semantica e primeira sintese dos textos.

---

## Como o Lutz funciona

```text
PDFs -> verificacao de seguranca -> extracao de texto -> [analise de secoes] -> embeddings -> banco vetorial -> analise com LLM -> relatorio JSON
```

Fluxo basico:

1. `lutz init` cria uma pasta de projeto com subpastas, prompts prontos e `.env.example`.
2. `lutz load` copia seus PDFs para a pasta `articles/`.
3. `lutz vectorize` verifica os PDFs, extrai texto, opcionalmente divide os artigos em secoes rotuladas (resumo, introducao, metodologia…), divide em trechos e cria embeddings.
4. `lutz analysis` usa um prompt em Markdown para analisar os artigos vetorizados.
5. Os resultados ficam em `analysis/execution_reports/`.

---

## Antes de comecar

Voce vai precisar de:

- Um computador com Windows, macOS ou Linux.
- Acesso ao terminal. No Windows, pode ser PowerShell; no macOS e Linux, Terminal.
- Python 3.10 ou superior.
- Uma pasta com seus artigos em PDF.
- Um modelo de IA para a analise: autohospedado via Docker Model Runner, Ollama ou llama.cpp; OpenAI/OpenRouter; ou Anthropic.

O caminho recomendado de instalacao usa o pacote publicado no PyPI.

---

## Instalacao

### Pelo PyPI

1. Instale Python 3.10 ou superior.

Verifique a versao:

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

4. Teste a instalacao.

```bash
lutz --help
lutz --version
```

### Pelo codigo-fonte

Use esta opcao se voce quer contribuir ou executar o codigo mais recente do repositorio.

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
python -m pip install --upgrade pip
pip install -e .
```

---

## Primeiro uso passo a passo

Os comandos abaixo assumem que o comando `lutz` ja funciona no seu terminal.

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
analysis/execution_reports/ relatorios gerados
.env.example               exemplo de configuracao
README.md                  anotacoes do projeto
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

Abra o arquivo `.env` em um editor de texto e escolha uma das configuracoes da secao [Configuracao dos modelos](#configuracao-dos-modelos).

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

Esse comando pode demorar na primeira execucao, principalmente se houver muitos PDFs ou se o modelo local ainda precisar ser baixado.

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

Cada execucao gera um arquivo `.json` com metadados, artigos usados, tokens e resposta do modelo.

---

## Configuracao dos modelos

As configuracoes ficam no arquivo `.env`, criado a partir de `.env.example`.

### Opcao local/autohospedada: Docker Model Runner

Esta opcao usa modelos locais pelo Docker Model Runner e nao exige chave de API externa.

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

### Opcao autohospedada com Ollama ou llama.cpp

O Lutz tambem pode usar servidores locais compativeis com a API da OpenAI. Isso inclui Ollama e llama.cpp server.

Para endpoints locais, `OPENAI_API_KEY` pode ser um valor ficticio quando o servidor nao exige autenticacao.

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

Se o servidor autohospedado tambem oferecer embeddings pela API compativel com OpenAI, voce pode configurar `EMBEDDING_PROVIDER=openai` e usar o modelo de embeddings correspondente.

### Opcao com OpenRouter ou API compativel com OpenAI

Use esta opcao se voce tem uma chave de API ou quer usar modelos gratuitos do OpenRouter.

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

Tambem funciona com OpenAI padrao:

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave-aqui
LLM_MODEL=gpt-4o-mini
```

### Opcao com Anthropic

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sua-chave-aqui
LLM_MODEL=claude-haiku-4-5-20251001
```

### Variaveis uteis

| Variavel | Para que serve |
|----------|----------------|
| `EMBEDDING_PROVIDER` | Define quem gera embeddings: `docker_model_runner`, `openai` ou `sentence_transformers`. |
| `EMBEDDING_MODEL` | Nome do modelo de embeddings. |
| `LLM_PROVIDER` | Define o provedor do modelo de linguagem: `docker_model_runner`, `openai` ou `anthropic`. |
| `LLM_MODEL` | Nome do modelo usado na analise. |
| `OPENAI_API_KEY` | Chave para OpenAI ou servico compativel. Em endpoints locais sem autenticacao, pode ser um valor ficticio. |
| `OPENAI_BASE_URL` | URL alternativa para APIs compativeis com OpenAI. |
| `ANTHROPIC_API_KEY` | Chave da Anthropic. |
| `DOCKER_MODEL_HOST` | Endereco do Docker Model Runner quando usado com instalacao Python local. |
| `DOCKER_MODEL_API_KEY` | Chave usada pelo cliente compativel com OpenAI do Docker Model Runner. Normalmente nao precisa ser alterada. |
| `LLM_MAX_TOKENS` | Tamanho maximo da resposta do modelo. Padrao: `4096`. |
| `LLM_TEMPERATURE` | Grau de variacao da resposta. Padrao: `0.2`. |
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

| Opcao | Descricao | Padrao |
|-------|-----------|--------|
| `--f` | Caminho da pasta onde estao os PDFs. | obrigatoria |
| `--so` | Sistema do caminho informado: `linux`, `windows` ou `mac`. | informe conforme seu sistema |
| `--overwrite` | Sobrescreve arquivos ja existentes em `articles/`. | desativado |

Exemplos:

```bash
lutz load --f ~/Downloads/artigos --so linux
lutz load --f ~/Desktop/artigos --so mac
```

Windows PowerShell:

```powershell
lutz load --f "C:\Users\Ana\Downloads\artigos" --so windows
```

### `lutz vectorize [opcoes]`

Processa os PDFs de `articles/` e cria o banco vetorial local em `.lutz/vector_store/`.

| Opcao | Descricao | Padrao |
|-------|-----------|--------|
| `--skip-security` | Pula a verificacao de seguranca. Nao recomendado. | desativado |
| `--chunk-size` | Tamanho dos trechos de texto em palavras. | `512` |
| `--chunk-overlap` | Sobreposicao entre trechos. | `64` |
| `--quarantine` | Processa arquivos em `articles/_quarantine/`. | desativado |
| `--section-parse` | Divide cada artigo em secoes rotuladas (resumo, introducao, metodologia, resultados, discussao, conclusao, referencias…) antes de fatiar em trechos. Cada trecho recebe o nome da sua secao. Os trechos nunca cruzam fronteiras de secao. | desativado |
| `--layout-parse` / `--no-layout-parse` | Quando `--section-parse` esta ativo, usa layout-parser para detectar secoes visualmente. Requer `pip install "lutz-research[layout]"`. Se nao instalado, usa heuristicas de texto. Sem efeito sem `--section-parse`. | ativado |

Exemplos:

```bash
lutz vectorize
lutz vectorize --chunk-size 256 --chunk-overlap 32

# Vetorizacao por secao (heuristica de texto, sem deps extras)
lutz vectorize --section-parse --no-layout-parse

# Vetorizacao por secao com deteccao visual de layout
pip install "lutz-research[layout]"
lutz vectorize --section-parse
```

**Instalando o backend de deteccao de layout**

A deteccao visual de layout usa [layout-parser](https://layout-parser.readthedocs.io/) com um modelo Detectron2 treinado no PubLayNet. Os pesos do modelo (~250 MB) sao baixados na primeira execucao.

```bash
# Instalar deps opcionais
pip install "lutz-research[layout]"

# Dependencia de sistema (necessaria para pdf2image)
# Debian/Ubuntu:
apt install poppler-utils
# macOS:
brew install poppler
```

Se o layout-parser nao estiver instalado, `--section-parse` usa heuristicas de texto por expressoes regulares, sem dependencias extras.

### `lutz unvectorize`

Apaga o banco vetorial, mas nao apaga seus PDFs.

```bash
lutz unvectorize
```

Use quando quiser reconstruir o indice do zero.

### `lutz analysis --p PROMPT [opcoes]`

Analisa os artigos vetorizados usando um prompt em Markdown. Dois modos estao disponiveis.

**Modo RAG (padrao)**

Incorpora o prompt em um vetor, busca os trechos mais relevantes do corpus inteiro e faz uma unica chamada ao modelo. Util para sintese geral e busca semantica.

**Modo por artigo (`--per-article`)**

Faz uma chamada separada ao modelo para cada artigo no banco vetorial. Util para triagem sistematica, onde voce precisa de uma decisao de inclusao ou exclusao por artigo.

| Opcao | Descricao | Padrao |
|-------|-----------|--------|
| `--p` | Caminho do prompt `.md`. | obrigatoria |
| `--top-k` | Trechos a recuperar no modo RAG. Use `'*'` para todos. | `10` |
| `--per-article` | Analisa cada artigo em uma chamada separada ao modelo. | desativado |
| `--workers` | Chamadas paralelas ao modelo no modo `--per-article`. | `1` |
| `--max-chunks-per-article` | Limite de trechos enviados por artigo no modo `--per-article`. | sem limite |
| `--filter-sections` | Lista de secoes separadas por virgula a incluir na analise (ex: `abstract,methodology,results`). Apenas trechos com o rotulo de secao correspondente sao recuperados. Requer artigos vetorizados com `--section-parse`. Use `lutz vector-store --sections` para verificar o que esta disponivel. | sem filtro |
| `--output-name` | Nome base do arquivo de saida. | gerado automaticamente |

Exemplos:

```bash
# Modo RAG padrao
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

# Analisar apenas metodologia e resultados (modo RAG)
lutz analysis --p prompts/methodology_analysis.md \
  --filter-sections methodology,results

# Triar artigos usando apenas o resumo (por artigo, paralelo)
lutz analysis --p prompts/screening.md --per-article --workers 4 \
  --filter-sections abstract

# Saida com nome personalizado
lutz analysis --p prompts/systematic_review.md --output-name minha-analise-v1
```

**Filtro de secoes (`--filter-sections`)**

Quando os artigos foram vetorizados com `--section-parse`, cada trecho carrega um rotulo de secao (`abstract`, `introduction`, `background`, `methodology`, `results`, `discussion`, `conclusion`, `references`, `acknowledgements`, `appendix`). O flag `--filter-sections` restringe a analise apenas a essas secoes, reduzindo o tamanho do contexto e focando a atencao do modelo.

- No **modo RAG** a busca por similaridade e executada apenas sobre as secoes especificadas, depois ordenada por relevancia normalmente.
- No **modo por artigo** cada artigo recebe apenas os trechos das secoes especificadas. Artigos sem trechos nessas secoes aparecem com `chunks_used: 0` no relatorio.
- Artigos vetorizados sem `--section-parse` nao possuem rotulo de secao e sao **excluidos** quando o filtro esta ativo.
- Execute `lutz vector-store --sections` primeiro para confirmar quais secoes estao presentes no banco.

**Desempenho no modo `--per-article`**

Com muitos artigos, o modo `--per-article` pode demorar porque cada chamada ao modelo espera a anterior terminar. Use `--workers` para paralelizar:

| Artigos | `--workers 1` | `--workers 4` | `--workers 8` |
|---------|--------------|--------------|--------------|
| 52 artigos a ~50s cada | ~43 min | ~11 min | ~6 min |

O limite pratico depende do provedor: APIs remotas como OpenRouter tem limites de requisicoes por minuto; modelos autohospedados podem ter gargalos de CPU, GPU, memoria ou fila de requisicoes. Ajuste `--workers` conforme a capacidade do servico usado.

Use `--max-chunks-per-article` para reduzir o tamanho do contexto por chamada, o que diminui a latencia e o custo por artigo. Os trechos sao enviados na ordem do documento.

> **Nota sobre tamanho de contexto:** o parametro `--chunk-size` do `lutz vectorize` e em palavras, nao em tokens do modelo. Um chunk de 512 palavras equivale a aproximadamente 680 tokens. Com 23 chunks por artigo (media de um corpus tipico), o contexto de entrada por chamada e de cerca de 15.000 a 16.000 tokens. Verifique se o modelo configurado suporta esse tamanho de janela.

### `lutz citations --analysis FILE [opcoes]`

Extrai citacoes estruturadas de um relatorio produzido por `lutz analysis --per-article`.

| Opcao | Descricao | Padrao |
|-------|-----------|--------|
| `--analysis` | Caminho do JSON de analise por artigo. | obrigatoria |
| `--workers` | Chamadas paralelas ao modelo. | `1` |
| `--only-relevant` | Inclui no relatorio apenas artigos relevantes. | desativado |
| `--output-name` | Nome base do arquivo de saida. | gerado automaticamente |

**Fluxo interno:**
1. Le o JSON produzido por `lutz analysis --per-article`.
2. Classifica cada artigo como relevante, nao relevante ou desconhecido usando o texto da analise (sem custo de LLM).
3. Para cada artigo relevante, recupera os trechos originais do banco vetorial e chama o LLM para extrair as 3 a 5 passagens que melhor justificam a classificacao.
4. Salva um relatorio JSON em `analysis/execution_reports/`.

O nome do arquivo de saida segue o padrao `<nome_da_analise>_citations_<timestamp>.json`.

```bash
# Extracao basica
lutz citations --analysis analysis/execution_reports/screening_20260501.json

# Com paralelismo e apenas artigos relevantes
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --workers 4 --only-relevant

# Com nome de saida personalizado
lutz citations --analysis analysis/execution_reports/screening_20260501.json \
  --output-name revisao_citacoes_v1
```

> **Prerequisito:** o relatorio de entrada deve ter sido gerado com `lutz analysis --per-article`. O banco vetorial precisa estar disponivel (`.lutz/vector_store/`), pois as citacoes sao extraidas dos trechos originais dos artigos.

---

### `lutz vector-store [--summarize] [--sections] [--export [FILE]]`

Inspeciona o banco vetorial local.

| Opcao | Descricao |
|-------|-----------|
| `--summarize` | Exibe o resumo no terminal. |
| `--sections` | Mostra o breakdown de secoes por artigo (resumo, introducao, metodologia…). Artigos vetorizados sem `--section-parse` aparecem em `(no section)`. |
| `--export` | Exporta o resumo como JSON (caminho gerado automaticamente em `.lutz/`). |
| `--export FILE` | Exporta para o caminho informado. Use `-` para imprimir no stdout. |

As opcoes podem ser combinadas na mesma execucao.

```bash
# Exibir resumo
lutz vector-store --summarize

# Ver quais secoes foram detectadas por artigo
lutz vector-store --sections

# Resumo + breakdown de secoes juntos
lutz vector-store --summarize --sections

# Exportar JSON com caminho automatico
lutz vector-store --export

# Exportar para um arquivo especifico
lutz vector-store --export summary.json

# Imprimir JSON no stdout
lutz vector-store --export -
```

---

## Como escrever prompts

Prompts sao arquivos Markdown dentro da pasta `prompts/`. Eles dizem ao modelo o que voce quer analisar.

Um bom prompt costuma ter:

```markdown
# Titulo da analise

## Objetivo
Explique em poucas linhas o que voce quer descobrir.

## Perguntas
1. Qual e a pergunta principal?
2. Quais informacoes devem ser extraidas dos artigos?
3. Que criterios de inclusao ou exclusao devem ser considerados?

## Formato da resposta
Peça uma tabela, uma lista ou secoes com titulos claros.

## Tema da pesquisa
Descreva o tema ou a pergunta de pesquisa.
```

O `lutz init` ja cria alguns modelos prontos:

| Arquivo | Uso sugerido |
|---------|--------------|
| `prompts/systematic_review.md` | Revisao sistematica com tabela de evidencias. |
| `prompts/methodology_analysis.md` | Comparacao de metodos de pesquisa. |
| `prompts/evidence_quality.md` | Avaliacao de qualidade e vieses. |
| `prompts/thematic_synthesis.md` | Sintese tematica entre artigos. |

Antes de rodar `lutz analysis`, abra o prompt escolhido e substitua os campos de exemplo pela sua pergunta de pesquisa.

---

## Onde ficam os resultados

Depois de `lutz analysis`, os resultados aparecem em:

```text
analysis/execution_reports/
```

O arquivo gerado e um `.json`. Ele inclui:

- prompt usado na analise;
- data e tempo de execucao;
- modo de analise, como `rag` ou `per_article`;
- modelo de embedding e modelo de linguagem usados;
- quantidade de tokens;
- artigos cobertos;
- resposta produzida pelo modelo.

Exemplo de nome de arquivo:

```text
systematic_review_20260501_153000.json
```

---

## Modelo de seguranca

Antes de vetorizar, o Lutz pode verificar os PDFs para reduzir riscos comuns em arquivos maliciosos ou inadequados.

| Verificacao | O que procura |
|-------------|---------------|
| Analise estrutural | JavaScript embutido, acoes automaticas e formularios XFA. |
| Prompt injection | Frases que tentam sobrescrever instrucoes do modelo. |
| Estrutura academica | Sinais basicos de artigo academico, como resumo, metodologia e referencias. |
| Anomalia no corpus | Quando ha 5 ou mais documentos, identifica possiveis outliers estatisticos. |

Arquivos suspeitos podem ser movidos para:

```text
articles/_quarantine/
```

Para processar arquivos em quarentena depois de revisa-los manualmente:

```bash
lutz vectorize --quarantine
```

Para pular a verificacao de seguranca:

```bash
lutz vectorize --skip-security
```

Use `--skip-security` apenas se voce confia na origem dos PDFs.

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
│   ├── security_checker.py   # verificacoes de seguranca em PDF
│   ├── pdf_processor.py      # extracao de texto e divisao em chunks
│   ├── section_parser.py     # deteccao de secoes (layout-parser ou heuristicas de texto)
│   ├── vector_store.py       # wrapper do LanceDB
│   ├── embedding_client.py   # provedores de embeddings
│   └── llm_client.py         # provedores de LLM
└── utils/
    ├── pdf.py                # validacao basica de PDF
    ├── project.py            # deteccao do projeto e leitura de .env
    └── templates.py          # arquivos criados pelo lutz init
```

O banco vetorial usa [LanceDB](https://lancedb.github.io/lancedb/) e fica em `.lutz/vector_store/` dentro do projeto. Esse diretorio nao deve ser versionado no Git.

---

## Fluxo completo de revisao sistematica

```bash
# 1. Criar projeto
lutz init minha-revisao && cd minha-revisao

# 2. Adicionar PDFs
lutz load --f ~/Downloads/artigos --so linux

# 3. Vetorizar com divisao por secoes (opcional, mas recomendado)
lutz vectorize --section-parse

# 4. Inspecionar o breakdown de secoes para confirmar a deteccao
lutz vector-store --sections

# 5. Triagem por artigo (apenas resumo — mais rapido e mais barato)
lutz analysis --p prompts/screening.md --per-article --workers 4 \
  --filter-sections abstract

# 6. Analise aprofundada sobre metodologia e resultados
lutz analysis --p prompts/methodology_analysis.md \
  --filter-sections methodology,results

# 7. Extrair citacoes dos artigos relevantes
lutz citations --analysis analysis/execution_reports/screening_<timestamp>.json \
  --workers 4 --only-relevant

# 8. Inspecionar o banco vetorial
lutz vector-store --summarize
lutz vector-store --export
```

---

## Contribuindo

Contribuicoes sao bem-vindas. Para preparar o ambiente de desenvolvimento:

```bash
git clone https://github.com/jooguilhermesc/lutz.git
cd lutz
pip install -e ".[dev]"
pytest
```

Antes de propor mudancas grandes, abra uma issue para discutir a ideia.

---

## Como citar

Se voce utilizar o Lutz em sua pesquisa, por favor cite usando as informacoes abaixo ou consulte o arquivo [`CITATION.cff`](CITATION.cff).

**APA**

> Cabral, J. G. S., & Azevedo Farias, A. K. (2026). *Lutz: AI-powered academic article screening and analysis tool* (Versao 0.1.2) [Software]. Zenodo. https://doi.org/10.5281/zenodo.19982571

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

## Licenca

MIT
