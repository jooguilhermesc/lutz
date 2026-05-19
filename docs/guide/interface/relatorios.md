# Relatórios

A página de Relatórios exibe todas as análises já executadas, com seus veredictos, respostas do LLM e opções de download.

![Página de Relatórios](/screenshots/relatorios.png)

---

## O que é gerado após uma análise

Cada execução de `lutz analysis` gera arquivos em `analysis/execution_reports/`:

| Arquivo | Conteúdo |
|---|---|
| `*.json` | Metadados, artigos usados, tokens, resposta do LLM |
| `*.html` | Tabela formatada com veredictos e análise expandível por artigo (apenas modo por artigo) |

---

## Tabela de relatórios

A tabela lista todas as análises com:

- **Nome** do arquivo de relatório
- **Modo** (RAG ou por artigo)
- **Data** de execução
- **Artigos** analisados
- **Modelo** de LLM utilizado

---

## Visualização por artigo

Ao expandir um relatório de modo por artigo, você vê para cada artigo:

- **Veredicto**: `INCLUDE`, `EXCLUDE`, `UNCERTAIN` ou `UNKNOWN`
- **Análise completa** do LLM
- **Chunks utilizados** como contexto

Os veredictos `INCLUDE` e `EXCLUDE` são coloridos para facilitar a triagem visual.

---

## Download

- **JSON**: relatório completo com todos os metadados, útil para processamento programático
- **HTML**: relatório formatado para compartilhar com colaboradores ou incluir em documentos

---

## Estrutura do JSON de relatório

```json
{
  "timestamp": "2026-05-18T15:30:00",
  "mode": "per_article",
  "prompt": "...",
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini",
  "embedding_model": "text-embedding-3-small",
  "total_tokens": 42000,
  "articles": [
    {
      "filename": "artigo_01.pdf",
      "relevance": "INCLUDE",
      "chunks_used": 8,
      "response": "..."
    }
  ]
}
```
