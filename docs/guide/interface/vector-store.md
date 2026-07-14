# Vector Store

O banco vetorial (LanceDB em `.lutz/vector_store/`) armazena os embeddings e chunks de todos os artigos indexados. Na interface web, o status do vector store é exibido no **painel de Pipeline** do rail lateral.

---

## Status no rail lateral

O pipeline mostra em tempo real:

```
Pipeline
  ✓  Biblioteca     — 12 PDFs carregados
  ✓  Vetorizado     — 12 artigos prontos
  ✓  Análise        — Concluída · 7 para incluir
```

O contador "Vetorizado" corresponde ao número de documentos únicos no banco.

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

::: danger
`lutz unvectorize` é irreversível. O banco só pode ser reconstruído rodando `lutz vectorize` novamente.
:::

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
