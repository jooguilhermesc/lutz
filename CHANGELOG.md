# Changelog

All notable changes to this project will be documented in this file.

## [0.5.6] - 2026-07-16

### Added

- **Categorias de resultado configuráveis** — o pesquisador define suas próprias categorias de veredicto (nome, cor, qual dispara extração de citações) na aba "Resultados" das Configurações; padrão mantém Include/Exclude/Uncertain para compatibilidade com relatórios anteriores; mínimo 2, máximo 8 categorias; code derivado automaticamente do label (ex: "Elegível" → `ELEGIVEL`)
- **Internacionalização (pt / en / es)** — toda a interface agora está disponível em Português, Inglês e Espanhol; o seletor de idioma já existente na barra superior agora altera todos os textos da aplicação: abas, botões, labels, mensagens de estado, tour de onboarding e modal de configurações
- **`--verdict-categories`** — opção no comando `lutz analysis` para passar as categorias configuradas como JSON; o LLM é instruído a usar exatamente os codes definidos pelo pesquisador
- **`--extract-citations-labels`** — opção no comando `lutz citations` para indicar qual(is) label(s) devem ser considerados "incluídos" na extração de citações

### Changed

- **Tela de Resultados** — botões de filtro e cards de resumo agora refletem dinamicamente as categorias configuradas em vez de INCLUDE/EXCLUDE/UNCERTAIN fixos
- **Tour de onboarding** — textos dos botões de navegação (Próximo/Anterior/Concluir) e contador de progresso adaptam-se ao idioma selecionado

## [0.5.4] - 2026-07-14

### Added

- **Extração de citações** — botão "Extrair citações" na tela de Resultados dispara job em segundo plano que busca, em cada artigo classificado como INCLUDE, trechos de texto que corroboram a classificação; citações aparecem inline nos cards expandidos com número de página
- **Roteiro de leitura** — botão "Roteiro de leitura" gera, via job em segundo plano, um plano de estudo com agrupamento dos artigos por estágio; modal exibe overview + artigos por estágio com notas de leitura
- **Aba "Roteiro" nas Configurações** — permite definir os agrupamentos do roteiro (nome + critério) com adição/remoção de estágios; configuração persiste em `localStorage`; padrão são três estágios (Leituras fundacionais, Casos específicos, Evolução do conteúdo)
- **Aba "Consumo" nas Configurações** — tabela com todas as análises realizadas (tipo, modelo, provedor, tokens de entrada/saída, custo estimado); totalizadores de tokens e custo; exportação em CSV; custo calculado com preços estáticos para Anthropic/OpenAI e busca lazy da API do OpenRouter
- **Custo estimado nos relatórios** — barra de metadados de cada relatório na aba Relatórios exibe "Custo est." quando o preço do modelo é conhecido
- **API `GET /api/usage`** — endpoint que agrega dados de consumo de todos os relatórios existentes com estimativa de custo
- **API `GET /api/usage/export`** — exporta registros de consumo como CSV gerado via DuckDB

### Fixed

- **Auto-refresh da aba Relatórios** — ao concluir um job de citações ou roteiro, a lista de relatórios é atualizada automaticamente sem precisar recarregar a página

## [0.5.3] - 2026-07-14

### Fixed

- **BibliotecaTab — status de vetorização incorreto** — `vectorize.py` armazena o filename sem extensão (`pdf.stem`) no vector store, mas a API `/articles` retorna o nome com `.pdf`. A comparação nunca batia, fazendo todos os artigos aparecerem como "Pendente" e a coluna Chunks mostrar "—". Ambos os lados agora são normalizados antes da comparação.

## [0.5.2] - 2026-07-14

### Added

- **Tour interativo** — botão "Tour" no header lança guia com 13 passos cobrindo toda a interface (pipeline, abas, critério de triagem, provedor LLM, modelo embedding, análise, histórico, configurações); usa driver.js com tema visual do Lutz
- **Workers de análise configurável** — campo stepper (1–32) em Settings → LLM & Embedding persiste `ANALYSIS_WORKERS` no `.env` e é usado em cada execução de análise; substitui o valor fixo anterior de 4
- **Modal do Vector Store** — botão "Vetorizar (N)"/"Detalhes" na etapa 2 do pipeline abre modal com 4 cards de metadados, tabela de artigos vetorizados e opção de limpar com confirmação inline
- **Logs de erro nos jobs** — painel de notificações exibe "Ver logs" em jobs terminais; busca output via `GET /api/jobs/{id}` e destaca linhas de erro em vermelho
- **OpenRouter como provedor de embedding** — `embedding_client.py` suporta `openrouter` com `OPENROUTER_API_KEY`, espelhando o suporte já existente em `llm_client.py`
- **Seletor de Modelo Embedding no rail** — novo dropdown "Modelo Embedding" na barra lateral, sincronizado com `.env` em tempo real; SettingsModal unifica "LLM Provider" e "Embedding Provider" em "Model Provider"

### Fixed

- **Sync embedding model** — `SettingsModal` chama `onSaved()` imediatamente após salvar, atualizando o dropdown do rail sem precisar fechar o modal
- **Modelo não encontrado na lista** — quando o modelo salvo em settings não existe na lista retornada pelo provedor (ex: `openai/text-embedding-3-small` no OpenRouter), cria entrada sintética `{id, name: id}` no topo da lista em vez de exibir o primeiro modelo
- **Apagamento em massa ao deletar análise** — `handleDelete` em RelatoriosTab chamava `deleteAllReports()` quando "também limpar vector store" estava marcado; corrigido para chamar `resetVectorStore()` apenas
- **Dark mode** — ResultadosTab, RelatoriosTab e BibliotecaTab reescritos com CSS vars (`--surface`, `--border`, `--text-*`) em vez de cores hardcoded Tailwind

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
