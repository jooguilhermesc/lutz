# Aba Resultados

A aba **Resultados** exibe os veredictos gerados pela análise RAG para cada artigo do corpus.

![Aba Resultados](/screenshots/resultados.png)

---

## Filtros de veredicto

A barra de filtros segmenta os artigos por decisão:

| Filtro | Significado |
|---|---|
| **Todos** | Todos os artigos do corpus |
| **Incluir** | Artigos marcados como relevantes pelo LLM |
| **Excluir** | Artigos marcados como irrelevantes |
| **Incerto** | Artigos sem análise concluída ou com baixa confiança |

Os contadores são atualizados em tempo real após cada análise.

---

## Lista de artigos

Cada linha exibe:

- **Nome do artigo** e status (Aguardando análise / Analisado)
- **Chunks usados** como contexto RAG
- **Veredicto** com badge colorido

Clique na seta **▼** para expandir e ver a resposta completa do LLM para aquele artigo.

---

## Metadados da análise

A linha de metadados acima da lista mostra:

```
google/gemini-3.1-flash-lite · 408.928 tokens · 9.6s
```

- **Modelo** utilizado na análise
- **Total de tokens** consumidos
- **Tempo de execução**

---

## Exportar PDF

O botão **↓ PDF** gera um relatório formatado com todos os veredictos, pronto para compartilhar ou arquivar.

---

## Executar nova análise

1. Preencha o **Critério de triagem** no painel lateral
2. Clique no botão verde **▶ Iniciar análise**
3. Acompanhe o progresso — os veredictos aparecem à medida que o LLM processa cada artigo

::: tip Modos de análise
- **RAG** (padrão): o prompt é vetorizado e chunks relevantes de todos os artigos são recuperados para uma resposta consolidada
- **Por artigo**: cada artigo é analisado individualmente, gerando um veredicto por PDF
:::
