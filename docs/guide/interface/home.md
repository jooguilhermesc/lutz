# Dashboard (Home)

O dashboard é a página inicial da interface web do Lutz. Ele oferece uma visão geral do estado do projeto e serve como ponto de entrada para todas as demais páginas.

![Dashboard do Lutz](/screenshots/home.png)

---

## Como acessar

Inicie a interface web e acesse `http://localhost:8765`:

```bash
lutz web
```

O Lutz detecta automaticamente a raiz do projeto pelo diretório de trabalho atual — o mesmo diretório que contém `articles/` ou `.lutz/`.

::: warning Projeto não encontrado
Se o dashboard exibir um aviso de "Nenhum projeto Lutz encontrado", execute `lutz web` a partir de um diretório que contenha `articles/` ou `.lutz/`. Crie um projeto com `lutz init` se necessário.
:::

---

## Métricas do projeto

O dashboard exibe métricas em tempo real:

| Métrica | O que representa |
|---|---|
| **Artigos PDF** | Número de arquivos `.pdf` na pasta `articles/` |
| **Análises** | Relatórios JSON gerados em `analysis/execution_reports/` |

---

## Fluxo de trabalho

Os cartões de navegação mostram as etapas principais:

| Cartão | Rota | Função |
|---|---|---|
| **Vetorização** | `/vectorize` | Upload de PDFs e indexação no banco vetorial |
| **Vector Store** | `/store` | Inspecionar artigos, chunks e distribuição de seções |
| **Análise** | `/analysis` | Executar análises com prompt em modo RAG ou por artigo |
| **Citações** | `/citations` | Extrair passagens relevantes com justificativa |
| **Roteiro de leitura** | `/roadmap` | Plano de leitura gerado por LLM com ordem de dependências |
| **Relatórios** | `/reports` | Visualizar e baixar resultados com veredictos INCLUDE/EXCLUDE |
| **Configurações** | `/settings` | Configurar provedores de LLM/embedding e chaves de API |

---

## Arquitetura RAG — contexto

O Lutz implementa o padrão **RAG (Retrieval-Augmented Generation)**:

```
PDFs → extração → chunks → embeddings → LanceDB
                                            ↓
              prompt → embedding → busca por similaridade
                                            ↓
                              chunks relevantes + LLM → resposta
```

Cada artigo é dividido em chunks de texto (padrão: 512 palavras com sobreposição de 64). Um modelo de embedding converte cada chunk em um vetor numérico de alta dimensão. Na hora da análise, o prompt também vira um vetor e os chunks com maior similaridade de cosseno são recuperados e enviados ao LLM como contexto.

Isso permite analisar centenas de artigos sem precisar enviar todo o texto para o modelo — apenas as passagens mais relevantes para a pergunta feita.
