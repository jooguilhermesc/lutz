"""Report text in Portuguese and English. Numbers are formatted per language.

The RAISE statement and the PRISMA map are drafts written for the researcher to review; the
report says so. The limitation sentence of the no-pilot Methods text is mandatory.
"""

from __future__ import annotations

import math

ESTRATEGIA = {
    "pt": {
        "fornecedores_diferentes": "modelos de fornecedores diferentes",
        "modelos_diferentes": "modelos diferentes (alguns do mesmo fornecedor)",
        "instrucoes_reescritas": "o mesmo modelo com três formulações diferentes da instrução",
        "nenhuma": "o mesmo modelo e a mesma instrução nos três extratores",
    },
    "en": {
        "fornecedores_diferentes": "models from different vendors",
        "modelos_diferentes": "different models (some from the same vendor)",
        "instrucoes_reescritas": "the same model with three different wordings of the instructions",
        "nenhuma": "the same model and the same instructions for all three extractors",
    },
}

DECISAO = {
    "pt": {"lutz_sozinho": "Lutz sozinho", "revisar_media_baixa": "Revisar Média e Baixa",
           "reescrever": "Reescrever / humano", "indefinida": "Decisão manual"},
    "en": {"lutz_sozinho": "Lutz alone", "revisar_media_baixa": "Review Medium and Low",
           "reescrever": "Rewrite / human", "indefinida": "Manual decision"},
}

TIPO = {
    "pt": {"categorico": "categórico", "ordinal": "ordinal", "numerico": "numérico", "texto": "texto"},
    "en": {"categorico": "categorical", "ordinal": "ordinal", "numerico": "numeric", "texto": "free text"},
}

NIVEL = {"pt": {"alta": "Alta", "media": "Média", "baixa": "Baixa"},
         "en": {"alta": "High", "media": "Medium", "baixa": "Low"}}

METRICA = {
    "pt": {"kappa": "κ", "kappa_ponderado": "κw", "icc": "ICC", "pct_equivalencia": "% equiv."},
    "en": {"kappa": "κ", "kappa_ponderado": "κw", "icc": "ICC", "pct_equivalencia": "% equiv."},
}

T = {
    "pt": {
        "titulo": "Relatório de confiabilidade da extração",
        "gerado": "Gerado em",
        "p1": "1. Identificação da execução",
        "p2": "2. Processo",
        "p3": "3. Confiabilidade por campo",
        "p4": "4. Calibração dos níveis de confiança",
        "p5": "5. Adjudicação e auditoria",
        "p6": "6. Texto para a seção de Métodos",
        "p7": "7. Mapa PRISMA 2020, anexos e declaração de uso de IA",
        "sem_piloto": "sem piloto",
        "item": "Item", "valor": "Valor", "campo": "Campo", "tipo": "Tipo", "decisao": "Decisão",
        "nivel": "Nível", "celulas": "Células", "acertos": "Acertos", "taxa": "Taxa de acerto (IC95% Wilson)",
        "rascunho": "Rascunho para revisão da equipe de pesquisa: confira e ajuste antes de publicar.",
    },
    "en": {
        "titulo": "Data extraction reliability report",
        "gerado": "Generated on",
        "p1": "1. Run identification",
        "p2": "2. Process",
        "p3": "3. Reliability by field",
        "p4": "4. Calibration of the confidence levels",
        "p5": "5. Adjudication and audit",
        "p6": "6. Text for the Methods section",
        "p7": "7. PRISMA 2020 map, annexes and AI use statement",
        "sem_piloto": "no pilot",
        "item": "Item", "valor": "Value", "campo": "Field", "tipo": "Type", "decisao": "Decision",
        "nivel": "Level", "celulas": "Cells", "acertos": "Hits", "taxa": "Accuracy (95% Wilson CI)",
        "rascunho": "Draft for the research team to review: check and adjust before publishing.",
    },
}


def num(x, lang: str, casas: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    s = f"{x:.{casas}f}"
    return s.replace(".", ",") if lang == "pt" else s


def pct(x, lang: str, casas: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    s = f"{100 * x:.{casas}f}%"
    return s.replace(".", ",") if lang == "pt" else s


def ic(lo, hi, lang: str, casas: int = 2, porcento: bool = False) -> str:
    if lo is None or hi is None or (isinstance(lo, float) and math.isnan(lo)):
        return "—"
    f = (lambda v: pct(v, lang, 1)) if porcento else (lambda v: num(v, lang, casas))
    return f"{f(lo)}–{f(hi)}"


def _por(autoria: str) -> str:
    """Portuguese contraction: 'a equipe' -> 'pela equipe', 'o autor' -> 'pelo autor'."""
    for artigo, contracao in (("os ", "pelos "), ("as ", "pelas "), ("o ", "pelo "), ("a ", "pela ")):
        if autoria.lower().startswith(artigo):
            return contracao + autoria[len(artigo):]
    return "por " + autoria


def processo(d: dict, lang: str) -> str:
    s = d["settings"]
    lim = s.limiares
    tem_v = any(e["rotulo"] == "V" for e in d["extratores"])
    est = ESTRATEGIA[lang][d["execucao"]["estrategia_diversidade"]]
    if lang == "pt":
        partes = [
            f"Cada célula (um campo de um artigo) foi extraída por três extratores independentes ({est}), "
            "que não viam as respostas uns dos outros. Cada extrator recebeu o texto visível do artigo, página "
            "a página e com identificadores por frase e por linha de tabela, e devolveu o valor, o trecho literal "
            "que o sustenta e a página.",
            "O trecho citado por cada extrator foi conferido sem uso de LLM contra o texto da página indicada "
            "(evidência e = 1 quando encontrado literalmente, 0,5 em página vizinha ou com similaridade parcial "
            f"≥ {num(lim.evidencia_similaridade, lang, 0)} em trechos de ao menos {lim.evidencia_min_chars_fuzzy} "
            "caracteres, 0 quando não encontrado; em campos numéricos o número precisa aparecer no trecho).",
        ]
        if tem_v:
            partes.append("Um verificador independente, sem acesso ao artigo inteiro, julgou se o trecho vencedor "
                          "sustentava o valor (v = 1, 0,5 ou 0). Quando a maioria indicou ausência da informação, "
                          "o verificador procurou o dado nas seções indicadas no codebook.")
        else:
            partes.append("Não houve verificador independente; v = 1 foi declarado em todas as células, o que "
                          "torna o nível Alta menos exigente.")
        partes.append(
            "Regras do codebook (tipo, lista de valores, faixa plausível e consistência entre campos) funcionaram "
            "como portão. Células com unanimidade, evidência exata, verificador favorável e regras atendidas "
            "receberam confiança Alta; com 2 de 3 e checagens parciais, Média; as demais, inclusive empates e "
            "regras violadas, Baixa. Informações dadas como não reportadas ficaram no máximo em Média. Todas as "
            "células Baixa foram enviadas à adjudicação humana.")
        return "\n\n".join(partes)
    partes = [
        f"Each cell (one field of one article) was extracted by three independent extractors ({est}) that did "
        "not see each other's answers. Each extractor received the visible text of the article, page by page, "
        "with identifiers for every sentence and table row, and returned the value, the verbatim passage that "
        "supports it and the page.",
        "The passage quoted by each extractor was checked without an LLM against the text of the indicated page "
        "(evidence e = 1 when found verbatim, 0.5 on a neighbouring page or with partial similarity "
        f"≥ {num(lim.evidencia_similaridade, lang, 0)} for passages of at least {lim.evidencia_min_chars_fuzzy} "
        "characters, 0 when not found; for numeric fields the number had to appear in the passage).",
    ]
    if tem_v:
        partes.append("An independent verifier, without access to the full article, judged whether the winning "
                      "passage supported the value (v = 1, 0.5 or 0). When the majority reported the information "
                      "as absent, the verifier searched the sections indicated in the codebook.")
    else:
        partes.append("There was no independent verifier; v = 1 was assumed for every cell, which makes the "
                      "High level less demanding.")
    partes.append(
        "Codebook rules (type, list of values, plausible range and cross-field consistency) acted as a gate. "
        "Cells with unanimity, exact evidence, a favourable verifier and passing rules were rated High; 2 of 3 "
        "with partial checks, Medium; all others, including ties and rule violations, Low. Information reported "
        "as absent was rated Medium at most. Every Low cell was sent to human adjudication.")
    return "\n\n".join(partes)


def metodos(d: dict, lang: str) -> str:
    ex = d["execucao"]
    versao = ex["versao_lutz"]
    modelos = ", ".join(f"{e['rotulo']} {e['modelo']}" for e in d["extratores"] if e["papel"] == "extrator")
    from lutz.report.dados import faixa

    fa = faixa(d["campos"])
    adj = d["adjudicacao"]["total"]
    n_baixa = d["adjudicacao"]["por_nivel"].get("baixa", {}).get("enviadas", 0)
    aud = d["auditoria"]
    cal = d["calibracao"]
    est = ESTRATEGIA[lang][ex["estrategia_diversidade"]]
    autoria = d["settings"].relatorio.autoria if lang == "pt" else "the authors"
    if lang == "pt":
        t = [f"A extração de dados foi realizada com o Lutz (versão {versao}), utilizando três extratores "
             f"independentes por artigo ({modelos}; {est}) e verificação automática da evidência textual de "
             "cada valor extraído contra o texto do PDF."]
        if cal:
            camp = [c for c in d["campos"] if c["ouro"]]
            vals = [c["ouro"]["valor"] for c in camp if c["ouro"].get("valor") is not None]
            nval = cal["amostra"].get("validacao", 0)
            nava = len(cal["avaliadores"])
            alta = cal["niveis"].get("alta", {})
            t.append(
                f"O desempenho foi avaliado em um piloto cego com {nval + cal['amostra'].get('ajuste', 0)} artigos "
                f"sorteados aleatoriamente (semente {cal['semente']}), extraídos de forma independente por "
                f"{'dois avaliadores humanos, cujo consenso serviu' if nava == 2 else 'um avaliador humano, cuja extração serviu'} "
                f"de padrão-ouro. Após {cal['n_rodadas_ajuste']} rodada(s) de ajuste do formulário em "
                f"{cal['amostra'].get('ajuste', 0)} artigos, a concordância entre o Lutz e o padrão-ouro no "
                f"conjunto de validação ({nval} artigos, codebook congelado) variou de "
                f"{num(min(vals), lang) if vals else '—'} a {num(max(vals), lang) if vals else '—'} entre os campos "
                "(kappa de Cohen, kappa ponderado ou ICC conforme o tipo, com IC95% por bootstrap sobre artigos).")
            if alta.get("n"):
                t.append(f"Células classificadas como confiança Alta concordaram com o padrão-ouro em "
                         f"{pct(alta['valor'], lang, 1)} dos casos (IC95% {ic(alta['ic_inf'], alta['ic_sup'], lang, porcento=True)}).")
        if fa:
            t.append(f"A confiabilidade entre os extratores, medida pelo alfa de Krippendorff, variou de "
                     f"α = {num(fa[0], lang)} a {num(fa[1], lang)} entre os campos.")
        t.append(f"Todas as células de baixa confiança (n = {n_baixa}) foram revisadas {_por(autoria)}; "
                 f"{adj['alteradas']} de {adj['decididas']} decisões alteraram o valor proposto.")
        if aud and aud["conferidas"]:
            plural = "células de confiança Alta foram conferidas" if aud["conferidas"] > 1 else \
                "célula de confiança Alta foi conferida"
            t.append(f"Uma amostra aleatória de {aud['conferidas']} {plural} "
                     f"manualmente, com acerto de {pct(aud['taxa'], lang, 1)} (IC95% "
                     f"{ic(aud['ic_inf'], aud['ic_sup'], lang, porcento=True)}).")
        if not cal:
            t.append("Por não ter havido comparação com extração humana, a concordância entre extratores indica "
                     "consistência e ancoragem no texto, mas não comprova que os valores estejam corretos.")
        if ex["estrategia_diversidade"] in ("instrucoes_reescritas", "nenhuma"):
            t.append("Como os três extratores usaram o mesmo modelo, seus erros podem ser correlacionados, o que "
                     "limita o valor da concordância entre eles.")
        return " ".join(t)
    t = [f"Data extraction was performed with Lutz (version {versao}), using three independent extractors per "
         f"article ({modelos}; {est}) and automatic verification of the textual evidence of every extracted value "
         "against the PDF text."]
    if cal:
        camp = [c for c in d["campos"] if c["ouro"]]
        vals = [c["ouro"]["valor"] for c in camp if c["ouro"].get("valor") is not None]
        nval = cal["amostra"].get("validacao", 0)
        nava = len(cal["avaliadores"])
        alta = cal["niveis"].get("alta", {})
        t.append(
            f"Performance was assessed in a blinded pilot of {nval + cal['amostra'].get('ajuste', 0)} randomly "
            f"sampled articles (seed {cal['semente']}), independently extracted by "
            f"{'two human reviewers whose consensus served' if nava == 2 else 'one human reviewer whose extraction served'} "
            f"as the reference standard. After {cal['n_rodadas_ajuste']} adjustment round(s) of the form on "
            f"{cal['amostra'].get('ajuste', 0)} articles, agreement between Lutz and the reference standard in the "
            f"validation set ({nval} articles, frozen codebook) ranged from {num(min(vals), lang) if vals else '—'} "
            f"to {num(max(vals), lang) if vals else '—'} across fields (Cohen's kappa, weighted kappa or ICC by "
            "field type, with 95% CIs from a bootstrap over articles).")
        if alta.get("n"):
            t.append(f"Cells rated High confidence agreed with the reference standard in {pct(alta['valor'], lang, 1)} "
                     f"of cases (95% CI {ic(alta['ic_inf'], alta['ic_sup'], lang, porcento=True)}).")
    if fa:
        t.append(f"Inter-extractor reliability, measured with Krippendorff's alpha, ranged from α = {num(fa[0], lang)} "
                 f"to {num(fa[1], lang)} across fields.")
    t.append(f"All low-confidence cells (n = {n_baixa}) were reviewed by {autoria}; {adj['alteradas']} of "
             f"{adj['decididas']} decisions changed the proposed value.")
    if aud and aud["conferidas"]:
        t.append(f"A random sample of {aud['conferidas']} High-confidence cell{'s' if aud['conferidas'] > 1 else ''} "
                 f"{'were' if aud['conferidas'] > 1 else 'was'} checked manually, with "
                 f"{pct(aud['taxa'], lang, 1)} accuracy (95% CI {ic(aud['ic_inf'], aud['ic_sup'], lang, porcento=True)}).")
    if not cal:
        t.append("Because no comparison with human extraction was performed, agreement among extractors indicates "
                 "consistency and grounding in the text but does not demonstrate that the values are correct.")
    if ex["estrategia_diversidade"] in ("instrucoes_reescritas", "nenhuma"):
        t.append("Because the three extractors used the same model, their errors may be correlated, which limits "
                 "the value of their agreement.")
    return " ".join(t)


def raise_declaracao(d: dict, lang: str) -> str:
    ex = d["execucao"]
    modelos = sorted({f"{e['provedor']}/{e['modelo']}" for e in d["extratores"]})
    validado = "piloto cego com padrão-ouro humano" if d["calibracao"] else (
        "auditoria de uma amostra de células Alta" if d["auditoria"] and d["auditoria"]["conferidas"]
        else "concordância entre extratores e verificação de evidência (sem comparação com humanos)")
    if lang == "pt":
        return (
            f"Declaração de uso de IA (RAISE). Ferramenta: Lutz {ex['versao_lutz']}, com os modelos "
            f"{', '.join(modelos)}. Etapa: extração de dados (PRISMA 2020, item 9). Uso: três extratores "
            "independentes propuseram cada valor com trecho e página; checagens automáticas atribuíram um nível de "
            f"confiança. Validação: {validado}. Modelos, versões observadas, prompts (hash {ex['hash_prompts']}), "
            f"parâmetros (hash {ex['hash_config']}) e o registro completo de chamadas estão nos anexos. As decisões "
            "finais sobre células duvidosas foram tomadas pela equipe de pesquisa, que permanece responsável pelos dados.")
    validado_en = "blinded pilot against a human reference standard" if d["calibracao"] else (
        "audit of a sample of High cells" if d["auditoria"] and d["auditoria"]["conferidas"]
        else "inter-extractor agreement and evidence checking (no comparison with humans)")
    return (
        f"AI use statement (RAISE). Tool: Lutz {ex['versao_lutz']}, with the models {', '.join(modelos)}. "
        "Stage: data extraction (PRISMA 2020, item 9). Use: three independent extractors proposed each value with "
        "a passage and page; automatic checks assigned a confidence level. Validation: "
        f"{validado_en}. Models, observed versions, prompts (hash {ex['hash_prompts']}), parameters (hash "
        f"{ex['hash_config']}) and the full call log are in the annexes. Final decisions on doubtful cells were "
        "made by the research team, which remains responsible for the data.")


def prisma(d: dict, lang: str) -> list[tuple[str, str]]:
    papeis = {c["papel"] for c in d["campos"]}
    if lang == "pt":
        linhas = [
            ("5. Critérios de elegibilidade",
             "Campos com papel 'criterio' ou 'triagem' no codebook (anexo A)" if papeis & {"criterio", "triagem"}
             else "Não se aplica: o codebook não tem campos de elegibilidade"),
            ("8. Processo de seleção",
             "Partes 1, 2 e 3, aplicadas aos campos de triagem" if "triagem" in papeis
             else "Não se aplica: o Lutz não fez a triagem nesta revisão"),
            ("9. Processo de coleta de dados", "Partes 1 a 6"),
            ("10. Itens de dados", "Codebook com tipo, instrução e regra de ausência de cada campo (anexo A)"),
            ("11. Risco de viés", "Partes 1 a 3, campos com papel 'risco_vies'" if "risco_vies" in papeis
             else "Não se aplica: o Lutz não avaliou risco de viés"),
            ("27. Disponibilidade de dados", "Anexos A (codebook), B (tabela) e C (registro completo)"),
        ]
    else:
        linhas = [
            ("5. Eligibility criteria",
             "Fields with role 'criterio' or 'triagem' in the codebook (annex A)" if papeis & {"criterio", "triagem"}
             else "Not applicable: the codebook has no eligibility fields"),
            ("8. Selection process", "Parts 1, 2 and 3, applied to screening fields" if "triagem" in papeis
             else "Not applicable: Lutz did not perform screening in this review"),
            ("9. Data collection process", "Parts 1 to 6"),
            ("10. Data items", "Codebook with type, instruction and missing-data rule of each field (annex A)"),
            ("11. Risk of bias", "Parts 1 to 3, fields with role 'risco_vies'" if "risco_vies" in papeis
             else "Not applicable: Lutz did not assess risk of bias"),
            ("27. Availability of data", "Annexes A (codebook), B (table) and C (full log)"),
        ]
    return linhas
