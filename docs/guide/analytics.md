# Análise Semântica do Corpus

O módulo de analytics do Lutz oferece ferramentas para **revisão sistemática assistida por IA**: deduplicação, ranking de relevância, clustering temático reprodutível e detecção de outliers — tudo sem depender de chamadas a LLM no caminho crítico.

Todas as operações estão disponíveis via CLI (`lutz model`, `lutz dedup`, `lutz rank`, `lutz query`).

---

## Pré-requisitos

O corpus deve estar vetorizado antes de usar qualquer funcionalidade de analytics:

```bash
lutz vectorize --section-parse
```

---

## Fluxo recomendado para revisão sistemática

```
1. lutz dedup            → remove duplicatas entre bases (PubMed, Scopus, WoS)
2. lutz rank             → prioriza triagem por relevância semântica
3. lutz model explore    → escolhe k para clustering
4. lutz model fit        → treina KMeans + centroide uma única vez
5. lutz model cluster-report  → síntese temática por cluster
6. lutz query            → exploração SQL livre com UDFs
```

---

## `lutz dedup` — Deduplicação por similaridade

Identifica artigos quase-duplicados entre bases de dados usando distância de cosseno no nível de artigo (não de chunk). Útil como primeira etapa PRISMA antes da triagem manual.

Na CLI:

```bash
lutz dedup --threshold 0.05
```

**Exemplo de saída:**

```
 Grupo  Manter              Duplicata(s)                   Distância
────────────────────────────────────────────────────────────────────
     1  smith_2022.pdf      smith_2022_scopus.pdf           0.018
                            smith_2022_wos.pdf              0.031
     2  jones_ml_2021.pdf   jones_machine_learning_21.pdf   0.042

Found 2 duplicate group(s) across 4 articles. No files were deleted.
```

::: tip
O Lutz **nunca apaga arquivos automaticamente** — apenas reporta os grupos. A decisão de exclusão é sempre do revisor.
:::

**Opções disponíveis:**

| Opção | Padrão | Descrição |
|---|---|---|
| `--threshold` | `0.05` | Distância de cosseno máxima para considerar duplicata |
| `--format` | `table` | Saída: `table`, `json` ou `html` |
| `--output PATH` | stdout | Salva em arquivo se informado |

**Saída JSON:**

```bash
lutz dedup --threshold 0.05 --format json --output duplicatas.json
```

```json
[
  {
    "group_id": 1,
    "keep": "smith_2022.pdf",
    "duplicates": [
      { "filename": "smith_2022_scopus.pdf", "distance": 0.018 },
      { "filename": "smith_2022_wos.pdf",    "distance": 0.031 }
    ]
  }
]
```

---

## `lutz rank` — Ranking de relevância

Ordena artigos pela similaridade semântica com a sua pergunta de pesquisa. Útil para priorizar a ordem de triagem e documentar um corte auditável.

Na CLI:

```bash
lutz rank --question "machine learning para diagnóstico de doenças cardiovasculares"
```

**Exemplo de saída:**

```
 Rank  Filename                          Score    Chunks
───────────────────────────────────────────────────────
    1  deep_learning_cardio_2023.pdf     0.8923   14
    2  ml_heart_disease_review_2022.pdf  0.8741   11
    3  cnn_ecg_classification_2021.pdf   0.8612    9
    4  random_forests_clinic_2020.pdf    0.7834    8
    5  nlp_radiology_2022.pdf            0.6123   12
   ...

Ranked 47 articles. Cutoff decision is yours — no automatic exclusions.
```

::: info
O ranking usa apenas embedding + distância de cosseno — sem chamada a LLM. Econômico e rápido mesmo para grandes corpora.
:::

**Opções disponíveis:**

| Opção | Padrão | Descrição |
|---|---|---|
| `--question` | obrigatório | Pergunta de pesquisa ou critério PICO |
| `--aggregation` | `mean` | `mean` ou `max` da similaridade dos chunks |
| `--filter-sections` | todos | Ex.: `abstract,introduction` |
| `--top` | todos | Limita a N artigos no resultado |
| `--format` | `table` | `table`, `json` ou `csv` |

**Ranquear apenas por abstract:**

```bash
lutz rank \
  --question "revisões sistemáticas sobre eficácia de vacinas" \
  --filter-sections abstract \
  --top 20 \
  --format csv > ranking.csv
```

---

## `lutz model` — Modelos fit-once

Treina modelos uma única vez sobre o corpus inteiro e os persiste em `.lutz/models/`. As UDFs SQL `predict_cluster` e `predict_centroid_distance` carregam esses modelos — garantindo labels **idênticos entre queries e entre execuções**, independentemente do tamanho do corpus.

### Explorar o número de clusters (`explore kmeans`)

Antes de treinar, use `explore` para escolher `k` com base em evidência:

```bash
lutz model explore kmeans --k-range 2..12
```

**Exemplo de saída:**

```
 k    Silhouette   Inércia       Sugestão
──────────────────────────────────────────
  2   0.241        28412.3
  3   0.318        22017.8
  4   0.376        17834.5
  5   0.401        15102.3       ← sugerido
  6   0.392        13887.1
  7   0.381        12934.4
  8   0.365        12201.7
 ...

Suggested k=5 (highest silhouette: 0.401).
To confirm: lutz model fit kmeans --k 5
Note: the choice of k is yours — silhouette is a guide, not a verdict.
```

Para corpus muito grande, use `--sample N` para amostrar com seed reprodutível:

```bash
lutz model explore kmeans --k-range 2..15 --sample 5000 --random-state 42
```

### Treinar o modelo KMeans (`fit kmeans`)

```bash
lutz model fit kmeans --k 5
```

```
Model saved: kmeans_5 (trained on 3412 chunks, embedding_model=text-embedding-3-small)
```

### Treinar o centroide do corpus (`fit centroid`)

```bash
lutz model fit centroid
```

```
Centroid saved: corpus_centroid (computed over 3412 chunks, embedding_model=text-embedding-3-small)
```

### Listar modelos treinados (`list`)

```bash
lutz model list
```

```
 Model ID          Algorithm   Params   Chunks   Treinado em          Corpus válido
──────────────────────────────────────────────────────────────────────────────────
 kmeans_5          kmeans      k=5      3412     2026-05-30 14:22      ✓
 kmeans_3          kmeans      k=3      3412     2026-05-29 09:15      ✓
 corpus_centroid   centroid    —        3412     2026-05-30 14:25      ✓
```

::: warning Corpus válido
Se novos artigos forem vetorizados após o treino, a coluna **Corpus válido** mostrará `✗`. Re-treine o modelo para garantir que os labels reflitam o corpus atual.
:::

### Remover um modelo (`rm`)

```bash
lutz model rm kmeans_3
```

---

## `lutz model cluster-report` — Síntese temática

Gera um relatório de síntese por cluster: quais artigos pertencem a cada tema e quais trechos são os mais representativos (mais próximos do centroide do cluster).

```bash
lutz model cluster-report --model kmeans_5 --top-chunks 3
```

**Exemplo de saída:**

```
Cluster 0 — 11 artigos
  Chunks representativos:
    [dist 0.012] deep_learning_cardio_2023.pdf (abstract)
                 "We propose a deep learning framework for early detection of..."
    [dist 0.019] cnn_ecg_2021.pdf (methodology)
                 "The convolutional neural network architecture consists of..."
    [dist 0.024] transformer_ecg_2022.pdf (results)
                 "Our model achieved 94.2% accuracy on the PhysioNet dataset..."

Cluster 1 — 9 artigos
  Chunks representativos:
    [dist 0.008] nlp_clinical_notes_2022.pdf (abstract)
                 "Natural language processing of clinical notes enables..."
    ...
```

**Gerar relatório em JSON para uso programático:**

```bash
lutz model cluster-report --model kmeans_5 --format json > clusters.json
```

```json
{
  "model_id": "kmeans_5",
  "clusters": [
    {
      "cluster_id": 0,
      "n_articles": 11,
      "article_filenames": ["deep_learning_cardio_2023.pdf", "cnn_ecg_2021.pdf"],
      "representative_chunks": [
        {
          "filename": "deep_learning_cardio_2023.pdf",
          "section": "abstract",
          "text": "We propose a deep learning framework...",
          "distance_to_centroid": 0.012
        }
      ]
    }
  ]
}
```

---

## `lutz query` com UDFs analíticas

O comando `lutz query` expõe SQL diretamente sobre o vector store. Com `--include-embeddings` (`-e`), as UDFs de distância, clustering e redução ficam disponíveis.

### Rotular chunks com cluster estável

```bash
lutz query -e \
  "SELECT filename, section, predict_cluster(embedding, 'kmeans_5') AS cluster
   FROM vectors
   ORDER BY cluster, filename"
```

### Detecção de outliers (escopo do corpus)

```bash
lutz query -e \
  "SELECT filename,
          AVG(predict_centroid_distance(embedding, 'corpus_centroid')) AS outlier_score
   FROM vectors
   GROUP BY filename
   ORDER BY outlier_score DESC
   LIMIT 10"
```

**Interpretação:** distância alta ao centroide pode indicar (a) artigo fora de escopo ou (b) trabalho genuinamente original. A decisão é do revisor.

### Busca de similaridade entre artigos

```bash
lutz query -e \
  "SELECT v2.filename,
          cosine_distance(v1.embedding, v2.embedding) AS dist
   FROM vectors v1
   JOIN vectors v2 ON v1.filename <> v2.filename
   WHERE v1.filename = 'artigo_referencia.pdf'
     AND v1.section = 'abstract'
     AND v2.section = 'abstract'
   ORDER BY dist
   LIMIT 5"
```

### Todas as UDFs disponíveis

```bash
lutz query "SELECT * FROM lutz_udfs()"
```

| UDF | Retorno | Descrição |
|---|---|---|
| `cosine_distance(a, b)` | DOUBLE | Distância de cosseno entre dois vetores |
| `cosine_similarity(a, b)` | DOUBLE | Similaridade de cosseno |
| `euclidean_distance(a, b)` | DOUBLE | Distância euclidiana (L2) |
| `dot_product(a, b)` | DOUBLE | Produto interno |
| `predict_cluster(emb, model_id)` | INTEGER | Label de cluster fit-once |
| `predict_coords(emb, model_id)` | DOUBLE[] | Projeção PCA fit-once |
| `predict_centroid_distance(emb, model_id)` | DOUBLE | Distância ao centroide fit-once |
| `corpus_centroid_distance(emb)` *(deprecated)* | DOUBLE | Distância ao centroide do batch |
| `kmeans_label(emb, k)` *(deprecated)* | INTEGER | Label KMeans do batch |
| `pca_project(emb, n)` *(deprecated)* | DOUBLE[] | Projeção PCA do batch |
| `embedding_norm(emb)` | DOUBLE | Norma L2 do vetor |
| `embedding_normalize(emb)` | DOUBLE[] | Vetor normalizado (unit) |
| `embedding_z_score(emb)` | DOUBLE[] | Z-score do batch |

::: warning UDFs marcadas como deprecated
`kmeans_label`, `pca_project`, `corpus_centroid_distance` e `batch_centroid` calculam o modelo **no batch Arrow atual**. Em corpora com mais de ~2048 chunks, o DuckDB pode dividir em múltiplos batches e os resultados ficam inconsistentes entre queries. Use as variantes `predict_*` com modelos fit-once para resultados reprodutíveis.
:::

---

## Fluxo completo de analytics para revisão sistemática

```bash
# 0. Vetorizar com seções
lutz vectorize --section-parse

# 1. Remover duplicatas entre bases
lutz dedup --threshold 0.05 --format json --output duplicatas.json

# 2. Priorizar triagem por relevância semântica
lutz rank \
  --question "eficácia de intervenções cognitivas em idosos com MCI" \
  --filter-sections abstract \
  --top 30

# 3. Explorar número de clusters antes de treinar
lutz model explore kmeans --k-range 2..12

# 4. Treinar modelo definitivo (após escolher k=6)
lutz model fit kmeans --k 6
lutz model fit centroid

# 5. Verificar modelos salvos
lutz model list

# 6. Síntese temática por cluster
lutz model cluster-report --model kmeans_6 --top-chunks 5 --format html > clusters.html

# 7. Identificar artigos fora de escopo
lutz query -e \
  "SELECT filename,
          AVG(predict_centroid_distance(embedding, 'corpus_centroid')) AS outlier_score
   FROM vectors GROUP BY filename ORDER BY outlier_score DESC LIMIT 10"
```
