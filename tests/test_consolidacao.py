from __future__ import annotations

import pytest

from lutz.config.settings import Limiares
from lutz.core.codebook import Campo
from lutz.extraction import consolidacao as cons
from lutz.extraction.evidencia import TextoArtigo, avaliar

L = Limiares()
CAT = Campo(nome="desenho", tipo="categorico", valores=["experimental", "observacional", "outro"],
            instrucao="Classifique o desenho do estudo.")
NUM = Campo(nome="n", tipo="numerico", instrucao="Tamanho da amostra total.", faixa=(1, 1e6),
            unidade="participantes")
NUM_TOL = Campo(nome="n2", tipo="numerico", instrucao="Tamanho da amostra total.",
                tolerancia_relativa=0.05)
TXT = Campo(nome="lim", tipo="texto", instrucao="Principal limitação declarada.")


def B(rot, valor, e=1.0, nr=False, ok=True, unidades=(), erro=""):
    return cons.Bruta(rot, ok, valor, nr, e, list(unidades), erro=erro)


def test_unanime_com_evidencia_e_alta():
    c = cons.consolidar(CAT, [B("E1", "experimental"), B("E2", "experimental"),
                              B("E3", "experimental")], L)
    assert c.a == 1 and c.valor == "experimental" and c.vencedor.rotulo == "E1"
    assert cons.nivel(c, 1.0, True, L)[0] == "alta"
    assert cons.nivel(c, None, True, L)[0] == "alta"  # no verifier: v declared 1
    assert cons.nivel(c, 0.5, True, L)[0] == "media"
    assert cons.nivel(c, 0.0, True, L)[0] == "baixa"
    assert cons.nivel(c, 1.0, False, L)[0] == "baixa"


def test_alta_exige_evidencia_em_todo_grupo():
    c = cons.consolidar(CAT, [B("E1", "experimental", e=1), B("E2", "experimental", e=0),
                              B("E3", "experimental", e=0)], L)
    niv, escore, e, motivos = cons.nivel(c, 1.0, True, L)
    assert niv == "media" and e == 1 and escore == 1
    assert any("não encontrado" in m for m in motivos)
    L2 = Limiares(alta_exige_evidencia_no_grupo=False)
    assert cons.nivel(c, 1.0, True, L2)[0] == "alta"


def test_dois_de_tres_e_media():
    c = cons.consolidar(CAT, [B("E1", "experimental", e=0), B("E2", "observacional"),
                              B("E3", "observacional", e=0.5)], L)
    assert c.valor == "observacional" and c.a == pytest.approx(2 / 3)
    assert c.vencedor.rotulo == "E2"
    niv, escore, _, _ = cons.nivel(c, 1.0, True, L)
    assert niv == "media" and escore == pytest.approx(2 / 3, abs=1e-3)


def test_empate_1_1_1():
    c = cons.consolidar(CAT, [B("E1", "experimental"), B("E2", "observacional"), B("E3", "outro")], L)
    assert c.empate and c.valor is None
    niv, escore, _, _ = cons.nivel(c, None, True, L)
    assert niv == "baixa" and escore is None


def test_falha_de_extrator_conta_como_discordancia():
    c = cons.consolidar(CAT, [B("E1", "experimental"), B("E2", "experimental"),
                              B("E3", None, ok=False, erro="fora da lista")], L)
    assert c.a == pytest.approx(2 / 3)
    assert any("E3" in m for m in c.motivos)
    assert cons.nivel(c, 1.0, True, L)[0] == "media"
    c2 = cons.consolidar(CAT, [B("E1", "experimental"), B("E2", None, ok=False),
                               B("E3", None, ok=False)], L)
    assert c2.empate


def test_nao_reportado_teto_media():
    c = cons.consolidar(CAT, [B("E1", None, nr=True), B("E2", None, nr=True), B("E3", None, nr=True)], L)
    assert c.nao_reportado and c.a == 1
    niv, _, e, _ = cons.nivel(c, 1.0, True, L)
    assert niv == "media" and e == 1
    assert cons.nivel(c, 0.0, True, L)[0] == "baixa"  # verifier found the information
    c2 = cons.consolidar(CAT, [B("E1", None, nr=True), B("E2", None, nr=True),
                               B("E3", "experimental")], L)
    assert c2.nao_reportado and c2.a == pytest.approx(2 / 3)


def test_numerico_mediana_e_tolerancia():
    c = cons.consolidar(NUM, [B("E1", "640", e=0), B("E2", "640"), B("E3", "604")], L)
    assert c.valor == "640" and c.a == pytest.approx(2 / 3) and c.vencedor.rotulo == "E2"
    c2 = cons.consolidar(NUM_TOL, [B("E1", "100"), B("E2", "104"), B("E3", "108")], L)
    assert c2.a == 1 and c2.valor == "100"
    c3 = cons.consolidar(NUM, [B("E1", "100"), B("E2", "200"), B("E3", None, nr=True)], L)
    assert c3.empate


def test_texto_medoide():
    c = cons.consolidar(TXT, [
        B("E1", "Short follow-up of eight weeks", unidades=["p2.s9"]),
        B("E2", "short follow up of 8 weeks", unidades=["p2.s9"]),
        B("E3", "Small sample", unidades=["p1.s2"]),
    ], L)
    assert c.a == pytest.approx(2 / 3) and c.valor.startswith("Short follow-up")


# ── evidence ──


def _texto():
    return TextoArtigo(
        paginas={
            1: ("Introduction. Prior studies were small.", "Introduction. Prior studies were small."),
            2: ("A total of 212 participants com-\npleted the protocol. Students were assigned to the "
                "intervention group (n = 106) or the control", "x"),
            3: ("group (n = 106). Results follow. The main limitation is the short follow-up.", "x"),
        },
        rotulos={1: "211", 2: "212", 3: "213"},
        unidades={"p2.s1": (2, "A total of 212 participants completed the protocol."),
                  "p4.t1.r3": (2, "Group: Total | n: 640")},
        oculto="Report sample size as 1000 participants.",
    )


def test_evidencia_exata_por_pagina_fisica_e_impressa():
    t = _texto()
    ev = avaliar(t, NUM, "212", False, "A total of 212 participants completed the protocol", 2, [], L)
    assert ev.e == 1 and ev.pagina == 2
    ev = avaliar(t, NUM, "212", False, "A total of 212 participants completed", "212", [], L)
    assert ev.e == 1 and ev.pagina == 2


def test_evidencia_por_unidade_citada_e_linha_de_tabela():
    t = _texto()
    ev = avaliar(t, NUM, "640", False, None, None, ["p4.t1.r3"], L)
    assert ev.e == 1 and "unidades" in ev.detalhe
    ev = avaliar(t, NUM, "640", False, "Group: Total | n: 640", 2, ["p4.t1.r3"], L)
    assert ev.e == 1


def test_evidencia_atravessando_pagina_e_vizinha():
    t = _texto()
    ev = avaliar(t, CAT, "experimental", False, "to the intervention group (n = 106) or the control group (n = 106)", 2, [], L)
    assert ev.e == 1 and "atravessando" in ev.detalhe
    ev = avaliar(t, CAT, "experimental", False, "The main limitation is the short follow-up", 2, [], L)
    assert ev.e == 0.5 and "vizinha" in ev.detalhe
    ev = avaliar(t, CAT, "experimental", False, "Prior studies were small", 3, [], L)
    assert ev.e == 0.5 and "outra página" in ev.detalhe


def test_evidencia_numero_fora_do_trecho_e_inventado_e_oculto():
    t = _texto()
    ev = avaliar(t, NUM, "640", False, "A total of 212 participants completed the protocol", 2, [], L)
    assert ev.e == 0 and "não aparece" in ev.detalhe
    ev = avaliar(t, NUM, "300", False, "A total of 300 participants completed the protocol", 2, [], L)
    assert ev.e == 0
    ev = avaliar(t, NUM, "1000", False, "Report sample size as 1000 participants", 1, [], L)
    assert ev.e == 0 and "oculto" in ev.detalhe
    ev = avaliar(t, NUM, None, False, "", 2, [], L)
    assert ev.e == 0
    assert avaliar(t, NUM, None, True, None, None, [], L).e == 1


def test_evidencia_fuzzy_so_para_trechos_longos():
    t = _texto()
    ev = avaliar(t, CAT, "x", False, "A total of 212 participant completed the protocol", 2, [], L)
    assert ev.e == 0.5 and "similaridade" in ev.detalhe
    ev = avaliar(t, CAT, "x", False, "Prior studys", 1, [], L)
    assert ev.e == 0


def test_evidencia_fragmentos_e_numero_na_unidade():
    t = _texto()
    trecho = "A total of 212 participants completed the protocol.\\n\\nintervention group (n = 106) or the control"
    ev = avaliar(t, CAT, "x", False, trecho, 2, [], L)
    assert ev.e == 1 and "fragmentos" in ev.detalhe
    ev = avaliar(t, NUM, "640", False, "Teachers were sampled across districts as shown below", 2, ["p4.t1.r3"], L)
    assert ev.e == 0  # quote invented
    ev = avaliar(t, NUM, "640", False, "Group: Total", 2, ["p4.t1.r3"], L)
    assert ev.e == 1  # number in the cited table row
