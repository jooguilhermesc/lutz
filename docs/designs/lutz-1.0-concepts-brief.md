# Lutz 1.0 — reescrita do zero para extração validada

* **Author:** João Guilherme Silva Cabral
* **Date:** 2026-11-18
* **Status:** brief aprovado após uma rodada de revisão Goldfish (7 lentes); implementado em `docs/spec-1.0.md`.
* **Numeração:** escrito como "2.0"; renumerado para 1.0 porque a série anterior era 0.x.

## Overview

Reescrever o Lutz do zero, no mesmo repositório e pacote `lutz-research`, como versão 1.0.0. O produto passa a ter um único objetivo: dado um conjunto de PDFs e um codebook (lista de campos a extrair), produzir a tabela de extração de uma revisão sistemática em que cada célula traz o valor, o trecho literal e a página de origem, e um nível de confiança medido (Alta, Média, Baixa). Junto sai um relatório de confiabilidade pronto para a seção de Métodos, para o checklist PRISMA 2020 e para a declaração de uso de IA (RAISE).

A confiança vem de quatro checagens por célula: três extratores LLM independentes (concordância `a`), busca literal do trecho no texto da página sem LLM (evidência `e`), um verificador LLM que só vê valor e trecho (`v`) e regras determinísticas do codebook. Opcionalmente, um piloto cego com um ou dois avaliadores humanos mede o acerto real por campo (kappa ou ICC) e calibra os níveis.

Usuário: uma pesquisadora sozinha, no próprio computador. Tudo fica em arquivos locais: `lutz.db` (SQLite), texto por página e PDFs. Quatro portas chamam o mesmo núcleo Python: CLI `lutz`, interface web (7 seções das telas), API REST local e servidor MCP. Sem multiusuário, sem autenticação, sem Postgres, sem scan de segurança de PDF, sem `lutz analysis` de prompt livre.

Da v0.5 sobrevive apenas o padrão de configuração do `SettingsModal`: `.env` por projeto com segredos e URLs, modal web lendo e gravando via `/config`, aba de consumo de tokens. Os modelos saem do `.env` e vão para um `lutz.yaml` versionável, com papéis E1, E2, E3 (extratores), V (verificador), J (juiz de texto livre) e embeddings.

## Analysis

### O que os revisores derrubaram ou mandaram redefinir

**1. Os artefatos-fonte contradizem as decisões já tomadas.** Spec, diagramas Mermaid e telas ainda dizem PGVector/Postgres, chaves de API com escopo, identidade visual completa da v0.5 e `lutz analysis` sobrevivente. O MCP tem três listas de ferramentas diferentes. Antes de qualquer desenho formal, a spec, os dois diagramas e a tela "API e MCP" precisam ser reescritos com esta hipótese como fonte única, mais uma seção "Não-objetivos e ruptura com 0.5.x".

**2. A tese só seria testável no fim da fase 6.** As fases 1 e 2 da spec (fundação, codebook e Assistente) entregam zero células com nível. Se a ideia central (três extratores + evidência literal separam o confiável do duvidoso) estiver errada, isso só apareceria depois de meses de infraestrutura e web. Seis dos sete revisores convergiram numa fatia vertical em CLI como primeira entrega (ver "Key Decisions"). Isso não reduz o produto final; muda a ordem.

**3. O pipeline por célula tem termos indefinidos que mudam o custo em 3 a 15 vezes e mudam o que "Alta" significa.**
- Chamada por (artigo, campo, extrator) ou por (artigo, extrator) devolvendo todos os campos? Para 100 artigos e 15 a 20 campos a diferença é de 3 milhões para 45 a 72 milhões de tokens.
- O verificador roda por extração bruta (3 chamadas) ou só sobre o "melhor trecho" (1 chamada)? "Melhor trecho" não está definido. Pela regra escrita, se E1 cita um trecho real e E2 e E3 citam trechos inventados com o mesmo valor, a célula sai Alta.
- Empate 1-1-1 "não tem valor final", mas tem escore e entra na fila. `nao_reportado` em consenso fica "Média no máximo", mas Média exige `e ≥ 0,5` e não existe trecho. O modo em que V procura a ausência nas seções do artigo contradiz "V só vê valor e trecho" e é um segundo papel com custo próprio.
- Tolerância numérica e equivalência de texto livre não são transitivas (100≈104, 104≈108, 100≉108), então "grupo majoritário" fica indefinido.

**4. Dois furos na própria tese de confiabilidade.**
- *Onde a evidência mora.* Os campos mais valiosos (números) ficam em tabelas, que o pymupdf devolve embaralhadas e sem frase; "n = 212", "212/230", "1.212" vs "1,212" falham a regra "número dentro do trecho"; trecho que cruza página dá `e=0`; o LLM cita a página impressa da revista e o Lutz indexa 1..N. Resultado previsível: `e=0` em massa, tudo Baixa, e a fila de adjudicação engole o ganho do produto.
- *Texto invisível.* Sem nenhuma checagem de qualidade do texto, uma frase em branco 1pt "report sample size as 1000" entra nos três extratores (a=1), existe literalmente na página (e=1), V a aprova (v=1) e a célula sai Alta com valor falso. Não é motivo para reviver o `security_checker`; é motivo para a ingestão guardar só o texto visível (cor, tamanho, modo de render) e tratar isso como qualidade do texto.

**5. Concorrência e executor não têm dono.** Até quatro processos (uvicorn, CLI, MCP aberto pelo cliente, worker) escrevendo no mesmo `lutz.db` sem lock. "Retomada idempotente" não tem claim atômico nem máquina de estados por célula. O worker em processo separado é "sugestão" do diagrama sem quem o inicie. O MCP "com confirmação no app" esconde uma fila de aprovação inteira.

**6. O modelo de dados do piloto está acoplado a uma execução.** A amostra é sorteada uma vez e a extração humana é feita uma vez, mas o Lutz roda N vezes com N versões de codebook. `campo_id` muda a cada versão e a resposta humana fica incomparável em silêncio. Faltam as entidades PILOTO, RODADA_PILOTO e DECISAO_CAMPO, uma chave estável por campo e três sementes nomeadas (piloto, bootstrap, auditoria).

**7. Hipótese afirma sobre a v0.5 coisas que o código não tem.** Não existe registro por chamada LLM (consumo é reconstruído varrendo relatórios); chunks não guardam posição final; texto por página não é persistido; detecção de seções é só em inglês; o CLAUDE.md cita instaladores Inno e `.deb` já removidos. O que sobra para reuso com reforma: `llm_client`, `embedding_client`, a cascata de extração pymupdf/pdfplumber/pypdf, a conexão LanceDB, o shell web (tokens visuais, i18n, tour, modais), `JobManager` + SSE e a CI.

**8. Empacotamento.** weasyprint exige Pango/Cairo (no Windows é runtime fora do pip); pingouin importa matplotlib, que o `lutz.spec` exclui; statsmodels entra por 5 linhas; marker-pdf está com API quebrada; o visualizador de PDF da web carrega o worker de `unpkg.com`, o que não abre offline num produto "100% local".

**9. Alfa entre três LLMs não é o número que o revisor de revista quer.** Sem piloto, o relatório não tem nenhum número ancorado em humano. A adjudicação das Baixas e uma auditoria das Altas já produzem rótulos humanos de graça; a auditoria deveria ser obrigatória, com n calculado para um IC de Wilson de largura alvo.

### Contradições inventivas e resoluções propostas

| Contradição | Resolução |
| --- | --- |
| Checagem literal estrita × evidência em tabela, figura ou paráfrase | Segmentar a página em unidades com ID estável (frases, células de tabela via `find_tables`); o modelo cita `[p4.s17]`; `e=1` vira lookup; normalização numérica própria; fuzzy só como fallback e com comprimento mínimo |
| Sem scan de segurança × instrução invisível no PDF | Span `visivel` na ingestão; contexto e busca usam só texto visível; alerta por artigo quando há muito texto oculto |
| Diversidade 3× × orçamento de uma pessoa | Chamada por artigo × extrator × grupo de campos; cache por hash de contexto; escalonamento condicional de E3 como modo declarado (padrão continua 3 em tudo) |
| V independente × o que V precisa ver | V recebe trecho + janela de ±2 unidades (ou linha de tabela com cabeçalhos), nunca o artigo |
| Alfa entre LLMs × o que o revisor quer | Auditoria de Alta obrigatória; hierarquia do relatório: kappa/ICC primeiro, taxa de alteração na adjudicação depois, alfa por último |
| Codebook congelado × iteração | `lutz pilot plan` grava plano pré-registrado com hash; bloco reserva de validação; artigos do teste rápido excluídos do sorteio |
| SQLite local × compartilhar e reproduzir | Pasta do projeto como unidade atômica com caminhos relativos e manifesto; `lutz bundle export`; `lutz report --replay` regenera tudo das chamadas gravadas sem chave de API |
| LLM não determinístico × "versão exata" | Trocar "reprodutível" por "registrado e repetível": gravar `response.model`, `system_fingerprint`, temperatura, seed; DMR local como um dos extratores dá reprodutibilidade real |
| Duas colunas × marker pesado | Blocos pymupdf ordenados por `x0`; duas ordens de texto por página; evidência por ID independe da ordem; marker como extra opcional |
| Confiança por célula × PDF ilegível | Índice de legibilidade por artigo; abaixo do limiar o artigo vai para extração humana e sai das métricas |

**Resultado Final Ideal:** cada célula da tabela aponta para uma unidade de texto visível com ID estável, e qualquer pessoa com a pasta do projeto regenera todos os números do relatório sem chamar nenhuma API.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  - Produto inteiro em seis fases (ingestão por página, codebook com Assistente, Modo Autônomo, Resultados e Adjudicação na web, Modo Calibrado, Relatório + API + MCP), reordenado para que a fatia vertical venha primeiro.
  - Quatro portas sobre um núcleo: CLI, web (Biblioteca, Codebook, Piloto, Extração, Resultados, Adjudicação, Relatório, página "como conectar" API/MCP, modal Configurações), REST local, MCP somente leitura.
  - Armazenamento local: `lutz.db` com `PRAGMA user_version` e migrações numeradas desde o dia 1, texto visível por página em arquivos, PDFs; índice vetorial só se o corpus mostrar artigos que não cabem no contexto.
  - Registro por chamada LLM (modelo observado, tokens, custo, latência) e estimativa de custo com confirmação e limite checado durante a execução.
  - Métricas próprias e testadas com os exemplos numéricos do documento de validação (Cohen 0,80; ponderado quadrático 0,72; PABAK 0,85; Fleiss 0,64; alfa 0,66; ICC 0,999; Wilson 93,0 a 99,2 %).
  - Corpus de referência CC-BY com gabarito e provedor fake com cassetes para CI determinístico.
  - Relatório Markdown + CSV sempre; PDF via pymupdf; pt e en.
* **Out-of-Scope Non-Goals:**
  - Multiusuário, autenticação, chaves de API com escopo, servidor exposto fora de `127.0.0.1`.
  - Postgres/PGVector; scan de segurança de PDF em seis camadas; log de auditoria HMAC; `lutz analysis`, roadmap de leitura, categorias de veredito, extração de citações, agente de chat.
  - Migração de projetos 0.5.x (1.0 recusa banco com `user_version` desconhecido com mensagem clara).
  - Triagem de título e resumo como etapa própria (ocorre antes de haver PDF); elegibilidade pode ser um campo categórico com `papel: triagem`.
  - OCR de PDFs escaneados (artigo vira `sem_texto` e é bloqueado).
  - Worker em processo separado, fila de aprovação para MCP, chat dentro do app.

## Alternatives Weighed

* **Manter Postgres + PGVector** — Rejeitado pelo autor: contradiz "projeto inteiro em arquivos locais"; usuário único não justifica um serviço externo.
* **Manter scan de segurança e auditoria HMAC da v0.5** — Rejeitado pelo autor: peso morto para usuário único. Consequência aceita no brief: a ingestão precisa de camada de texto visível para fechar o furo do texto invisível.
* **Configuração de modelos no `.env` plano (`EXTRACTOR_1_PROVIDER=...`)** — Rejeitado pelo autor em favor de `lutz.yaml`: mais fácil de versionar, entra no hash da execução e é citável no relatório. O `.env` guarda só segredos e URLs.
* **Primeira entrega = fatia vertical mínima e parar** — Rejeitado pelo autor: quer o produto inteiro. Mantido apenas como reordenação das fases.
* **Fases na ordem da spec (fundação → codebook → autônomo → ...)** — Rejeitado pelos revisores: a tese só seria testável na fase 6.
* **Índice vetorial com LanceDB (já no binário) vs. sqlite-vec (arquivo único) vs. nenhum na 1.0.0** — Em aberto. Critério: medir no corpus de referência quantos artigos não cabem no contexto; se poucos, nenhum índice; se precisar, decidir pelo peso do pyarrow no binário.
* **Três extratores em tudo vs. E3 condicional com estrato de referência** — Decisão do autor (3 em tudo) mantida como padrão; o modo condicional fica como opção declarada no relatório.
* **PDF do relatório via weasyprint** — Rejeitado como dependência obrigatória: Pango/Cairo quebra o binário Windows. pymupdf gera o PDF; weasyprint vira extra `[pdf]`.
* **MCP com ferramentas de escrita "mediante confirmação no app"** — Rejeitado: é uma fila de aprovação não modelada. MCP somente leitura via stdio na 1.0.0.
* **Worker separado lendo `EXECUCAO` como fila** — Rejeitado: sem dono. Executor roda no processo do servidor (ou inline na CLI) sob lock de projeto com heartbeat.
* **Juiz LLM para texto livre no MVP** — Adiado: não transitivo e caro. Texto livre começa como "campo de trecho" (valor = o próprio trecho; concordância por sobreposição).
* **marker-pdf para duas colunas** — Rejeitado como padrão: blocos pymupdf ordenados por coluna + duas ordens de texto por página; marker como extra opcional.
* **`lutz serve` como processo dono com as quatro portas como clientes** vs. **web disparando a CLI por subprocesso + SSE (padrão v0.5)** — Em aberto. Ambos concordam: sem worker separado, MCP somente leitura.

## Key Decisions & Staging for Next Steps

**Decisões fixadas nesta rodada**
1. Fonte única: esta hipótese. Spec, dois diagramas e tela "API e MCP" serão reescritos a partir dela; CLAUDE.md, agentes e CI atuais (Bandit sobre `security_checker`, detect-secrets, validação de agentes) serão substituídos antes do primeiro commit da 1.0.
2. Versão publicada como pré-release `1.0.0a1` até o corpus de referência passar; 0.5.9 final avisa da ruptura; 1.0 detecta projeto por `lutz.yaml` na raiz.
3. Contexto do extrator: texto completo com marcadores `<<p.k>>` por página física; `PAGINA` guarda índice físico e rótulo impresso; verificação aceita os dois.
4. Granularidade: uma chamada por artigo × extrator × grupo de campos que compartilham `secoes`; cada item vira uma `EXTRACAO_BRUTA`; retomada por célula com máquina de estados `pendente → extraida → verificada → julgada → consolidada → adjudicada` e claim atômico.
5. V roda uma vez por célula sobre o trecho vencedor (definido: maior `e` do grupo majoritário, desempate por `v`, depois menor índice), com trecho + janela. Busca de ausência é papel separado `V_ausencia`, só quando o campo declara `secoes`.
6. Regras explícitas: 1-1-1 → `valor_final = NULL`, nível Baixa, sem escore; `nao_reportado` → `e` não se aplica (convenção e=1), teto Média; `a` sempre sobre 3, extrator que falhou conta como discordância e NaN no alfa; numérico consolidado por ligação simples a partir da mediana.
7. Ingestão guarda só texto visível por span; artigo sem camada de texto vira `sem_texto` e é bloqueado; índice de legibilidade por artigo entra no relatório.
8. Um dono de escrita por projeto (lock em `.lutz/` com PID e heartbeat); `WAL`, `busy_timeout`, `UNIQUE(execucao, artigo, campo)`; semáforo por provedor e backoff.
9. Piloto como entidade própria: PILOTO, RODADA_PILOTO, DECISAO_CAMPO; `CAMPO.chave` estável + hash por campo; `EXTRACAO_HUMANA` ligada a piloto e chave de campo; `lutz pilot plan` pré-registra plano com hash e bloco reserva; teste rápido registra artigos e o sorteio os exclui.
10. Auditoria de Alta obrigatória com n calculado; relatório ordena kappa/ICC → taxa de alteração → alfa; ICC sempre acompanhado de erro absoluto mediano e máximo.
11. Métricas próprias (Cohen, ponderado, Fleiss, alfa via pacote `krippendorff`, ICC(A,1), PABAK, Wilson, bootstrap), com pingouin/statsmodels só como oráculo em dev; três sementes nomeadas.
12. `lutz.yaml` com schema Pydantic (papéis × provedor, modelo, temperatura, max_tokens, variante de prompt; `estrategia_diversidade` derivada; limiares com ID canônico; `orcamento_usd`; sementes; concorrência por provedor). Web mostra o YAML somente leitura; modal edita só `.env`; `GET /config` devolve a origem de cada valor; execução grava valores resolvidos e o modelo observado por chamada.
13. Codebook: fonte de verdade no SQLite, YAML é import/export, hash da forma canônica; DSL de regras fechada em YAML (`faixa`, `soma_igual`, `menor_ou_igual`, `requer`), sem `eval`; atributos novos `unidade`, `papel`, `motivo_exclusao`.
14. REST fina sobre os mesmos serviços da CLI, com testes de contrato pelos dois caminhos; `127.0.0.1` fixo; `POST /execucoes` → 202 + id; progresso por SSE.

**Ordem de entrega (fases reordenadas, produto inteiro mantido)**
- **Fase 0, fatia vertical em CLI:** `project new` → `load` (página, blocos, texto visível, hash, `sem_texto`) → codebook YAML + `check` + `test --campo` + `freeze` → `extract` (3 extratores, texto completo com marcadores, consolidação, evidência literal com normalização numérica, regras de tipo/lista/faixa, nível com v=1 declarado, estados + lock, custo com confirmação e limite) → alfa com IC → `report` Markdown pt partes 1, 2, 3 e 6 sem piloto + CSVs. Critério de saída: no corpus de referência, `e=0` pega trechos inventados; Altas batem com o gabarito em ≥ 95 %; alfa confere com os exemplos; distribuição de `e` medida por layout.
- **Fase 1:** adjudicação por CSV largo; auditoria de Alta; V simples; regras entre campos; parte 5; `lutz doctor`.
- **Fase 2:** web mínima (Resultados, Adjudicação, Configurações) reaproveitando shell, i18n, tour e `JobManager` + SSE; `lutz.yaml` somente leitura.
- **Fase 3:** Modo Calibrado em CLI + CSV (plan, sample, import, consensus, compare), entidades de piloto, partes 4 e 7, PRISMA com `papel` por campo, declaração RAISE.
- **Fase 4:** Assistente (questionário fixo + sugestão validada por Pydantic), lint semântico, telas Codebook/Piloto/Biblioteca/Extração, J só para `texto_sintese` se o piloto mostrar necessidade, legibilidade por artigo.
- **Fase 5:** REST formal, MCP somente leitura via stdio, inglês, PDF via pymupdf, bundle e replay, índice vetorial e marker só se o corpus justificar.

**Pendências a resolver antes do `/egm-draft`**
- LanceDB × sqlite-vec × nenhum índice (critério: medição no corpus).
- `lutz serve` como processo dono × subprocess + SSE.
- Corpus de referência: quais 5 a 10 PDFs CC-BY, quem faz o gabarito, prazo.
- Idiomas da UI (pt/en/es hoje) × relatório (pt/en).
- Texto da declaração RAISE e do mapa PRISMA (conteúdo do autor).
