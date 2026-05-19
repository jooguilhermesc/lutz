# Vector Store

A página Vector Store permite inspecionar o banco vetorial — os artigos indexados, a quantidade de chunks, o modelo de embedding usado e a distribuição de seções detectadas.

![Página Vector Store](/screenshots/vector_store.png)

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

### Resumo do banco

- Total de chunks indexados
- Número de artigos únicos
- Modelo de embedding utilizado
- Tamanho médio dos chunks

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
