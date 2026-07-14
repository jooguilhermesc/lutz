# Configurações

O modal de **Configurações** é acessado pelo ícone ⚙ no canto superior direito da interface. Ele permite ajustar provedores de LLM e embedding, chaves de API, URL base e idioma — tudo salvo no `.env` do projeto.

![Modal de Configurações](/screenshots/configuracoes.png)

---

## Abas do modal

O modal tem três abas:

| Aba | Conteúdo |
|---|---|
| **LLM & Embedding** | Provider, modelo, temperatura, tokens máximos, URL base |
| **Chaves de API** | OpenAI/OpenRouter API Key, Anthropic API Key |
| **Idioma** | Idioma da interface |

---

## Aba LLM & Embedding

| Campo | Descrição |
|---|---|
| **LLM PROVIDER** | `OpenAI / OpenRouter`, `Anthropic` ou `Docker Model Runner` |
| **LLM MODEL** | Nome do modelo (ex: `google/gemini-3.1-flash-lite`, `claude-sonnet-4-6`) |
| **TEMPERATURE** | Variação da resposta (padrão: `0.2`) |
| **MAX OUTPUT TOKENS** | Limite de tokens na resposta (padrão: `2048`) |
| **EMBEDDING PROVIDER** | `OpenAI`, `sentence_transformers` ou `Docker Model Runner` |
| **EMBEDDING MODEL** | Nome do modelo (ex: `openai/text-embedding-3-small`) |
| **OPENAI BASE URL** | URL para APIs compatíveis (ex: `https://openrouter.ai/api/v1`) |
| **DOCKER MODEL HOST** | Endereço do Docker Model Runner (ex: `http://localhost:11434`) |

---

## Configuração recomendada — OpenRouter + OpenAI embeddings

| Campo | Valor |
|---|---|
| **LLM PROVIDER** | `OpenAI / OpenRouter` |
| **LLM MODEL** | `google/gemini-3.1-flash-lite` |
| **EMBEDDING PROVIDER** | `OpenAI` |
| **EMBEDDING MODEL** | `openai/text-embedding-3-small` |
| **OPENAI BASE URL** | `https://openrouter.ai/api/v1` |

---

## Segurança

::: warning
As credenciais são armazenadas **exclusivamente** no `.env` do projeto e nunca exibidas em texto plano. O `.env` está no `.gitignore` e não é commitado ao repositório.
:::

---

## Quando as configurações entram em vigor?

Imediatamente após clicar em **Salvar configurações** — sem necessidade de reiniciar o servidor.
