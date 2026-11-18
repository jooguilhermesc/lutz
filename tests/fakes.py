"""Scripted fake LLM for tests: answers depend on (model, article key, field)."""

from __future__ import annotations

import json
import re

from lutz.llm import provedores

CODEBOOK = """
descricao: Codebook de teste
campos:
  - nome: desenho_estudo
    tipo: categorico
    valores: [experimental, observacional, revisao, outro]
    instrucao: Classifique o desenho principal do estudo.
    secoes: [Methods]
  - nome: tamanho_amostra
    tipo: numerico
    unidade: participantes
    faixa: [1, 100000]
    instrucao: Número total de participantes que completaram o estudo.
    secoes: [Methods]
    regras:
      - {tipo: soma_igual, campos: [n_intervencao, n_controle]}
  - nome: n_intervencao
    tipo: numerico
    unidade: participantes
    faixa: [0, 100000]
    instrucao: Participantes alocados no grupo de intervenção.
    secoes: [Methods]
  - nome: n_controle
    tipo: numerico
    unidade: participantes
    faixa: [0, 100000]
    instrucao: Participantes alocados no grupo controle.
    secoes: [Methods]
  - nome: limitacoes
    tipo: texto
    instrucao: Principal limitação declarada pelos autores do estudo.
"""

T_AMOSTRA = "A total of 212 participants completed the protocol."
T_GRUPOS = "Students were assigned to the intervention group (n = 106) or the control group (n = 106)."
T_DESENHO = "We conducted a randomized controlled trial in three public schools."
T_LIMIT = "The main limitation is the short follow-up of eight weeks."


def item(nome, valor=None, trecho=None, pagina=None, nr=False, unidades=()):
    return {"nome": nome, "valor": valor, "nao_reportado": nr, "unidades": list(unidades),
            "trecho": trecho, "pagina": pagina}


def padrao_silva(nome: str) -> dict:
    return {
        "desenho_estudo": item("desenho_estudo", "experimental", T_DESENHO, 2),
        "tamanho_amostra": item("tamanho_amostra", "212", T_AMOSTRA, 2),
        "n_intervencao": item("n_intervencao", "106", T_GRUPOS, 2),
        "n_controle": item("n_controle", "106", T_GRUPOS, 2),
        "limitacoes": item("limitacoes", "Short follow-up of eight weeks", T_LIMIT, 2),
    }[nome]


class Roteiro:
    """roteiro[modelo][(chave, campo)] = item dict; missing entries use the default answer."""

    def __init__(self, padrao=padrao_silva):
        self.padrao = padrao
        self.especifico: dict[str, dict] = {}
        self.chamadas: list[tuple[str, str]] = []
        self.malformar: set[tuple[str, str]] = set()
        self.veredito: dict[tuple[str, str], str] = {}
        self.ausencia: dict[tuple[str, str], str] = {}

    def definir(self, modelo, chave, campo, **kw):
        self.especifico.setdefault(modelo, {})[(chave, campo)] = item(campo, **kw)

    def __call__(self, cfg, req) -> str:
        chave_m = re.search(r"=== ARTICLE (\S+)", req.usuario)
        if req.sistema.startswith("You verify"):
            campo = re.search(r"Field 1: (\S+)", req.usuario).group(1)
            self.chamadas.append((cfg.modelo, f"V:{campo}"))
            ver = "sustenta"
            for (art, c), v in self.veredito.items():
                if c == campo and art in req.usuario:
                    ver = v
            return json.dumps({"veredito": ver, "justificativa": "teste"})
        if req.sistema.startswith("Extractors reported"):
            campo = re.search(r"Field 1: (\S+)", req.usuario).group(1)
            self.chamadas.append((cfg.modelo, f"A:{campo}"))
            return json.dumps({"veredito": self.ausencia.get(campo, "ausente"), "trecho": None,
                               "justificativa": "teste"})
        chave = chave_m.group(1)
        nomes = re.search(r"entries: ([^\n]+?)\.(?:\n|$)", req.usuario).group(1).split(", ")
        self.chamadas.append((cfg.modelo, chave))
        if (cfg.modelo, chave) in self.malformar and "previous answer was invalid" not in req.usuario:
            return "isto não é JSON"
        campos = []
        for n in nomes:
            esp = self.especifico.get(cfg.modelo, {}).get((chave, n))
            campos.append(esp if esp is not None else self.padrao(n))
        return json.dumps({"campos": campos})


def instalar(roteiro: Roteiro) -> None:
    provedores.registrar_fake("*", roteiro)
