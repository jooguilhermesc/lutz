# ADR-004 — Todos os modelos passam pelo OpenRouter

* **Data:** 2026-11-18
* **Estado:** aceita
* **Decisão de:** João Guilherme Silva Cabral (autor)

## Contexto

A versão de desenvolvimento do Lutz 1.0, antes deste ADR, falava com quatro provedores (Anthropic pelo SDK oficial, OpenAI, OpenRouter e Docker Model Runner). Para montar três extratores de fornecedores diferentes, a pessoa pesquisadora precisava de até três chaves e de três contas. Também precisava digitar ids de modelo no `lutz.yaml` sem ver a lista de modelos disponíveis, e manter preços à mão para tudo o que não fosse Anthropic. A tela de Configurações tinha quatro abas, e o `lutz.yaml` aparecia nela só para leitura.

O OpenRouter dá acesso aos modelos de todos esses fornecedores com uma única chave. Ele publica o catálogo (id, contexto, preço por token), informa o gasto e o limite da chave e devolve o custo cobrado em cada resposta.

## Decisão

1. **Um provedor:** `lutz.llm.provedores` passa a ter só `openrouter` (Chat Completions compatível com OpenAI) e `fake` (testes). Saem `anthropic`, `openai` e `docker_model_runner`, e a dependência do SDK `anthropic`. A diversidade de fornecedores passa a vir do prefixo do id do modelo (`anthropic/`, `openai/`, `google/`...).
2. **`.env`:** a lista branca fica só com `OPENROUTER_API_KEY` e `OPENROUTER_BASE_URL`.
3. **`lutz.yaml`:** `provedor` aceita `openrouter` (padrão, pode ser omitido) e `fake`. Um projeto que ainda cita um provedor removido não abre, e a mensagem diz o que escrever (`provedor: openrouter`, `modelo: anthropic/<modelo>`).
4. **Tela de Configurações:** uma tela só, com a chave, os modelos e o consumo. Ela deixa de ser somente leitura em um ponto: **escreve o bloco `modelos`** do `lutz.yaml` (um modelo do catálogo para E1, E2, E3 e V). As demais opções de cada papel, o resto do arquivo e os comentários são mantidos. O arquivo é validado antes de ser gravado. Limiares, orçamento e o restante continuam sendo editados à mão.
5. **Preços:** vêm do catálogo do OpenRouter (`GET /models`), guardado em `.lutz/openrouter_modelos.json` por um dia; as estimativas leem só essa cópia e nunca esperam a rede. O custo gravado em `chamada_llm` é o que o OpenRouter informa na resposta (`usage.cost`); sem ele, tokens × preço do catálogo. `precos` no `lutz.yaml` continua tendo prioridade. Sai a tabela embutida `lutz/data/precos.yaml`.
6. **Consumo:** a tela mostra o gasto e o limite da chave (`GET /key`), o saldo de créditos quando a chave pode lê-lo (`GET /credits`) e o consumo do projeto registrado pelo Lutz.

## Consequências

* Modelos locais deixam de ser suportados; não há versão publicada da 1.0 com eles; o código anterior a este ADR está no commit `900ed7b` (merge do PR #38). Nenhum texto sai do computador sem passar pelo OpenRouter, o que passa a constar da spec (§1.2).
* Projetos criados antes desta decisão precisam trocar os quatro modelos (pela tela ou à mão). Execuções antigas continuam legíveis e o relatório delas não muda. Retomar uma execução antiga que usava um provedor removido falha com a mesma mensagem, porque a execução retomada usa a configuração registrada nela.
* O Lutz passa a depender da disponibilidade e dos preços do OpenRouter. O modelo observado e o provedor que atendeu (`provider`) continuam registrados em cada chamada.
* A tela grava o `lutz.yaml`. Como cada execução guarda a configuração resolvida e o hash, mudar os modelos não altera execuções já iniciadas.
* O catálogo e a conta são lidos por HTTP fora do `ClienteLLM`. Não são chamadas de LLM, não enviam texto de artigos e não entram em `chamada_llm`.
