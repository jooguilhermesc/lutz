# Interface Web — Visão Geral

A interface web do Lutz é iniciada com `lutz web` e abre automaticamente em `http://localhost:8765`.

![Interface principal do Lutz](/screenshots/biblioteca.png)

---

## Estrutura da tela

A interface é organizada em três áreas principais:

| Área | Descrição |
|---|---|
| **Painel lateral esquerdo** | Pipeline de status, critério de triagem, templates, provedor LLM e modelo |
| **Abas principais** | Biblioteca · Resultados · Relatórios |
| **Barra superior** | Estimativa de custo, notificações, Histórico, modo escuro, Configurações |

---

## Abas principais

### Biblioteca
Lista todos os artigos PDF do projeto, permite carregar novos arquivos e iniciar a vetorização. [Saiba mais →](./biblioteca.md)

### Resultados
Exibe os artigos com seus veredictos após a análise RAG (INCLUIR / EXCLUIR / INCERTO). [Saiba mais →](./resultados.md)

### Relatórios
Lista os relatórios gerados, com opção de visualização e download em PDF. [Saiba mais →](./relatorios.md)

---

## Painel lateral

O painel esquerdo condensa o fluxo completo de trabalho:

**Pipeline** — indicadores visuais das etapas concluídas:
- Biblioteca (PDFs carregados)
- Vetorizado (artigos indexados)
- Análise (status da última execução)

**Critério de triagem** — campo de texto onde você descreve os critérios de inclusão/exclusão. É o prompt enviado ao LLM na análise.

**Templates** — prompts salvos para reutilização. Clique em um template para carregá-lo no campo de triagem.

**Provedor LLM** — seletor rápido de provider e modelo, com link "Gerenciar" para abrir o modal de Configurações.

---

## Barra superior

| Elemento | Função |
|---|---|
| **Est. análise** | Estimativa de custo da próxima análise em USD |
| **Sininho** | Painel de notificações |
| **Histórico** | Drawer lateral com execuções anteriores ([ver →](./historico.md)) |
| **Lua/Sol** | Alternar modo escuro/claro |
| **⚙** | Abrir modal de Configurações ([ver →](./configuracoes.md)) |

---

## Fluxo típico

```
1. lutz load --f /pasta/artigos    # copia PDFs para articles/
2. lutz web                        # abre a interface
3. Aba Biblioteca → Vetorizar      # indexa os artigos
4. Preencher critério de triagem
5. Iniciar análise (botão verde)
6. Aba Resultados → revisar veredictos
7. Aba Relatórios → baixar PDF
```
