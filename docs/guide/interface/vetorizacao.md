# Biblioteca

A aba **Biblioteca** é o ponto de entrada para adicionar e gerenciar os artigos do projeto. A vetorização é disparada pelo painel lateral, não por uma página separada.

![Aba Biblioteca](/screenshots/biblioteca.png)

---

## Lista de artigos

A aba exibe todos os arquivos `.pdf` presentes em `articles/`. Para cada arquivo são mostrados:

- Nome do arquivo
- Tamanho em KB/MB
- Indicador de vetorização (artigo já indexado no LanceDB)

### Upload de PDFs

Clique em **+ Adicionar PDFs** para selecionar múltiplos arquivos. O Lutz valida a assinatura binária, sanitiza o nome e copia para `articles/`.

::: tip
Você também pode copiar arquivos manualmente para `articles/` via `lutz load` e recarregar a aba.
:::

### Renomear com IA

O botão **Sugerir nomes** lê o conteúdo dos PDFs e propõe nomes limpos e descritivos sem precisar vetorizar antes.

---

## Vetorização

A vetorização é iniciada pelo **rail lateral**, não pela aba Biblioteca. Quando há artigos pendentes, o botão **Vetorizar (N)** aparece no painel de Pipeline:

```
Pipeline
  ✓  Biblioteca     — 12 PDFs carregados
  …  Vetorizado     — 8 / 12 — 4 pendentes    [Vetorizar (4)]
  ○  Análise        — Aguardando vetorização
```

O processo executa três fases:

1. **Verificação de segurança** — JavaScript embutido, XFA, prompt injection
2. **Extração de texto** — `pdfplumber` com fallback para `pypdf`, divisão em chunks de 512 palavras com sobreposição de 64
3. **Embedding e indexação** — vetores armazenados em `.lutz/vector_store/`

O progresso aparece no painel de **Atividades** (sino na barra superior).

PDFs suspeitos são movidos para `articles/_quarantine/` automaticamente.

---

## Arquivos de contexto

Na seção **Critério de triagem** do rail lateral, o botão **Anexar arquivo** permite enviar arquivos adicionais (PDF, DOCX, XLSX, PPTX) como contexto suplementar. Esses arquivos são vetorizados automaticamente e aparecem como pills no critério.

---

## Como funcionam os chunks e embeddings

```
Artigo PDF
    ↓ pdfplumber / pypdf
Texto bruto
    ↓ divisão por palavras com sobreposição
[chunk 1][chunk 2][chunk 3]...
    ↓ modelo de embedding
[[0.12, -0.34, 0.78, ...], ...]
    ↓ LanceDB (.lutz/vector_store/)
```

A sobreposição entre chunks preserva o contexto nas fronteiras — uma frase que cai no final de um chunk aparece também no início do próximo.

---

## Equivalente no CLI

```bash
# Adicionar PDFs
lutz load --f ~/Downloads/artigos --so linux

# Vetorizar todos os artigos pendentes
lutz vectorize

# Vetorizar com detecção de seções
lutz vectorize --section-parse --chunk-size 256 --chunk-overlap 32
```
