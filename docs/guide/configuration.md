# Configuração do ambiente

Todas as configurações de modelo e API vivem no arquivo `.env` dentro do seu projeto Lutz. O arquivo é criado a partir do `.env.example` gerado pelo `lutz init`.

```bash
cp .env.example .env
```

---

## Variáveis disponíveis

| Variável | Descrição | Padrão |
|---|---|---|
| `EMBEDDING_PROVIDER` | Provedor de embeddings: `docker_model_runner`, `openai`, `sentence_transformers` | — |
| `EMBEDDING_MODEL` | Nome do modelo de embeddings | — |
| `LLM_PROVIDER` | Provedor de LLM: `docker_model_runner`, `openai`, `anthropic` | — |
| `LLM_MODEL` | Nome do modelo usado nas análises | — |
| `OPENAI_API_KEY` | Chave da OpenAI ou serviço compatível | — |
| `OPENAI_BASE_URL` | URL alternativa para APIs OpenAI-compatíveis | API OpenAI padrão |
| `ANTHROPIC_API_KEY` | Chave da Anthropic | — |
| `DOCKER_MODEL_HOST` | Endereço do Docker Model Runner local | — |
| `DOCKER_MODEL_API_KEY` | Chave do client OpenAI-compatível do Docker Model Runner | — |
| `LLM_MAX_TOKENS` | Tamanho máximo da resposta do LLM | `4096` |
| `LLM_TEMPERATURE` | Variação da resposta | `0.2` |
| `HUGGINGFACE_TOKEN` | Token opcional para modelos restritos via `sentence_transformers` | — |

---

## Provedores suportados

### Docker Model Runner (local, sem API key)

Opção recomendada para uso offline. Requer Docker Desktop com Model Runner habilitado.

```bash
docker model pull nomic-embed-text
docker model pull ai/llama3.2
```

```dotenv
EMBEDDING_PROVIDER=docker_model_runner
EMBEDDING_MODEL=nomic-embed-text

LLM_PROVIDER=docker_model_runner
LLM_MODEL=ai/llama3.2

DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
```

### Ollama

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2
```

### OpenAI

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

### OpenRouter

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-...
LLM_MODEL=google/gemma-3-12b-it:free
```

### Anthropic

```dotenv
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001
```

---

## Configuração pela interface web

A página **Configurações** da interface web permite alterar todas essas variáveis sem editar o arquivo `.env` diretamente. As chaves de API são mascaradas e nunca exibidas em texto plano.

Veja [Configurações](/guide/interface/configuracoes) para detalhes.

---

## Segurança das credenciais

- O arquivo `.env` é adicionado ao `.gitignore` pelo `lutz init` e nunca é commitado.
- O banco vetorial (`.lutz/vector_store/`) também é gitignored.
- As chaves só são carregadas em memória durante a execução dos comandos.
