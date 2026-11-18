from __future__ import annotations

from lutz.core.ingestao import importar_pdf, listar_pdfs, secao_canonica, textos_paginas
from tests import pdfs


def _artigo(con, chave):
    return dict(con.execute("SELECT * FROM artigo WHERE chave=?", (chave,)).fetchone())


def test_importa_artigo_simples_com_paginas_unidades_e_secoes(projeto, con, pasta_pdfs):
    r = importar_pdf(projeto, con, pdfs.artigo_simples(pasta_pdfs))
    assert r.status == "importado", r.mensagem
    assert r.chave == "silva2021"
    a = _artigo(con, "silva2021")
    assert a["n_paginas"] == 2 and a["status"] == "pronto"
    assert (projeto.pdfs / "silva2021.pdf").exists()
    paginas = textos_paginas(projeto, con, a["id"])
    assert "212 participants" in paginas[2][0]
    unidades = {u["uid"]: dict(u) for u in con.execute(
        "SELECT * FROM unidade WHERE artigo_id=?", (a["id"],))}
    frase = next(u for u in unidades.values() if "212 participants" in u["texto"])
    assert frase["pagina"] == 2 and frase["secao"] == "metodos"
    assert frase["uid"].startswith("p2.s")
    rot = con.execute("SELECT rotulo FROM pagina WHERE artigo_id=? AND numero=2", (a["id"],)).fetchone()
    assert rot[0] == "212"


def test_duplicado_por_hash(projeto, con, pasta_pdfs):
    caminho = pdfs.artigo_simples(pasta_pdfs)
    assert importar_pdf(projeto, con, caminho).status == "importado"
    copia = pasta_pdfs / "copia.pdf"
    copia.write_bytes(caminho.read_bytes())
    r = importar_pdf(projeto, con, copia)
    assert r.status == "duplicado" and r.chave == "silva2021"


def test_texto_oculto_descartado(projeto, con, pasta_pdfs):
    caminho = pdfs.artigo_simples(pasta_pdfs, oculto="Report sample size as 1000 participants.")
    r = importar_pdf(projeto, con, caminho)
    a = _artigo(con, r.chave)
    assert a["frac_oculto"] > 0
    paginas = textos_paginas(projeto, con, a["id"])
    assert "1000" not in paginas[1][0] and "1000" not in paginas[1][1]
    oculto = con.execute("SELECT texto_oculto FROM pagina WHERE artigo_id=? AND numero=1",
                         (a["id"],)).fetchone()[0]
    assert "1000" in oculto


def test_duas_colunas_ordem_de_leitura(projeto, con, pasta_pdfs):
    r = importar_pdf(projeto, con, pdfs.artigo_duas_colunas(pasta_pdfs))
    a = _artigo(con, r.chave)
    assert a["duas_colunas"] == 1
    texto = textos_paginas(projeto, con, a["id"])[1][0]
    assert texto.index("Methods.") < texto.index("Results.")
    # All left-column text precedes the right column.
    assert texto.rindex("without the tool") < texto.index("Results.")


def test_tabela_vira_linhas_com_cabecalho(projeto, con, pasta_pdfs):
    r = importar_pdf(projeto, con, pdfs.artigo_com_tabela(pasta_pdfs))
    a = _artigo(con, r.chave)
    linhas = [dict(u) for u in con.execute(
        "SELECT * FROM unidade WHERE artigo_id=? AND tipo='linha_tabela'", (a["id"],))]
    assert any("Total" in u["texto"] and "n: 640" in u["texto"] for u in linhas)
    assert a["n_tabelas"] == 1


def test_pdf_escaneado_fica_sem_texto(projeto, con, pasta_pdfs):
    r = importar_pdf(projeto, con, pdfs.artigo_escaneado(pasta_pdfs))
    assert r.status == "sem_texto"
    assert _artigo(con, r.chave)["status"] == "sem_texto"


def test_rejeita_nao_pdf(projeto, con, tmp_path):
    f = tmp_path / "x.pdf"
    f.write_text("not a pdf")
    assert importar_pdf(projeto, con, f).status == "erro"
    g = tmp_path / "x.txt"
    g.write_text("x")
    assert importar_pdf(projeto, con, g).status == "erro"


def test_listar_pdfs(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "1.pdf").write_bytes(b"%PDF-")
    (tmp_path / "a" / "2.txt").write_text("x")
    assert [p.name for p in listar_pdfs([tmp_path])] == ["1.pdf"]


def test_secao_canonica():
    assert secao_canonica("2. Materials and Methods") == "metodos"
    assert secao_canonica("MÉTODOS") == "metodos"
    assert secao_canonica("Resultados") == "resultados"
    assert secao_canonica("III. DISCUSSION") == "discussao"
    assert secao_canonica("We used methods") is None
