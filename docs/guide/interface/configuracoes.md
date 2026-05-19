# Configurações

A página de Configurações permite ajustar provedores de LLM e embedding, chaves de API e URLs customizadas — tudo salvo diretamente no `.env` do projeto sem precisar abrir um editor de texto.

![Página de Configurações](/screenshots/configuracoes.png)

---

## Campos do formulário

### Provedor de LLM

| Campo | Descrição |
|---|---|
| **LLM_PROVIDER** | `openai`, `anthropic` ou `docker_model_runner` |
| **LLM_MODEL** | Nome do modelo (ex: `gpt-4o-mini`, `claude-haiku-4-5-20251001`) |

### Provedor de Embeddings

| Campo | Descrição |
|---|---|
| **EMBEDDING_PROVIDER** | `openai`, `sentence_transformers` ou `docker_model_runner` |
| **EMBEDDING_MODEL** | Nome do modelo (ex: `text-embedding-3-small`, `all-MiniLM-L6-v2`) |

### Chaves de API

As chaves são inseridas em campos mascarados (tipo password). Deixe em branco para **manter o valor atual** sem alteração — útil quando você quer mudar apenas o modelo sem reexpor a chave.

| Campo | Quando usar |
|---|---|
| **OPENAI_API_KEY** | OpenAI, OpenRouter, Ollama e outros compatíveis |
| **ANTHROPIC_API_KEY** | Anthropic Claude |

### Configurações avançadas

| Campo | Descrição |
|---|---|
| **OPENAI_BASE_URL** | URL base para APIs compatíveis com OpenAI (ex: `https://openrouter.ai/api/v1`, `http://localhost:11434/v1`) |

---

## Segurança

::: warning
As credenciais são armazenadas **exclusivamente** no arquivo `.env` do projeto e nunca são exibidas em texto plano na interface. O arquivo `.env` está no `.gitignore` e não é commitado ao repositório.
:::

---

## Configuração atual

Abaixo do formulário, uma tabela exibe os valores atuais de todas as variáveis do `.env`. Chaves sensíveis (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) aparecem mascaradas como `••••••••••••`.

---

## Quando as novas configurações são aplicadas?

As novas configurações entram em vigor na **próxima** execução de análise ou vetorização. Não é necessário reiniciar o servidor.
