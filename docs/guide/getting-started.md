# Começar

O Lutz monta a tabela de extração de uma revisão sistemática com um nível de confiança medido em cada célula e gera o relatório de confiabilidade para a seção de Métodos e o checklist PRISMA 2020.

## Instalar

```bash
pip install --pre lutz-research    # 1.0.0a1
lutz --version
```

Python 3.10 ou mais novo. No Windows há também o executável do instalador.

## 1. Criar o projeto

```bash
lutz init minha-revisao --pergunta "LLMs melhoram o engajamento de estudantes?"
cd minha-revisao
```

## 2. Configurar os modelos

* Chaves de API no `.env` (ou `lutz config set ANTHROPIC_API_KEY ...`).
* Modelos E1, E2, E3 (extratores) e V (verificador) no `lutz.yaml`. Prefira fornecedores diferentes: os erros ficam menos correlacionados. Modelos locais do Docker Model Runner funcionam sem chave.
* `lutz doctor --chamar` confere tudo com uma chamada mínima a cada modelo.

Detalhes em [Configuração](/configuracao).

## 3. Importar os PDFs

```bash
lutz load ~/artigos/
lutz library
```

O Lutz guarda o texto visível de cada página, corrige a ordem de leitura em duas colunas, lê as tabelas linha a linha e marca PDFs sem camada de texto.

## 4. Montar o codebook

```bash
lutz codebook new                         # Assistente
lutz codebook test --campo tamanho_amostra
lutz codebook freeze
```

Ou escreva o `codebook.yaml` e use `lutz codebook import codebook.yaml`.

## 5. (Opcional) Piloto com humanos

```bash
lutz pilot plan --n 30 --ajuste 10
lutz pilot sample
# avaliadores preenchem exports/piloto/humano_A.csv e humano_B.csv sem ver o Lutz
lutz pilot import exports/piloto/humano_A.csv --avaliador A
lutz pilot import exports/piloto/humano_B.csv --avaliador B
lutz pilot consensus            # e depois --importar
lutz extract --piloto validacao
lutz pilot compare
```

## 6. Extrair, revisar e relatar

```bash
lutz extract                    # estimativa de custo, confirmação, execução
lutz adjudicate export          # planilha das células duvidosas
lutz adjudicate import exports/adjudicacao_0001.csv
lutz audit sample               # confira uma amostra das células Alta
lutz report                     # relatorios/execucao-0001/
```

Ou faça tudo pela interface: `lutz web`.

## Integrar

`lutz mcp --projeto .` expõe o projeto, somente leitura, para Claude Desktop, Cursor e VS Code. A API REST fica em `http://127.0.0.1:8000/api/docs` com `lutz web`.
