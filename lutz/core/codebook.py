"""The codebook: the extraction form. One field = one column of the final table.

Source of truth is the database. ``codebook.yaml`` is only an import/export format.
Every version has a canonical hash; every field also has its own hash (semantic attributes
only), so human pilot answers stay comparable across codebook versions when the field did
not change.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from lutz.config.settings import hash_obj
from lutz.core.db import agora, jdump, jload, transacao, um
from lutz.core.errors import CodebookInvalido, EstadoInvalido

Tipo = Literal["categorico", "ordinal", "numerico", "texto"]
Papel = Literal["dado", "triagem", "risco_vies", "criterio"]
NOME_VALIDO = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class Exemplo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trecho: str
    valor: str
    positivo: bool = True


class Regra(BaseModel):
    """Closed set of cross-field rules (no eval).

    * ``soma_igual``: the sum of ``campos`` must equal this field (numeric).
    * ``menor_ou_igual`` / ``maior_ou_igual``: this field compared to ``campo``.
    * ``requer``: when this field is reported, ``campo`` must be reported too.
    * ``valor_implica``: when this field equals ``se``, ``campo`` must be one of ``entao``.
    """

    model_config = ConfigDict(extra="forbid")
    tipo: Literal["soma_igual", "menor_ou_igual", "maior_ou_igual", "requer", "valor_implica"]
    campos: list[str] = []
    campo: str | None = None
    se: str | None = None
    entao: list[str] = []
    tolerancia_relativa: float = 0.0

    def referencias(self) -> list[str]:
        return list(self.campos) + ([self.campo] if self.campo else [])


class Campo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    rotulo: str = ""
    tipo: Tipo
    instrucao: str
    valores: list[str] = []
    definicoes: dict[str, str] = {}
    exemplos: list[Exemplo] = []
    secoes: list[str] = []
    se_ausente: str = "nao_reportado"
    tolerancia_relativa: float = Field(default=0.0, ge=0, le=1)
    faixa: tuple[float, float] | None = None
    unidade: str = ""
    papel: Papel = "dado"
    motivo_exclusao: bool = False
    regras: list[Regra] = []
    origem: Literal["manual", "assistente"] = "manual"

    @model_validator(mode="after")
    def _rotulo(self):
        if not self.rotulo:
            self.rotulo = self.nome.replace("_", " ").capitalize()
        return self

    def semantica(self) -> dict:
        """Attributes that change what is extracted (label, order and origin excluded)."""
        d = self.model_dump(mode="json", exclude={"rotulo", "origem"})
        return d

    def hash(self) -> str:
        return hash_obj(self.semantica())[:16]


class Codebook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int | None = None
    descricao: str = ""
    campos: list[Campo]

    def hash(self) -> str:
        return hash_obj({"descricao": self.descricao,
                         "campos": [c.model_dump(mode="json", exclude={"origem"}) for c in self.campos]})[:16]

    def campo(self, nome: str) -> Campo:
        for c in self.campos:
            if c.nome == nome:
                return c
        raise KeyError(nome)

    def para_yaml(self) -> str:
        d = self.model_dump(mode="json", exclude_defaults=True)
        d.setdefault("campos", [])
        for c, orig in zip(d["campos"], self.campos, strict=True):
            c["tipo"] = orig.tipo
            c["instrucao"] = orig.instrucao
        return yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=100)


def ler_yaml(texto: str) -> Codebook:
    try:
        bruto = yaml.safe_load(texto) or {}
    except yaml.YAMLError as exc:
        raise CodebookInvalido(f"YAML inválido: {exc}") from exc
    return de_dict(bruto)


def de_dict(bruto) -> Codebook:
    """Validate a codebook given as a dict (or a list of fields), with messages per field."""
    if isinstance(bruto, list):
        bruto = {"campos": bruto}
    if not isinstance(bruto, dict):
        raise CodebookInvalido("O codebook deve ser um objeto com a lista 'campos'.")
    try:
        return Codebook.model_validate(bruto)
    except ValidationError as exc:
        msgs = []
        for err in exc.errors():
            loc = list(err["loc"])
            if len(loc) >= 2 and loc[0] == "campos" and isinstance(loc[1], int):
                try:
                    nome = bruto["campos"][loc[1]].get("nome", f"#{loc[1] + 1}")
                except Exception:  # pragma: no cover
                    nome = f"#{loc[1] + 1}"
                loc = [f"campo '{nome}'", *loc[2:]]
            msgs.append(f"  {'.'.join(str(x) for x in loc)}: {err['msg']}")
        raise CodebookInvalido("Codebook inválido:\n" + "\n".join(msgs)) from exc


# ── lint ─────────────────────────────────────────────────────────────────────


def lint(cb: Codebook) -> list[dict]:
    """Deterministic checks before spending tokens. Severity: erro | aviso | sugestao."""
    out: list[dict] = []

    def add(campo: str | None, codigo: str, sev: str, msg: str) -> None:
        out.append({"campo": campo, "codigo": codigo, "severidade": sev, "mensagem": msg})

    nomes = [c.nome for c in cb.campos]
    if not cb.campos:
        add(None, "L000", "erro", "O codebook não tem campos.")
    por_nome = {c.nome: c for c in cb.campos}
    for c in cb.campos:
        if not NOME_VALIDO.match(c.nome):
            add(c.nome, "L001", "erro",
                "Nome inválido: use letras minúsculas, números e '_', começando por letra.")
        if nomes.count(c.nome) > 1:
            add(c.nome, "L002", "erro", "Nome repetido no codebook.")
        if c.tipo in ("categorico", "ordinal"):
            if len(c.valores) < 2:
                add(c.nome, "L003", "erro", "Campo categórico/ordinal precisa de pelo menos 2 valores.")
            norm = [v.casefold().strip() for v in c.valores]
            if len(set(norm)) != len(norm):
                add(c.nome, "L004", "erro", "Valores repetidos na lista.")
            if c.se_ausente.casefold() in norm:
                add(c.nome, "L010", "erro",
                    f"O valor '{c.se_ausente}' é a regra de ausência e não pode estar na lista.")
            if c.tipo == "categorico" and len(c.valores) >= 3 and not any(
                v in ("outro", "outros", "other", "misto", "mixed") for v in norm
            ):
                add(c.nome, "L011", "aviso",
                    "Sem categoria residual ('outro'): casos que não se encaixam serão forçados "
                    "numa categoria. Confirme que a lista cobre todos os casos.")
            if c.tipo == "ordinal" and len(c.valores) == 2:
                add(c.nome, "L015", "sugestao",
                    "Ordinal com dois valores se comporta como categórico.")
            for d in c.definicoes:
                if d.casefold() not in norm:
                    add(c.nome, "L012", "erro", f"Definição para valor inexistente: '{d}'.")
            for ex in c.exemplos:
                if ex.valor.casefold() not in norm and ex.valor != c.se_ausente:
                    add(c.nome, "L014", "erro", f"Exemplo com valor fora da lista: '{ex.valor}'.")
            if len(c.valores) >= 3 and len(c.definicoes) < len(c.valores):
                add(c.nome, "L016", "sugestao",
                    "Defina operacionalmente cada valor (definicoes): categorias sem definição "
                    "costumam se sobrepor.")
        elif c.valores:
            add(c.nome, "L017", "aviso", f"Campo {c.tipo} não usa 'valores'; a lista será ignorada.")
        if c.tipo == "numerico":
            if c.faixa is None:
                add(c.nome, "L005", "aviso",
                    "Numérico sem faixa plausível: valores absurdos não serão barrados.")
            elif c.faixa[0] > c.faixa[1]:
                add(c.nome, "L018", "erro", "Faixa com mínimo maior que o máximo.")
            if not c.unidade:
                add(c.nome, "L006", "aviso", "Numérico sem unidade (ex.: participantes, %, anos).")
        if len(c.instrucao.strip()) < 15:
            add(c.nome, "L007", "aviso", "Instrução muito curta; descreva o que extrair e como.")
        if _dois_pedidos(c.instrucao):
            add(c.nome, "L008", "aviso",
                "A instrução parece pedir duas coisas. Divida em dois campos.")
        if c.tipo == "texto" and re.search(
            r"\b(classifique|classify|categorize|sim ou n[aã]o|yes or no|indique se|indicate whether)\b",
            c.instrucao, re.I,
        ):
            add(c.nome, "L009", "sugestao",
                "Este campo de texto livre parece categórico. Campos categóricos são mais fáceis "
                "de validar.")
        if c.papel == "triagem" and c.tipo != "categorico":
            add(c.nome, "L019", "erro", "Campo de triagem precisa ser categórico (ex.: incluir/excluir).")
        for r in c.regras:
            for ref in r.referencias():
                if ref not in por_nome:
                    add(c.nome, "L013", "erro", f"Regra '{r.tipo}' cita campo inexistente: '{ref}'.")
            if r.tipo in ("soma_igual", "menor_ou_igual", "maior_ou_igual"):
                alvos = [c.nome, *r.referencias()]
                if any(a in por_nome and por_nome[a].tipo != "numerico" for a in alvos):
                    add(c.nome, "L013", "erro", f"Regra '{r.tipo}' só vale entre campos numéricos.")
                if r.tipo == "soma_igual" and len(r.campos) < 2:
                    add(c.nome, "L013", "erro", "soma_igual precisa de pelo menos dois campos.")
            if r.tipo == "valor_implica" and (r.se is None or not r.entao or not r.campo):
                add(c.nome, "L013", "erro", "valor_implica precisa de 'se', 'campo' e 'entao'.")
    return out


def _dois_pedidos(instr: str) -> bool:
    t = instr.casefold()
    if t.count("?") >= 2:
        return True
    return bool(re.search(r"\b(e também|e ainda|além disso|and also|as well as|y también)\b", t))


def tem_erros(achados: list[dict]) -> bool:
    return any(a["severidade"] == "erro" for a in achados)


# ── persistence and versions ─────────────────────────────────────────────────


def _ultima(con: sqlite3.Connection) -> dict | None:
    return um(con, "SELECT * FROM codebook ORDER BY versao DESC LIMIT 1")


def salvar_rascunho(con: sqlite3.Connection, cb: Codebook, origem: str = "manual",
                    nota: str = "") -> dict:
    """Store *cb* as the editable draft (new version when the latest one is frozen).

    Returns the codebook row. Saving content identical to the latest version is a no-op.
    """
    achados = lint(cb)
    erros = [a for a in achados if a["severidade"] == "erro"]
    if erros:
        raise CodebookInvalido(
            "O codebook tem erros:\n" + "\n".join(f"  [{a['campo'] or '-'}] {a['mensagem']}" for a in erros)
        )
    h = cb.hash()
    with transacao(con):
        ult = _ultima(con)
        if ult and ult["hash"] == h:
            return ult
        cb_y = cb.model_copy()
        if ult is None or ult["congelado"]:
            versao = (ult["versao"] + 1) if ult else 1
            cb_y.versao = versao
            cur = con.execute(
                """INSERT INTO codebook (versao, hash, yaml, origem, congelado, versao_anterior_id,
                   nota, criado_em) VALUES (?,?,?,?,0,?,?,?)""",
                (versao, h, cb_y.para_yaml(), origem, ult["id"] if ult else None, nota, agora()),
            )
            cid = cur.lastrowid
        else:
            versao = ult["versao"]
            cb_y.versao = versao
            cid = ult["id"]
            con.execute("DELETE FROM campo WHERE codebook_id=?", (cid,))
            con.execute("UPDATE codebook SET hash=?, yaml=?, origem=?, nota=? WHERE id=?",
                        (h, cb_y.para_yaml(), origem, nota or ult["nota"], cid))
        for i, c in enumerate(cb.campos):
            con.execute(
                """INSERT INTO campo (codebook_id, chave, rotulo, tipo, definicao, hash, origem, ordem)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (cid, c.nome, c.rotulo, c.tipo, jdump(c.model_dump(mode="json")), c.hash(), c.origem, i),
            )
    return um(con, "SELECT * FROM codebook WHERE id=?", (cid,))


def congelar(con: sqlite3.Connection, versao: int | None = None) -> dict:
    with transacao(con):
        row = (um(con, "SELECT * FROM codebook WHERE versao=?", (versao,)) if versao
               else _ultima(con))
        if row is None:
            raise EstadoInvalido("Não há codebook. Importe um com 'lutz codebook import'.")
        if row["congelado"]:
            return row
        cb = carregar(con, row["versao"])
        if tem_erros(lint(cb)):
            raise CodebookInvalido("O codebook tem erros de lint; corrija antes de congelar.")
        con.execute("UPDATE codebook SET congelado=1, congelado_em=? WHERE id=?", (agora(), row["id"]))
    return um(con, "SELECT * FROM codebook WHERE id=?", (row["id"],))


def carregar(con: sqlite3.Connection, versao: int | None = None) -> Codebook:
    row = (um(con, "SELECT * FROM codebook WHERE versao=?", (versao,)) if versao
           else _ultima(con))
    if row is None:
        raise EstadoInvalido("Não há codebook neste projeto.")
    campos = [Campo.model_validate(jload(r["definicao"])) for r in con.execute(
        "SELECT definicao FROM campo WHERE codebook_id=? ORDER BY ordem", (row["id"],))]
    return Codebook(versao=row["versao"], campos=campos,
                    descricao=(yaml.safe_load(row["yaml"]) or {}).get("descricao", ""))


def linha_codebook(con: sqlite3.Connection, versao: int | None = None) -> dict | None:
    if versao:
        return um(con, "SELECT * FROM codebook WHERE versao=?", (versao,))
    return _ultima(con)


def ultimo_congelado(con: sqlite3.Connection) -> dict | None:
    return um(con, "SELECT * FROM codebook WHERE congelado=1 ORDER BY versao DESC LIMIT 1")


def historico(con: sqlite3.Connection) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM codebook ORDER BY versao"):
        d = dict(r)
        d["n_campos"] = con.execute("SELECT count(*) FROM campo WHERE codebook_id=?", (r["id"],)).fetchone()[0]
        d["n_assistente"] = con.execute(
            "SELECT count(*) FROM campo WHERE codebook_id=? AND origem='assistente'", (r["id"],)).fetchone()[0]
        d["execucoes"] = [x[0] for x in con.execute(
            "SELECT id FROM execucao WHERE codebook_id=? ORDER BY id", (r["id"],))]
        out.append(d)
    return out


def diff(con: sqlite3.Connection, v1: int, v2: int) -> dict:
    a, b = carregar(con, v1), carregar(con, v2)
    ca, cbm = {c.nome: c for c in a.campos}, {c.nome: c for c in b.campos}
    alterados = []
    for nome in sorted(set(ca) & set(cbm)):
        if ca[nome].hash() != cbm[nome].hash():
            ya = yaml.safe_dump(ca[nome].semantica(), allow_unicode=True, sort_keys=True).splitlines()
            yb = yaml.safe_dump(cbm[nome].semantica(), allow_unicode=True, sort_keys=True).splitlines()
            alterados.append({"campo": nome, "diff": "\n".join(
                difflib.unified_diff(ya, yb, f"v{v1}", f"v{v2}", lineterm=""))})
    return {
        "adicionados": sorted(set(cbm) - set(ca)),
        "removidos": sorted(set(ca) - set(cbm)),
        "alterados": alterados,
    }


def campos_db(con: sqlite3.Connection, codebook_id: int) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM campo WHERE codebook_id=? ORDER BY ordem", (codebook_id,)):
        d = dict(r)
        d["def"] = Campo.model_validate(jload(r["definicao"]))
        out.append(d)
    return out
