# Lutz 2.0 — Especificação do sistema

## 1. Visão geral

O Lutz 2.0 é uma reescrita completa do Lutz, construída do zero para um único objetivo: produzir a **tabela de extração validada** de uma revisão sistemática, com um nível de confiança medido para cada célula e um relatório de confiabilidade pronto para a seção de Métodos e para o checklist PRISMA 2020.

O Lutz 2.0 não é buscador de literatura nem gerador de sínteses. Síntese, lacunas e tendências são trabalho do pesquisador, feito em cima da tabela.

**Princípios**

- Toda entrada é por importação de PDFs.
- Todo valor extraído tem evidência: trecho literal e página.
- Toda execução é reprodutível: modelos, versões, prompts, codebook e sementes ficam registrados.
- A decisão final sobre células duvidosas é humana (adjudicação), alinhada ao RAISE.
- Sem chat. Integração com outros softwares por API e servidor MCP.

**O que se mantém da versão atual**

- Identidade visual da interface web v0.5 (Biblioteca, Resultados, Relatórios), incluindo o rastreamento de uso de tokens.
- Python como linguagem principal, CLI e camada plugável de provedores de LLM.
- PGVector como banco vetorial.

**O que muda**

- O prompt livre (`lutz analysis`) deixa de ser o fluxo principal.
- Entra um banco relacional leve (SQLite) para projetos, codebooks, extrações, piloto, adjudicação e logs.
- Entram o Assistente de Codebook, o Modo Autônomo, o Modo Calibrado e o Relatório de Confiabilidade.

## 2. Arquitetura

**Camadas**

1. **Interface:** web (mesma identidade visual), CLI `lutz`, API REST e servidor MCP. As quatro chamam o mesmo núcleo.
2. **Núcleo de domínio (Python):** módulos de ingestão, codebook, extração, verificação, consolidação, piloto, adjudicação, métricas e relatório.
3. **Provedores de LLM:** interface única com adaptadores por fornecedor. Cada chamada registra modelo, versão exata, temperatura, tokens e custo.
4. **Armazenamento:**
   - **PGVector:** chunks dos PDFs com embeddings e metadados de página e posição.
   - **SQLite:** todo o resto (dados estruturados do projeto).
   - **Sistema de arquivos:** PDFs originais, texto extraído por página e exportações.

**Por que dois bancos**

O PGVector cuida só da recuperação semântica. O SQLite guarda o estado da revisão num arquivo único por projeto, fácil de versionar, copiar e anexar como material suplementar.

**Fluxo principal**

1. Importar PDFs e extrair texto por página.
2. Indexar no PGVector.
3. Montar o codebook com o Assistente.
4. (Opcional) Rodar o piloto calibrado.
5. Rodar a extração autônoma no corpus.
6. Adjudicar as células duvidosas.
7. Gerar o relatório e exportar os anexos.

## 3. Ingestão e indexação

**Requisitos**

- Importar PDFs individualmente ou em lote; calcular hash SHA-256 de cada arquivo para detectar duplicatas.
- Extrair o texto **por página**, guardando o número da página original.
- Corrigir a ordem de leitura em layouts de duas colunas antes de indexar.
- Identificar seções (Métodos, Resultados etc.) quando possível e guardar como metadado.
- Gerar chunks com metadados obrigatórios: artigo, página, posição inicial e final, seção.
- Guardar o texto completo de cada página no sistema de arquivos e o caminho no SQLite. A verificação de evidência usa esse texto, nunca o chunk.

**Regra de contexto**

- Se o artigo cabe no contexto do modelo, o extrator recebe o texto completo.
- Se não cabe, cada extrator usa uma estratégia de recuperação diferente (outra consulta, outro número de chunks ou as seções indicadas no codebook), para evitar erro compartilhado.

**Comandos**

- `lutz project new <nome>`
- `lutz load <pasta|arquivo>`
- `lutz index`

## 4. Codebook e Assistente de Codebook

O codebook é o formulário de extração: a lista de campos que o pesquisador quer extrair de cada artigo. O Assistente ajuda a escrevê-lo bem, porque um campo mal definido derruba a confiabilidade de toda a coluna.

**Estrutura de um campo**

| Atributo | Obrigatório | Descrição |
| --- | --- | --- |
| nome | sim | Identificador sem espaços, ex.: `tamanho_amostra` |
| rotulo | sim | Nome legível para a interface e o relatório |
| tipo | sim | categorico, ordinal, numerico ou texto; define a métrica de concordância |
| valores | categórico e ordinal | Lista de valores aceitos; no ordinal, a ordem importa |
| instrucao | sim | O "campo de comando": o que extrair, em linguagem do pesquisador |
| definicoes | não | Definição operacional de cada valor da lista |
| exemplos | não | Pares trecho → valor esperado, positivos e negativos |
| secoes | não | Seções onde procurar (ex.: Métodos) |
| se\_ausente | sim | Valor quando o dado não aparece (padrão: nao\_reportado) |
| tolerancia\_relativa | numérico | 0 = valores precisam ser iguais |
| faixa | numérico | Mínimo e máximo plausíveis |
| regras | não | Consistência com outros campos, ex.: soma dos grupos = n total |

Todo codebook tem versão e hash. Qualquer mudança gera versão nova; o relatório cita a versão que produziu cada número.

**Assistente de Codebook**

Objetivo: transformar a pergunta de pesquisa do usuário num codebook claro, tipado e testado antes da extração.

Fluxo:

1. **Entrevista inicial:** o pesquisador informa a pergunta de pesquisa (ex.: PICO ou PCC), o tipo de revisão e as variáveis que já tem em mente.
2. **Proposta de campos:** o Assistente sugere a lista de campos, com tipo, valores e instrução de cada um. Pode partir de modelos prontos (ensaio clínico, estudo observacional, revisão de escopo, educação, engenharia).
3. **Revisão campo a campo:** a interface mostra cada campo num cartão editável. O pesquisador aceita, edita ou descarta.
4. **Lint do codebook:** checagens automáticas que apontam problemas antes de gastar tokens:
   - instrução ambígua ou com dois pedidos no mesmo campo;
   - categorias que se sobrepõem ou não cobrem todos os casos;
   - campo ordinal sem ordem clara;
   - numérico sem unidade ou sem faixa;
   - ausência de regra para dado não reportado;
   - campo de texto livre que poderia ser categórico (texto livre é mais difícil de validar).
5. **Teste rápido:** o Assistente roda o campo em 2 ou 3 artigos do corpus e mostra o valor, o trecho e a página. O pesquisador vê na hora se a instrução funciona.
6. **Congelar versão:** o pesquisador salva a versão, que recebe hash e passa a valer para extração e piloto.

Regras do Assistente:

- Ele sugere; quem decide é o pesquisador. Nada entra no codebook sem confirmação.
- Toda sugestão aceita fica registrada no histórico de versões, marcada como sugerida pelo Assistente.
- O teste rápido não conta como piloto e não gera métrica para o relatório.

**Comandos**

- `lutz codebook new` (abre o Assistente na CLI, em modo de perguntas)
- `lutz codebook check codebook.yaml`
- `lutz codebook test --campo <nome> --n 3`
- `lutz codebook freeze`

## 5. Modelo de dados (SQLite)

Um arquivo `lutz.db` por projeto. Tabelas principais:

| Tabela | Conteúdo |
| --- | --- |
| projetos | id, nome, pergunta de pesquisa, data de criação |
| artigos | id, chave (ex.: silva2021), título, hash do PDF, caminho, nº de páginas, status |
| paginas | artigo, número, caminho do texto, seção detectada |
| codebooks | versão, hash, YAML completo, origem (manual ou Assistente), data, congelado |
| campos | codebook, nome, tipo, definição completa |
| execucoes | id, tipo (autônoma, piloto, teste), codebook, modelos e versões, parâmetros, sementes, hashes de prompts, início e fim, tokens e custo |
| extracoes\_brutas | execução, artigo, campo, extrator, valor, nao\_reportado, trecho, página, e, v, regras\_ok |
| celulas | execução, artigo, campo, valor final, a, e, v, escore, nível, origem (maioria ou adjudicação) |
| piloto\_amostras | execução, artigo, conjunto (ajuste ou validação), semente |
| piloto\_humano | avaliador, artigo, campo, valor, nao\_reportado, página, data de importação |
| adjudicacoes | célula, valor anterior, valor decidido, justificativa, data |
| metricas | execução, campo, métrica, valor, IC95% inferior e superior |
| relatorios | execução, caminho, data, hash |

Decisões:

- Formato longo em `extracoes_brutas` e `celulas`; a tabela larga é gerada na exportação.
- O PGVector guarda só chunks e embeddings, ligados ao SQLite pelo id do artigo e pelo número da página.
- Nada é apagado: uma nova execução cria novas linhas, para manter o histórico auditável.

## 6. Modo Autônomo (extração validada)

Roda sempre, em todo o corpus. Mede confiabilidade (consistência e ancoragem no texto), não validade.

**Pipeline por célula**

1. **Três extratores independentes.** Nenhum vê a resposta dos outros. Estratégias de diversidade, em ordem de preferência: modelos de fornecedores diferentes; mesmo modelo com instruções reescritas; mesmo modelo com contexto diferente. A estratégia usada fica registrada.
2. **Resposta estruturada.** Cada extrator devolve JSON com artigo, campo, extrator, valor, nao\_reportado, trecho e página. Trecho é obrigatório quando nao\_reportado é falso.
3. **Consolidação.** Concordância por tipo: igualdade em categórico e ordinal; diferença dentro da tolerância em numérico; LLM juiz em texto livre. Valor final = maioria. Empate 1-1-1 vai direto para Baixa. a = proporção no grupo majoritário.
4. **Verificação de evidência, sem LLM.** Normalização (NFKC, minúsculas, hifenização, aspas, espaços) e busca no texto da página: e = 1 exato na página; 0,5 em página vizinha ou similaridade ≥ 90; 0 não encontrado. Em numéricos, o número precisa estar no trecho.
5. **Verificador independente.** Modelo diferente dos extratores, recebe só campo, instrução, valor e trecho. v = 1, 0,5 ou 0.
6. **Regras do codebook.** Tipo, lista de valores, faixa plausível e consistência entre campos. Falhou, vai para Baixa.
7. **Escore e nível.** Escore s = a × e × v, usado para ordenar a fila de adjudicação.

| Nível | Condição | Ação sugerida |
| --- | --- | --- |
| Alta | a = 1, e = 1, v = 1, regras OK | Aceita; auditoria por amostragem |
| Média | a ≥ 2/3, e ≥ 0,5, v ≥ 0,5, regras OK | Revisar se o campo foi fraco no piloto |
| Baixa | Qualquer outro caso | Adjudicar sempre |

Caso "não reportado": o verificador procura a informação nas seções indicadas. Ausência confirmada fica em Média, no máximo; se encontrar, vai para Baixa.

Limiares são configuráveis e sempre registrados no relatório.

**Métricas por campo**

- Alfa de Krippendorff entre os 3 extratores, com IC95% por bootstrap sobre artigos (nominal, ordinal ou intervalar conforme o tipo).
- % de células unânimes (substitui o alfa em texto livre).
- % Alta, Média e Baixa.
- % com evidência exata.
- % de não reportado, com alerta quando alto (possível falha de recuperação).

**Comandos**

- `lutz extract --extratores 3`
- `lutz extract --campos desenho_estudo,pais` (subconjunto)
- `lutz extract --retomar <execução>` (continua após falha, sem repetir células prontas)

## 7. Modo Calibrado (piloto com humanos)

Opcional. Mede validade: o acerto do Lutz contra humanos, e calibra os níveis do Modo Autônomo.

**Etapas**

1. **Planejamento.** Antes do sorteio, a interface mostra a tabela de tamanho do piloto × largura do IC95% do kappa. Com corpus abaixo de \~60 artigos, sugere extração humana dupla em tudo, com o Lutz como terceiro avaliador.
2. **Sorteio.** Aleatório com semente registrada, estratificado opcionalmente por ano, revista ou tipo de estudo. Divide em conjunto de ajuste (ex.: 10) e de validação (ex.: 20).
3. **Cegamento.** O Lutz gera planilha em branco por avaliador; a interface também oferece um formulário de extração lado a lado com o PDF. Nenhuma resposta do Lutz aparece até a importação da extração humana.
4. **Um ou dois humanos.** Com dois, calcula kappa humano × humano (teto realista) e abre uma tela de consenso; o consenso vira padrão-ouro.
5. **Ajuste.** Rodadas livres no conjunto de ajuste; cada mudança de instrução gera versão nova do codebook. O Assistente pode sugerir reescritas com base nos erros.
6. **Validação final.** Codebook congelado; uma única rodada no conjunto de validação. Só essas métricas vão para o relatório.
7. **Calibração dos níveis.** Taxa de acerto de Alta, Média e Baixa contra o padrão-ouro, com IC de Wilson. Alerta se Alta ficar abaixo de \~95%.

**Métricas por tipo**

| Tipo | Principal | Apoio |
| --- | --- | --- |
| Categórico | Kappa de Cohen | % concordância; PABAK se uma categoria passa de \~80% |
| Ordinal | Kappa ponderado quadrático | Kappa simples; % concordância |
| Numérico | ICC(A,1) | % exata ou na tolerância; erro absoluto mediano e máximo |
| Texto livre | % equivalência julgada pelo humano | Lista de divergências |

Todo kappa e ICC com IC95% por bootstrap sobre artigos (2.000 repetições, semente fixa).

**Regra de decisão por campo (configurável)**

| Resultado na validação | Decisão |
| --- | --- |
| κ ou ICC ≥ 0,80 e IC inferior ≥ 0,60 | Lutz sozinho; adjudicar só Baixa |
| Entre 0,60 e 0,79 | Revisar Média e Baixa |
| Abaixo de 0,60 | Reescrever e repetir; se não melhorar, extração humana |

Auditoria opcional: após a extração completa, sorteio de \~5% das células Alta para conferência humana.

**Comandos**

- `lutz pilot plan`
- `lutz pilot sample --n 30 --ajuste 10 --seed 42 [--estratos ano]`
- `lutz pilot import --avaliador A pilot/humano_A.csv`
- `lutz pilot consensus`
- `lutz pilot compare --conjunto validacao`
- `lutz audit --fracao 0.05`

## 8. Adjudicação

Fila de células para decisão humana, ordenada pelo escore, do pior para o melhor.

- Entram sempre as células Baixa; entram também as Média dos campos que o piloto mandou revisar.
- Na interface: valor de cada extrator, trecho destacado no PDF na página indicada, resultado de cada checagem e campo para o valor final e a justificativa.
- Atalhos: aceitar maioria, escolher outro extrator, digitar valor, marcar não reportado.
- Toda decisão grava o valor anterior, o novo, a justificativa e a data.
- Exportação e importação por CSV para quem prefere planilha.

Comandos: `lutz adjudicate export`, `lutz adjudicate import extraction/adjudicacao.csv`.

## 9. Relatório de confiabilidade

Gerado em Markdown e PDF, com CSVs, em português e inglês. Sete partes, sempre nesta ordem:

1. **Identificação da execução:** versão do Lutz, modelos e versões exatas, parâmetros, estratégia de diversidade, versão e hash do codebook e prompts, sementes, datas.
2. **Processo:** parágrafo automático com extratores, verificação, limiares e regra de adjudicação.
3. **Tabela por campo:** tipo, alfa (IC95%), % Alta/Média/Baixa, % evidência exata, κ ou ICC contra padrão-ouro, % concordância, κ humano × humano, decisão. Colunas do piloto marcadas "sem piloto" quando não houve. Nota de PABAK quando há categoria dominante.
4. **Calibração dos níveis:** taxa de acerto por nível com IC de Wilson, rodadas de ajuste e o que mudou.
5. **Adjudicação:** células enviadas e alteradas por campo e nível; resultado da auditoria.
6. **Texto para Métodos:** modelo com piloto e modelo sem piloto. O modelo sem piloto sempre inclui a frase de limitação: concordância entre extratores não comprova acerto.
7. **Mapa PRISMA 2020 e anexos:** itens 5, 8, 9, 10, 11 e 27; anexos A (codebook e histórico, incluindo sugestões do Assistente), B (tabela consolidada com nível e evidência), C (log completo). Inclui declaração de uso de IA alinhada ao RAISE.

Comando: `lutz report [--idioma pt,en] [--formato md,pdf]`.

## 10. Interface web

Mantém a identidade visual da v0.5: mesma paleta, tipografia, componentes e navegação lateral. As seções passam a ser:

| Seção | Função |
| --- | --- |
| Biblioteca | Importação de PDFs, status de indexação, alerta de layout em duas colunas |
| Codebook | Assistente, cartões de campo, lint, teste rápido, histórico de versões |
| Piloto | Planejamento, sorteio, formulário cego lado a lado com o PDF, consenso, métricas |
| Extração | Execuções, progresso por artigo, uso de tokens e custo |
| Resultados | Tabela larga com cor por nível de confiança; clique na célula abre o trecho no PDF |
| Adjudicação | Fila ordenada pelo escore |
| Relatórios | Geração, prévia e exportação |

## 11. API e MCP

- **API REST:** mesmos recursos da CLI (projetos, artigos, codebooks, execuções, células, piloto, adjudicação, relatórios). Execuções longas são assíncronas, com consulta de status.
- **Servidor MCP:** ferramentas para listar projetos, ler o codebook, consultar células com nível e evidência, e gerar relatório. Sem chat e sem criar extrações sem confirmação do pesquisador.

## 12. Requisitos não funcionais

- **Reprodutibilidade:** toda execução grava `execucao.json` com tudo que é preciso para repetir.
- **Custo:** estimativa de tokens e custo antes de cada extração, com confirmação; limite por projeto.
- **Retomada:** extração idempotente por célula; falha de API não perde trabalho.
- **Testes:** suíte com corpus de referência e gabarito; os exemplos numéricos do documento de validação viram testes das funções de métrica.
- **Bibliotecas:** scikit-learn, statsmodels, krippendorff, pingouin, rapidfuzz, com versões fixadas.
- **Privacidade:** PDFs e dados ficam locais; só o texto necessário vai ao provedor de LLM.

## 13. Fases de entrega

1. **Fundação:** projeto, ingestão por página, PGVector com metadados, SQLite, provedores de LLM.
2. **Codebook:** schema, lint, Assistente e teste rápido.
3. **Modo Autônomo:** 3 extratores, verificação de evidência, verificador, regras, níveis e alfa.
4. **Adjudicação e Resultados** na interface.
5. **Modo Calibrado:** piloto cego, consenso, kappa e ICC, calibração dos níveis.
6. **Relatório, API e MCP.**

## 14. Questões em aberto

- Quais provedores de LLM entram na primeira versão para garantir diversidade real de extratores?
- O LLM juiz de texto livre precisa ser um modelo diferente dos extratores?
- O PGVector continua num Postgres separado ou vale avaliar uma opção embutida, para o projeto inteiro caber em arquivos locais?
