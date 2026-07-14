# Análise e Resultados

A análise é configurada no **rail lateral** e os resultados aparecem na aba **Resultados**. O Lutz executa cada artigo individualmente com veredicto INCLUDE/EXCLUDE.

![Aba Resultados](/screenshots/resultados.png)

---

## Configurar e executar

### 1. Critério de triagem

No rail lateral, escreva o critério de inclusão/exclusão no campo de texto:

```
Inclua artigos que descrevam ensaios clínicos randomizados com
população adulta (≥18 anos) e desfecho primário de mortalidade
hospitalar. Exclua revisões narrativas, cartas e estudos com menos
de 50 participantes.
```

**Templates salvos**: clique em uma pill de template para preencher o campo automaticamente. Salve novos templates pelo campo "Salvar como…" abaixo do textarea.

**Anexar arquivo**: envie PDFs, DOCX, XLSX ou PPTX como contexto extra que o LLM recebe junto com os chunks dos artigos.

### 2. Provedor e modelo

Selecione o provedor LLM (Anthropic, OpenAI, Docker Model Runner) e o modelo no rail lateral. A estimativa de custo é atualizada automaticamente.

| Provedor | Modelos disponíveis |
|---|---|
| Anthropic | claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5 |
| OpenAI | gpt-4o, gpt-4o-mini |
| Docker Model Runner | llama3.2 (local, gratuito) |

### 3. Analisar

Clique em **Analisar N artigos**. O botão fica ativo quando há artigos vetorizados e um critério preenchido. A análise roda em modo *per-article* com 4 workers paralelos.

A aba muda para **Resultados** automaticamente e os logs aparecem em tempo real.

---

## Aba Resultados

Enquanto a análise roda, a aba exibe logs de progresso. Ao terminar, mostra:

- **INCLUDE** (verde) — artigo atende ao critério
- **EXCLUDE** (vermelho) — artigo não atende
- **UNCERTAIN** — trechos insuficientes para decidir
- **UNKNOWN** — veredicto não encontrado na resposta do LLM

Cada item pode ser expandido para ver a análise completa do LLM e os chunks utilizados como contexto.

---

## Como escrever bons critérios

Um critério eficaz para triagem sistemática inclui:

```
## Critério de inclusão
- Ensaios clínicos randomizados
- População adulta (≥18 anos)
- Desfecho primário de mortalidade hospitalar

## Critério de exclusão
- Revisões narrativas ou sistemáticas
- Estudos com n < 50
- Cartas ao editor ou editoriais
```

::: tip
Use a estrutura de inclusão/exclusão explícita para obter veredictos mais precisos.
:::

---

## Equivalente no CLI

```bash
# Análise por artigo (modo padrão da interface)
lutz analysis --p prompts/screening.md --per-article --workers 4

# Filtrar por seção antes de analisar
lutz analysis --p prompts/screening.md --per-article \
  --filter-sections abstract

# Modo RAG (corpus inteiro, uma chamada)
lutz analysis --p prompts/synthesis.md
```
