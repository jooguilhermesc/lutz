# Relatórios

A aba **Relatórios** lista todas as análises executadas, com opções de visualização e download.

![Aba Relatórios](/screenshots/relatorios.png)

---

## Lista de relatórios

Cada entrada exibe:

- Nome do arquivo de relatório
- Modo (por artigo ou RAG)
- Data de execução
- Número de artigos analisados
- Modelo de LLM utilizado

Clique em um relatório para expandi-lo e ver os veredictos por artigo.

---

## Histórico (drawer)

O botão **Histórico** na barra superior abre um drawer lateral com os relatórios mais recentes para acesso rápido sem sair da aba atual.

![Drawer de histórico](/screenshots/historico.png)

---

## Download

Cada relatório pode ser baixado em dois formatos:

| Formato | Uso |
|---|---|
| **JSON** | Processamento programático, importação em outras ferramentas |
| **HTML** | Compartilhar com colaboradores, incluir em documentos |

---

## Estrutura do JSON

```json
{
  "timestamp": "2026-05-18T15:30:00",
  "mode": "per_article",
  "prompt": "...",
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-6",
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

Os arquivos são salvos em `analysis/execution_reports/` e nunca são apagados automaticamente.

---

## Equivalente no CLI

```bash
# Listar relatórios disponíveis
lutz reports

# Abrir relatório específico
lutz reports --open screening_20260501_1432.json
```
