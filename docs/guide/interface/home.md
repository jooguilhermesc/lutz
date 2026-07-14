# Interface Web — Visão Geral

A interface web do Lutz é uma aplicação de página única (SPA) acessível via `lutz web`. Ela reúne todo o fluxo de triagem em uma única tela: carregamento de PDFs, vetorização, execução de análise e visualização de resultados.

![Interface principal do Lutz](/screenshots/home.png)

---

## Como acessar

```bash
lutz web
```

O servidor inicia em `http://localhost:8765` e abre o navegador automaticamente. Para usar outra porta:

```bash
lutz web --port 8080
```

::: warning Projeto não encontrado
Execute `lutz web` a partir de um diretório que contenha `articles/` ou `.lutz/`. Crie um projeto com `lutz init` se necessário.
:::

---

## Layout

A interface é dividida em duas áreas principais:

### Rail lateral (esquerda)

Painel de controle fixo com:

| Seção | Função |
|---|---|
| **Pipeline** | Status das três etapas: Biblioteca → Vetorizado → Análise. O botão "Vetorizar" / "Detalhes" abre o **modal do Vector Store** |
| **Critério de triagem** | Área de texto para o prompt de análise, com templates salvos e opção de anexar arquivos de contexto |
| **Provedor LLM** | Seletor de provedor (Anthropic, OpenAI, OpenRouter, Docker Model Runner) |
| **Modelo LLM** | Modelo de linguagem para raciocinar e redigir a análise |
| **Modelo Embedding** | Modelo de vetorização para busca semântica nos chunks |
| **Estimativa de custo** | Cálculo automático baseado no corpus vetorizado e modelo LLM escolhido |
| **Botão Analisar** | Executa a análise e redireciona para a aba Resultados |

### Área principal (direita)

Três abas de visualização:

| Aba | Conteúdo |
|---|---|
| **Biblioteca** | Lista de PDFs, upload e gestão de artigos, progresso de vetorização |
| **Resultados** | Veredictos INCLUDE/EXCLUDE por artigo com logs de execução em tempo real |
| **Relatórios** | Histórico de análises com download em JSON e HTML |

---

## Barra superior

| Elemento | Função |
|---|---|
| Nome do projeto | Pasta atual detectada pelo Lutz |
| Est. análise | Custo estimado para a análise com o modelo LLM atual |
| Atividades | Painel de jobs em execução (vetorização, análise) |
| Histórico | Drawer lateral com relatórios anteriores |
| Tema | Alterna entre modo claro e escuro |
| Configurações | Abre o modal de configurações de modelos e chaves de API |

---

## Modal do Vector Store

Acessível pelo botão **Vetorizar** ou **Detalhes** no painel de Pipeline. Exibe:

- Número de registros (chunks) e documentos únicos no banco
- Data da última atualização e modelo de embedding usado
- Lista de todos os artigos vetorizados com data e contagem de chunks
- Botão para iniciar vetorização de artigos pendentes
- Botão para **limpar** o vector store (com confirmação)

Veja [Vector Store](/guide/interface/vector-store) para detalhes.

---

## Fluxo típico

1. **Biblioteca** — faça upload dos PDFs ou confirme os arquivos em `articles/`
2. **Pipeline → Vetorizar** — clique no botão no painel lateral para abrir o modal e iniciar a vetorização
3. **Critério de triagem** — escreva o prompt ou selecione um template
4. **Analisar** — clique em "Analisar N artigos"
5. **Resultados** — revise os veredictos por artigo
6. **Relatórios** — baixe o JSON ou HTML da análise
