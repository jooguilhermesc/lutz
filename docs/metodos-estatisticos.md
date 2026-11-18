# Métodos estatísticos do Lutz

Este documento descreve as métricas que o Lutz calcula e de onde vem cada número do relatório de confiabilidade. Cada exemplo numérico abaixo é um teste automatizado em `tests/test_metricas.py`; as implementações estão em `lutz/core/metricas.py` e são conferidas contra scikit-learn e statsmodels nos testes.

## 1. Dois modos que se somam

| | Modo Autônomo | Modo Calibrado |
|---|---|---|
| Quando roda | Sempre, em todo o corpus | Quando há um piloto com humanos |
| O que mede | Confiabilidade: consistência entre extratores e ancoragem no texto | Validade: acerto do Lutz contra humanos |
| Métrica principal | Alfa de Krippendorff entre E1, E2 e E3; nível por célula | Kappa (ou ICC) Lutz × padrão-ouro, por campo |
| Limitação | Não prova acerto: extratores podem errar juntos | Custa horas de trabalho humano |

Sem piloto, o único número Lutz × humano é a **auditoria das células Alta** (§9). O relatório avisa quando ela falta.

## 2. Porcentagem de concordância

`p_o = células em que os avaliadores concordam / n`. Sempre aparece no relatório, mas sozinha engana quando uma categoria domina.

## 3. Kappa de Cohen (2 avaliadores, categórico)

`κ = (p_o − p_e) / (1 − p_e)`, com `p_e = Σ_k (linha_k / n)(coluna_k / n)`.

Exemplo, campo "desenho do estudo", 40 artigos (linhas = Lutz, colunas = humano):

| | Experimental | Observacional | Revisão |
|---|---|---|---|
| Experimental | 14 | 2 | 0 |
| Observacional | 1 | 15 | 1 |
| Revisão | 0 | 1 | 6 |

`p_o = 0,875`, `p_e = 0,372`, **κ = 0,80**. "Não reportado" entra como uma categoria a mais.

## 4. Kappa ponderado (ordinal)

Pesos quadráticos (padrão) `w_ij = 1 − (i − j)² / (k − 1)²` ou lineares `1 − |i − j| / (k − 1)`. A ordem é a da lista `valores` do codebook. Exemplo, "risco de viés", 30 artigos (linhas Lutz: [10, 2, 0], [1, 8, 2], [1, 1, 5]): kappa simples **0,64**, linear **0,68**, quadrático **0,72**.

## 5. Paradoxo do kappa e PABAK

`PABAK = (k · p_o − 1) / (k − 1)`. Exemplo: 40 artigos, "feito no Brasil?", concordância 92,5% e **κ = 0,36**; **PABAK = 0,85**. O relatório mostra o PABAK ao lado do kappa quando a categoria mais frequente passa de 80% (`pabak_categoria_dominante`). Ele explica o kappa baixo; não o substitui.

## 6. Kappa de Fleiss

Generalização para m avaliadores; usado como referência (o Modo Autônomo usa o alfa). Exemplo de 6 artigos × 3 extratores: **κ = 0,64**.

## 7. Alfa de Krippendorff (padrão do Modo Autônomo)

`α = 1 − D_o / D_e`. Aceita qualquer número de avaliadores, dados faltantes e os níveis nominal, ordinal e intervalar; corrige para amostras pequenas. Com os mesmos 6 artigos do Fleiss, **α = 0,66**.

No Lutz:

* categórico → nominal, com "não reportado" como categoria;
* ordinal → ordinal, na ordem do codebook; "não reportado" vira faltante;
* numérico → intervalar; "não reportado" vira faltante;
* extrator que falhou ou violou uma regra → faltante;
* texto livre → sem alfa; usa-se a % de células unânimes com IC de Wilson;
* menos de dois artigos com valores pareáveis, ou nenhuma variação → indefinido.

Leitura (Krippendorff): α ≥ 0,800 confiável; 0,667 a 0,800 só conclusões provisórias; abaixo de 0,667, reescrever o campo.

## 8. ICC(A,1) (numérico)

Dois fatores aleatórios, concordância absoluta, avaliador único (McGraw e Wong):

`ICC(A,1) = (MSR − MSE) / (MSR + (k − 1)MSE + (k/n)(MSC − MSE))`

Exemplo, tamanho da amostra em 6 artigos (humano 120, 45, 300, 80, 210, 60; Lutz 120, 48, 300, 80, 201, 60): MSR = 19.560,7, MSC = 3,0, MSE = 8,4, **ICC = 0,999**, mas só 4 de 6 valores iguais e erro médio 2,0 (máximo 9). Por isso campos numéricos sempre mostram também a % exata (na tolerância do codebook) e os erros absolutos mediano e máximo, e só recebem "Lutz sozinho" com pelo menos 90% de valores iguais (`decisao_numerico_exato`).

## 9. Intervalo de Wilson (proporções)

`(p̂ + z²/2n ± z·√(p̂(1−p̂)/n + z²/4n²)) / (1 + z²/n)`. Exemplo: 118 acertos em 121 células Alta → **97,5% (IC95% 93,0% a 99,2%)**.

Usado na calibração dos níveis, na % de unânimes, na % de equivalência de texto e na auditoria. O tamanho da auditoria é o menor n cujo intervalo de Wilson, na proporção esperada (`auditoria.p_esperado`, 0,95), tem meia largura ≤ `auditoria.meia_largura_alvo` (0,06), limitado ao número de células Alta.

## 10. Intervalo por bootstrap

Sorteiam-se **artigos** com reposição (nunca células: as células de um artigo não são independentes), recalcula-se a métrica, repete-se 2.000 vezes (`metricas.bootstrap_repeticoes`) e tomam-se os percentis 2,5 e 97,5. A semente é `sementes.bootstrap`, registrada no relatório. Réplicas em que a métrica fica indefinida são descartadas; se mais da metade for indefinida, o intervalo é indefinido.

## 11. Tamanho do piloto

`EP(κ) ≈ √(p_o(1 − p_o) / (n(1 − p_e)²))`. Com p_o = 0,90 e p_e = 0,50:

| Artigos | Erro padrão | Meia largura do IC95% |
|---|---|---|
| 20 | 0,13 | ±0,26 |
| 30 | 0,11 | ±0,21 |
| 40 | 0,09 | ±0,19 |
| 60 | 0,08 | ±0,15 |
| 100 | 0,06 | ±0,12 |

`lutz pilot plan` mostra esta tabela antes do sorteio e avisa quando o corpus tem menos de ~60 artigos.

## 12. Regra de decisão por campo (piloto)

| Resultado na validação | Decisão |
|---|---|
| métrica ≥ 0,80 e IC inferior ≥ 0,60 (numérico: também ≥ 90% iguais) | Lutz sozinho; adjudicar só Baixa |
| métrica ≥ 0,60 | Revisar Média e Baixa |
| métrica < 0,60 | Reescrever a instrução; se não melhorar, extração humana |
| métrica indefinida | Decisão manual |

Texto livre usa a % de equivalência: ≥ 0,90 com IC inferior ≥ 0,75 → Lutz sozinho; ≥ 0,75 → revisar. Os limiares são configuráveis e impressos no relatório. A regra é mais exigente que Landis e Koch (1977), seguindo McHugh (2012).

## 13. Nível de cada célula

| Nível | Condição |
|---|---|
| Alta | a = 1, e = 1, v = 1, regras OK e todas as respostas do grupo majoritário com e ≥ 0,5 |
| Média | a ≥ 2/3, e ≥ 0,5, v ≥ 0,5 e regras OK |
| Baixa | qualquer outro caso, inclusive empate e regra violada |

Escore `s = a × e × v` ordena a fila de adjudicação. "Não reportado" fica no máximo em Média. A calibração do piloto mede com que frequência cada nível acertou; se Alta acerta menos de 95%, os limiares estão frouxos para o corpus.

## Referências

Page MJ et al. (2021) BMJ 372:n71 · Cohen J (1960, 1968) · Fleiss JL (1971) · Hayes AF, Krippendorff K (2007) · Krippendorff K (2004) · Landis JR, Koch GG (1977) · McHugh ML (2012) · Feinstein AR, Cicchetti DV (1990) · Byrt T, Bishop J, Carlin JB (1993) · Shrout PE, Fleiss JL (1979) · McGraw KO, Wong SP (1996) · Koo TK, Li MY (2016) · Wilson EB (1927) · Efron B, Tibshirani RJ (1993) · Declaração conjunta Cochrane, Campbell, JBI e CEE sobre IA em síntese de evidências (RAISE).
