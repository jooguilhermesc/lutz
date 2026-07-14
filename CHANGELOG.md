# Changelog

All notable changes to this project will be documented in this file.

## [0.5.1] - 2026-07-14

### Added

- **Aviso de API key não cadastrada** — ao abrir o seletor de modelo, exibe banner com botão "Configurar" quando o provedor selecionado não tem key no `.env`; estado recarregado automaticamente ao fechar o modal de configurações

### Fixed

- **Documentação da interface web** — todos os docs e screenshots atualizados para refletir a nova UI v0.5.0 (SPA de aba única); screenshots antigos removidos; referências à aba Analytics removidas de `analytics.md`
- **Workflow CI Windows** — remove etapas de build do instalador Inno Setup e launcher GUI deletados na v0.5.0

## [0.5.0] - 2026-07-14

### Changed

#### Redesign completo da interface web

- Nova arquitetura de UI baseada em `AppShell` único com navegação por abas (Biblioteca / Resultados / Relatórios) — substitui o roteamento de páginas anteriores
- `BibliotecaTab` — gestão de artigos e vetorização unificadas em uma única tela
- `ResultadosTab` — visualização de resultados de análise RAG com histórico de execuções
- `RelatoriosTab` — listagem, abertura e exportação de relatórios gerados
- `HistoryDrawer` — painel lateral com histórico de análises anteriores
- `SettingsModal` — configuração de provider/modelo/prompt em modal, sem página separada
- `tailwind.config.js` atualizado com paleta e tipografia do novo design

### Removed

- Páginas legacy: `Analysis`, `Citations`, `Home`, `Process`, `Reports`, `Roadmap`, `Settings`, `VectorStore`, `Vectorize`
- Componentes `CollapsibleSection` e `Layout` (substituídos pelo `AppShell`)
- Instaladores Linux (`build-deb.sh`, `lutz.desktop`) e Windows (`launcher.py`, `lutz.iss`) — distribuição exclusiva via PyPI

## [0.4.1] - 2026-05-30

### Added

#### Analytics para revisão sistemática

- `lutz dedup` — deduplicação semântica de artigos por distância de cosseno no nível de artigo; agrupa pares com distância < threshold usando Union-Find; nunca apaga arquivos, apenas reporta grupos para revisão do pesquisador. Saída em `table`, `json` ou `html`.
- `lutz rank` — ranking de relevância dos artigos contra uma pergunta de pesquisa; embedding da pergunta + similaridade de cosseno por artigo (agregação `mean` ou `max`); suporta `--filter-sections`; sem chamada a LLM. Saída em `table`, `json` ou `csv`.
- `lutz model fit kmeans --k N` — treina KMeans uma única vez sobre o corpus inteiro e persiste em `.lutz/models/`; labels reprodutíveis independentemente do tamanho do corpus e do batching do DuckDB.
- `lutz model fit pca --n N` — treina PCA fit-once sobre o corpus inteiro.
- `lutz model fit centroid` — persiste o centroide médio do corpus; substitui o cálculo batch-fitted de `corpus_centroid_distance`.
- `lutz model explore kmeans --k-range 2..15` — varre uma faixa de valores de k calculando silhouette e inércia; sugere o melhor k sem fixá-lo automaticamente; suporta `--sample N` para corpus grande.
- `lutz model cluster-report --model kmeans_N` — síntese temática por cluster: artigos pertencentes a cada grupo e chunks mais representativos (mais próximos do centroide). Saída em `table`, `json` ou `html`.
- `lutz model list` — lista modelos persistidos com metadados e indicador de validade do corpus (hash).
- `lutz model rm <model_id>` — remove modelo salvo.
- UDFs SQL fit-once: `predict_cluster(embedding, model_id)`, `predict_coords(embedding, model_id)`, `predict_centroid_distance(embedding, model_id)` e variantes `_checked` com validação de `embedding_model`.
- `VectorStore.get_all_embeddings()` — lê todos os embeddings em uma passada usando `to_numpy(zero_copy_only=False)`.
- `VectorStore.get_all_embeddings_with_metadata()` — embeddings alinhados com metadados por índice.
- `VectorStore.get_chunk_embeddings_by_article()` — embeddings agrupados por artigo com filtro de seção.
- `FittedModelStore` em `lutz/analytics/model_store.py` — persiste/carrega objetos sklearn como `.joblib` + `.meta.json`; valida `corpus_hash` para detectar corpus desatualizado.
- `docs/adr/ADR-001` — override documentado do Gate G3 para déficit de cobertura pré-existente em módulos fora do escopo analítico.
- Documentação wiki: nova página `/guide/analytics` com fluxo completo, exemplos de saída e tabela de UDFs.

### Deprecated

- `kmeans_label(embedding, k)` — use `lutz model fit kmeans` + `predict_cluster()` para labels estáveis.
- `pca_project(embedding, n)` — use `lutz model fit pca` + `predict_coords()`.
- `corpus_centroid_distance(embedding)` — use `lutz model fit centroid` + `predict_centroid_distance()`.
- `batch_centroid(embedding)` — substituído por centroide fit-once.

## [0.3.1] - 2026-05-29

### Removed
- Chat page (`/chat`) and all related UI, API client functions, and i18n keys
- Agent Chat page (`/agent`) and all related UI, API client functions, and i18n keys
- `showChat` toggle from Settings and LanguageContext
- Floating chat button from Layout
- All `chat.*`, `agent.*`, `nav.chat`, `nav.agent`, and `settings.showChat` translation keys (PT, EN, ES)

## [0.3.0] - 2026-05-28

### Added
- F6: per-session file activate/deactivate
- Persist chat options per session in localStorage
- F3: inline memory edit, compaction, project scoping
- SSE streaming for regular chat
- Fix `analyze_corpus` inline prompt
