# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="160"/>
</p>

**Idiomas:** [English](README.md) | **Português** | [Español](README.es.md)

> Extração validada para revisões sistemáticas: cada célula da tabela de extração vem com o trecho, a página e um nível de confiança medido, e um relatório de confiabilidade pronto para a seção de Métodos e o checklist PRISMA 2020.

[![DOI](https://zenodo.org/badge/1227342715.svg)](https://doi.org/10.5281/zenodo.19982571)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-1.0.0a1-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)

O Lutz 1.0 é uma reescrita e não abre projetos 0.5.x; veja [do 0.5 para o 1.0](docs/upgrade-0.5-para-1.0.md). Para continuar na 0.5: `pip install "lutz-research<1"`.

## Como funciona

1. **Importar PDFs.** O Lutz guarda o texto visível de cada página (texto oculto é descartado), corrige a ordem de leitura em duas colunas, lê tabelas linha a linha e dá a cada frase e linha de tabela um identificador citável.
2. **Montar o codebook** (o formulário de extração) com o Assistente, um lint determinístico e um teste rápido em poucos artigos.
3. **Modo Autônomo.** Três extratores independentes (de preferência de fornecedores diferentes) preenchem cada célula com valor, trecho literal e página. O trecho é conferido no texto da página sem LLM, um verificador independente julga se o trecho sustenta o valor e as regras do codebook funcionam como portão. Cada célula recebe um nível: Alta, Média ou Baixa. O alfa de Krippendorff por campo mede a concordância entre extratores.
4. **Modo Calibrado (opcional).** Piloto cego com um ou dois avaliadores humanos: kappa de Cohen, kappa ponderado ou ICC por campo com IC por bootstrap, decisão por campo e a taxa de acerto medida de cada nível.
5. **Adjudicação e auditoria.** As células Baixa vão para decisão humana; uma amostra aleatória das células Alta é conferida à mão.
6. **Relatório.** Sete partes em português e inglês (Markdown e PDF): identificação, processo, confiabilidade por campo, calibração dos níveis, adjudicação, texto para Métodos, mapa PRISMA 2020, declaração de uso de IA (RAISE) e anexos com todo o registro.

## Instalação

```bash
pip install --pre lutz-research
```

Python 3.10+. Instalador para Windows na página de releases.

**Windows com `pip`:** o PyMuPDF, que lê os PDFs, precisa do [Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe). A maioria das máquinas já tem; num Windows recém-instalado, use `winget install --id Microsoft.VCRedist.2015+.x64 -e`. Se faltar, o `lutz doctor` avisa. O `lutz.exe` da página de releases já leva essas DLLs e não precisa de mais nada.

## Início rápido

```bash
lutz init minha-revisao --pergunta "Tutores com LLM melhoram o engajamento?"
cd minha-revisao
lutz config set OPENROUTER_API_KEY sk-or-...   # uma chave para todos os modelos (https://openrouter.ai/keys)
# escolha E1, E2, E3 (extratores) e V (verificador) em lutz web > Configurações, ou no lutz.yaml
lutz doctor --chamar
lutz load ~/artigos/
lutz codebook new                 # ou: lutz codebook import codebook.yaml
lutz codebook test --campo tamanho_amostra
lutz codebook freeze
lutz extract                      # estimativa de custo, confirmação, execução
lutz adjudicate export            # depois: lutz adjudicate import <arquivo>
lutz audit sample                 # depois: lutz audit import <arquivo>
lutz report
lutz web                          # o mesmo fluxo no navegador
```

Todos os modelos passam pelo [OpenRouter](https://openrouter.ai): uma chave, o catálogo inteiro, preços e consumo na tela de Configurações; veja [configuração](docs/configuracao.md).

## Interfaces

* **CLI** `lutz` — [referência](docs/referencia-cli.md).
* **Web** — `lutz web` (só em 127.0.0.1): Biblioteca, Codebook, Piloto, Extração, Resultados, Adjudicação, Relatório, API e MCP, Configurações.
* **API REST** — OpenAPI em `/api/docs` com `lutz web` rodando.
* **Servidor MCP** — `lutz mcp --projeto .` (stdio, somente leitura) para Claude Desktop, Cursor e VS Code.

## Documentação

* [Especificação do sistema](docs/spec-1.0.md)
* [Métodos estatísticos](docs/metodos-estatisticos.md)
* [Configuração](docs/configuracao.md)
* [Validação com um artigo real](docs/validacao-e2e.md)
* Site: [jooguilhermesc.github.io/lutz](https://jooguilhermesc.github.io/lutz/)

## Como citar

```bibtex
@software{cabral2026lutz,
  author  = {Cabral, João Guilherme Silva and Azevedo Farias, Anna Karoline},
  title   = {{Lutz: validated data extraction for systematic reviews}},
  year    = {2026},
  version = {1.0.0a1},
  doi     = {10.5281/zenodo.19982571},
  url     = {https://github.com/jooguilhermesc/lutz}
}
```

## Licença

MIT
