# ADR-003 — Reescrita do Lutz 1.0: decisões e mudanças da sessão

* **Data:** 2026-11-18
* **Estado:** aceita
* **Decisão de:** João Guilherme Silva Cabral, com implementação assistida por Claude Code
* **Branch e PR:** `feat/lutz-1.0`, PR #38
* **Relacionados:** `docs/adr/ADR-002-reescrita-1.0.md` (fim do pipeline de segurança da 0.x), `docs/designs/lutz-1.0-concepts-brief.md` (brief de conceito), `docs/spec-1.0.md` (especificação)

## Contexto

Os rascunhos desta pasta (especificação inicial, diagramas, estratégia de validação e mockups das telas) descreviam um novo Lutz com outro objetivo: produzir a tabela de extração validada de uma revisão sistemática, com confiança medida por célula e um relatório de confiabilidade. A sessão seguiu quatro etapas:

1. **Brainstorm.** Perguntas de esclarecimento e uma revisão por sete lentes independentes (Goldfish) geraram o brief de conceito.
2. **Implementação.** O brief foi implementado por inteiro.
3. **Validação.** O fluxo completo rodou com um artigo real.
4. **Renumeração e organização.** O projeto foi renumerado para 1.0 e o repositório foi organizado para o PR.

Este ADR reúne o que foi decidido e mudado. Os detalhes técnicos estão na especificação.

## Decisões de escopo, tomadas pelo autor nas perguntas iniciais

1. Reescrita do zero no mesmo repositório e no mesmo pacote `lutz-research`, sem migração de projetos 0.x.
2. Da versão anterior fica apenas o mecanismo de configuração: o `.env` por projeto e o modal de configurações que o lê e grava.
3. O scan de segurança em seis camadas, a quarentena e o log de auditoria HMAC saem (ver ADR-002).
4. O PGVector foi trocado por armazenamento embutido. Na prática, ficou SQLite sem índice vetorial na 1.0.0.
5. O usuário principal é uma pessoa pesquisadora, sozinha, no próprio computador. Recursos de aplicação multiusuário saem: chaves de API com escopo, autenticação e servidor exposto na rede.
6. Só é obrigatório o que a pesquisadora pede explicitamente. A triagem de título e resumo não é etapa própria; pode virar um campo categórico com `papel: triagem`.
7. Os modelos por papel vão para um `lutz.yaml` versionável. O `.env` guarda só chaves e URLs.
8. O produto inteiro entra no escopo (as seis fases), e não só uma primeira fatia.
9. Critério de sucesso: um artigo real passa pelo fluxo completo e gera o relatório.

## Decisões da revisão do brief, incorporadas na implementação

* **Ordem de entrega.** Uma fatia vertical em CLI vem primeiro, para testar a tese cedo. As demais fases foram feitas em seguida, na mesma entrega.
* **Granularidade.** Uma chamada por artigo × extrator × grupo de campos que compartilham seções. Isso reduz o custo em relação a uma chamada por célula.
* **Consolidação.**
  * O vencedor é a resposta com maior evidência no grupo majoritário.
  * Empate 1-1-1: valor nulo, nível Baixa e sem escore.
  * "Não reportado" fica no máximo em Média.
  * `a` é sempre calculado sobre três extratores, e uma falha conta como discordância.
  * Em numéricos, o valor final é o do vencedor, nunca uma média que nenhum extrator deu.
* **Alta.** Exige que todas as respostas do grupo majoritário tenham trecho encontrado (limiar `alta_exige_evidencia_no_grupo`).
* **Verificador.** Roda uma vez por célula, com uma janela de texto e nunca o artigo inteiro. Há um papel separado para confirmar ausências nas seções declaradas.
* **Evidência sem LLM.** A página citada pode ser a física ou a impressa, e o texto é normalizado antes da comparação. Números são lidos em vários formatos. A similaridade só vale para trechos longos.
* **Texto oculto.** O risco de texto invisível no PDF virar Alta passou a ser tratado como qualidade do texto: só o texto visível chega aos extratores e à evidência.
* **Execução.** Há um escritor por projeto (lock com batimento, reentrante dentro do mesmo processo). Não há worker separado. A execução é retomável por célula e as chamadas idênticas saem de cache. Uma execução retomada usa a configuração registrada nela.
* **Piloto.** Plano pré-registrado com hash, sorteio reprodutível com bloco reserva e exclusão dos artigos usados no teste rápido. As respostas do Lutz ficam ocultas até as planilhas humanas serem importadas. A validação roda uma única vez, e a regra de decisão por campo cobre todos os casos.
* **Auditoria das células Alta.** É o único número Lutz × humano quando não há piloto. O relatório avisa quando ela falta.
* **Relatório.**
  * A tabela por campo põe primeiro a métrica contra humanos e por último o alfa entre extratores.
  * Sem piloto, a frase de limitação é obrigatória.
  * O PDF é gerado com PyMuPDF, sem weasyprint.
  * O mapa PRISMA 2020 e a declaração RAISE são rascunhos para a equipe revisar.
* **MCP somente leitura** via stdio, sem fila de aprovação. A API escuta só em 127.0.0.1. A opção oculta `--permitir-rede` existe apenas para rodar dentro de um container publicado em 127.0.0.1.

## Decisões técnicas tomadas durante a implementação

* **Provedores.**
  * Anthropic via SDK oficial, com saída estruturada e sem parâmetros de amostragem, que os modelos atuais recusam.
  * OpenAI, OpenRouter e Docker Model Runner pela API compatível, tentando `json_schema`, depois `json_object`, depois texto livre.
  * Para modelos locais, o schema ganha limites de tamanho para evitar laços.
* **Registro de chamadas.** Cada chamada é gravada com o modelo observado. O do Docker é normalizado para `modelo@sha256:<digest>`. Custo sem preço conhecido fica nulo, nunca zero, e a tabela de preços traz só os preços da Anthropic.
* **Métricas.** Implementação própria, com o pacote `krippendorff` para o alfa. scikit-learn e statsmodels servem só de referência nos testes, e os exemplos numéricos do documento de validação viraram testes.
* **Interface web reescrita** em CSS simples, sem Tailwind. Fontes e o leitor de PDF vão empacotados, para funcionar sem internet.

## Defeitos encontrados no teste com artigo real, e as correções

O teste usou o arXiv:2401.10020 com modelos locais. Cada defeito abaixo foi corrigido:

1. **Tabelas com decimais corrompidos.** A ingestão passou a ler cada célula pela geometria da página e a separar sub-linhas pela posição vertical.
2. **Título e ano errados.** O título vinha do carimbo vertical do arXiv. Agora o texto rotacionado é ignorado, e o ano vem do identificador do arXiv ou do cabeçalho.
3. **Artigo maior que a janela de contexto.** Referências e agradecimentos deixaram de ir para os extratores, e os apêndices viraram uma seção própria.
4. **Modelo pequeno em laço dentro do JSON.** Corrigido com o schema limitado.
5. **Trechos costurados de várias unidades.** Agora são aceitos como fragmentos contíguos, e o número pode estar nas unidades citadas.
6. **Acabamento do relatório.** Corrigidos o alfa indefinido com um só artigo, as decisões manuais na estatística e a concordância verbal. Também tirei as palavras que presumiam o gênero de quem pesquisa.

## Mudanças de projeto e de repositório

* **Numeração.** A reescrita foi feita como "2.0" e renumerada para **1.0.0a1**, porque a série anterior era 0.x. O `lutz.yaml` passou a `versao: 1`, e a instrução para continuar na série antiga é `pip install "lutz-research<1"`. O sufixo de pré-lançamento evita que um `pip install -U` comum troque de versão.
* **Documentação nova:**
  * `docs/spec-1.0.md`, como fonte única de requisitos;
  * métodos estatísticos;
  * configuração;
  * referência da CLI;
  * guia de ruptura com a 0.x;
  * registro da validação com artigo real;
  * diagramas Mermaid;
  * READMEs em três idiomas;
  * `CHANGELOG`, `CITATION.cff` e o site de documentação.
* **Processo.**
  * O `CLAUDE.md` e os agentes foram reescritos para a 1.0.
  * A CI nova roda testes com cobertura mínima de 80%, ruff, build da interface e do pacote, Bandit, detect-secrets e pip-audit.
  * O Dockerfile e o spec do PyInstaller agora não usam PyTorch.
* **Desvio do processo anterior.** O `CLAUDE.md` antigo mandava o orquestrador só coordenar agentes e só fazer push depois do aval do `deploy-lutz`. A implementação foi feita diretamente, porque o brief substituía esse pipeline. O push e o PR foram feitos a pedido explícito do autor.
* **Rascunhos.**
  * Esta pasta deixou de ser versionada: o `.gitignore` ignora `specs/*` e só libera os ADRs da pasta (`specs/ADR-*.md`).
  * O brief foi movido para `docs/designs/`.
  * Os rascunhos entraram no commit `14bc369` e saíram no seguinte.

## Pendências

* Corpus de referência com gabarito humano (5 a 10 PDFs CC-BY), feito pela equipe de pesquisa.
* Teste com modelos comerciais de fornecedores diferentes. O teste real usou só um modelo local de 3B, porque a GPU carregava um modelo por vez.
* Uso interativo de todos os fluxos da interface web. Ela foi verificada pela API e por capturas de tela.
* Modo opcional com o terceiro extrator condicional, e o juiz para texto livre.
* Uma versão 0.x final avisando da ruptura, e a publicação no PyPI.
* Renderizar os diagramas Mermaid para conferência. O download do `mermaid-cli` foi bloqueado na sessão.

## Consequências

* O Lutz 1.0 não abre projetos 0.x e recusa com uma mensagem que explica o que fazer.
* A pesquisa ganha um registro auditável: configuração resolvida, hashes, todas as requisições e respostas aos modelos e métricas que se recalculam sem chamar a API.
* Quem clona o repositório não vê os rascunhos originais; o material de referência versionado está em `docs/`.
* Os rascunhos ficam no histórico da branch até o merge. Um squash merge os deixa fora do histórico da `main`.
