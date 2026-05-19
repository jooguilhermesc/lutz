# Citações

A página de Citações permite extrair passagens textuais relevantes dos artigos classificados como `INCLUDE`, com nível de confiança e justificativa gerados pelo LLM.

![Página de Citações](/screenshots/citacoes.png)

---

## O que são citações no contexto do Lutz?

Após a triagem por artigo, você tem veredictos de inclusão/exclusão. A extração de citações vai além: para cada artigo relevante, o LLM identifica as **3 a 5 passagens** que melhor justificam a classificação.

Cada passagem inclui:
- **Trecho original** do artigo
- **Nível de confiança** (0–1) atribuído pelo LLM
- **Justificativa** de por que a passagem é relevante

---

## Fluxo interno

```
relatório JSON (--per-article)
    ↓
classificação de relevância (sem LLM)
    ↓
para cada artigo INCLUDE:
    chunks originais ← LanceDB
    ↓
    LLM → 3-5 passagens + confiança + justificativa
    ↓
JSON de citações salvo em analysis/execution_reports/
```

::: info Pré-requisito
A extração de citações exige um relatório gerado com `lutz analysis --per-article`. O banco vetorial deve estar disponível em `.lutz/vector_store/`.
:::

---

## Opções

| Opção | Descrição |
|---|---|
| **Relatório base** | Selecione o relatório de análise por artigo |
| **Apenas relevantes** | Inclui somente artigos com veredicto `INCLUDE` |
| **Workers** | Chamadas paralelas ao LLM |
| **Nome do output** | Nome base do arquivo de saída |

---

## Equivalente no CLI

```bash
# Extração básica
lutz citations \
  --analysis analysis/execution_reports/screening_20260501.json

# Paralelo, apenas artigos relevantes
lutz citations \
  --analysis analysis/execution_reports/screening_20260501.json \
  --workers 4 --only-relevant

# Com nome customizado
lutz citations \
  --analysis analysis/execution_reports/screening_20260501.json \
  --output-name revisao_citacoes_v1
```

O arquivo de saída segue o padrão: `<nome_analise>_citations_<timestamp>.json`.
