# Lutz Agent — User Stories & Architecture

> **Status:** Proposta | **Versão:** 1.0 | **Data:** 2026-05-23
>
> Documento de requisitos para a camada agentiva do Lutz, com foco em autonomia do pesquisador,
> roteamento inteligente de modelos baseado em Mixture-of-Experts (MoE) e economia de tokens.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [User stories](#2-user-stories)
3. [Estratégia MoE — Roteamento inteligente de modelos](#3-estratégia-moe--roteamento-inteligente-de-modelos)
4. [Arquitetura do agente](#4-arquitetura-do-agente)
5. [Modelo de dados — configuração .env](#5-modelo-de-dados--configuração-env)
6. [Plano de implementação](#6-plano-de-implementação)
7. [Métricas de sucesso](#7-métricas-de-sucesso)

---

## 1. Visão geral

### Problema atual

O pipeline CLI do Lutz expõe **dezenas de parâmetros operacionais** que o pesquisador precisa dominar antes de qualquer análise:
`--top-k`, `--per-article`, `--workers`, `--max-chunks-per-article`, `--filter-sections`, `--language`,
`--output-name`, `--only-relevant`, `--reading-roadmap`, `--user-instructions`, `--multiple`.

Cada escolha desses parâmetros **pode enviesar** os resultados da revisão sistemática. Um pesquisador que escolhe
`--top-k 5` obtém uma análise fundamentalmente diferente de outro que usa `--top-k 50`.

Além disso, o fluxo de trabalho é fragmentado: o pesquisador executa `lutz analysis`, depois manualmente
`lutz citations`, depois opcionalmente `lutz citations --reading-roadmap` — cada etapa exige conhecimento
prévio de que o próximo comando existe e como encadeá-lo.

### Solução proposta

Uma **camada agentiva conversacional** que:

1. **Entende objetivos em linguagem natural** — o pesquisador descreve o que quer, não como fazer
2. **Planeja e executa pipelines multi-etapa** — decompõe objetivos em sequências de tool calls
3. **Seleciona o modelo ideal por tarefa** — roteamento MoE: tarefa simples → modelo barato; tarefa complexa → modelo potente
4. **Explica cada decisão** — transparência total sobre por que escolheu cada parâmetro
5. **Preserva o CLI como expert mode** — power users continuam com controle granular

---

## 2. User stories

### US-01: Conversa como interface primária

**Como** pesquisador acadêmico
**Quero** descrever meu objetivo de pesquisa em linguagem natural ("faça uma revisão sistemática sobre X")
**Para que** eu não precise aprender dezenas de flags de CLI antes de começar a trabalhar

**Definition of Ready:**
- [ ] LLM client suporta tool calling (function calling) com schema JSON
- [ ] Catálogo de tools mapeado para as funções internas de `analysis.py`, `citations.py`, `vector_store.py`, `query.py`
- [ ] Protótipo de UI conversacional validado (HTML/CSS/JS estático)
- [ ] `.env` com suporte a múltiplos perfis de modelo (ver seção 5)

**Critérios de aceitação:**
- [ ] O pesquisador digita um objetivo em texto livre e o agente responde com um plano de ação
- [ ] O agente faz perguntas de clarification quando o objetivo é ambíguo (ex: "você quer screening individual ou síntese aberta?")
- [ ] O agente NUNCA executa ações destrutivas sem confirmação explícita do usuário
- [ ] Todas as respostas do agente incluem o raciocínio por trás das decisões
- [ ] A conversa persiste entre sessões (SQLite, estrutura já existente em `lutz/server/db.py`)

**Definition of Done:**
- [ ] Cobertura de testes ≥ 80% para o módulo `lutz/agent/`
- [ ] Integração com `lutz web` — substitui `_run_chat()` atual por `_run_agentic_chat()`
- [ ] Endpoints novos: `POST /agent/chat`, `GET /agent/sessions`, `GET /agent/sessions/{id}/stream`
- [ ] Documentação no help do CLI: `lutz agent --help`
- [ ] Handoff YAML registrado em `.lutz/audit/` para cada sessão agentiva

---

### US-02: Planejamento multi-passo com ferramentas

**Como** pesquisador
**Quero** que o agente decomponha automaticamente meu objetivo ("revisão sistemática sobre IA na educação")
em passos executáveis e os execute em sequência
**Para que** eu não precise saber que `analysis` vem antes de `citations`, que `citations` depende do modo `per-article`, etc.

**Definition of Ready:**
- [ ] Tool Registry implementado com schemas JSON Schema para cada tool
- [ ] LLM com capacidade de function calling disponível (modelos OpenAI, Anthropic, ou OpenRouter com suporte a tools)
- [ ] Sistema de prompt de planejamento testado com pelo menos 3 objetivos de pesquisa distintos
- [ ] Métricas de sucesso definidas: % de planos corretos em primeira tentativa

**Critérios de aceitação:**
- [ ] Dado um objetivo de pesquisa, o agente produz um plano com 2-5 passos sequenciais
- [ ] Cada passo do plano mapeia para uma ou mais tool calls
- [ ] O agente detecta dependências entre passos (ex: `citations` só roda após `analysis --per-article`)
- [ ] O agente replaneja quando um passo falha (ex: vector store vazio → sugere `lutz vectorize`)
- [ ] O progresso do plano é visível em tempo real (painel lateral com indicador de passo atual)
- [ ] O pesquisador pode pausar, pular ou cancelar passos a qualquer momento

**Tools mínimas (v1):**

| Tool | Função interna | Descrição |
|------|---------------|-----------|
| `inspect_corpus` | `VectorStore.info()` + `section_breakdown()` | Retorna contagem de artigos, chunks, seções disponíveis |
| `search_corpus` | `VectorStore.search()` | Busca semântica no corpus (modo RAG exploratório) |
| `analyze_corpus` | `_run_per_article()` ou `_run_rag()` | Executa análise com prompt, modo e parâmetros |
| `extract_citations` | `_run_citations_for_experiment()` | Extrai citações de relatório per-article |
| `generate_roadmap` | `_rank_articles_by_centrality()` + LLM | Gera roadmap de leitura |
| `query_analytics` | `lutz query` (DuckDB) | Consultas analíticas no vector store |
| `get_article_chunks` | `VectorStore.get_by_filename()` | Retorna chunks de um artigo específico |
| `get_section_breakdown` | `VectorStore.section_breakdown()` | Breakdown de seções por artigo |

**Definition of Done:**
- [ ] 8 tools implementadas com schema JSON e tratamento de erro
- [ ] Testes de integração: 3 cenários completos de revisão sistemática simulados
- [ ] Cada tool registra uso no audit log (`lutz/core/audit.py`)
- [ ] Timeout configurável por tool (default 300s para análise, 60s para busca)
- [ ] Retry automático (até 2x) em erros transientes (rate-limit, timeout de rede)

---

### US-03: Roteamento inteligente de modelos (MoE-aware)

**Como** pesquisador
**Quero** que o agente escolha automaticamente o melhor modelo para cada tarefa, usando modelos MoE (Mixture-of-Experts) quando apropriado e modelos mais simples para tarefas triviais
**Para que** eu economize tokens e dinheiro sem sacrificar a qualidade da análise

**Definition of Ready:**
- [ ] Catálogo de modelos mapeado com atributos: arquitetura, custo por 1M tokens, capacidades, limites
- [ ] Heurísticas de classificação de tarefas definidas (ver seção 3)
- [ ] Provider OpenRouter configurável (já suportado via `OPENAI_BASE_URL`)
- [ ] Testes de custo com pelo menos 3 modelos diferentes

**Critérios de aceitação:**
- [ ] O agente classifica cada tool call em um tier de complexidade (L0-L3) ANTES de executar
- [ ] Cada tier mapeia para um perfil de modelo específico (configurável no `.env`)
- [ ] O modelo usado é visível no painel de detalhes durante a execução
- [ ] O sistema NUNCA usa um modelo mais caro quando um mais barato é suficiente
- [ ] O pesquisador pode sobrescrever a escolha do agente por mensagem ("use o Claude para esta análise")
- [ ] Fallback automático: se o modelo primário falhar (rate-limit, timeout), tenta o secundário do mesmo tier
- [ ] Relatório de economia: ao final da sessão, mostra tokens economizados vs. usar sempre o modelo mais caro

**Modelos MoE prioritários (catálogo inicial):**

| Modelo | Arquitetura | Tier recomendado | Custo input/1M tok | Custo output/1M tok | Provider |
|--------|------------|------------------|---------------------|----------------------|----------|
| DeepSeek-V3 | MoE (671B total, 37B ativos) | L2, L3 | $0.27 | $1.10 | OpenRouter |
| DeepSeek-R1 | MoE + reasoning | L3 | $0.55 | $2.19 | OpenRouter |
| Mixtral 8x22B | MoE (141B total, 39B ativos) | L2, L3 | $0.90 | $0.90 | OpenRouter |
| Qwen2.5-32B | Dense (32B) | L1, L2 | $0.18 | $0.18 | OpenRouter |
| GPT-4o-mini | Dense (proprietário) | L0, L1 | $0.15 | $0.60 | OpenAI |
| Claude Haiku 3.5 | Dense (proprietário) | L0, L1 | $0.80 | $4.00 | Anthropic |
| Claude Sonnet 4 | Dense (proprietário) | L2, L3 | $3.00 | $15.00 | Anthropic |

**Definition of Done:**
- [ ] Sistema de roteamento implementado em `lutz/agent/model_router.py`
- [ ] Testes unitários para cada regra de classificação de tier
- [ ] Teste de integração: 1 sessão completa com pelo menos 2 modelos diferentes usados
- [ ] Documentação: tabela de tiers no `lutz agent --help`
- [ ] Economia de tokens mensurável: target ≥ 40% vs. usar modelo premium para tudo

---

### US-04: O agente entende cada modelo e adapta sua estratégia

**Como** sistema
**Quero** que o agente conheça as capacidades, limitações e melhores práticas de cada modelo disponível
**Para que** ele adapte prompts, tamanhos de contexto e níveis de raciocínio automaticamente

**Definition of Ready:**
- [ ] Perfis de modelo definidos com campos: `context_window`, `max_output_tokens`, `supports_tool_calling`, `supports_thinking`, `supports_json_mode`, `recommended_temperature`, `known_weaknesses`
- [ ] Função `get_model_profile(model_id)` retorna perfil completo
- [ ] Testes de prompt adaptation para pelo menos 3 modelos com context windows diferentes

**Critérios de aceitação:**
- [ ] O agente ajusta `max_chunks_per_article` automaticamente com base no context window do modelo
- [ ] Para modelos sem suporte nativo a tool calling, o agente usa prompt-based tool simulation (parse de JSON na resposta)
- [ ] Para modelos com thinking blocks (Anthropic), o agente ativa raciocínio estendido em tarefas L3
- [ ] Para modelos MoE como DeepSeek, o agente sabe que o contexto efetivo é maior que modelos dense equivalentes e ajusta `top_k` para cima
- [ ] O agente avisa proativamente quando um modelo é inadequado para a tarefa ("este modelo tem context window de 8K, mas a análise estima 15K tokens — recomendo trocar para X")
- [ ] Temperatura ajustada por tarefa: 0.0 para classificação (INCLUDE/EXCLUDE), 0.3 para síntese, 0.5 para brainstorming

**Perfis de modelo (exemplo):**

```yaml
deepseek-v3:
  context_window: 131072
  max_output_tokens: 8192
  supports_tool_calling: true
  supports_json_mode: true
  architecture: moe
  active_params: 37B
  strengths: [reasoning, code, structured_output]
  weaknesses: [creative_writing]
  recommended_temperature:
    classification: 0.0
    synthesis: 0.3
    planning: 0.2

mixtral-8x22b:
  context_window: 65536
  max_output_tokens: 4096
  supports_tool_calling: false  # requer prompt-based simulation
  supports_json_mode: false
  architecture: moe
  active_params: 39B
  strengths: [multilingual, instruction_following]
  weaknesses: [very_long_contexts, strict_json]
  recommended_temperature:
    classification: 0.1
    synthesis: 0.3
    planning: 0.2

gpt-4o-mini:
  context_window: 131072
  max_output_tokens: 16384
  supports_tool_calling: true
  supports_json_mode: true
  architecture: dense
  strengths: [speed, cost, tool_calling]
  weaknesses: [deep_reasoning, academic_rigor]
```

**Definition of Done:**
- [ ] 6+ perfis de modelo implementados em `lutz/agent/model_profiles.yaml`
- [ ] Prompt adaptation testado: mesmo objetivo executado com DeepSeek-V3 e GPT-4o-mini, ambos produzem resultados válidos
- [ ] Context window overflow prevention: agente NUNCA envia prompt que exceda o context window do modelo
- [ ] Documentação de cada perfil acessível via `lutz agent --model-info deepseek-v3`

---

### US-05: O pesquisador mantém controle — sem viés de parâmetros

**Como** pesquisador
**Quero** que o agente tome decisões operacionais por mim, mas me permita intervir quando eu tiver conhecimento de domínio específico
**Para que** eu não perca o controle da pesquisa, mas também não seja sobrecarregado com decisões que o agente pode tomar melhor

**Definition of Ready:**
- [ ] UI de confirmação implementada no protótipo (validada com UX review)
- [ ] Sistema de "ajuste de parâmetros" por linguagem natural ("filtra só abstract e methodology")
- [ ] CLI commands mantidos como estão (compatibilidade reversa total)

**Critérios de aceitação:**
- [ ] Antes de executar análise, o agente mostra um plano e pede confirmação
- [ ] O pesquisador pode responder com ajustes em linguagem natural ("sim, mas com 8 workers e filtrando só methodology")
- [ ] O pesquisador pode pular steps ("pula as citações, vai direto pro roadmap")
- [ ] O pesquisador pode voltar a um passo anterior ("refaça o screening com o prompt methodology.md")
- [ ] O pesquisador pode especificar um modelo específico por mensagem ("use deepseek-r1 para essa análise")
- [ ] Comandos CLI continuam 100% funcionais — o agente é aditivo, não substitutivo
- [ ] NUNCA executar ação sem confirmação quando o impacto é irreversível ou de alto custo (≥ 1000 chamadas LLM estimadas)
- [ ] O relatório final inclui todas as decisões tomadas pelo agente e suas justificativas (para reprodutibilidade)

**Definition of Done:**
- [ ] Todos os comandos CLI passam na suíte de testes existente sem modificações
- [ ] Teste E2E: 1 cenário completo via agente produz o mesmo resultado que via CLI com parâmetros equivalentes
- [ ] Aprovação de UX: 2 pesquisadores reais testam e aprovam o fluxo

---

### US-06: Memória cross-session e aprendizado

**Como** pesquisador
**Quero** que o agente lembre minhas preferências e decisões entre sessões
**Para que** eu não precise re-explicar meu contexto de pesquisa a cada nova conversa

**Definition of Ready:**
- [ ] Estrutura de `chat_memory` existente em `lutz/server/db.py` estendida com campos para preferências
- [ ] Modelo de perfil de pesquisador definido (campos: `preferred_language`, `preferred_models`, `research_domain`, `saved_prompts`)

**Critérios de aceitação:**
- [ ] O agente lembra o idioma preferido entre sessões
- [ ] O agente lembra o domínio de pesquisa e usa para contextualizar novas consultas
- [ ] O agente sugere prompts salvos de sessões anteriores ("quer usar o mesmo prompt de screening da sessão passada?")
- [ ] O agente aprende com erros: se uma estratégia falhou (ex: context window overflow), não a repete
- [ ] O pesquisador pode limpar a memória a qualquer momento (`lutz agent --clear-memory`)

**Definition of Done:**
- [ ] Migração de schema do SQLite sem breaking changes
- [ ] Testes de persistência: memória sobrevive a restart do servidor
- [ ] Auditoria: toda memória extraída é registrada no audit log

---

## 3. Estratégia MoE — Roteamento inteligente de modelos

### Princípio fundamental

> **Cada tool call é roteada para o modelo mais barato capaz de executá-la com qualidade aceitável.**

Modelos MoE como DeepSeek-V3 e Mixtral oferecem qualidade comparável a modelos dense 5-10x mais caros
porque ativam apenas uma fração dos parâmetros por token (37B de 671B no DeepSeek-V3).
Isso significa que podemos usar MoE para tarefas complexas com custo de modelo simples.

### Tiers de complexidade

| Tier | Complexidade | Exemplos de tarefa | Modelo recomendado | Custo estimado/1M tok |
|------|-------------|-------------------|-------------------|----------------------|
| **L0** | Trivial | Classificação de intenção, parsing de linguagem natural, sumarização de mensagem curta | GPT-4o-mini | ~$0.20 |
| **L1** | Simples | Geração de query de busca, formatação de output, extração de entidades, resposta a perguntas factuais | GPT-4o-mini ou DeepSeek-V3 | ~$0.20-0.50 |
| **L2** | Moderada | Planejamento de tarefas, síntese de múltiplos artigos, extração de citações, análise de metodologia | DeepSeek-V3 ou Mixtral 8x22B | ~$0.50-1.00 |
| **L3** | Complexa | Revisão sistemática completa, reconciliação de contradições entre artigos, raciocínio multi-step profundo, geração de roadmap | DeepSeek-R1 ou Claude Sonnet 4 | ~$1.00-5.00 |

### Algoritmo de classificação de tier

```python
def classify_tier(tool_name: str, tool_input: dict, context_size: int) -> int:
    """Classifica uma tool call em L0-L3."""
    # L0: operações determinísticas, sem LLM
    if tool_name in ("inspect_corpus", "get_section_breakdown", "get_article_chunks"):
        return 0  # sem LLM, usa cliente direto

    # L1: buscas e consultas simples
    if tool_name in ("search_corpus", "query_analytics"):
        return 1

    # L2 vs L3 para análise: depende do número de artigos e presença de critério
    if tool_name == "analyze_corpus":
        article_count = tool_input.get("article_count", 0)
        has_relevance_criterion = tool_input.get("has_relevance_criterion", False)
        
        if article_count > 30 or has_relevance_criterion:
            return 3  # screening grande ou com critério → modelo forte
        return 2

    # L2 vs L3 para citações
    if tool_name == "extract_citations":
        article_count = tool_input.get("article_count", 0)
        return 3 if article_count > 15 else 2

    # Roadmap sempre L3 (requer síntese de alto nível)
    if tool_name == "generate_roadmap":
        return 3

    return 1
```

### Economia projetada

Cenário: revisão sistemática de 52 artigos com screening + citações + roadmap.

| Estratégia | Modelo único | Tokens estimados | Custo estimado |
|-----------|-------------|-----------------|---------------|
| Sem roteamento | Claude Sonnet 4 para tudo | 850K | ~$8.50 |
| Sem roteamento | GPT-4o para tudo | 850K | ~$4.25 |
| **Com roteamento MoE** | **Mix L0-L3** | **850K** | **~$1.80** |
| Economia vs. Claude | — | — | **79%** |
| Economia vs. GPT-4o | — | — | **58%** |

### Política de fallback

```
Tentativa 1: modelo primário do tier
    ↓ falha (rate-limit, timeout)
Tentativa 2: modelo secundário do mesmo tier
    ↓ falha
Tentativa 3: modelo do tier inferior (degradação controlada, com aviso ao usuário)
    ↓ falha
Escalar para o pesquisador com diagnóstico do erro
```

---

## 4. Arquitetura do agente

### Visão estrutural

```
┌──────────────────────────────────────────────────────────┐
│  Interface (CLI `lutz agent` ou web `lutz web`)           │
│  Conversação em linguagem natural + painéis de progresso  │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  lutz/agent/orchestrator.py                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ GoalManager  │ │ TaskPlanner  │ │ ExecutionEngine  │  │
│  │              │ │              │ │                  │  │
│  │ Extrai       │ │ Decompõe     │ │ Executa tools    │  │
│  │ objetivos    │ │ em passos    │ │ em sequência     │  │
│  │ da conversa  │ │ com tools    │ │ com retry/fallbk │  │
│  └──────────────┘ └──────────────┘ └──────┬───────────┘  │
└───────────────────────────────────────────┼──────────────┘
                                            │
┌───────────────────────────────────────────▼──────────────┐
│  lutz/agent/model_router.py                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ Tier         │ │ Model        │ │ Prompt           │  │
│  │ Classifier   │ │ Selector     │ │ Adapter          │  │
│  │              │ │              │ │                  │  │
│  │ L0-L3 por    │ │ Melhor       │ │ Ajusta tamanho   │  │
│  │ tool + input │ │ modelo/tier  │ │ temp, formato    │  │
│  └──────────────┘ └──────────────┘ └──────────────────┘  │
└──────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  lutz/agent/tools.py — Tool Registry                      │
│  ┌───────────┐ ┌──────────┐ ┌─────────┐ ┌────────────┐  │
│  │ inspect   │ │ analyze  │ │ extract │ │ generate   │  │
│  │ _corpus   │ │ _corpus  │ │ _citat. │ │ _roadmap   │  │
│  └───────────┘ └──────────┘ └─────────┘ └────────────┘  │
│  ┌───────────┐ ┌──────────┐ ┌────────────────────────┐   │
│  │ search    │ │ query    │ │ get_section_breakdown  │   │
│  │ _corpus   │ │ _analyt. │ │                        │   │
│  └───────────┘ └──────────┘ └────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  lutz/core/ (módulos existentes — sem alterações)         │
│  VectorStore | LLMClient | EmbeddingClient | ContextStore │
│  SecurityChecker | Audit | Extraction | SectionParser     │
└──────────────────────────────────────────────────────────┘
```

### Novos arquivos

```
lutz/agent/
├── __init__.py              # exports públicos
├── orchestrator.py          # GoalManager + TaskPlanner + ExecutionEngine
├── model_router.py          # TierClassifier + ModelSelector + PromptAdapter
├── tools.py                 # Tool definitions (JSON Schema + implementações)
├── model_profiles.yaml      # Catálogo de modelos com capacidades
├── prompts/
│   ├── planner_system.md    # System prompt do TaskPlanner
│   ├── goal_extractor.md    # System prompt do GoalManager
│   └── tier_classifier.md   # System prompt do TierClassifier
└── conversation.py          # Gerenciador de estado da conversa agentiva
```

### Estados da conversa agentiva

```
IDLE → GOAL_EXTRACTION → PLANNING → AWAITING_CONFIRMATION
                                         │
                                         ├─ CONFIRMED → EXECUTING → STEP_COMPLETE
                                         │       ↑                    │
                                         │       └── (próximo step) ──┘
                                         │
                                         ├─ ADJUSTING → PLANNING (replaneja)
                                         │
                                         └─ CANCELLED → IDLE
```

---

## 5. Modelo de dados — Configuração .env

### Novas variáveis de ambiente

```bash
# =============================================================================
# Lutz Agent — Configuração de modelos por tier
# =============================================================================

# Tier L0 (trivial: parsing, classificação de intenção)
AGENT_MODEL_L0_PROVIDER=openai
AGENT_MODEL_L0_MODEL=gpt-4o-mini

# Tier L1 (simples: busca, queries, extração)
AGENT_MODEL_L1_PROVIDER=openai
AGENT_MODEL_L1_MODEL=gpt-4o-mini

# Tier L2 (moderada: planejamento, síntese, citações)
# Recomendado: MoE model (DeepSeek-V3, Mixtral 8x22B)
AGENT_MODEL_L2_PROVIDER=openai
AGENT_MODEL_L2_MODEL=deepseek/deepseek-chat-v3
AGENT_MODEL_L2_BASE_URL=https://openrouter.ai/api/v1

# Tier L3 (complexa: revisão sistemática, roadmap, raciocínio profundo)
# Recomendado: MoE + reasoning (DeepSeek-R1) ou Claude Sonnet 4
AGENT_MODEL_L3_PROVIDER=openai
AGENT_MODEL_L3_MODEL=deepseek/deepseek-r1
AGENT_MODEL_L3_BASE_URL=https://openrouter.ai/api/v1

# Modelo de planejamento (sempre usado para TaskPlanner, independente das tools)
# Deve ser um modelo com excelente capacidade de reasoning estruturado
AGENT_PLANNER_PROVIDER=openai
AGENT_PLANNER_MODEL=deepseek/deepseek-chat-v3
AGENT_PLANNER_BASE_URL=https://openrouter.ai/api/v1

# Fallback: se true, quando um modelo falha tenta o próximo do mesmo tier
AGENT_FALLBACK_ENABLED=true

# Máximo de retries por tool call antes de escalar para o usuário
AGENT_MAX_RETRIES=2

# Timeout por tool call (segundos)
AGENT_TOOL_TIMEOUT=300

# Confirmação automática: se true, pula confirmação para ações de baixo risco
# (apenas inspect_corpus, search_corpus, get_section_breakdown, query_analytics)
AGENT_AUTO_CONFIRM_L0=true
```

### Schema SQLite estendido (aditivo ao `lutz/server/db.py`)

```sql
-- Tabela de preferências do pesquisador (nova)
CREATE TABLE IF NOT EXISTS researcher_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Extensão de chat_sessions (coluna nova)
ALTER TABLE chat_sessions ADD COLUMN agent_plan TEXT;  -- JSON do plano atual
ALTER TABLE chat_sessions ADD COLUMN agent_state TEXT;  -- IDLE|PLANNING|EXECUTING|...

-- Extensão de chat_messages (colunas novas)
ALTER TABLE chat_messages ADD COLUMN tool_calls TEXT;   -- JSON de tool calls
ALTER TABLE chat_messages ADD COLUMN model_used TEXT;   -- modelo que gerou a resposta
ALTER TABLE chat_messages ADD COLUMN tier TEXT;         -- L0|L1|L2|L3
ALTER TABLE chat_messages ADD COLUMN token_cost REAL;   -- custo estimado em USD
```

---

## 6. Plano de implementação

### Sprint 1 — Tool Registry (2 semanas)

**Objetivo:** Wraps das funções internas como tools tipadas.

- [ ] Criar `lutz/agent/__init__.py`
- [ ] Criar `lutz/agent/tools.py` com 8 tools + JSON Schema
- [ ] Criar `lutz/agent/model_profiles.yaml` com 6 perfis
- [ ] Testes unitários para cada tool (mock dos stores)
- [ ] `lutz agent --list-tools` para inspeção

**Modelo alvo:** GPT-4o-mini (L0), DeepSeek-V3 (L2, planejamento)

### Sprint 2 — Model Router (2 semanas)

**Objetivo:** Classificação de tiers e seleção automática de modelos.

- [ ] Criar `lutz/agent/model_router.py` (`TierClassifier`, `ModelSelector`, `PromptAdapter`)
- [ ] Criar `lutz/agent/prompts/tier_classifier.md`
- [ ] Testes unitários para classificação de tier
- [ ] Testes de integração: prompt adaptation para context windows diferentes
- [ ] Métricas de economia no log do agente

**Modelo alvo:** DeepSeek-V3 (roteamento + planning), GPT-4o-mini (L0-L1)

### Sprint 3 — Orquestrador (3 semanas)

**Objetivo:** Goal extraction, planning, execution engine.

- [ ] Criar `lutz/agent/orchestrator.py` (`GoalManager`, `TaskPlanner`, `ExecutionEngine`)
- [ ] Criar `lutz/agent/prompts/planner_system.md`
- [ ] Criar `lutz/agent/prompts/goal_extractor.md`
- [ ] Criar `lutz/agent/conversation.py` — máquina de estados
- [ ] Testes de integração: 5 cenários E2E com tool calls simuladas
- [ ] Integração com `lutz/core/audit.py`

**Modelo alvo:** DeepSeek-V3 (planner), GPT-4o-mini (goal extraction)

### Sprint 4 — CLI + Web (2 semanas)

**Objetivo:** Interface conversacional no terminal e na web.

- [ ] Comando `lutz agent` — sessão interativa no terminal com Rich
- [ ] Endpoints `POST /agent/chat`, `GET /agent/sessions/{id}/stream`
- [ ] Substituir `_run_chat()` por `_run_agentic_chat()` no `lutz/server/app.py`
- [ ] Frontend: integrar protótipo `agentic-chat-prototype.html` com endpoints reais
- [ ] Migração SQLite (aditiva, sem breaking changes)
- [ ] Testes E2E: 1 cenário completo via CLI, 1 via web

### Definição de pronto para cada sprint

- [ ] Todos os testes passam (`pytest --cov=lutz/agent --cov-report=term`)
- [ ] Cobertura ≥ 80% no novo código
- [ ] Zero findings CVSS ≥ 7.0 no Bandit
- [ ] Zero secrets hardcoded (detect-secrets)
- [ ] `pip-audit` limpo para novas dependências
- [ ] Handoff YAML registrado em `.lutz/audit/`

---

## 7. Métricas de sucesso

### Métricas de autonomia

| Métrica | Target | Como medir |
|---------|--------|-----------|
| % de sessões que completam sem intervenção manual | ≥ 70% | Log de tool calls vs. mensagens do usuário |
| Passos por sessão (média) | 3-6 | Log de execução do agente |
| Tempo até primeira análise (mediana) | < 2 min | Timestamp da primeira tool call - início da sessão |
| NPS (Net Promoter Score) em teste com pesquisadores | ≥ 40 | Survey pós-uso |

### Métricas de eficiência de tokens

| Métrica | Target | Como medir |
|---------|--------|-----------|
| Economia de tokens vs. baseline (modelo único premium) | ≥ 40% | Soma de tokens × custo/token por tier |
| % de tool calls roteadas corretamente (tier apropriado) | ≥ 90% | Auditoria manual de 100 tool calls |
| Redução de tokens por análise vs. CLI manual | ≥ 15% | Comparação A/B: mesma análise via CLI vs. agente |
| Fallbacks acionados (% de tool calls) | < 5% | Log de ModelRouter |

### Métricas de qualidade

| Métrica | Target | Como medir |
|---------|--------|-----------|
| Concordância INCLUDE/EXCLUDE agente vs. CLI equivalente | ≥ 95% | Mesmo prompt, mesmo corpus, modos equivalentes |
| Planos válidos (tool calls executáveis sem erro de parâmetro) | ≥ 85% | Primeira tentativa, sem replanejamento |
| Citações extraídas com page number válido | ≥ 90% | Validação cruzada com PDF source |

---

## Apêndice A — Ferramentas disponíveis em versões futuras (v2+)

Estas ferramentas estão fora do escopo da v1 mas são extensões naturais:

| Tool | Descrição | Complexidade |
|------|----------|-------------|
| `compare_articles` | Análise comparativa head-to-head entre 2 artigos | L2 |
| `suggest_prompts` | Sugere prompts de análise baseado no domínio de pesquisa | L1 |
| `detect_gaps` | Identifica lacunas na literatura do corpus | L3 |
| `export_bibtex` | Exporta lista de artigos incluídos em BibTeX | L0 |
| `summarize_article` | Resumo executivo de um artigo específico | L1 |
| `translate_analysis` | Traduz relatório de análise para outro idioma | L1 |
| `full_text_search` | Busca textual (Tantivy) no corpus, complementar à busca semântica | L0 |
| `cluster_corpus` | Agrupamento K-means dos artigos com visualização PCA | L2 |
| `prisma_diagram` | Gera diagrama PRISMA do fluxo de screening | L1 |
| `peer_review_sim` | Simula revisão por pares dos artigos incluídos | L3 |

---

## Apêndice B — Exemplo de interação completa

```
── Sessão iniciada (DeepSeek-V3 planner, GPT-4o-mini L0-L1) ──

[Pesquisador] Preciso fazer uma revisão sistemática sobre o uso de IA
              adaptativa em plataformas de ensino fundamental.
              Meu critério de inclusão: estudos empíricos com
              estudantes de 6 a 14 anos, publicados após 2020.

[Agente 🧠]   Entendi. Deixa eu primeiro inspecionar o corpus.
              [tool: inspect_corpus] → L0, sem LLM

[Agente 🧠]   Corpus: 52 artigos, 1.196 chunks. Seções incluem
              abstract, methodology, results, discussion.
              
              Montei um plano em 4 passos:
              
              1. Inspecionar corpus ✓ (concluído)
              2. Screening per-article com critério de inclusão
                 → 52 chamadas LLM, ~11 min com 4 workers
              3. Extrair citações dos artigos INCLUDE
                 → ~18 chamadas LLM, ~5 min
              4. Gerar roadmap de leitura
                 → 1 chamada LLM, ~30s
              
              Estratégia: per-article (necessário para decisões
              individuais), 4 workers (OpenAI detectado — I/O bound),
              seções: todas.
              
              Modelos: DeepSeek-V3 para screening (L3, 52 artigos
              com critério), GPT-4o-mini para extração de citações
              (L1, tarefa de extração estruturada).
              
              Posso começar?

[Pesquisador] Sim, mas quero usar DeepSeek-R1 para o screening —
              o raciocínio mais profundo vai ajudar com artigos
              borderline.

[Agente 🧠]   Perfeito. Ajustei: screening com DeepSeek-R1 (L3,
              reasoning mode). Isso vai aumentar o custo em ~40%
              mas a qualidade das decisões UNCERTAIN deve melhorar.
              Mantenho GPT-4o-mini para citações?
              
              [tool: analyze_corpus] → DeepSeek-R1, L3, per-article

── 11 minutos depois... ──

[Agente 🧠]   ✓ Screening concluído!
              INCLUDE: 18 | EXCLUDE: 27 | UNCERTAIN: 7
              
              [tool: extract_citations] → GPT-4o-mini, L1

── 5 minutos depois... ──

[Agente 🧠]   ✓ 54 citações extraídas dos 18 artigos incluídos.
              [tool: generate_roadmap] → DeepSeek-V3, L2

[Agente 🧠]   ✓ Pipeline completo!
              
              📊 Roadmap: 3 estágios (Fundamentos → Métodos → Avançados)
              📄 Relatórios salvos em analysis/execution_reports/
              💰 Custo total: ~$2.80 (economia de 62% vs. Claude-only)
              ⏱️  Tempo total: 16 minutos
              
              Quer que eu exporte o PRISMA ou gere um resumo executivo?

[Pesquisador] Exporta PRISMA e gera um resumo de 1 página em inglês.

[Agente 🧠]   [tool: prisma_diagram] → (L1, v2)
              [tool: summarize_analysis] → GPT-4o-mini (L1)
              
              Pronto! PRISMA salvo, resumo em reports/summary_en.md.
```

---

## Apêndice C — Handoff YAML (template para cada sessão agentiva)

```yaml
agent: lutz-agent
phase: agentic-conversation
started_at: "2026-05-23T14:30:00Z"
ended_at: "2026-05-23T14:46:00Z"
artifacts:
  - path: analysis/execution_reports/screening_20260523.json
    kind: analysis_report
  - path: analysis/execution_reports/citations_20260523.json
    kind: citations_report
  - path: analysis/execution_reports/roadmap_20260523.json
    kind: reading_roadmap
gate: null
gate_result: null
security_events: []
status: success
cost:
  input_tokens: 245000
  output_tokens: 89000
  estimated_usd: 2.80
model_usage:
  - model: deepseek/deepseek-r1
    tier: L3
    tool: analyze_corpus
    tokens: 210000
    cost_estimated: 1.65
  - model: openai/gpt-4o-mini
    tier: L1
    tool: extract_citations
    tokens: 98000
    cost_estimated: 0.35
  - model: deepseek/deepseek-chat-v3
    tier: L2
    tool: generate_roadmap
    tokens: 26000
    cost_estimated: 0.15
  - model: openai/gpt-4o-mini
    tier: L1
    tool: summarize_analysis
    tokens: 8000
    cost_estimated: 0.05
savings:
  baseline_model: anthropic/claude-sonnet-4
  baseline_cost_estimated: 7.40
  savings_percent: 62.2
next_agent: null
notes: "Pipeline completo de revisão sistemática. DeepSeek-R1 para screening complexo, GPT-4o-mini para extração de citações e sumarização. Economia de 62% vs. Claude Sonnet 4."
```