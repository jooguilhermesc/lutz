# Configurações

A página de Configurações permite ajustar provedores de LLM e embedding, chaves de API e URLs customizadas — tudo salvo diretamente no `.env` do projeto sem precisar abrir um editor de texto.

![Página de Configurações](/screenshots/configuracoes.png)

---

## Campos do formulário

### Provedor de LLM

| Campo | Descrição |
|---|---|
| **LLM PROVIDER** | `OpenAI / OpenRouter`, `Anthropic` ou `Docker Model Runner` |
| **LLM MODEL** | Nome do modelo (ex: `google/gemini-flash-1.5-8b`, `gpt-4o-mini`) |
| **TEMPERATURE** | Variação da resposta (padrão: `0.2`) |
| **MAX OUTPUT TOKENS** | Limite de tokens na resposta (padrão: `4096`) |

### Provedor de Embeddings

| Campo | Descrição |
|---|---|
| **EMBEDDING PROVIDER** | `OpenAI`, `sentence_transformers` ou `Docker Model Runner` |
| **EMBEDDING MODEL** | Nome do modelo (ex: `openai/text-embedding-3-small`, `all-MiniLM-L6-v2`) |

### Chaves de API

As chaves são inseridas em campos mascarados (tipo password). Deixe em branco para **manter o valor atual** sem alteração — útil quando você quer mudar apenas o modelo sem reexpor a chave.

| Campo | Quando usar |
|---|---|
| **OPENAI / OPENROUTER API KEY** | OpenAI, OpenRouter, Ollama e outros compatíveis |
| **ANTHROPIC API KEY** | Anthropic Claude |

### Configurações avançadas

| Campo | Descrição |
|---|---|
| **OPENAI BASE URL** | URL base para APIs compatíveis com OpenAI. Exemplos: `https://openrouter.ai/api/v1` (OpenRouter), `http://localhost:11434/v1` (Ollama) |
| **DOCKER MODEL HOST** | Endereço do Docker Model Runner (padrão: `http://localhost:11434`) |

---

## Exemplo: OpenRouter com Gemini e embeddings OpenAI

Esta é a configuração usada no exemplo desta documentação:

| Campo | Valor |
|---|---|
| **LLM PROVIDER** | `OpenAI / OpenRouter` |
| **LLM MODEL** | `google/gemini-flash-1.5-8b` |
| **EMBEDDING PROVIDER** | `OpenAI` |
| **EMBEDDING MODEL** | `openai/text-embedding-3-small` |
| **OPENAI BASE URL** | `https://openrouter.ai/api/v1` |
| **OPENAI API KEY** | `sk-or-...` (sua chave do OpenRouter) |

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
