# Lutz 1.0 — Especificação do sistema

* **Versão do documento:** 1.0.0a1 · **Estado:** publicado como 1.0.0a1 (pré-release)
* **Fonte única.** Este documento substitui a especificação inicial, os diagramas e a tela "API e MCP" dos mockups (rascunhos fora do repositório, escritos como "Lutz 2.0" antes da renumeração para 1.0) onde eles divergem. As decisões vêm de `docs/designs/lutz-1.0-concepts-brief.md`.

## 1. Objetivo e escopo

O Lutz 1.0 produz a **tabela de extração validada** de uma revisão sistemática: para cada artigo e cada campo do formulário (codebook), o valor, o trecho literal e a página de onde saiu, e um nível de confiança (Alta, Média, Baixa) medido. Junto sai um **relatório de confiabilidade** para a seção de Métodos, o checklist PRISMA 2020 e a declaração de uso de IA (RAISE).

O Lutz não busca literatura nem escreve sínteses. Síntese, lacunas e tendências são trabalho de quem pesquisa, feito em cima da tabela.

### 1.1 Critério de sucesso

Um artigo real passa por importar → codebook (Assistente, lint, teste rápido, congelar) → extração autônoma → adjudicação → auditoria → relatório, e o relatório sai pronto para a seção de Métodos. Verificado na branch com um artigo do arXiv e modelos locais (ver `docs/validacao-e2e.md`).

### 1.2 Usuário e premissas

* Uma pessoa pesquisadora, sozinha, no próprio computador.
* Tudo fica em arquivos locais na pasta do projeto. A API só escuta em `127.0.0.1` e não tem autenticação.
* Só o texto necessário vai ao modelo escolhido, sempre pelo OpenRouter (uma chave; ADR-004). Não há modelos locais.

### 1.3 Não-objetivos

* Multiusuário, autenticação, chaves de API com escopo, servidor exposto na rede.
* Postgres/PGVector ou qualquer índice vetorial na 1.0.0: o extrator recebe o texto completo (ver §6.2).
* Scan de segurança de PDF em seis camadas e log HMAC da 0.5 (a ingestão trata texto oculto como qualidade do texto, §5.1).
* `lutz analysis` com prompt livre, roadmap de leitura, categorias de veredito, extração de citações, agente de chat.
* Triagem de título e resumo como etapa própria (acontece antes de haver PDF). Elegibilidade pode ser um campo categórico com `papel: triagem`.
* OCR: um PDF sem camada de texto vira `sem_texto` e fica fora da extração.
* Worker em processo separado, fila de aprovação no MCP, chat dentro do app.

### 1.4 Ruptura com 0.5.x

O 1.0 **não lê projetos 0.5.x** e não tem migração. Ver `docs/upgrade-0.5-para-1.0.md`.

## 2. Glossário

| Termo | Significado |
|---|---|
| Corpus | Conjunto de artigos (PDFs) da revisão. |
| Codebook | Formulário de extração: a lista de campos, com tipo, instrução e regras. |
| Campo | Uma variável do codebook (ex.: `tamanho_amostra`). Tem `nome` estável e hash próprio. |
| Célula | O valor de um campo para um artigo. |
| Extrator | Uma chamada independente a um LLM (E1, E2, E3) que preenche as células. |
| Unidade | Frase ou linha de tabela do texto visível, com ID citável (`p4.s17`, `p8.t1.r3`). |
| `a`, `e`, `v` | Concordância entre extratores, evidência literal, veredito do verificador. |
| Adjudicação | Decisão humana sobre uma célula duvidosa. |
| Piloto | Amostra extraída também por humanos, para medir acerto. |
| Padrão-ouro | Extração humana de referência (consenso de dois avaliadores, ou um avaliador). |
| PABAK | Kappa ajustado para prevalência e viés; explica kappa baixo com categoria dominante. |
| ICC(A,1) | Correlação intraclasse de concordância absoluta, avaliador único. |
| PICO / PCC | Estruturas de pergunta: População, Intervenção, Comparação, Desfecho / População, Conceito, Contexto. |
| RAISE | Recomendações para uso responsável de IA em síntese de evidências (Cochrane, Campbell, JBI, CEE). |

## 3. Arquitetura

Quatro portas sobre um núcleo Python:

* **CLI** `lutz` e **servidor MCP** (`lutz mcp`, stdio, somente leitura) chamam os módulos de domínio no próprio processo.
* **Interface web** (React) consome a **API REST** local (FastAPI, `lutz web`).

Pacotes: `lutz.core` (projeto, banco, lock, ingestão, codebook, métricas, Assistente, bundle), `lutz.config` (`.env` e `lutz.yaml`), `lutz.llm` (provedores e gateway), `lutz.extraction` (Modo Autônomo), `lutz.calibrated` (piloto), `lutz.revisao` (adjudicação e auditoria), `lutz.report`, `lutz.server` (API, jobs, MCP), `lutz.cli`.

### 3.1 Executor e concorrência

* **Um escritor por projeto.** `.lutz/lock` guarda PID, host, comando e batimento (15 s). Outro processo que tente escrever recebe erro claro. Lock de processo morto ou sem batimento há 90 s é assumido. Dentro de um processo o lock é reentrante (threads do servidor web compartilham; o SQLite em WAL serializa as escritas).
* **Sem worker separado.** A CLI executa inline; a web executa em threads do próprio servidor (`GerenciadorJobs`), uma extração por vez. Ao subir, execuções `rodando` sem lock viram `pausada` (retomáveis).
* **Retomável por célula.** Uma chamada por artigo × extrator × grupo de campos; um grupo só é pedido de novo a um extrator se alguma célula dele não tiver resposta desse extrator. Requisições idênticas saem do cache.

### 3.2 Armazenamento e layout

```
<projeto>/
  lutz.yaml        modelos, limiares, orçamento, sementes (entra no hash de cada execução)
  .env             segredos e URLs de provedor (nunca versionado)
  lutz.db          SQLite: todo o estado da revisão
  pdfs/            PDFs originais renomeados <chave>.pdf
  texto/<chave>/   texto visível por página: p0001.txt (ordem de leitura) e p0001.raw.txt (ordem bruta)
  codebook.yaml    cópia de importação/exportação (a fonte de verdade é o banco)
  exports/         planilhas (resultados, adjudicação, auditoria, piloto)
  relatorios/      execucao-NNNN/ com relatório, anexos e manifesto
  .lutz/           lock e estado de execução
```

Todos os caminhos no banco são relativos à raiz. `lutz bundle export` gera um zip com manifesto SHA-256 (sem `.env`, PDFs opcionais).

### 3.3 Provedores e registro de chamadas

`lutz.llm.provedores`: `openrouter` (Chat Completions compatível com OpenAI; `json_schema` com recuo para `json_object` e texto livre; modelos `anthropic/` sem parâmetros de amostragem; `reasoning.effort` a partir de `esforco`; o custo cobrado, `usage.cost`, é guardado) e `fake` (testes). ADR-004.

`lutz.llm.openrouter` lê, fora do `ClienteLLM` e sem enviar texto de artigos, o catálogo de modelos (`GET /models`, em cache por um dia em `.lutz/openrouter_modelos.json`) e o consumo da chave (`GET /key` e, quando permitido, `GET /credits`).

`lutz.llm.cliente.ClienteLLM` grava cada chamada em `chamada_llm` (requisição, resposta, modelo pedido e **observado**, fingerprint, tokens, custo, latência, tentativas, cache). Erros transitórios (429, 5xx, timeout, conexão) têm backoff exponencial com `retry-after`; erros definitivos (400, autenticação, modelo inexistente, recusa, corte por `max_tokens`) não se repetem. Semáforo por provedor (`concorrencia.por_provedor`). Custo: o valor cobrado informado pelo OpenRouter; sem ele, tokens × preço do catálogo (ou de `precos` no `lutz.yaml`, que tem prioridade); sem preço conhecido fica `NULL`, nunca 0.

## 4. Configuração

Detalhes em `docs/configuracao.md`.

* **`.env`** (mecanismo mantido da 0.5): `OPENROUTER_API_KEY` e `OPENROUTER_BASE_URL`. Variáveis do ambiente do terminal têm precedência. Lista branca de chaves; um valor pode ser apagado; a web e `lutz config show` mostram a origem de cada valor (`processo`, `.env`, `padrao`, `ausente`).
* **`lutz.yaml`** (schema Pydantic): papéis `E1`, `E2`, `E3` (obrigatórios), `V` e `J` (opcionais) com provedor (`openrouter`, padrão, ou `fake`), modelo (id do catálogo do OpenRouter), temperatura, `max_tokens`, `variante_prompt`, `janela_tokens`, `esforco`; `limiares`; `custo`; `sementes`; `concorrencia`; `contexto`; `auditoria`; `relatorio`; `metricas`; `precos`. A tela de Configurações grava só o bloco `modelos` (um modelo do catálogo por papel, mantendo o resto do arquivo e validando antes de gravar); o restante é editado à mão. Um provedor removido pelo ADR-004 é recusado com a migração na mensagem.
* A **estratégia de diversidade** é derivada do prefixo do id do modelo (o fornecedor): `fornecedores_diferentes`, `modelos_diferentes`, `instrucoes_reescritas` ou `nenhuma`.
* Cada execução grava a configuração **resolvida** e seu hash; uma execução retomada usa a configuração registrada nela, nunca a atual.

### 4.1 Limiares (IDs canônicos)

| ID | Padrão | Uso |
|---|---|---|
| `evidencia_similaridade` | 90 | similaridade parcial mínima para e = 0,5 |
| `evidencia_min_chars_fuzzy` | 25 | trecho mínimo para aceitar similaridade |
| `alta_exige_evidencia_no_grupo` | true | Alta exige e ≥ 0,5 em todas as respostas do grupo majoritário |
| `texto_similaridade` | 85 | concordância entre respostas de texto livre |
| `nao_reportado_alerta` | 0,20 | alerta de possível falha de leitura |
| `alfa_confiavel` / `alfa_provisorio` | 0,800 / 0,667 | faixas de Krippendorff |
| `decisao_alto` / `decisao_ic_inferior` / `decisao_medio` | 0,80 / 0,60 / 0,60 | regra de decisão do piloto |
| `decisao_numerico_exato` | 0,90 | numérico só "Lutz sozinho" com ≥ 90% de valores iguais |
| `decisao_texto_alto` / `decisao_texto_medio` | 0,90 / 0,75 | regra para texto livre |
| `calibracao_alta_minima` | 0,95 | alerta se Alta acerta menos que isso no piloto |
| `pabak_categoria_dominante` | 0,80 | quando mostrar PABAK |
| `legibilidade_minima` | 0,5 | artigo listado como leitura limitada |
| `texto_oculto_alerta` | 0,02 | artigo listado com texto oculto |

## 5. Modelo de dados

`lutz.db`, versão de esquema em `PRAGMA user_version` (migrações numeradas em `lutz/core/db.py`), `application_id` próprio, WAL, `busy_timeout`, chaves estrangeiras. Diagrama: `docs/diagrams/er.mmd`.

| Tabela | Conteúdo |
|---|---|
| `projeto` | nome, pergunta, tipo de revisão |
| `artigo` | chave, metadados, hash SHA-256 (único), páginas, `duas_colunas`, fração de texto oculto, tabelas, seções, status (`pronto`, `sem_texto`, `erro`) |
| `pagina` | número físico, rótulo impresso, caminhos de texto, texto oculto descartado, seção |
| `unidade` | ID citável, página, ordem, tipo (`frase`, `linha_tabela`), seção, texto |
| `codebook` / `campo` | versões com hash, congelamento, versão anterior; campos com `chave` estável e hash semântico |
| `execucao` / `extrator` | tipo (`autonoma`, `piloto`, `teste`), configuração resolvida, hashes, versão do Lutz, status; papéis E1–E3, V, J |
| `chamada_llm` | uma linha por chamada (ver §3.3) |
| `celula` / `extracao_bruta` | estado, valor final, a, e, v, escore, nível, motivos, vencedor, trecho, página, unidades; uma resposta por extrator |
| `adjudicacao` / `envio_manual` | decisões com valor anterior, novo, justificativa, data; envios manuais |
| `auditoria` / `auditoria_item` | amostra de células Alta e conferência |
| `piloto` / `piloto_amostra` / `avaliador` / `extracao_humana` / `decisao_campo` | plano pré-registrado com hash, sorteio, respostas humanas ligadas à chave e ao hash do campo, decisões por campo |
| `teste_rapido` | artigos usados em testes rápidos (excluídos do sorteio do piloto) |
| `metrica` | métricas por execução, campo, escopo (`autonomo`, `calibrado`, `nivel`) e par comparado |
| `relatorio` | arquivos gerados com hash |

Nada é apagado pelo pipeline: uma nova execução cria linhas novas. Métricas derivadas são recalculadas.

### 5.1 Estados da célula

`pendente → extraida → verificada → consolidada → adjudicada`.

## 6. Ingestão (`lutz load`)

### 6.1 Processo

1. Valida magic bytes e senha; calcula SHA-256 e recusa duplicatas.
2. Por página: separa o **texto visível** (descarta texto em modo invisível que não seja camada de OCR sobre imagem, opacidade 0, corpo < 4 pt, cor quase branca, fora da página) e guarda o oculto à parte.
3. Ordena os blocos por coluna quando a página tem duas colunas; guarda também a ordem bruta.
4. Lê tabelas célula a célula pela geometria e separa sub-linhas pela coordenada vertical (cada linha impressa vira uma unidade com os cabeçalhos das colunas).
5. Detecta seções em pt/en/es (resumo, introdução, métodos, resultados, discussão, conclusão, limitações, referências, agradecimentos, apêndice).
6. Gera unidades com ID, grava texto por página e metadados (título, autores, ano, chave tipo `silva2021`).
7. Marca `sem_texto` quando há menos de 300 caracteres no total ou menos de 80 por página.

### 6.2 Contexto do extrator

Sempre o texto completo, **sem referências e agradecimentos**, com marcadores `<<p.N | printed page X>>` e unidades `[p4.s17] …`. Se não couber em `contexto.fracao_janela` da janela do modelo menos `max_tokens`, vão só as unidades das seções declaradas nos campos do grupo (mais o resumo); se ainda não couber, as células falham com "excede a janela de contexto". Sem índice vetorial na 1.0.0.

## 7. Codebook e Assistente

Campo: `nome`, `rotulo`, `tipo` (`categorico`, `ordinal`, `numerico`, `texto`), `instrucao`, `valores`, `definicoes`, `exemplos`, `secoes`, `se_ausente`, `tolerancia_relativa`, `faixa`, `unidade`, `papel` (`dado`, `triagem`, `risco_vies`, `criterio`), `motivo_exclusao`, `regras`, `origem` (`manual`, `assistente`).

* **Regras entre campos** (linguagem fechada, sem `eval`): `soma_igual`, `menor_ou_igual`, `maior_ou_igual`, `requer`, `valor_implica`. Campo referido como não reportado → regra não se aplica.
* **Versões:** a fonte de verdade é o banco; salvar com a última versão congelada cria versão nova; conteúdo igual não gera versão. Hash do codebook e hash semântico por campo (exclui rótulo e origem).
* **Lint determinístico** (códigos L000–L019) antes de gastar tokens; **lint semântico** opcional por LLM (S001–S006).
* **Teste rápido:** só E1, 2–3 artigos, mostra valor, trecho, página e evidência; não conta como piloto; os artigos usados ficam fora do sorteio.
* **Assistente:** pergunta, componentes PICO/PCC, variáveis, modelos de partida (ensaio clínico, observacional, escopo, educação, engenharia) e sugestões por LLM (papel J, senão V, senão E1) validadas por Pydantic. Nada entra sem confirmação; campos aceitos ficam com `origem: assistente`.

## 8. Modo Autônomo (`lutz extract`)

1. **Três extratores independentes** respondem JSON com `nome, valor, nao_reportado, unidades, trecho, pagina` por campo. Resposta malformada: uma nova tentativa com a mensagem de erro, depois falha registrada.
2. **Regras por resposta:** tipo, lista de valores (normalizada), faixa plausível.
3. **Evidência sem LLM** (`lutz.extraction.evidencia`): e = 1 se o trecho normalizado aparece literalmente na página indicada (qualquer ordem), nas unidades citadas, atravessando a quebra de página, ou como fragmentos contíguos todos encontrados; 0,5 em página vizinha, em outra página, por similaridade (trechos longos) ou com metade dos fragmentos; 0 se não encontrado ou só em texto oculto. Numérico: o número precisa aparecer no trecho ou nas unidades citadas (separadores de milhar e decimal, porcentagem, notação científica, números por extenso).
4. **Consolidação:** categórico/ordinal por igualdade; numérico pelo grupo dentro da tolerância da mediana (valor do vencedor); texto pelo medoide (similaridade ou unidades em comum). "Não reportado" é um grupo. Sem grupo de pelo menos dois: empate, valor nulo, Baixa, sem escore. `a` sempre sobre três; falha conta como discordância.
5. **Verificador** (V) uma vez por célula sobre o trecho vencedor, com uma janela de ±2 unidades (ou a tabela inteira), nunca o artigo: `sustenta` = 1, `parcial` = 0,5, `nao_sustenta` = 0. **Ausência:** com maioria "não reportado" e `secoes` declaradas, V procura nas seções (`ausente` = 1, `incerto` = 0,5, `presente` = 0).
6. **Regras entre campos** sobre os valores consolidados do artigo.
7. **Nível:** Alta se a = 1, e = 1, v = 1, regras OK e todas as respostas do grupo com e ≥ 0,5; Média se a ≥ 2/3, e ≥ 0,5, v ≥ 0,5 e regras OK; Baixa nos demais. Não reportado: no máximo Média. Sem V: v = 1 declarado. Escore s = a × e × v.
8. **Métricas por campo:** alfa de Krippendorff (nominal/ordinal/intervalar) com IC95% por bootstrap sobre artigos; % unânimes com IC de Wilson; % por nível; % evidência exata; % não reportado com alerta.
9. **Custo:** estimativa antes de rodar (com chamadas em cache), confirmação (`custo.confirmar`), orçamento do projeto verificado antes de cada chamada; ao atingir, a execução pausa e é retomável.
10. **Recálculo** (`lutz extract recompute`): refaz evidência, regras, consolidação, níveis e métricas a partir das respostas gravadas, sem chamar modelos (opcionalmente com os limiares atuais, registrado na execução).

## 9. Modo Calibrado (`lutz pilot`)

1. **Plano** pré-registrado com hash: tamanhos de ajuste, validação e reserva, estratos (`ano`, `revista`), semente, avaliadores (1 ou 2), regra de decisão e versão do codebook das planilhas. Mostra a tabela tamanho × IC do kappa e alerta corpus < 60.
2. **Sorteio** reprodutível, estratificado com alocação proporcional (Hamilton), exclui artigos do teste rápido, não se repete.
3. **Cegamento:** respostas do Lutz para artigos de ajuste e validação ficam ocultas na web, API, MCP, exportações e relatório até todas as planilhas declaradas serem importadas.
4. **Planilhas** largas (uma linha por artigo; colunas `campo`, `campo__nao_reportado`, `campo__pagina`) com guia em Markdown; importação valida cada célula contra o codebook e não grava nada se houver erro. A web oferece formulário cego lado a lado com o PDF.
5. **Consenso** (dois avaliadores): planilha só com divergências; o consenso vira o avaliador `consenso` (padrão-ouro).
6. **Ajuste:** rodadas livres (`lutz extract --piloto ajuste`), cada mudança é uma nova versão congelada; métricas de ajuste não vão para o relatório.
7. **Validação:** uma única execução com codebook congelado (`--forcar` registrado no relatório).
8. **Comparação** por tipo: kappa (categórico, "não reportado" como categoria, PABAK com categoria dominante); kappa ponderado quadrático (ordinal) e kappa simples; ICC(A,1) com % exata e erros absolutos (numérico) e concordância de presença; % de equivalência com Wilson (texto). IC95% por bootstrap sobre artigos. Humano × humano com dois avaliadores. Campos cujo tipo ou valores mudaram desde a planilha são excluídos com aviso.
9. **Decisão por campo** (exaustiva): `lutz_sozinho` (métrica ≥ 0,80 e IC inferior ≥ 0,60; numérico também ≥ 90% iguais), `revisar_media_baixa` (≥ 0,60), `reescrever` (< 0,60), `indefinida` (métrica indefinida).
10. **Calibração dos níveis:** taxa de acerto de Alta, Média e Baixa com IC de Wilson; alerta se Alta < 95%. A calibração só se aplica a uma execução com o mesmo codebook e os mesmos limiares da validação.

## 10. Resultados, adjudicação e auditoria

* **Fila:** toda célula Baixa; Média dos campos que o piloto mandou revisar; células enviadas manualmente. Ordem: nível, escore (empates primeiro), campo, artigo.
* **Decisão:** aceitar maioria, escolher um extrator, digitar valor ou marcar não reportado, com justificativa; valida o valor contra o codebook. A célula mantém o nível original e passa a `origem = adjudicacao`.
* **CSV** de ida e volta (`valor_decidido` com `=` para aceitar; `nao_reportado_decidido`; `justificativa`); importação relata erros por linha.
* **Auditoria de Alta** (`lutz audit`): amostra com a semente de auditoria e n para meia largura alvo do IC de Wilson (padrão ±6% em p = 0,95), limitada ao número de células Alta. Célula errada é adjudicada com motivo `auditoria`. Sem piloto, é o único número Lutz × humano; o relatório avisa quando falta.

## 11. Relatório (`lutz report`)

Markdown e PDF (PyMuPDF), pt e en, sete partes fixas:

1. Identificação: versão, modelos pedidos e observados, temperatura (n/a para modelos Anthropic), variantes de prompt, diversidade, contexto usado, hashes de configuração e prompts, sementes, chamadas e custo.
2. Processo: parágrafo gerado, tabela de limiares, artigos com leitura limitada (sem texto, excedeu a janela, índice de legibilidade baixo) e texto oculto descartado.
3. Tabela por campo, ordenada para quem avalia: Lutz × padrão-ouro (IC), % concordância, humano × humano, decisão, alteradas na adjudicação, % A/M/B, evidência exata, não reportado, α (ou % unânimes). Notas de PABAK, erros numéricos e alertas.
4. Calibração dos níveis (ou o motivo de não haver).
5. Adjudicação por nível e auditoria.
6. Texto para Métodos com e sem piloto; sem piloto inclui sempre a frase de limitação; com um único modelo inclui a limitação de erros correlacionados.
7. Mapa PRISMA 2020 (5, 8, 9, 10, 11, 27) conforme o `papel` dos campos, anexos e declaração RAISE (rascunho para revisão).

Anexos: A (codebook, histórico, origem dos campos), B (tabelas longa e larga), C (respostas de cada extrator, chamadas, adjudicações, auditoria), `metricas.csv`, `execucao.json`, `manifest.json`. O relatório é recusado para execuções de teste, não concluídas ou com artigos do piloto ainda cegos.

## 12. Interfaces

* **Web:** Biblioteca, Codebook, Piloto, Extração, Resultados, Adjudicação, Relatório, API e MCP, e a tela de Configurações (chave do OpenRouter, modelos por papel escolhidos no catálogo, consumo da conta e do projeto, idioma).
* **CLI:** ver `docs/referencia-cli.md`.
* **REST:** `/api/v1/...`; OpenAPI em `/api/docs`. Execuções longas respondem `202` com `job_id`; progresso por SSE em `/api/v1/jobs/{id}/eventos`. Erros de domínio: `{"erro": ...}` com 400, 409 (estado) ou 422 (validação).
* **MCP** (somente leitura): `listar_projeto`, `ler_codebook`, `consultar_celulas`, `detalhe_celula`, `metricas_execucao`, `buscar_trechos`, `ler_relatorio`. Nenhuma ferramenta escreve, roda extração ou revela células do piloto cego.

## 13. Requisitos não funcionais

* **Repetível e registrado:** cada execução guarda configuração resolvida, hashes, versão e todas as requisições e respostas; métricas e relatório se refazem sem API (`recompute`, `report`, `bundle`).
* **Privacidade:** dados locais; `.env` nunca entra em bundle.
* **Testes:** suíte com PDFs sintéticos (uma coluna, duas colunas, tabela, texto oculto, escaneado), provedor falso roteirizado, os exemplos numéricos de `docs/metodos-estatisticos.md` como asserções e oráculos (scikit-learn, statsmodels). Cobertura mínima 80%.
* **Windows:** saída do console nunca quebra por codificação. O PyMuPDF é carregado só quando um PDF é lido ou gerado: sem o Visual C++ Redistributable, `lutz web`, `lutz doctor` e `lutz mcp` abrem, e a leitura de PDFs falha com mensagem que diz o que instalar. O `lutz.exe` leva o runtime do Visual C++ (o build falha se ele não entrar).

## 14. Fases de entrega (todas implementadas nesta versão)

| Fase | Capacidades | Critério de aceite |
|---|---|---|
| 0 | CLI vertical: ingestão, codebook, teste rápido, extração, evidência, regras, níveis, alfa, relatório | Corpus sintético e um artigo real geram relatório; testes de métricas batem com o documento |
| 1 | Adjudicação CSV, auditoria, verificador, regras entre campos, `doctor` | Testes de adjudicação e auditoria |
| 2 | Web: Resultados, Adjudicação, Configurações | Build da SPA e smoke test contra a API |
| 3 | Modo Calibrado completo | Teste de ponta a ponta do piloto e relatório com calibração |
| 4 | Assistente, lint semântico, telas restantes | Testes de API do Assistente |
| 5 | REST, MCP, PDF, bundle | Testes de API, MCP e bundle |

## 15. Questões em aberto

| Questão | Situação |
|---|---|
| Corpus de referência real (5–10 PDFs CC-BY com gabarito humano) | Pendente: depende da equipe de pesquisa. A suíte usa PDFs sintéticos e um artigo do arXiv só para o teste manual. |
| Índice vetorial para artigos que não cabem na janela | Adiado até medir no corpus real quantos artigos excedem a janela dos modelos escolhidos. |
| Juiz de texto livre (J) | Não usado na consolidação; texto livre usa similaridade e unidades. J serve ao Assistente e ao lint semântico. |
| Texto definitivo da declaração RAISE e do mapa PRISMA | Rascunho gerado; revisão da equipe de pesquisa. |
| Prompt injection em texto visível | Risco residual aceito (ADR-002): o artigo é tratado como dado no prompt, o verificador vê só uma janela, a evidência é literal e as células duvidosas vão para adjudicação. |
