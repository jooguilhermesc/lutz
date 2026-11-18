"""Markdown rendering of the seven parts, Markdown → HTML subset, and PDF via PyMuPDF Story."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import pymupdf

from lutz.report import textos as tx
from lutz.report.textos import T, num, pct


def _tabela(cab: list[str], linhas: list[list[str]]) -> str:
    def esc(x):
        return str(x).replace("|", "\\|").replace("\n", " ")

    out = ["| " + " | ".join(esc(c) for c in cab) + " |", "|" + "---|" * len(cab)]
    out += ["| " + " | ".join(esc(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(out)


def markdown(d: dict, lang: str) -> str:
    t = T[lang]
    ex = d["execucao"]
    s = d["settings"]
    pt = lang == "pt"
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    partes: list[str] = []
    partes.append(f"# {t['titulo']}")
    modo = ("Modo Autônomo + Modo Calibrado" if d["calibracao"] else "Modo Autônomo (sem piloto)") if pt else (
        "Autonomous mode + Calibrated mode" if d["calibracao"] else "Autonomous mode (no pilot)")
    partes.append(f"**{d['projeto']['nome']}** · {'execução' if pt else 'run'} {ex['id']} · {modo}  \n"
                  f"{t['gerado']} {agora}")
    if d["projeto"].get("pergunta"):
        partes.append(("Pergunta de pesquisa: " if pt else "Research question: ") + d["projeto"]["pergunta"])
    sem_alta = not ((d["geral"].get("pct_alta") or {}).get("valor") or 0)
    if (not d["auditoria"] or not d["auditoria"]["conferidas"]) and not d["calibracao"]:
        if sem_alta:
            partes.append("> **Atenção:** nenhuma célula ficou em confiança Alta, então não há auditoria possível, e "
                          "não houve piloto: nenhum número deste relatório compara o Lutz com um humano."
                          if pt else
                          "> **Warning:** no cell reached High confidence, so there is nothing to audit, and there "
                          "was no pilot: no number in this report compares Lutz with a human.")
        else:
            partes.append("> **Atenção:** a auditoria das células Alta não foi feita. Sem piloto e sem auditoria, "
                          "nenhum número deste relatório compara o Lutz com um humano. Rode `lutz audit sample`."
                          if pt else
                          "> **Warning:** the audit of High cells was not done. Without a pilot and without an audit, "
                          "no number in this report compares Lutz with a human. Run `lutz audit sample`.")

    # ── 1 ──
    partes.append(f"## {t['p1']}")
    linhas = [
        ["Lutz", ex["versao_lutz"]],
        ["Execução" if pt else "Run", f"{ex['id']} ({ex['tipo']}) · {ex['iniciada_em'] or '—'} → {ex['concluida_em'] or '—'}"],
        ["Codebook", f"v{d['codebook_row']['versao']} · hash {d['codebook_row']['hash']}"],
    ]
    for e in d["extratores"]:
        temp = "n/a" if e["provedor"] == "anthropic" else num(e["temperatura"], lang, 1)
        obs = e.get("modelo_observado") or "—"
        m_sha = re.search(r"sha256[:/]([0-9a-f]{12})", obs)
        if m_sha:
            obs = f"sha256:{m_sha.group(1)}"
        papel = {"extrator": "Extrator" if pt else "Extractor", "verificador": "Verificador" if pt else "Verifier",
                 "juiz": "Juiz" if pt else "Judge"}[e["papel"]]
        linhas.append([f"{papel} {e['rotulo']}",
                       f"{e['provedor']} · {e['modelo']} ({'observado' if pt else 'observed'}: {obs}) · "
                       f"temp. {temp} · prompt {e['variante_prompt']}"])
    if not any(e["papel"] == "verificador" for e in d["extratores"]):
        linhas.append(["Verificador" if pt else "Verifier", "não configurado (v = 1 declarado)" if pt
                       else "not configured (v = 1 assumed)"])
    linhas.append(["Diversidade" if pt else "Diversity", tx.ESTRATEGIA[lang][ex["estrategia_diversidade"]]])
    ctx = d["contexto"]
    linhas.append(["Contexto" if pt else "Context",
                   (f"texto completo em {ctx.get('completo', 0)} chamadas; seções do codebook em "
                    f"{ctx.get('secoes', 0)}" if pt else
                    f"full text in {ctx.get('completo', 0)} calls; codebook sections in {ctx.get('secoes', 0)}")])
    linhas.append(["Hash da configuração (lutz.yaml)" if pt else "Configuration hash (lutz.yaml)", ex["hash_config"]])
    linhas.append(["Hash dos prompts" if pt else "Prompt hash", ex["hash_prompts"]])
    linhas.append(["Sementes" if pt else "Seeds",
                   f"piloto {s.sementes.piloto} · bootstrap {s.sementes.bootstrap} · "
                   f"{'auditoria' if pt else 'audit'} {s.sementes.auditoria} · "
                   f"{s.metricas.bootstrap_repeticoes} {'repetições' if pt else 'resamples'}"])
    cs = d["consumo"]["total"]
    linhas.append(["Chamadas e custo" if pt else "Calls and cost",
                   f"{cs['chamadas']} ({cs['em_cache'] or 0} cache) · "
                   f"{(cs['tokens_entrada'] or 0) + (cs['tokens_saida'] or 0):,} tokens · US$ "
                   f"{num(cs['custo_usd'] or 0, lang, 2)}"
                   + ((" · " + ("preço desconhecido para parte das chamadas" if pt else "unknown price for some calls"))
                      if cs.get("sem_preco") else "")])
    linhas.append(["Artigos e células" if pt else "Articles and cells",
                   f"{len(d['artigos'])} · {d['total_celulas']}"])
    partes.append(_tabela([t["item"], t["valor"]], linhas))

    # ── 2 ──
    partes.append(f"## {t['p2']}")
    partes.append(tx.processo(d, lang))
    lim = s.limiares
    partes.append("Limiares desta execução (decisões de projeto do Lutz, não padrões da literatura):" if pt else
                   "Thresholds of this run (Lutz design decisions, not literature standards):")
    partes.append(_tabela(["ID", t["valor"]], [[k, str(v)] for k, v in lim.model_dump().items()]))
    leg_baixa = [x for x in d["legibilidade"] if x["indice"] < lim.legibilidade_minima]
    if d["fora_do_corpus"] or leg_baixa or d["excedeu_contexto"]:
        partes.append("### Artigos com leitura limitada" if pt else "### Articles with limited reading")
        ll = []
        for a in d["fora_do_corpus"]:
            ll.append([a["chave"], ("fora da extração: " if pt else "excluded from extraction: ") + (a["erro"] or a["status"])])
        for a in d["excedeu_contexto"]:
            ll.append([a, "excedeu a janela de contexto de um extrator" if pt else "exceeded an extractor's context window"])
        for a in leg_baixa:
            ll.append([a["chave"], (f"índice de legibilidade {num(a['indice'], lang)}: recomenda-se extração humana"
                                    if pt else f"legibility index {num(a['indice'], lang)}: human extraction recommended")])
        partes.append(_tabela(["Artigo" if pt else "Article", "Motivo" if pt else "Reason"], ll))
    oculto = [x for x in d["legibilidade"] if x["frac_oculto"] > lim.texto_oculto_alerta]
    if oculto:
        partes.append(("Texto oculto descartado na ingestão (não chega aos extratores): " if pt else
                       "Hidden text discarded at ingestion (never reaches the extractors): ")
                      + ", ".join(f"{x['chave']} ({pct(x['frac_oculto'], lang, 1)})" for x in oculto))

    # ── 3 ──
    partes.append(f"## {t['p3']}")
    sp = t["sem_piloto"]
    cab = [t["campo"], t["tipo"], "Lutz × ouro (IC95%)" if pt else "Lutz × reference (95% CI)",
           "% conc." if pt else "% agr.", "Humano × humano" if pt else "Human × human", t["decisao"],
           "Alteradas na adjudicação" if pt else "Changed in adjudication", "% A / M / B" if pt else "% H / M / L",
           "Evid. exata" if pt else "Exact evid.", "Não rep." if pt else "Not rep.", "α (IC95%)" if pt else "α (95% CI)"]
    linhas = []
    notas = []
    for c in d["campos"]:
        o = c["ouro"]
        if o:
            sim = tx.METRICA[lang].get(o["nome"], o["nome"])
            v = pct(o["valor"], lang) if o["nome"] == "pct_equivalencia" else num(o["valor"], lang)
            ouro = f"{sim} {v} ({tx.ic(o['ic_inf'], o['ic_sup'], lang, porcento=o['nome'] == 'pct_equivalencia')})"
        else:
            ouro = sp
        hh = c["humano_humano"]
        hh_s = (pct(hh["valor"], lang) if hh and hh["nome"] == "pct_equivalencia" else num(hh["valor"], lang)) if hh else (
            sp if not d["calibracao"] else "—")
        dec = tx.DECISAO[lang][c["decisao"]["decisao"]] if c["decisao"] else sp
        ad = c["adjudicacao"]
        ad_s = f"{ad['alteradas']} / {ad['decididas']}" if ad and ad["decididas"] else "—"
        p = c["pct"]
        niv = " / ".join(pct(p[k], lang) for k in ("alta", "media", "baixa"))
        alfa = c["alfa"]
        if c["tipo"] == "texto":
            u = c["unanimes"] or {}
            alfa_s = (f"{pct(u.get('valor'), lang)} {'unânimes' if pt else 'unanimous'}" if u else "—")
        else:
            alfa_s = f"{num(alfa['valor'], lang)} ({tx.ic(alfa['ic_inf'], alfa['ic_sup'], lang)})" if alfa else "—"
        nr = c["nao_reportado"] or {}
        nr_s = pct(nr.get("valor"), lang) + (" ⚠" if nr.get("nota") else "")
        linhas.append([c["nome"], tx.TIPO[lang][c["tipo"]], ouro,
                       pct(c["ouro_concordancia"]["valor"], lang) if c["ouro_concordancia"] else sp,
                       hh_s, dec, ad_s, niv, pct(c["evidencia_exata"], lang), nr_s, alfa_s])
        if c["pabak"]:
            notas.append(f"{c['nome']}: PABAK {num(c['pabak']['valor'], lang)} — " + (
                "uma categoria domina as respostas; o kappa fica baixo mesmo com concordância alta."
                if pt else "one category dominates the answers; kappa is low even with high agreement."))
        if c["tipo"] == "numerico" and c["pct_exato"]:
            notas.append(f"{c['nome']}: " + (
                f"{pct(c['pct_exato']['valor'], lang)} dos valores iguais ao padrão-ouro (dentro da tolerância); "
                f"erro absoluto mediano {num(c['erro_mediano']['valor'], lang)}, máximo {num(c['erro_maximo']['valor'], lang)}."
                if pt else
                f"{pct(c['pct_exato']['valor'], lang)} of values equal to the reference (within tolerance); "
                f"median absolute error {num(c['erro_mediano']['valor'], lang)}, maximum {num(c['erro_maximo']['valor'], lang)}."))
        if nr.get("nota"):
            notas.append(f"{c['nome']}: " + ("muitos 'não reportado' — pode ser falha de leitura, não ausência real."
                                             if pt else "many 'not reported' — may be a reading failure, not true absence."))
        if c["decisao"] and c["decisao"].get("nota"):
            notas.append(f"{c['nome']}: {c['decisao']['nota']}")
        if alfa and alfa.get("nota") and ("abaixo" in alfa["nota"] or "entre" in alfa["nota"]):
            notas.append(f"{c['nome']}: α " + (alfa["nota"].split("; ", 1)[-1] if pt else
                         ("below 0.667: rewrite the field" if "abaixo" in alfa["nota"] else
                          "between 0.667 and 0.800: tentative conclusions only")))
    partes.append("A ordem das colunas segue o que pesa para quem avalia o artigo: acerto contra humanos primeiro, "
                   "consistência entre extratores por último." if pt else
                   "Columns follow what matters to a reviewer: accuracy against humans first, agreement among "
                   "extractors last.")
    partes.append(_tabela(cab, linhas))
    if notas:
        partes.append("\n".join(f"- {n}" for n in notas))
    partes.append("O alfa de Krippendorff e a % de células unânimes medem consistência entre os extratores, não "
                   "acerto: três extratores podem errar do mesmo jeito." if pt else
                   "Krippendorff's alpha and % unanimous cells measure consistency among extractors, not accuracy: "
                   "three extractors can make the same mistake.")

    # ── 4 ──
    partes.append(f"## {t['p4']}")
    cal = d["calibracao"]
    if cal:
        ll = []
        for niv in ("alta", "media", "baixa"):
            m = cal["niveis"].get(niv)
            if not m:
                continue
            ll.append([tx.NIVEL[lang][niv], str(m["n"]), m["nota"].split(" ")[0] if m["nota"] else "—",
                       f"{pct(m['valor'], lang, 1)} ({tx.ic(m['ic_inf'], m['ic_sup'], lang, porcento=True)})"])
        partes.append(_tabela([t["nivel"], t["celulas"], t["acertos"], t["taxa"]], ll))
        rod = [r for r in cal["rodadas"] if r["conjunto_piloto"] == "ajuste"]
        txt_rod = []
        for i, r in enumerate(rod, start=1):
            mud = r["mudancas"]
            desc = ("campos alterados: " + ", ".join(mud["alterados"]) if mud and mud["alterados"] else
                    "sem mudança no codebook") if pt else (
                "changed fields: " + ", ".join(mud["alterados"]) if mud and mud["alterados"] else "no codebook change")
            txt_rod.append(f"- {'Rodada' if pt else 'Round'} {i}: codebook v{r['versao']} ({r['hash']}) — {desc}")
        partes.append(f"Plano pré-registrado (hash {cal['hash_plano']}), semente {cal['semente']}, "
                       f"{cal['amostra'].get('ajuste', 0)} artigos de ajuste, {cal['amostra'].get('validacao', 0)} de "
                       f"validação e {cal['amostra'].get('reserva', 0)} de reserva. O piloto foi cego: as respostas do "
                       "Lutz ficaram ocultas até a importação das planilhas humanas."
                       if pt else
                       f"Pre-registered plan (hash {cal['hash_plano']}), seed {cal['semente']}, "
                       f"{cal['amostra'].get('ajuste', 0)} adjustment articles, {cal['amostra'].get('validacao', 0)} "
                       f"validation and {cal['amostra'].get('reserva', 0)} reserve. The pilot was blinded: Lutz answers "
                       "stayed hidden until the human sheets were imported.")
        if txt_rod:
            partes.append("\n".join(txt_rod))
        if cal["forcada"]:
            partes.append("> " + ("O conjunto de validação foi executado mais de uma vez (--forcar)." if pt else
                                  "The validation set was run more than once (--forcar)."))
        alta = cal["niveis"].get("alta")
        if alta and alta.get("valor") is not None and alta["valor"] < s.limiares.calibracao_alta_minima:
            partes.append("> " + (f"Células Alta acertaram menos de {pct(s.limiares.calibracao_alta_minima, lang)}: "
                                  "os limiares do Modo Autônomo estão frouxos para este corpus." if pt else
                                  f"High cells were right less than {pct(s.limiares.calibracao_alta_minima, lang)} of "
                                  "the time: the autonomous thresholds are too loose for this corpus."))
    else:
        partes.append(("Sem calibração: " if pt else "No calibration: ") + (d["motivo_sem_piloto"] if pt else {
            "não houve piloto": "there was no pilot"}.get(d["motivo_sem_piloto"], d["motivo_sem_piloto"])) + ".")

    # ── 5 ──
    partes.append(f"## {t['p5']}")
    adj = d["adjudicacao"]
    ll = [[tx.NIVEL[lang][n], str(v["enviadas"]), str(v["decididas"]), str(v["alteradas"]),
           pct(v["alteradas"] / v["decididas"], lang) if v["decididas"] else "—"]
          for n, v in sorted(adj["por_nivel"].items(), key=lambda x: ["baixa", "media", "alta"].index(x[0]))]
    ll.append(["Total", str(adj["total"]["enviadas"]), str(adj["total"]["decididas"]), str(adj["total"]["alteradas"]),
               pct(adj["total"]["alteradas"] / adj["total"]["decididas"], lang) if adj["total"]["decididas"] else "—"])
    partes.append(_tabela([t["nivel"], "Enviadas" if pt else "Sent", "Decididas" if pt else "Decided",
                           "Alteradas" if pt else "Changed", "% alteradas" if pt else "% changed"], ll))
    if adj["total"]["enviadas"] > adj["total"]["decididas"]:
        partes.append("> " + (f"{adj['total']['enviadas'] - adj['total']['decididas']} células ainda aguardam "
                              "adjudicação." if pt else
                              f"{adj['total']['enviadas'] - adj['total']['decididas']} cells still await adjudication."))
    aud = d["auditoria"]
    if aud and aud["conferidas"]:
        partes.append(f"Auditoria das células Alta: {aud['conferidas']} de {aud['n_amostra']} conferidas "
                       f"(amostra de {aud['n_alta']} Alta, semente {aud['semente']}); {aud['acertos']} corretas, "
                       f"acerto {pct(aud['taxa'], lang, 1)} (IC95% {tx.ic(aud['ic_inf'], aud['ic_sup'], lang, porcento=True)})."
                       if pt else
                       f"Audit of High cells: {aud['conferidas']} of {aud['n_amostra']} checked (out of {aud['n_alta']} "
                       f"High, seed {aud['semente']}); {aud['acertos']} correct, accuracy {pct(aud['taxa'], lang, 1)} "
                       f"(95% CI {tx.ic(aud['ic_inf'], aud['ic_sup'], lang, porcento=True)}).")
    elif sem_alta:
        partes.append("Auditoria das células Alta: não se aplica (nenhuma célula Alta)." if pt else
                      "Audit of High cells: not applicable (no High cell).")
    else:
        partes.append("Auditoria das células Alta: não realizada." if pt else "Audit of High cells: not done.")

    # ── 6 ──
    partes.append(f"## {t['p6']}")
    partes.append(tx.metodos(d, lang))

    # ── 7 ──
    partes.append(f"## {t['p7']}")
    partes.append(_tabela(["Item PRISMA 2020", "Onde está a resposta" if pt else "Where it is answered"],
                          [list(x) for x in tx.prisma(d, lang)]))
    partes.append("Anexos: A — codebook final e histórico de versões (inclui a origem de cada campo: manual ou "
                   "Assistente); B — tabela consolidada com nível, escore e evidência de cada célula; C — registro "
                   "completo: respostas de cada extrator, chamadas aos modelos e decisões de adjudicação e auditoria."
                   if pt else
                   "Annexes: A — final codebook and version history (including each field's origin: manual or "
                   "Assistant); B — consolidated table with level, score and evidence of every cell; C — full log: "
                   "answers of each extractor, model calls, adjudication and audit decisions.")
    partes.append(f"*{t['rascunho']}*")
    partes.append(tx.raise_declaracao(d, lang))
    return "\n\n".join(p for p in partes if p) + "\n"


# ── Markdown -> HTML (only the subset produced above) ───────────────────────


def _inline(texto: str) -> str:
    t = html.escape(texto)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = t.replace("  \n", "<br/>")
    return t


def md_para_html(md: str) -> str:
    out = []
    blocos = re.split(r"\n\s*\n", md.strip())
    for b in blocos:
        linhas = b.splitlines()
        if b.startswith("#"):
            n = len(b) - len(b.lstrip("#"))
            out.append(f"<h{n}>{_inline(b[n:].strip())}</h{n}>")
        elif linhas[0].startswith("|") and len(linhas) > 1 and set(linhas[1].replace("|", "")) <= {"-"}:
            def cel(linha):
                partes = re.split(r"(?<!\\)\|", linha.strip().strip("|"))
                return [p.replace("\\|", "|").strip() for p in partes]
            h = "".join(f"<th>{_inline(c)}</th>" for c in cel(linhas[0]))
            corpo = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cel(linha)) + "</tr>"
                            for linha in linhas[2:])
            out.append(f"<table><tr>{h}</tr>{corpo}</table>")
        elif all(linha.startswith("- ") for linha in linhas):
            out.append("<ul>" + "".join(f"<li>{_inline(linha[2:])}</li>" for linha in linhas) + "</ul>")
        elif b.startswith("> "):
            out.append(f"<blockquote>{_inline(' '.join(linha[2:] for linha in linhas))}</blockquote>")
        else:
            out.append(f"<p>{_inline(b)}</p>")
    return "\n".join(out)


CSS = """
body { font-family: sans-serif; font-size: 9pt; line-height: 1.35; color: #1f1e1d; }
h1 { font-size: 16pt; margin-bottom: 4pt; }
h2 { font-size: 12pt; margin-top: 12pt; border-bottom: 1px solid #ccc; }
h3 { font-size: 10pt; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0; }
th { background-color: #eef0f3; text-align: left; }
td, th { border: 1px solid #c8ccd2; padding: 2pt 3pt; font-size: 7.5pt; }
blockquote { background-color: #fff6e5; padding: 4pt; margin: 4pt 0; }
code { font-family: monospace; }
"""


def pdf(md: str, destino) -> None:
    html_doc = f"<html><body>{md_para_html(md)}</body></html>"
    story = pymupdf.Story(html_doc, user_css=CSS)
    escritor = pymupdf.DocumentWriter(str(destino))
    pagina = pymupdf.paper_rect("a4")
    area = pagina + (42, 42, -42, -42)
    mais = True
    while mais:
        dev = escritor.begin_page(pagina)
        mais, _ = story.place(area)
        story.draw(dev)
        escritor.end_page()
    escritor.close()
