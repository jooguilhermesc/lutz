# Citações

A extração de citações está disponível exclusivamente via **CLI** a partir da versão 0.5. Ela não faz parte da interface web.

---

## O que são citações no Lutz?

Após a triagem por artigo, você tem veredictos de inclusão/exclusão. A extração de citações vai além: para cada artigo `INCLUDE`, o LLM identifica as 3 a 5 passagens que melhor justificam a classificação.

Cada passagem inclui:
- Trecho original do artigo
- Nível de confiança (0–1)
- Justificativa de relevância

---

## Fluxo interno

```
relatório JSON (--per-article)
    ↓ artigos com INCLUDE
    chunks originais ← LanceDB
    ↓
    LLM → 3-5 passagens + confiança + justificativa
    ↓
JSON salvo em analysis/execution_reports/
```

::: info Pré-requisito
Requer um relatório gerado com `lutz analysis --per-article` e o banco vetorial disponível em `.lutz/vector_store/`.
:::

---

## Uso via CLI

```bash
# Extração básica
lutz citations \
  --analysis analysis/execution_reports/screening_20260501.json

# Paralelo, apenas artigos INCLUDE
lutz citations \
  --analysis analysis/execution_reports/screening_20260501.json \
  --workers 4 --only-relevant

# Com nome customizado
lutz citations \
  --analysis analysis/execution_reports/screening_20260501.json \
  --output-name revisao_citacoes_v1
```

O arquivo de saída segue o padrão: `<nome_analise>_citations_<timestamp>.json`.
