# Plano de PRs e Continuidade

> Criado em: 2026-05-21

---

## Estrutura de branches

| Branch | Base | Propósito |
|---|---|---|
| `main` | — | Releases estáveis |
| `feat/relevance-html-experiments` | `main` | Melhorias core: HTML reports, LLM/Embedding clients, Citations refactor |
| `feat/web-ui` | `feat/relevance-html-experiments` | Nova interface React + FastAPI server |
| `docs/site` | `main` | Site de documentação VitePress + screenshots |

---

## PR 1 — `feat/relevance-html-experiments` → `main`

**Status:** mudanças no working tree, **ainda não commitadas**

### O que precisa ser commitado

```
lutz/commands/analysis.py       — refactor + novas flags
lutz/commands/citations.py      — relatório de citações redesenhado
lutz/commands/vectorize.py      — melhorias de chunking/segurança
lutz/core/embedding_client.py   — suporte a múltiplos providers
lutz/core/llm_client.py         — suporte a Anthropic, Docker Model Runner
lutz/core/pdf_processor.py      — section-aware chunking
lutz/core/security_checker.py   — melhorias de detecção
lutz/ui/_utils.py               — utilitários Streamlit
lutz/ui/pages/1_Vetorizacao.py  — UI Streamlit atualizada
lutz/ui/pages/5_Citacoes.py     — UI Streamlit atualizada
lutz/utils/html_report.py       — templates HTML para relatórios
```

### Como fazer o commit amanhã

```bash
git checkout feat/relevance-html-experiments
git add lutz/commands/ lutz/core/ lutz/ui/ lutz/utils/html_report.py
git commit -m "feat(core): refactor LLM/embedding clients and improve citations HTML report"
git push origin feat/relevance-html-experiments
# Abrir PR no GitHub: feat/relevance-html-experiments → main
```

### Checklist de revisão

- [ ] Testar `lutz vectorize` com PDFs reais
- [ ] Testar `lutz analysis` nos modos `per_article` e `rag`
- [ ] Testar `lutz citations --reading-roadmap`
- [ ] Verificar HTML report gerado abre corretamente no browser
- [ ] Checar que `LLM_PROVIDER=anthropic` e `docker_model_runner` funcionam

---

## PR 2 — `feat/web-ui` → `main`

**Status:** ✅ commitado (2 commits: `3a4a89e`, `fafbd3e`)

> **Depende do PR 1** — `feat/web-ui` foi criado a partir de
> `feat/relevance-html-experiments`, então só deve ir para `main`
> depois que o PR 1 for mergeado.

### O que está incluído

- `web/` — SPA React (Vite + Tailwind + TypeScript)
  - Páginas: Home, Biblioteca, Vector Store, Análise, Citações, Roteiro, Relatórios, Chat, Configurações
  - Chat com sessões, markdown, memória auto e pinada
  - Background jobs com WebSocket notifications
  - PDF viewer inline (react-pdf)
  - Sugestão de rename por leitura direta do PDF
- `lutz/server/app.py` — FastAPI server
- `lutz/core/context_store.py` — store de contexto para o chat
- `lutz/utils/document_reader.py` — extração multi-formato (PDF, DOCX, XLSX, etc.)

### Como abrir o PR amanhã

```bash
# Depois que o PR 1 for mergeado e main atualizado:
git checkout feat/web-ui
git rebase main           # ou merge, se preferir
git push origin feat/web-ui
# Abrir PR no GitHub: feat/web-ui → main
```

### Checklist de revisão

- [ ] `lutz web` sobe o servidor sem erros
- [ ] `npm run build` gera `dist/` limpo
- [ ] Processar artigos em background e navegar livremente
- [ ] Notificações via WebSocket chegam em tempo real
- [ ] Chat com sessões salva histórico em disco
- [ ] Sugestão de rename funciona (lê PDF direto, sem vector store)
- [ ] Confirmar que `web/dist/` e `web/node_modules/` **não** foram commitados
- [ ] Verificar que nenhum `.env` ou chave de API está no repo

### Pendências conhecidas (backlog)

- [ ] **Chat → conectar vector store de artigos**: hoje o chat busca nos "chat files" (store separado). Conectar também a vector store principal (`/vectorize`) para responder perguntas sobre os artigos analisados
- [ ] **go/**: existe um server experimental em Go (`go/cmd/lutz-server/`). Decidir se vai para o mesmo PR ou um branch separado
- [ ] Build do React não está sendo copiado para `lutz/web/` automaticamente no `pyproject.toml` — avaliar se `lutz web` deve fazer isso ou se `web/dist/` deve ser bundled no wheel

---

## PR 3 — `docs/site` → `main`

**Status:** branch criado, **vazio** (aguarda trabalho de docs)

### O que fazer

```bash
git checkout docs/site
# take_screenshots.py está no root (ignorado pelo .gitignore de main)
# Atualizar para a nova UI React:
#   - Trocar BASE_URL de :8501 (Streamlit) para :8765 (FastAPI)
#   - Adaptar seletores (trocar stApp por elementos React)
#   - Rodar e salvar screenshots em docs/public/screenshots/
# Atualizar docs/index.md, docs/guide/, docs/api/ com a nova UI
```

### Script de screenshots

`take_screenshots.py` está na raiz do projeto (ignorado pelo git, não será commitado).
Serve para regenerar screenshots automaticamente para a documentação.

**Atualizar o script para a nova UI:**

```python
BASE_URL = "http://localhost:8765"   # FastAPI, não Streamlit

pages = [
    ("home",       "/"),
    ("biblioteca", "/vectorize"),
    ("analise",    "/analysis"),
    ("citacoes",   "/citations"),
    ("roteiro",    "/roadmap"),
    ("relatorios", "/reports"),
    ("chat",       "/chat"),
    ("config",     "/settings"),
]

# Trocar wait_for_selector para elementos React:
# page.wait_for_selector("main", timeout=5000)
```

---

## Arquivos sensíveis — nunca commitar

| Arquivo/padrão | Motivo |
|---|---|
| `.env` | Chaves de API (OpenAI, Anthropic) |
| `web/articles/*.pdf` | Dados do usuário |
| `web/analysis/execution_reports/*.json` | Resultados privados |
| `web/.lutz/` | Vector store (LanceDB) — pode ser grande |
| `web/prompts/*.md` | Prompts customizados do usuário |
| `take_screenshots.py` | Script de dev, já no .gitignore |
| `go/` | Experimento em Go, não pronto para PR |

---

## Ordem recomendada para amanhã

1. **Commitar PR 1** (`feat/relevance-html-experiments`) — mudanças de core Python
2. **Abrir PR 1** no GitHub e fazer code review
3. **Mergear PR 1** → main
4. **Rebase PR 2** (`feat/web-ui`) em cima do main atualizado
5. **Abrir PR 2** no GitHub
6. **Começar trabalho de docs** no `docs/site` em paralelo

---

## Comandos úteis de referência

```bash
# Ver o que está em cada branch
git log --oneline --graph --all | head -20

# Verificar arquivos sensíveis antes de commitar
git diff --cached --name-only

# Conferir que .env não está staged
git status | grep -i env

# Rodar a UI React em dev
cd web && npm run dev

# Build de produção
cd web && npm run build

# Subir o servidor
lutz web
```
