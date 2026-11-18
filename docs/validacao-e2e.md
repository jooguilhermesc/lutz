# Validação de ponta a ponta com um artigo real

> Registro histórico da validação da 1.0.0a1, feita com Docker Model Runner. Desde o [ADR-004](adr/ADR-004-somente-openrouter.md) o Lutz usa só o OpenRouter.

Critério de sucesso do brief: um artigo real passa pelo fluxo completo e gera o relatório.

## Configuração

* **Artigo:** Yuan et al., *Self-Rewarding Language Models*, arXiv:2401.10020v3 (23 páginas, 3 tabelas).
* **Modelos:** Docker Model Runner local, `ai/qwen2.5:3B-Q4_K_M` nos três extratores (variantes de prompt `padrao`, `reescrita_a`, `reescrita_b`) e no verificador. A GPU da máquina de teste só comportava um modelo carregado por vez (gemma3, gemma4 e llama3.2 falharam por falta de memória), então a diversidade foi `instrucoes_reescritas`, registrada como limitação no relatório.
* **Codebook:** 5 campos — `tipo_contribuicao` (categórico), `modelo_base` (texto), `numero_iteracoes` (numérico), `win_rate_final` (numérico, %), `limitacoes` (texto, seção Limitations).

## Fluxo executado

```
lutz init e2e --pergunta "..."
lutz load download_pdfs/
lutz codebook import codebook.yaml
lutz codebook test --campo numero_iteracoes,win_rate_final --n 1
lutz codebook freeze
lutz extract --sim                 # 39 s, 11 chamadas (2 em cache), US$ 0
lutz adjudicate decide ...         # 3 decisões
lutz audit sample / import         # 1 célula Alta conferida
lutz report                        # pt e en, md e pdf, anexos A, B e C
lutz web                           # telas conferidas com captura headless
```

## Resultado

| Campo | Valor final | Nível | Observação |
|---|---|---|---|
| tipo_contribuicao | metodo | Baixa → adjudicada | 2 de 3 extratores; o verificador (mesmo modelo de 3B) não sustentou |
| modelo_base | Llama 2 70B | Alta | Unanimidade, trecho exato, verificador sustenta; conferida na auditoria |
| numero_iteracoes | 3 | Baixa → adjudicada | Valor correto, mas os trechos citados não traziam o número |
| win_rate_final | 20.44 | Média | Valor correto (20,44% no AlpacaEval 2.0); página citada vizinha |
| limitacoes | não reportado → adjudicada | Média | Erro dos extratores; a busca de ausência também errou; corrigido na adjudicação |

O relatório gerado tem as sete partes, a frase de limitação obrigatória sem piloto e a limitação de erros correlacionados por usar um único modelo.

## Defeitos encontrados pelo artigo real e corrigidos

1. **Tabelas com decimais corrompidos.** `Table.extract()` do PyMuPDF devolvia "994% ." para "9.94%". A ingestão passou a ler cada célula pela geometria e a separar sub-linhas pela posição vertical.
2. **Título e ano errados.** O título vinha do carimbo vertical do arXiv e o ano das citações. Agora o título ignora texto rotacionado e o ano vem do identificador arXiv ou do cabeçalho.
3. **Artigo maior que a janela de 32 mil tokens.** Referências e agradecimentos deixaram de ir para os extratores; apêndices passaram a ser uma seção própria.
4. **Modelo pequeno em laço dentro do JSON.** Para endpoints locais o Lutz pede `json_schema` com listas e textos limitados, recuando para `json_object` e depois texto livre se o endpoint recusar.
5. **Trechos costurados com `\n` literal.** A evidência aceita fragmentos contíguos todos encontrados na página, e o número de um campo numérico pode estar nas unidades citadas.
6. **Acabamento do relatório:** alfa com um único artigo agora é indefinido, decisões fora da fila entram na estatística de adjudicação, modelo observado do Docker aparece como `modelo@sha256:<digest>`, textos sem gênero presumido.

## Leitura

O fluxo funciona de ponta a ponta. A qualidade das respostas é a de um modelo de 3B parâmetros com quantização de 4 bits, e o Lutz fez o que deve fazer com ela: marcou como duvidosas as células erradas ou mal ancoradas e as mandou para decisão humana. Uma validação de qualidade exige o corpus de referência com gabarito humano (questão em aberto da spec) e modelos de fornecedores diferentes.
