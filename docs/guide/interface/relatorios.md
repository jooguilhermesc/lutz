# Aba Relatórios

A aba **Relatórios** lista todos os relatórios gerados pelas análises anteriores, com opções de visualização e download.

![Aba Relatórios](/screenshots/relatorios.png)

---

## Lista de relatórios

Cada card exibe:

| Campo | Descrição |
|---|---|
| **Nome** | Identificador único da execução (ex: `tmpglwe1i2p_20260522_012658`) |
| **Data** | Data e hora da análise |
| **Artigos** | Quantidade de artigos processados |
| **Tokens** | Total de tokens consumidos |
| **Tempo** | Duração da análise |

---

## Ações

### Download PDF

Clique em **↓ PDF** para baixar o relatório formatado. O PDF inclui:

- Metadados da execução (modelo, tokens, data)
- Tabela de veredictos por artigo
- Resposta completa do LLM por artigo (modo por artigo)

### Remover relatório

Clique no ícone de lixeira para excluir um relatório. Use **Remover todos** para limpar o histórico completo.

### Atualizar lista

O botão **↻ Atualizar** recarrega a lista caso relatórios tenham sido gerados via CLI enquanto a interface estava aberta.

---

## Arquivos gerados

Cada análise salva arquivos em `analysis/execution_reports/`:

| Arquivo | Conteúdo |
|---|---|
| `*.json` | Metadados, artigos, tokens e resposta bruta do LLM |

---

## Estrutura do JSON de relatório

```json
{
  "timestamp": "2026-05-22T22:26:58",
  "mode": "per_article",
  "prompt": "...",
  "llm_provider": "openai",
  "llm_model": "google/gemini-3.1-flash-lite",
  "embedding_model": "openai/text-embedding-3-small",
  "total_tokens": 408928,
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
