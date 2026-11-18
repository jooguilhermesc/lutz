# Configuração

A configuração de um projeto fica em dois arquivos na raiz:

| Arquivo | Guarda | Versionar? | Quem edita |
|---|---|---|---|
| `.env` | Chaves de API e URLs de provedor | Nunca | Modal de Configurações da web, `lutz config set/unset`, ou um editor |
| `lutz.yaml` | Modelos por papel, limiares, orçamento, sementes, concorrência, idiomas do relatório | Sim | Um editor de texto (a web mostra somente leitura) |

## `.env` (mecanismo mantido da 0.5)

Chaves aceitas: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `OPENROUTER_BASE_URL`, `DOCKER_MODEL_HOST`.

* **Precedência:** valor exportado no terminal > `.env` > padrão. Quando uma chave do `.env` é sombreada pelo terminal, a web e `lutz config show` avisam.
* **Gravar e apagar:** `lutz config set OPENAI_API_KEY sk-...`, `lutz config unset OPENAI_API_KEY`; na web, `PUT /api/v1/config` com `{"CHAVE": "valor"}` ou `{"CHAVE": null}`. Outras chaves são recusadas.
* **Origem:** cada valor é mostrado como `processo`, `.env`, `padrao` ou `ausente`; segredos aparecem mascarados.

## `lutz.yaml`

```yaml
versao: 1
modelos:
  E1: {provedor: anthropic, modelo: claude-opus-5-5}
  E2: {provedor: openai, modelo: gpt-4.1-mini, temperatura: 0}
  E3: {provedor: openrouter, modelo: google/gemini-2.5-flash, temperatura: 0}
  V:  {provedor: anthropic, modelo: claude-sonnet-5-5}
  # J: juiz para o Assistente e o lint semântico (opcional)
custo: {orcamento_usd: 20, confirmar: true}
sementes: {piloto: 42, bootstrap: 42, auditoria: 42}
concorrencia: {por_provedor: 4, tentativas: 5, timeout_s: 180}
contexto: {fracao_janela: 0.7, janela_tokens_padrao: 128000}
auditoria: {meia_largura_alvo: 0.06, p_esperado: 0.95}
relatorio: {idiomas: [pt, en], formatos: [md, pdf], autoria: a equipe de pesquisa}
metricas: {bootstrap_repeticoes: 2000}
limiares: {}          # ver docs/spec-1.0.md §4.1
precos:               # USD por milhão de tokens; complementa lutz/data/precos.yaml
  gpt-4.1-mini: {entrada: 0.4, saida: 1.6}
```

### Papéis

| Papel | Obrigatório | Função |
|---|---|---|
| `E1`, `E2`, `E3` | sim | Extratores independentes |
| `V` | não | Verificador do trecho vencedor e busca de ausência. Sem ele, v = 1 é declarado e o relatório registra a limitação |
| `J` | não | Assistente de Codebook e lint semântico (senão usa V, senão E1) |

Campos de cada papel: `provedor` (`anthropic`, `openai`, `openrouter`, `docker_model_runner`, `fake`), `modelo`, `temperatura` (ignorada pela Anthropic: os modelos atuais não aceitam parâmetros de amostragem), `max_tokens`, `variante_prompt` (`padrao`, `reescrita_a`, `reescrita_b`), `janela_tokens` (janela de contexto do modelo), `esforco` (Anthropic: `low` a `max`), `base_url`.

### Diversidade

Derivada automaticamente e impressa no relatório:

* `fornecedores_diferentes` — três fornecedores e três modelos (a mais forte);
* `modelos_diferentes` — modelos distintos, alguns do mesmo fornecedor;
* `instrucoes_reescritas` — mesmo modelo com as três variantes de prompt (vira limitação no relatório);
* `nenhuma` — mesmo modelo e mesma instrução (aviso no `lutz doctor`).

### Modelos locais (Docker Model Runner)

```yaml
modelos:
  E1: {provedor: docker_model_runner, modelo: ai/qwen2.5:3B-Q4_K_M, variante_prompt: padrao, janela_tokens: 32768}
  E2: {provedor: docker_model_runner, modelo: ai/qwen2.5:3B-Q4_K_M, variante_prompt: reescrita_a, janela_tokens: 32768}
  E3: {provedor: docker_model_runner, modelo: ai/qwen2.5:3B-Q4_K_M, variante_prompt: reescrita_b, janela_tokens: 32768}
concorrencia: {por_provedor: 1}
```

Sem chave e sem custo. Para modelos locais o Lutz pede saída com `json_schema` (gramática do llama.cpp), com listas e textos limitados. Uma GPU pequena costuma carregar um modelo por vez: nesse caso use o mesmo modelo com variantes de prompt, ou carregue modelos diferentes com `docker model configure --keep-alive`.

### Preços

`lutz/data/precos.yaml` traz os preços de primeira parte da Anthropic. Modelos de outros fornecedores precisam de `precos` no `lutz.yaml`; sem preço, o custo aparece como desconhecido (nunca 0) e a estimativa avisa. Modelos do Docker Model Runner custam 0.

### Orçamento

`custo.orcamento_usd` vale para o projeto inteiro. É verificado antes de cada chamada; ao atingir, a execução pausa e pode ser retomada (`lutz extract --retomar ID`) depois de aumentar o valor. Uma execução retomada usa a configuração registrada nela, não o `lutz.yaml` atual.

## Verificação

```
lutz doctor            # configuração, chaves, preços, banco, interface web
lutz doctor --chamar   # também faz uma chamada mínima a cada papel e mostra o modelo observado
lutz config show       # .env com origem e resumo do lutz.yaml
```
