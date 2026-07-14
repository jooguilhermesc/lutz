# Configurações

O modal de **Configurações** permite ajustar provedores de LLM e embedding, chaves de API e idioma dos relatórios — tudo salvo no `.env` do projeto sem precisar abrir um editor de texto.

Acesse pelo ícone de engrenagem (⚙) na barra superior.

![Modal de Configurações](/screenshots/configuracoes.png)

---

## Seções

O modal tem três abas internas:

### LLM & Embedding

| Campo | Descrição |
|---|---|
| **LLM Provider** | `OpenAI / OpenRouter`, `Anthropic` ou `Docker Model Runner` |
| **LLM Model** | Nome do modelo (ex: `claude-sonnet-4-6`, `gpt-4o-mini`) |
| **Embedding Provider** | `OpenAI`, `sentence_transformers` ou `Docker Model Runner` |
| **Embedding Model** | Nome do modelo (ex: `text-embedding-3-small`, `all-MiniLM-L6-v2`) |
| **Temperature** | Variação da resposta (padrão: `0.2`) |
| **Max Output Tokens** | Limite de tokens na resposta (padrão: `4096`) |
| **OpenAI Base URL** | URL base para APIs compatíveis com OpenAI (OpenRouter, Ollama, etc.) |
| **Docker Model Host** | Endereço do Docker Model Runner |

### Chaves de API

Campos mascarados (tipo password). Deixe em branco para **manter o valor atual** — útil ao mudar apenas o modelo sem reexpor a chave.

| Campo | Quando usar |
|---|---|
| **OpenAI / OpenRouter API Key** | OpenAI, OpenRouter, Ollama e compatíveis |
| **Anthropic API Key** | Claude (Anthropic) |

### Idioma

Controla o idioma da UI e o idioma em que os relatórios são gerados pelo LLM.

---

## Exemplo: OpenRouter com Gemini

| Campo | Valor |
|---|---|
| LLM Provider | `OpenAI / OpenRouter` |
| LLM Model | `google/gemini-flash-1.5-8b` |
| OpenAI Base URL | `https://openrouter.ai/api/v1` |
| OpenAI API Key | `sk-or-...` |

---

## Segurança

::: warning
As credenciais são armazenadas exclusivamente no `.env` do projeto e nunca exibidas em texto plano. O `.env` está no `.gitignore` e não é commitado.
:::

As novas configurações entram em vigor na **próxima** execução — não é necessário reiniciar o servidor.

---

## Alternativa: editar o `.env` diretamente

```bash
# .env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
```
