"""Generate the reliability report and its annexes for one run.

Output: ``relatorios/execucao-<id>/`` with the report (md, pdf; pt, en), annexes A/B/C as CSV
and YAML, ``metricas.csv``, ``execucao.json`` and ``manifest.json`` (SHA-256 of every file).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from lutz.core.db import agora, jload, transacao
from lutz.core.project import Projeto
from lutz.report import render
from lutz.report.dados import coletar


def _csv(destino: Path, cab: list[str], linhas) -> None:
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cab)
        for linha in linhas:
            w.writerow(["" if x is None else x for x in linha])


def tabela_longa(con, execucao_id: int):
    cab = ["artigo", "titulo", "campo", "valor_final", "nao_reportado", "nivel", "escore", "a", "e", "v",
           "trecho", "pagina", "unidades", "origem", "motivos"]
    linhas = []
    for r in con.execute(
        """SELECT a.chave, a.titulo, c.* FROM celula c JOIN artigo a ON a.id=c.artigo_id JOIN campo cp ON cp.id=c.campo_id
           WHERE c.execucao_id=? ORDER BY a.chave, cp.ordem""", (execucao_id,)):
        linhas.append([r["chave"], r["titulo"], r["campo_chave"], r["valor_final"], int(r["nao_reportado"]),
                       r["nivel"], r["escore"], r["a"], r["e"], r["v"], r["trecho"], r["pagina"],
                       " ".join(jload(r["unidades"], [])), r["origem"], "; ".join(jload(r["motivos"], []))])
    return cab, linhas


def tabela_larga(con, execucao_id: int):
    campos = [r[0] for r in con.execute(
        """SELECT DISTINCT c.campo_chave FROM celula c JOIN campo cp ON cp.id=c.campo_id WHERE c.execucao_id=?
           ORDER BY cp.ordem""", (execucao_id,))]
    cab = ["artigo", "titulo"]
    for c in campos:
        cab += [c, f"{c}__nivel", f"{c}__trecho", f"{c}__pagina"]
    por_art: dict[str, dict] = {}
    titulos = {}
    for r in con.execute("""SELECT a.chave, a.titulo, c.* FROM celula c JOIN artigo a ON a.id=c.artigo_id
                            WHERE c.execucao_id=?""", (execucao_id,)):
        titulos[r["chave"]] = r["titulo"]
        valor = "não reportado" if r["nao_reportado"] else r["valor_final"]
        por_art.setdefault(r["chave"], {})[r["campo_chave"]] = (valor, r["nivel"], r["trecho"], r["pagina"])
    linhas = []
    for chave in sorted(por_art):
        linha = [chave, titulos[chave]]
        for c in campos:
            linha += list(por_art[chave].get(c, (None, None, None, None)))
        linhas.append(linha)
    return cab, linhas


def gerar(projeto: Projeto, con, execucao_id: int, idiomas=None, formatos=None) -> dict:
    d = coletar(projeto, con, execucao_id)
    s = d["settings"]
    idiomas = idiomas or s.relatorio.idiomas
    formatos = formatos or s.relatorio.formatos
    pasta = projeto.relatorios / f"execucao-{execucao_id:04d}"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos: list[Path] = []

    for lang in idiomas:
        md = render.markdown(d, lang)
        if "md" in formatos:
            p = pasta / f"relatorio_{lang}.md"
            p.write_text(md, encoding="utf-8")
            arquivos.append(p)
        if "pdf" in formatos:
            p = pasta / f"relatorio_{lang}.pdf"
            render.pdf(md, p)
            arquivos.append(p)

    cb = d["codebook"]
    p = pasta / f"anexo_A_codebook_v{d['codebook_row']['versao']}.yaml"
    p.write_text(cb.para_yaml(), encoding="utf-8")
    arquivos.append(p)
    p = pasta / "anexo_A_historico.csv"
    _csv(p, ["versao", "hash", "origem", "congelado", "congelado_em", "criado_em", "campos", "campos_do_assistente",
             "execucoes", "nota"],
         [[h["versao"], h["hash"], h["origem"], h["congelado"], h["congelado_em"], h["criado_em"], h["n_campos"],
           h["n_assistente"], " ".join(map(str, h["execucoes"])), h["nota"]] for h in d["historico_codebook"]])
    arquivos.append(p)
    p = pasta / "anexo_A_origem_campos.csv"
    _csv(p, ["campo", "tipo", "papel", "origem", "hash"], [[c.nome, c.tipo, c.papel, c.origem, c.hash()] for c in cb.campos])
    arquivos.append(p)

    cab, linhas = tabela_longa(con, execucao_id)
    p = pasta / "anexo_B_tabela_longa.csv"
    _csv(p, cab, linhas)
    arquivos.append(p)
    cab, linhas = tabela_larga(con, execucao_id)
    p = pasta / "anexo_B_tabela_larga.csv"
    _csv(p, cab, linhas)
    arquivos.append(p)

    p = pasta / "anexo_C_respostas_extratores.csv"
    _csv(p, ["artigo", "campo", "extrator", "status", "valor", "valor_normalizado", "nao_reportado", "trecho",
             "pagina", "unidades", "e", "e_detalhe", "regras_ok", "regras_detalhe", "erro", "chamada_id"],
         [[r["chave"], r["campo_chave"], r["rotulo"], r["status"], r["valor"], r["valor_normalizado"],
           r["nao_reportado"], r["trecho"], r["pagina"], " ".join(jload(r["unidades"], [])), r["e"], r["e_detalhe"],
           r["regras_ok"], r["regras_detalhe"], r["erro"], r["chamada_id"]]
          for r in con.execute("""SELECT a.chave, c.campo_chave, b.* FROM extracao_bruta b JOIN celula c ON c.id=b.celula_id
                                  JOIN artigo a ON a.id=c.artigo_id WHERE c.execucao_id=?
                                  ORDER BY a.chave, c.campo_chave, b.rotulo""", (execucao_id,))])
    arquivos.append(p)
    p = pasta / "anexo_C_chamadas.csv"
    _csv(p, ["id", "papel", "rotulo", "artigo", "grupo", "provedor", "modelo_pedido", "modelo_observado",
             "fingerprint", "tokens_entrada", "tokens_saida", "custo_usd", "latencia_ms", "status", "erro",
             "tentativas", "cache", "hash_requisicao", "criado_em"],
         [[r["id"], r["papel"], r["rotulo"], r["chave"], r["grupo"], r["provedor"], r["modelo_pedido"],
           r["modelo_observado"], r["fingerprint"], r["tokens_entrada"], r["tokens_saida"], r["custo_usd"],
           r["latencia_ms"], r["status"], r["erro"], r["tentativas"], r["cache"], r["hash_requisicao"], r["criado_em"]]
          for r in con.execute("""SELECT l.*, a.chave FROM chamada_llm l LEFT JOIN artigo a ON a.id=l.artigo_id
                                  WHERE l.execucao_id=? ORDER BY l.id""", (execucao_id,))])
    arquivos.append(p)
    p = pasta / "anexo_C_adjudicacoes.csv"
    _csv(p, ["artigo", "campo", "motivo", "valor_anterior", "nao_reportado_anterior", "valor_decidido",
             "nao_reportado", "alterou", "justificativa", "decidido_em"],
         [[r["chave"], r["campo_chave"], r["motivo"], r["valor_anterior"], r["nao_reportado_anterior"],
           r["valor_decidido"], r["nao_reportado"], r["alterou"], r["justificativa"], r["decidido_em"]]
          for r in con.execute("""SELECT a.chave, c.campo_chave, j.* FROM adjudicacao j JOIN celula c ON c.id=j.celula_id
                                  JOIN artigo a ON a.id=c.artigo_id WHERE c.execucao_id=? ORDER BY j.id""", (execucao_id,))])
    arquivos.append(p)
    p = pasta / "anexo_C_auditoria.csv"
    _csv(p, ["artigo", "campo", "valor_lutz", "correto", "valor_correto", "nao_reportado_correto", "nota", "conferido_em"],
         [[r["chave"], r["campo_chave"], r["valor_final"], r["correto"], r["valor_correto"], r["nao_reportado_correto"],
           r["nota"], r["conferido_em"]]
          for r in con.execute("""SELECT a.chave, c.campo_chave, c.valor_final, i.* FROM auditoria_item i
                                  JOIN auditoria u ON u.id=i.auditoria_id JOIN celula c ON c.id=i.celula_id
                                  JOIN artigo a ON a.id=c.artigo_id WHERE u.execucao_id=?""", (execucao_id,))])
    arquivos.append(p)
    p = pasta / "metricas.csv"
    _csv(p, ["escopo", "campo", "nome", "valor", "ic_inf", "ic_sup", "n", "par", "nota", "execucao_id", "piloto_id"],
         [[r["escopo"], r["campo_chave"], r["nome"], r["valor"], r["ic_inf"], r["ic_sup"], r["n"], r["par"], r["nota"],
           r["execucao_id"], r["piloto_id"]]
          for r in con.execute("SELECT * FROM metrica WHERE execucao_id IN (?, ?) ORDER BY escopo, campo_chave, nome",
                               (execucao_id, (d["calibracao"] or {}).get("validacao_id", -1)))])
    arquivos.append(p)
    p = pasta / "execucao.json"
    ex = dict(d["execucao"])
    ex["config"] = jload(ex["config"])
    ex["artigos"] = [a["chave"] for a in d["artigos"]]
    ex["campos"] = jload(ex["campos"])
    p.write_text(json.dumps({"execucao": ex, "extratores": d["extratores"],
                             "codebook": {"versao": d["codebook_row"]["versao"], "hash": d["codebook_row"]["hash"]},
                             "piloto": (d["calibracao"] or {}).get("hash_plano")},
                            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    arquivos.append(p)

    manifesto = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in arquivos}
    (pasta / "manifest.json").write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    with transacao(con):
        for f in arquivos:
            if f.name.startswith("relatorio_"):
                lang = f.stem.split("_")[1]
                con.execute("INSERT INTO relatorio (execucao_id, idioma, formato, caminho, hash, gerado_em) "
                            "VALUES (?,?,?,?,?,?)", (execucao_id, lang, f.suffix[1:], projeto.rel(f),
                                                     manifesto[f.name], agora()))
    return {"pasta": str(pasta), "arquivos": [f.name for f in arquivos], "manifesto": manifesto}
