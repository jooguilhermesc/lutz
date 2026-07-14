# Vector Store

O banco vetorial (LanceDB em `.lutz/vector_store/`) armazena os embeddings e chunks de todos os artigos indexados. Na interface web, o status do vector store é exibido no **painel de Pipeline** do rail lateral — e pode ser inspecionado em detalhes pelo **modal do Vector Store**.

---

## Modal do Vector Store

Clique em **Vetorizar (N)** ou **Detalhes** no painel de Pipeline para abrir o modal do Vector Store.

![Modal do Vector Store](/screenshots/vector-store-modal.png)

### Metadados

O topo do modal exibe quatro cards de informação:

| Card | Conteúdo |
|---|---|
| **Registros totais** | Número de chunks indexados (um artigo = vários chunks) |
| **Documentos únicos** | Número de arquivos PDF distintos no banco |
| **Atualizado em** | Data e hora da última operação de vetorização |
| **Modelo** | ID do modelo de embedding usado na última indexação |

### Tabela de artigos

Lista todos os arquivos já vetorizados, com:
- Nome do arquivo
- Data e hora da vetorização
- Quantidade de chunks gerados

::: tip
Se um artigo tiver muito mais chunks do que os demais, pode indicar que o PDF tem muito texto de OCR repetido ou tabelas extensas — considere revisar o arquivo.
:::

### Artigos pendentes

Quando há PDFs em `articles/` que ainda não foram indexados, um aviso amarelo exibe a contagem. O botão **Vetorizar (N pendentes)** no rodapé do modal inicia a vetorização e fecha o modal automaticamente.

### Limpar vector store

O botão **Limpar vector store** (rodapé direito) apaga **todos** os vetores do banco — os PDFs em `articles/` são preservados. Uma confirmação inline é exibida antes da ação.

::: danger
Limpar o vector store é irreversível. O banco só pode ser reconstruído rodando a vetorização novamente (CLI ou modal).
:::

---

## Status no rail lateral

O pipeline mostra em tempo real:

```
Pipeline
  ✓  Biblioteca     — 12 PDFs carregados
  ✓  Vetorizado     — 12 artigos prontos    [Detalhes]
  ✓  Análise        — Concluída · 7 para incluir
```

O contador "Vetorizado" corresponde ao número de documentos únicos no banco. Quando há artigos pendentes, o botão muda para **Vetorizar (N)**.

---

## Por que vetores?

Cada chunk é representado como um ponto em um espaço vetorial de alta dimensão. Chunks com conteúdo semanticamente similar ficam próximos nesse espaço.

Na análise, o prompt é convertido no mesmo espaço e os chunks com menor distância de cosseno são recuperados como contexto — isso é a **busca semântica**.

---

## Inspecionar via CLI

```bash
# Resumo do banco (chunks, artigos, modelo)
lutz vector-store --summarize

# Distribuição de chunks por seção
lutz vector-store --sections

# Exportar para JSON
lutz vector-store --export

# Limpar banco (preserva os PDFs)
lutz unvectorize
```

---

## O que é armazenado

| Campo | Conteúdo |
|---|---|
| `vector` | Vetor de embedding do chunk |
| `text` | Texto original do chunk |
| `source` | Nome do arquivo PDF |
| `section` | Seção detectada (se `--section-parse` foi usado) |
| `chunk_index` | Posição do chunk no documento |

O banco é local, nunca sincronizado com servidores externos.
