---
layout: home

hero:
  name: Lutz
  text: Triagem de artigos acadêmicos com IA
  tagline: Organize, vetorize e analise coleções de PDFs científicos usando RAG e modelos de linguagem — na linha de comando ou pelo navegador.
  image:
    src: /logo.png
    alt: Lutz logo
  actions:
    - theme: brand
      text: Começar agora
      link: /guide/getting-started
    - theme: alt
      text: Interface Web
      link: /guide/interface/home
    - theme: alt
      text: GitHub
      link: https://github.com/jooguilhermesc/lutz

features:
  - icon: 📄
    title: Vetorização de PDFs
    details: Extrai texto, detecta seções (abstract, metodologia, resultados…) e armazena embeddings em um banco vetorial local via LanceDB.
  - icon: 🔍
    title: Busca semântica (RAG)
    details: Recupera os trechos mais relevantes para cada prompt usando similaridade de embeddings, reduzindo o contexto enviado ao LLM.
  - icon: 🤖
    title: Análise com LLM
    details: Suporta OpenAI, Anthropic, Docker Model Runner, Ollama e qualquer API compatível com OpenAI.
  - icon: 🛡️
    title: Verificação de segurança
    details: Detecta JavaScript embutido, ações automáticas, XFA e padrões de prompt injection antes de processar os PDFs.
  - icon: 🌐
    title: Interface Web
    details: Dashboard React completo com FastAPI — vetorize, analise, converse via Chat, gerencie relatórios e configure modelos sem sair do navegador.
  - icon: 📊
    title: Analytics para Revisão Sistemática
    details: Deduplicação por similaridade semântica, ranking de relevância, clustering temático reprodutível e detecção de outliers — sem depender de LLM no caminho crítico.
  - icon: 🔬
    title: Open Science
    details: Projeto de código aberto, nomeado em homenagem a Bertha Lutz, cientista e pesquisadora brasileira.
---
