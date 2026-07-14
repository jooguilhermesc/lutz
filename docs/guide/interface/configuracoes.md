# Configurações

O modal de **Configurações** permite ajustar o provedor de modelos, as chaves de API e o idioma dos relatórios — tudo salvo no `.env` do projeto sem precisar abrir um editor de texto.

Acesse pelo ícone de engrenagem (⚙) na barra superior.

![Modal de Configurações](/screenshots/configuracoes.png)

---

## Seções

O modal tem três abas internas:

### LLM & Embedding

| Campo | Descrição |
|---|---|
| **Model Provider** | `Anthropic`, `OpenAI`, `OpenRouter` ou `Docker Model Runner` |
| **LLM Model** | Modelo usado para raciocinar e redigir a análise |
| **Embedding Model** | Modelo usado para vetorizar os artigos (busca semântica) |
| **Temperature** | Variação da resposta (padrão: `0.2`) |
| **Max Output Tokens** | Limite de tokens na resposta (padrão: `4096`) |
| **OpenAI Base URL** | URL base para APIs compatíveis com OpenAI (Ollama, etc.) |
| **Docker Model Host** | Endereço do Docker Model Runner |

#### LLM Model vs. Embedding Model

**LLM Model** é o modelo de linguagem que lê os chunks relevantes e escreve a análise de cada artigo — ele precisa ser bom em raciocínio e seguir instruções. Modelos maiores custam mais, mas produzem análises mais precisas.

**Embedding Model** converte cada trecho de texto num vetor numérico para que o Lutz encontre os trechos mais relevantes antes de chamar o LLM. Não há "análise" aqui — é uma operação matemática de similaridade.

::: tip Para iniciantes
Mantenha `text-embedding-3-small` (OpenAI) como modelo de embedding. Ele é rápido, barato e funciona bem com qualquer provedor LLM. Troque apenas se já usar Sentence Transformers local ou Docker Model Runner para embedding.
:::

### Chaves de API

Campos mascarados (tipo password). Deixe em branco para **manter o valor atual** — útil ao mudar apenas o modelo sem reexpor a chave.

| Campo | Quando usar |
|---|---|
| **OpenAI API Key** | OpenAI e endpoints compatíveis (Ollama, etc.) |
| **Anthropic API Key** | Claude (Anthropic) |
| **OpenRouter API Key** | OpenRouter (multi-provedor) |

### Idioma

Controla o idioma da UI e o idioma em que os relatórios são gerados pelo LLM.

---

## Seleção de modelos na barra lateral

Além do modal de Configurações, você pode trocar o **Modelo LLM** e o **Modelo Embedding** diretamente na barra lateral esquerda, clicando nos respectivos dropdowns. A escolha é salva automaticamente no `.env`.

---

## Exemplo: OpenRouter com Gemini Flash

| Campo | Valor |
|---|---|
| Model Provider | `OpenRouter` |
| LLM Model | `google/gemini-flash-1.5` |
| Embedding Model | `text-embedding-3-small` (via OpenAI) |
| OpenRouter API Key | `sk-or-...` |

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
