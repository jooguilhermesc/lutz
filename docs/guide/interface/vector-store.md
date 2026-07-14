# Vector Store

::: warning Página removida na v0.5.0
A página `/store` foi removida. O status do vector store agora é refletido na **[aba Biblioteca](./biblioteca.md)** e no bloco Pipeline do painel lateral.
:::

---

## O que é o banco vetorial?

O banco vetorial (implementado com [LanceDB](https://lancedb.github.io/lancedb/)) é o coração do Lutz. Ele armazena:

- **Vetores de embedding** de cada chunk de texto
- **Metadados** como nome do artigo, seção e posição do chunk
- **Texto original** do chunk para exibição e uso no contexto do LLM

O banco é armazenado localmente em `.lutz/vector_store/` e nunca é commitado ao Git.

### Por que vetores?

Cada chunk é representado como um ponto em um espaço vetorial de alta dimensão (ex: 768 dimensões para `all-MiniLM-L6-v2`). Chunks com conteúdo semanticamente similar ficam próximos nesse espaço.

Quando você faz uma análise, o prompt é convertido no mesmo espaço vetorial e os chunks com menor distância de cosseno são recuperados — isso é a **busca semântica**.

```
                    espaço vetorial
                    
  "metodologia de pesquisa"  ●───────● "research methodology"
                                    (semanticamente próximos)
  
  "resultados clínicos"  ●
                                 
  "clinical outcomes"  ●────────────────────── (próximos)
```

---

## Informações exibidas

### Cards de resumo

O topo da página exibe quatro métricas principais:

| Métrica | Descrição |
|---|---|
| **Chunks totais** | Total de fragmentos de texto indexados |
| **Artigos indexados** | Número de documentos únicos no banco |
| **Modelo** | Nome do modelo de embedding utilizado |
| **Atualizado em** | Data/hora da última vetorização |

### Tabela de artigos indexados

Para cada artigo mostra: nome do arquivo, número de chunks, data de vetorização e modelo utilizado.

### Consulta SQL

A seção **Consulta SQL** permite inspecionar o banco vetorial diretamente com abas rápidas:

- **Contar chunks por arquivo** — distribuição de chunks entre artigos
- **Ver schema** — estrutura da tabela LanceDB
- **Buscar texto** — busca por substring no conteúdo dos chunks
- **Arquivos únicos** — lista de artigos distintos
- **Chunks recentes** — últimos chunks adicionados

### Distribuição por seções

Quando artigos foram vetorizados com `--section-parse`, exibe quantos chunks existem em cada seção por artigo.

Útil para confirmar que a detecção de seções funcionou corretamente antes de usar `--filter-sections` nas análises.

---

## Ação: Unvectorize

O botão **Limpar banco vetorial** remove todos os registros do LanceDB. Os PDFs em `articles/` são preservados.

::: danger
Esta ação é irreversível. O banco só pode ser reconstruído rodando `lutz vectorize` novamente.
:::

---

## Equivalente no CLI

```bash
# Resumo do banco
lutz vector-store --summarize

# Distribuição por seções
lutz vector-store --sections

# Exportar JSON
lutz vector-store --export

# Limpar banco
lutz unvectorize
```
