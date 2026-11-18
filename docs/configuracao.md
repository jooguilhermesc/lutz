# Configuração

A configuração de um projeto fica em dois arquivos na raiz:

| Arquivo | Guarda | Versionar? | Quem edita |
|---|---|---|---|
| `.env` | Chave do OpenRouter | Nunca | Tela de Configurações da web, `lutz config set/unset`, ou um editor |
| `lutz.yaml` | Modelos por papel, limiares, orçamento, sementes, concorrência, idiomas do relatório | Sim | Modelos: tela de Configurações ou editor. O resto: editor de texto |

Todos os modelos passam pelo [OpenRouter](https://openrouter.ai): uma chave dá acesso aos modelos de Anthropic, OpenAI, Google e outros ([ADR-004](adr/ADR-004-somente-openrouter.md)).

## `.env` (mecanismo mantido da 0.5)

Chaves aceitas: `OPENROUTER_API_KEY` (crie em <https://openrouter.ai/keys>) e `OPENROUTER_BASE_URL` (padrão `https://openrouter.ai/api/v1`).

* **Precedência:** valor exportado no terminal > `.env` > padrão. Quando uma chave do `.env` é sombreada pelo terminal, a web e `lutz config show` avisam.
* **Gravar e apagar:** `lutz config set OPENROUTER_API_KEY sk-or-...`, `lutz config unset OPENROUTER_API_KEY`; na web, `PUT /api/v1/config` com `{"CHAVE": "valor"}` ou `{"CHAVE": null}`. Outras chaves são recusadas.
* **Origem:** cada valor é mostrado como `processo`, `.env`, `padrao` ou `ausente`; segredos aparecem mascarados.

## `lutz.yaml`

```yaml
versao: 1
modelos:
  E1: {provedor: openrouter, modelo: anthropic/claude-opus-5.5}
  E2: {provedor: openrouter, modelo: openai/gpt-4.1-mini, temperatura: 0}
  E3: {provedor: openrouter, modelo: google/gemini-2.5-flash, temperatura: 0}
  V:  {provedor: openrouter, modelo: anthropic/claude-sonnet-5.5}
  # J: juiz para o Assistente e o lint semântico (opcional)
custo: {orcamento_usd: 20, confirmar: true}
sementes: {piloto: 42, bootstrap: 42, auditoria: 42}
concorrencia: {por_provedor: 4, tentativas: 5, timeout_s: 180}
contexto: {fracao_janela: 0.7, janela_tokens_padrao: 128000}
auditoria: {meia_largura_alvo: 0.06, p_esperado: 0.95}
relatorio: {idiomas: [pt, en], formatos: [md, pdf], autoria: a equipe de pesquisa}
metricas: {bootstrap_repeticoes: 2000}
limiares: {}          # ver docs/spec-1.0.md §4.1
precos:               # USD por milhão de tokens; sobrescreve o catálogo do OpenRouter
  openai/gpt-4.1-mini: {entrada: 0.4, saida: 1.6}
```

### Papéis

| Papel | Obrigatório | Função |
|---|---|---|
| `E1`, `E2`, `E3` | sim | Extratores independentes |
| `V` | não | Verificador do trecho vencedor e busca de ausência. Sem ele, v = 1 é declarado e o relatório registra a limitação |
| `J` | não | Assistente de Codebook e lint semântico (senão usa V, senão E1) |

Campos de cada papel: `provedor` (`openrouter`, o padrão; `fake` só nos testes), `modelo` (id do catálogo do OpenRouter, como `anthropic/claude-opus-5.5`), `temperatura` (não enviada a modelos `anthropic/`, que não aceitam parâmetros de amostragem), `max_tokens`, `variante_prompt` (`padrao`, `reescrita_a`, `reescrita_b`), `janela_tokens` (janela de contexto do modelo), `esforco` (enviado como `reasoning.effort`: `low` a `max`), `base_url`.

### Escolher os modelos na web

Em `lutz web`, **Configurações** mostra o catálogo do OpenRouter com preço e contexto de cada modelo. Escolha um modelo para E1, E2, E3 e, se quiser, V, e clique em **Salvar modelos**. O Lutz grava só o bloco `modelos` do `lutz.yaml`. As outras opções de cada papel (temperatura, `max_tokens`, variante de prompt), o resto do arquivo e os comentários ficam como estavam. O arquivo é validado antes de gravar. Execuções já iniciadas mantêm a configuração registrada nelas.

### Projetos anteriores ao ADR-004

Um `lutz.yaml` com `provedor: anthropic`, `openai` ou `docker_model_runner` é recusado. A mensagem mostra o que escrever no lugar, por exemplo `provedor: openrouter` e `modelo: anthropic/claude-sonnet-5-5`. Confira o id exato no catálogo, que usa pontos (`claude-sonnet-5.5`). A forma mais simples é escolher os quatro modelos na tela de Configurações e salvar.

### Diversidade

Derivada automaticamente e impressa no relatório:

* `fornecedores_diferentes` — três fornecedores (prefixos do id: `anthropic/`, `openai/`, `google/`...) e três modelos (a mais forte);
* `modelos_diferentes` — modelos distintos, alguns do mesmo fornecedor;
* `instrucoes_reescritas` — mesmo modelo com as três variantes de prompt (vira limitação no relatório);
* `nenhuma` — mesmo modelo e mesma instrução (aviso no `lutz doctor`).

### Preços e consumo

Os preços vêm do catálogo do OpenRouter, baixado pela tela de Configurações (ou pelo botão **Atualizar**) e guardado por um dia em `.lutz/openrouter_modelos.json`. A estimativa de custo usa essa cópia e não espera a rede. Em cada chamada, o Lutz grava o custo que o OpenRouter informa ter cobrado; sem essa informação, usa tokens × preço do catálogo. `precos` no `lutz.yaml` tem prioridade sobre o catálogo. Sem preço conhecido, o custo aparece como desconhecido (nunca 0) e a estimativa avisa.

A tela de Configurações mostra o gasto e o limite da chave no OpenRouter, o saldo de créditos (quando a chave pode lê-lo) e o consumo deste projeto por papel e modelo.

### Orçamento

`custo.orcamento_usd` vale para o projeto inteiro. É verificado antes de cada chamada; ao atingir, a execução pausa e pode ser retomada (`lutz extract --retomar ID`) depois de aumentar o valor. Uma execução retomada usa a configuração registrada nela, não o `lutz.yaml` atual.

## Verificação

```
lutz doctor            # PyMuPDF, configuração, chave, modelos no catálogo, preços, banco, interface web
lutz doctor --chamar   # também faz uma chamada mínima a cada papel e mostra o modelo observado
lutz config show       # .env com origem e resumo do lutz.yaml
```
