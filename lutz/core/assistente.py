"""Codebook Assistant: turns the research question into a typed, testable codebook.

The Assistant suggests; the researcher decides. Nothing enters the codebook without
confirmation, and every accepted suggestion is stored with ``origem: assistente``.

* Starting templates per area (no LLM, free).
* Field suggestions from the research question (one LLM call, validated by Pydantic; invalid
  suggestions are dropped with the reason).
* Semantic lint (one LLM call): ambiguous instructions, overlapping categories, incomplete
  coverage — checks that a deterministic lint cannot do.

The LLM used is ``J`` when configured, otherwise ``V``, otherwise ``E1``.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from lutz.config.settings import ModeloPapel, Settings
from lutz.core.codebook import Campo, Codebook
from lutz.core.errors import LutzError
from lutz.core.project import Projeto
from lutz.llm.cliente import ClienteLLM
from lutz.llm.provedores import Requisicao, extrair_json

MODELOS: dict[str, dict] = {
    "ensaio_clinico": {
        "rotulo": "Ensaio clínico",
        "campos": [
            {"nome": "desenho_estudo", "tipo": "categorico",
             "valores": ["ensaio_randomizado", "ensaio_nao_randomizado", "crossover", "cluster", "outro"],
             "instrucao": "Classifique o desenho do ensaio conforme descrito nos Métodos.", "secoes": ["Methods"]},
            {"nome": "tamanho_amostra", "tipo": "numerico", "unidade": "participantes", "faixa": [1, 1000000],
             "instrucao": "Número total de participantes randomizados.", "secoes": ["Methods", "Results"]},
            {"nome": "intervencao", "tipo": "texto", "instrucao": "Descreva a intervenção aplicada ao grupo experimental.",
             "secoes": ["Methods"]},
            {"nome": "comparador", "tipo": "categorico", "valores": ["placebo", "tratamento_ativo", "cuidado_usual", "sem_intervencao", "outro"],
             "instrucao": "Tipo de comparador usado no grupo controle.", "secoes": ["Methods"]},
            {"nome": "desfecho_primario", "tipo": "texto", "instrucao": "Desfecho primário declarado pelos autores.",
             "secoes": ["Methods"]},
            {"nome": "risco_vies_randomizacao", "tipo": "ordinal", "valores": ["baixo", "algumas_preocupacoes", "alto"],
             "papel": "risco_vies", "instrucao": "Julgue o risco de viés do processo de randomização (domínio 1 do RoB 2).",
             "secoes": ["Methods"]},
        ],
    },
    "observacional": {
        "rotulo": "Estudo observacional",
        "campos": [
            {"nome": "desenho_estudo", "tipo": "categorico", "valores": ["coorte", "caso_controle", "transversal", "outro"],
             "instrucao": "Classifique o desenho do estudo observacional.", "secoes": ["Methods"]},
            {"nome": "tamanho_amostra", "tipo": "numerico", "unidade": "participantes", "faixa": [1, 100000000],
             "instrucao": "Número de participantes incluídos na análise principal.", "secoes": ["Methods", "Results"]},
            {"nome": "pais", "tipo": "texto", "instrucao": "País ou países onde os dados foram coletados.",
             "secoes": ["Methods"]},
            {"nome": "exposicao", "tipo": "texto", "instrucao": "Exposição principal estudada.", "secoes": ["Methods"]},
            {"nome": "ajuste_confundidores", "tipo": "categorico", "valores": ["sim", "nao"],
             "instrucao": "A análise principal ajustou para confundidores?", "secoes": ["Methods"]},
        ],
    },
    "escopo": {
        "rotulo": "Revisão de escopo",
        "campos": [
            {"nome": "tipo_estudo", "tipo": "categorico",
             "valores": ["empirico_quantitativo", "empirico_qualitativo", "metodos_mistos", "revisao", "teorico", "outro"],
             "instrucao": "Classifique o tipo de estudo.", "secoes": ["Methods"]},
            {"nome": "populacao", "tipo": "texto", "instrucao": "População ou participantes estudados."},
            {"nome": "conceito", "tipo": "texto", "instrucao": "Conceito central investigado no estudo."},
            {"nome": "contexto", "tipo": "texto", "instrucao": "Contexto (país, setor, ambiente) do estudo."},
            {"nome": "ano_coleta", "tipo": "numerico", "unidade": "ano", "faixa": [1900, 2100],
             "instrucao": "Ano em que os dados foram coletados (último ano, se houver período).", "secoes": ["Methods"]},
        ],
    },
    "educacao": {
        "rotulo": "Educação",
        "campos": [
            {"nome": "desenho_estudo", "tipo": "categorico",
             "valores": ["experimental", "quase_experimental", "observacional", "qualitativo", "metodos_mistos", "outro"],
             "instrucao": "Classifique o desenho principal do estudo.", "secoes": ["Methods"]},
            {"nome": "nivel_ensino", "tipo": "categorico",
             "valores": ["educacao_infantil", "ensino_fundamental", "ensino_medio", "ensino_superior", "pos_graduacao", "misto"],
             "instrucao": "Nível de ensino dos participantes.", "secoes": ["Methods"]},
            {"nome": "tamanho_amostra", "tipo": "numerico", "unidade": "participantes", "faixa": [1, 1000000],
             "instrucao": "Número total de participantes analisados.", "secoes": ["Methods", "Results"]},
            {"nome": "instrumento_coleta", "tipo": "categorico",
             "valores": ["questionario", "teste", "entrevista", "observacao", "logs_sistema", "misto", "outro"],
             "instrucao": "Principal instrumento de coleta de dados.", "secoes": ["Methods"]},
            {"nome": "limitacoes", "tipo": "texto", "instrucao": "Principal limitação declarada pelos autores."},
        ],
    },
    "engenharia": {
        "rotulo": "Engenharia",
        "campos": [
            {"nome": "tipo_contribuicao", "tipo": "categorico",
             "valores": ["metodo", "ferramenta", "estudo_empirico", "estudo_de_caso", "revisao", "outro"],
             "instrucao": "Tipo principal de contribuição do artigo."},
            {"nome": "metodo_avaliacao", "tipo": "categorico",
             "valores": ["experimento_controlado", "benchmark", "estudo_de_caso", "survey", "simulacao", "sem_avaliacao", "outro"],
             "instrucao": "Como a contribuição foi avaliada.", "secoes": ["Methods", "Results"]},
            {"nome": "conjunto_dados", "tipo": "texto", "instrucao": "Conjunto(s) de dados ou sistemas usados na avaliação."},
            {"nome": "metrica_principal", "tipo": "texto", "instrucao": "Métrica principal de desempenho reportada."},
            {"nome": "disponibilidade_artefatos", "tipo": "categorico", "valores": ["codigo_e_dados", "so_codigo", "so_dados", "nenhum"],
             "instrucao": "Os autores disponibilizam código e/ou dados?"},
        ],
    },
}


def modelo_de_partida(area: str) -> list[Campo]:
    if area not in MODELOS:
        raise LutzError(f"Modelo desconhecido: {area}. Opções: {', '.join(MODELOS)}")
    return [Campo.model_validate({**c, "origem": "assistente"}) for c in MODELOS[area]["campos"]]


def _modelo_assistente(settings: Settings) -> tuple[str, ModeloPapel]:
    m = settings.modelos
    if m.J:
        return "J", m.J
    if m.V:
        return "V", m.V
    return "E1", m.E1


SISTEMA_SUGESTAO = """\
You help a researcher write the extraction form (codebook) of a systematic review. Propose
fields that answer the research question. Each field has: nome (snake_case, lowercase ASCII),
rotulo (short label in the language of the question), tipo (categorico | ordinal | numerico |
texto), valores (for categorico/ordinal; ordered for ordinal; include a residual value such as
"outro" for categorico when categories may not cover every case), instrucao (one clear request
in the language of the question; never two requests in one field), definicoes (object value ->
operational definition, for categorico/ordinal), secoes (where to look: Methods, Results...),
unidade and faixa [min, max] for numerico. Prefer categorical fields over free text: they are
easier to validate. Do not include a value for "not reported"; that is handled separately.
Answer with one JSON object {"campos": [...]}."""

SISTEMA_LINT = """\
You review the extraction form (codebook) of a systematic review before it is used. For each
problem you find, report: campo (field name), codigo, severidade (aviso | sugestao) and mensagem
(one sentence in Portuguese). Codes: S001 ambiguous instruction; S002 categories that overlap;
S003 categories that do not cover all cases; S004 two requests in one field; S005 ordinal
values without a clear order; S006 free-text field that could be categorical. Report only real
problems. Answer with one JSON object {"achados": [...]}."""


def sugerir_campos(projeto: Projeto, settings: Settings, *, pergunta: str, componentes: dict[str, str] | None = None,
                   tipo_revisao: str = "sistematica", variaveis: list[str] | None = None,
                   existentes: list[str] | None = None) -> dict:
    rot, cfg = _modelo_assistente(settings)
    partes = [f"Research question: {pergunta}", f"Review type: {tipo_revisao}"]
    for k, v in (componentes or {}).items():
        if v:
            partes.append(f"{k}: {v}")
    if variaveis:
        partes.append("Variables the researcher already has in mind: " + "; ".join(variaveis))
    if existentes:
        partes.append("Fields that already exist (do not repeat): " + ", ".join(existentes))
    req = Requisicao(SISTEMA_SUGESTAO, "\n".join(partes))
    cliente = ClienteLLM(projeto, settings)
    try:
        res = cliente.chamar(papel="assistente", rotulo=rot, cfg=cfg, req=req, execucao_id=None, artigo_id=None)
    finally:
        cliente.fechar()
    if res.resposta is None:
        raise LutzError(f"O Assistente não respondeu: {res.erro}")
    try:
        bruto = extrair_json(res.resposta.texto).get("campos", [])
    except ValueError as exc:
        raise LutzError(f"Resposta do Assistente malformada: {exc}") from exc
    aceitos, descartados = [], []
    for item in bruto if isinstance(bruto, list) else []:
        if not isinstance(item, dict):
            continue
        item = {k: v for k, v in item.items() if k in Campo.model_fields}
        item["origem"] = "assistente"
        if item.get("nome") in (existentes or []):
            continue
        try:
            aceitos.append(Campo.model_validate(item))
        except ValidationError as exc:
            descartados.append({"campo": item.get("nome"), "motivo": exc.errors()[0]["msg"]})
    return {"campos": aceitos, "descartados": descartados, "chamada_id": res.chamada_id}


def lint_semantico(projeto: Projeto, settings: Settings, cb: Codebook) -> list[dict]:
    rot, cfg = _modelo_assistente(settings)
    corpo = json.dumps([c.model_dump(mode="json", exclude={"origem"}) for c in cb.campos], ensure_ascii=False, indent=1)
    cliente = ClienteLLM(projeto, settings)
    try:
        res = cliente.chamar(papel="lint", rotulo=rot, cfg=cfg, req=Requisicao(SISTEMA_LINT, corpo),
                             execucao_id=None, artigo_id=None)
    finally:
        cliente.fechar()
    if res.resposta is None:
        raise LutzError(f"O lint semântico falhou: {res.erro}")
    try:
        achados = extrair_json(res.resposta.texto).get("achados", [])
    except ValueError as exc:
        raise LutzError(f"Resposta do lint semântico malformada: {exc}") from exc
    nomes = {c.nome for c in cb.campos}
    out = []
    for a in achados if isinstance(achados, list) else []:
        if isinstance(a, dict) and a.get("campo") in nomes and a.get("mensagem"):
            out.append({"campo": a["campo"], "codigo": str(a.get("codigo", "S000")),
                        "severidade": a.get("severidade") if a.get("severidade") in ("aviso", "sugestao") else "aviso",
                        "mensagem": str(a["mensagem"])[:400], "origem": "llm"})
    return out
