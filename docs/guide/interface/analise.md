# Análise

::: warning Página removida na v0.5.0
A página `/analysis` foi removida. A análise RAG agora é iniciada pelo painel lateral da interface principal, e os resultados são exibidos na **[aba Resultados](./resultados.md)**.
:::

---

## Modos de análise

### Modo RAG (padrão)

No modo RAG, o Lutz:

1. Converte o prompt em um vetor de embedding
2. Recupera os *N* chunks mais similares do corpus completo (padrão: `top_k = 10`)
3. Envia esses chunks como contexto para o LLM
4. Faz **uma única chamada** ao modelo

Ideal para síntese geral, mapeamento de literatura e perguntas sobre o corpus.

```
prompt → embedding → busca vetorial → top-K chunks → LLM → resposta
```

### Modo por artigo

No modo por artigo, o Lutz itera sobre cada artigo no banco e faz uma chamada separada ao LLM para cada um. O modelo é instruído a emitir um veredicto estruturado:

```
---VERDICT---
RELEVANCE: INCLUDE
```

| Veredicto | Significado |
|---|---|
| `INCLUDE` | Artigo atende ao critério de inclusão do prompt |
| `EXCLUDE` | Artigo não atende ao critério |
| `UNCERTAIN` | Trechos disponíveis são insuficientes para decidir |
| `UNKNOWN` | Nenhum bloco de veredicto encontrado |

Ideal para triagem sistemática com inclusão/exclusão por artigo.

---

## Opções da interface

| Campo | Descrição |
|---|---|
| **Prompt** | Selecione um arquivo `.md` dos `prompts/` ou escreva diretamente |
| **Modo de análise** | **Por artigo** (individual) ou **Biblioteca completa** (RAG) |
| **Arquivos de contexto** | Arquivos adicionais enviados como contexto junto ao prompt |
| **Opções avançadas** | top_k, paralelismo, filtro de seções, nome do output |

### Modos de análise

- **Por artigo** — LLM analisa cada artigo individualmente (recomendado para triagem sistemática com veredicto INCLUDE/EXCLUDE)
- **Biblioteca completa** — busca semântica recupera os chunks mais relevantes do corpus e faz uma única chamada ao LLM (ideal para síntese geral)

---

## Experimentos múltiplos (YAML)

A aba de experimentos permite rodar várias análises em sequência a partir de um arquivo YAML:

```yaml
# experiments/pilot.yaml
screening_abstract:
  prompt: prompts/screening.md
  mode: per_article
  workers: 4
  filter_sections:
    - abstract

deep_methodology:
  prompt: prompts/methodology_analysis.md
  mode: top_k
  top_k: 20
```

Um JSON de sumário consolidado é gerado junto com os relatórios individuais.

---

## Como escrever bons prompts

Um prompt eficaz para triagem sistemática geralmente inclui:

```markdown
# Título da análise

## Objetivo
Explique o que você quer descobrir.

## Critério de inclusão
Descreva claramente quando um artigo deve ser incluído.

## Perguntas
1. O artigo trata de [tema]?
2. O método utilizado é [tipo]?
3. O contexto é [população/período]?

## Formato da resposta
Solicite lista, tabela ou seções com títulos claros.
```

::: tip
O `lutz init` cria quatro templates prontos para editar em `prompts/`.
:::

---

## Equivalente no CLI

```bash
# Modo RAG
lutz analysis --p prompts/screening.md

# Por artigo com 4 workers
lutz analysis --p prompts/screening.md --per-article --workers 4

# Filtrar por seção
lutz analysis --p prompts/screening.md --per-article \
  --filter-sections abstract

# Múltiplos experimentos
lutz analysis --multiple experiments/pilot.yaml
```
