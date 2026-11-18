---
layout: home

hero:
  name: Lutz 1.0
  text: Extração validada para revisões sistemáticas
  tagline: Cada célula da tabela com o trecho, a página e um nível de confiança medido. Um relatório de confiabilidade pronto para a seção de Métodos e o PRISMA 2020.
  image:
    src: /logo.png
    alt: Lutz
  actions:
    - theme: brand
      text: Começar
      link: /guide/getting-started
    - theme: alt
      text: Especificação
      link: /spec-1.0
    - theme: alt
      text: GitHub
      link: https://github.com/jooguilhermesc/lutz

features:
  - title: Três extratores independentes
    details: Modelos de fornecedores diferentes extraem cada célula sem ver as respostas uns dos outros.
  - title: Evidência conferida sem LLM
    details: O trecho citado precisa existir no texto visível da página indicada; números precisam estar no trecho.
  - title: Níveis Alta, Média e Baixa
    details: Concordância, evidência, verificador independente e regras do codebook decidem o nível; as células Baixa vão para adjudicação humana.
  - title: Piloto cego com humanos
    details: Kappa, kappa ponderado ou ICC por campo, com IC por bootstrap, decisão por campo e calibração dos níveis.
  - title: Relatório de confiabilidade
    details: Sete partes, pt e en, texto para Métodos, mapa PRISMA 2020, declaração RAISE e anexos com todo o registro.
  - title: Tudo local
    details: Um projeto é uma pasta (SQLite + texto por página). CLI, interface web, API REST e servidor MCP somente leitura.
---
