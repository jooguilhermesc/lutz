"""``lutz.yaml``: models per role, thresholds, budget, seeds and concurrency.

The file is part of every run: the resolved settings are stored with the run and hashed, so
the reliability report can cite exactly which models and thresholds produced each number.
Every model runs through OpenRouter (ADR-004). The web settings screen writes only the
``modelos`` block (one model per role, chosen from the OpenRouter catalog); everything else is
edited in a text editor.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from lutz.core.errors import ConfigInvalida
from lutz.core.project import Projeto

Provedor = Literal["openrouter", "fake"]
PROVEDORES_REMOVIDOS = {"anthropic": "anthropic", "openai": "openai", "docker_model_runner": None}
VARIANTES = ("padrao", "reescrita_a", "reescrita_b")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModeloPapel(_Base):
    provedor: Provedor = "openrouter"
    modelo: str = Field(min_length=1)
    temperatura: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=256, le=200_000)
    variante_prompt: Literal["padrao", "reescrita_a", "reescrita_b"] = "padrao"
    janela_tokens: int | None = Field(
        default=None, ge=2048, description="Context window of the model, in tokens."
    )
    esforco: Literal["low", "medium", "high", "xhigh", "max"] | None = Field(
        default=None, description="Reasoning effort, sent as OpenRouter 'reasoning.effort'."
    )
    base_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _provedor_removido(cls, dados):
        """Projects created before ADR-004 name a vendor; say exactly what to write instead."""
        if isinstance(dados, dict) and dados.get("provedor") in PROVEDORES_REMOVIDOS:
            antigo, modelo = dados["provedor"], str(dados.get("modelo") or "MODELO")
            prefixo = PROVEDORES_REMOVIDOS[antigo]
            sugestao = f"{prefixo}/{modelo}" if prefixo and "/" not in modelo else "o id do modelo no catálogo"
            raise ValueError(
                f"o provedor '{antigo}' saiu do Lutz: todos os modelos passam pelo OpenRouter. "
                f"Use 'provedor: openrouter' e 'modelo: {sugestao}' (confira o id na tela de Configurações)."
            )
        return dados

    @property
    def fornecedor(self) -> str:
        """Vendor behind the model: the prefix of the OpenRouter id (``anthropic/...``)."""
        return self.modelo.split("/")[0] if "/" in self.modelo else self.provedor

    def temperatura_efetiva(self) -> float | None:
        """Anthropic models do not accept sampling parameters; the value is not sent."""
        return None if self.fornecedor == "anthropic" else self.temperatura


class Modelos(_Base):
    E1: ModeloPapel
    E2: ModeloPapel
    E3: ModeloPapel
    V: ModeloPapel | None = None
    J: ModeloPapel | None = None

    def extratores(self) -> dict[str, ModeloPapel]:
        return {"E1": self.E1, "E2": self.E2, "E3": self.E3}


class Limiares(_Base):
    """Every threshold has a stable id (the attribute name) cited in the report."""

    evidencia_similaridade: float = Field(default=90, ge=50, le=100)
    evidencia_min_chars_fuzzy: int = Field(default=25, ge=5)
    alta_exige_evidencia_no_grupo: bool = True
    texto_similaridade: float = Field(default=85, ge=50, le=100)
    nao_reportado_alerta: float = Field(default=0.20, ge=0, le=1)
    alfa_confiavel: float = 0.800
    alfa_provisorio: float = 0.667
    decisao_alto: float = 0.80
    decisao_ic_inferior: float = 0.60
    decisao_medio: float = 0.60
    decisao_numerico_exato: float = 0.90
    decisao_texto_alto: float = 0.90
    decisao_texto_medio: float = 0.75
    calibracao_alta_minima: float = 0.95
    pabak_categoria_dominante: float = 0.80
    legibilidade_minima: float = Field(default=0.5, ge=0, le=1)
    texto_oculto_alerta: float = Field(default=0.02, ge=0, le=1)


class Custo(_Base):
    orcamento_usd: float | None = Field(default=None, ge=0)
    confirmar: bool = True


class Sementes(_Base):
    piloto: int = 42
    bootstrap: int = 42
    auditoria: int = 42


class Concorrencia(_Base):
    por_provedor: int = Field(default=4, ge=1, le=32)
    tentativas: int = Field(default=5, ge=1, le=10)
    timeout_s: float = Field(default=180, ge=5)


class Contexto(_Base):
    fracao_janela: float = Field(default=0.7, gt=0.1, le=0.95)
    janela_tokens_padrao: int = Field(default=128_000, ge=2048)


class Auditoria(_Base):
    meia_largura_alvo: float = Field(default=0.06, gt=0.005, lt=0.5)
    p_esperado: float = Field(default=0.95, gt=0.5, lt=1)


class Relatorio(_Base):
    idiomas: list[Literal["pt", "en"]] = ["pt", "en"]
    formatos: list[Literal["md", "pdf"]] = ["md", "pdf"]
    autoria: str = Field(default="a equipe de pesquisa", description="How the Portuguese report refers to the authors.")


class Metricas(_Base):
    bootstrap_repeticoes: int = Field(default=2000, ge=100, le=20000)


class Preco(_Base):
    entrada: float = Field(ge=0, description="USD per million input tokens")
    saida: float = Field(ge=0, description="USD per million output tokens")


class Settings(_Base):
    versao: Literal[1] = 1
    modelos: Modelos
    limiares: Limiares = Limiares()
    custo: Custo = Custo()
    sementes: Sementes = Sementes()
    concorrencia: Concorrencia = Concorrencia()
    contexto: Contexto = Contexto()
    auditoria: Auditoria = Auditoria()
    relatorio: Relatorio = Relatorio()
    metricas: Metricas = Metricas()
    precos: dict[str, Preco] = {}

    @field_validator("precos")
    @classmethod
    def _chaves_precos(cls, v: dict[str, Preco]) -> dict[str, Preco]:
        return {k.strip(): p for k, p in v.items()}

    def dump(self) -> dict:
        return self.model_dump(mode="json")

    def hash(self) -> str:
        return hash_obj(self.dump())


def hash_obj(obj) -> str:
    texto = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def estrategia_diversidade(modelos: Modelos) -> str:
    """Derived automatically; the researcher never types it.

    * ``fornecedores_diferentes``: three different vendors (strongest), e.g. ``anthropic/``,
      ``openai/`` and ``google/`` models on OpenRouter;
    * ``modelos_diferentes``: different models, some sharing a vendor;
    * ``instrucoes_reescritas``: same model, different prompt variants;
    * ``nenhuma``: same model and same prompt three times (reported as a limitation).
    """
    ex = list(modelos.extratores().values())
    fornecedores = {m.fornecedor for m in ex}
    if len(fornecedores) == 3 and len({m.modelo for m in ex}) == 3:
        return "fornecedores_diferentes"
    if len({(m.provedor, m.modelo) for m in ex}) == 3:
        return "modelos_diferentes"
    if len({(m.provedor, m.modelo) for m in ex}) == 1 and len({m.variante_prompt for m in ex}) == 3:
        return "instrucoes_reescritas"
    if len({(m.provedor, m.modelo, m.variante_prompt) for m in ex}) == 3:
        return "modelos_diferentes"
    return "nenhuma"


def avisos(s: Settings) -> list[str]:
    """Non-blocking warnings shown by 'lutz doctor' and the web settings modal."""
    out = []
    est = estrategia_diversidade(s.modelos)
    if est == "nenhuma":
        out.append(
            "E1, E2 e E3 usam o mesmo modelo e a mesma instrução: os erros serão correlacionados. "
            "Escolha modelos de fornecedores diferentes ou variantes de prompt diferentes."
        )
    elif est == "instrucoes_reescritas":
        out.append(
            "E1, E2 e E3 usam o mesmo modelo; a diversidade vem só das instruções reescritas. "
            "Isso entra como limitação no relatório."
        )
    if s.modelos.V is None:
        out.append(
            "Sem verificador (V): v = 1 é declarado em todas as células e isso aparece no relatório."
        )
    else:
        ex = {(m.provedor, m.modelo) for m in s.modelos.extratores().values()}
        if (s.modelos.V.provedor, s.modelos.V.modelo) in ex:
            out.append("O verificador usa o mesmo modelo de um extrator; prefira um modelo diferente.")
    for rot, m in s.modelos.extratores().items():
        if m.temperatura_efetiva() is not None and m.temperatura > 0.3:
            out.append(f"{rot} usa temperatura {m.temperatura}; extração costuma usar 0.")
    if s.custo.orcamento_usd is None:
        out.append("Sem orçamento (custo.orcamento_usd): nenhuma execução será interrompida por custo.")
    return out


LUTZ_YAML_MODELO = """\
# Lutz 1.0 — project configuration.
# This file is stored (resolved) with every extraction run and its hash appears in the
# reliability report. Secrets (API keys) go in .env, never here.
versao: 1

# Three independent extractors, all through OpenRouter (one key: OPENROUTER_API_KEY).
# Models from different vendors (anthropic/, openai/, google/...) give the strongest
# diversity: their errors are less correlated. The verifier (V) should differ from the
# extractors. Pick the models in the web interface (Settings) or write the OpenRouter ids here.
modelos:
# Model ids are examples: check them in the OpenRouter catalog before the first run
# ('lutz doctor --chamar' makes one small call per role). Anthropic models ignore 'temperatura'.
  E1: {provedor: openrouter, modelo: anthropic/claude-opus-5.5}
  E2: {provedor: openrouter, modelo: openai/gpt-4.1-mini, temperatura: 0}
  E3: {provedor: openrouter, modelo: google/gemini-2.5-flash, temperatura: 0}
  V:  {provedor: openrouter, modelo: anthropic/claude-sonnet-5.5}

custo:
  orcamento_usd: 20        # the run pauses when the project spend reaches this value
  confirmar: true          # show the estimate and ask before every run

sementes: {piloto: 42, bootstrap: 42, auditoria: 42}

concorrencia: {por_provedor: 4, tentativas: 5, timeout_s: 180}

relatorio:
  idiomas: [pt, en]
  formatos: [md, pdf]
  autoria: a equipe de pesquisa   # Methods text: "revisadas pela equipe de pesquisa"

# Thresholds are project decisions, not literature standards; they are printed in the report.
# Uncomment to change any default.
# limiares:
#   evidencia_similaridade: 90
#   evidencia_min_chars_fuzzy: 25
#   alta_exige_evidencia_no_grupo: true
#   nao_reportado_alerta: 0.20
#   decisao_alto: 0.80
#   decisao_ic_inferior: 0.60
#   decisao_medio: 0.60
#   calibracao_alta_minima: 0.95

# Prices come from the OpenRouter catalog (and the billed cost of each call). To override
# one, in USD per million tokens:
# precos:
#   openai/gpt-4.1-mini: {entrada: 0.4, saida: 1.6}
"""


def carregar_settings(projeto: Projeto) -> Settings:
    if not projeto.yaml.exists():
        raise ConfigInvalida(f"{projeto.yaml} não existe.")
    return validar_yaml(projeto.yaml.read_text(encoding="utf-8"))


def validar_yaml(texto: str) -> Settings:
    try:
        bruto = yaml.safe_load(texto) or {}
    except yaml.YAMLError as exc:
        raise ConfigInvalida(f"lutz.yaml não é um YAML válido: {exc}") from exc
    try:
        return Settings.model_validate(bruto)
    except ValidationError as exc:
        linhas = []
        for err in exc.errors():
            onde = ".".join(str(p) for p in err["loc"])
            linhas.append(f"  {onde}: {err['msg']}")
        raise ConfigInvalida("lutz.yaml inválido:\n" + "\n".join(linhas)) from exc


# ── writing the 'modelos' block from the web settings screen ──────────────────

PAPEIS_EDITAVEIS = ("E1", "E2", "E3", "V")
_ORDEM_PAPEIS = ("E1", "E2", "E3", "V", "J")


def _linha_papel(rotulo: str, dados: dict) -> str:
    corpo = yaml.safe_dump(dados, default_flow_style=True, allow_unicode=True, sort_keys=False,
                           width=10_000).strip()
    return f"  {rotulo}:{' ' * (3 - len(rotulo))}{corpo}"


def _bloco_modelos(linhas: list[str]) -> tuple[int, int] | None:
    """(first, last) line indexes of the top-level 'modelos' block, or None."""
    ini = next((i for i, ln in enumerate(linhas) if re.match(r"modelos\s*:", ln)), None)
    if ini is None:
        return None
    if linhas[ini].split(":", 1)[1].split("#", 1)[0].strip():  # inline mapping: one line
        return ini, ini
    fim = ini
    for j in range(ini + 1, len(linhas)):
        ln = linhas[j]
        if ln and not ln[0].isspace() and not ln.startswith("#"):
            break
        if ln.strip() and ln[0].isspace():  # entries and indented comments (old commented roles)
            fim = j
    return ini, fim


def gravar_modelos(projeto: Projeto, escolhas: dict[str, str | None]) -> Settings:
    """Set the OpenRouter model of each role in *escolhas* (``None`` removes V).

    Other options of a role (temperature, max_tokens, prompt variant...) are kept, as are the
    rest of the file and its comments. The result is validated before it is written, so a
    failed save leaves lutz.yaml untouched.
    """
    desconhecidos = sorted(set(escolhas) - set(PAPEIS_EDITAVEIS))
    if desconhecidos:
        raise ConfigInvalida(f"Papéis que a tela não edita: {', '.join(desconhecidos)}.")
    for rot in ("E1", "E2", "E3"):
        if rot in escolhas and not (escolhas[rot] or "").strip():
            raise ConfigInvalida(f"{rot} precisa de um modelo.")
    texto = projeto.yaml.read_text(encoding="utf-8") if projeto.yaml.exists() else LUTZ_YAML_MODELO
    try:
        bruto = yaml.safe_load(texto) or {}
    except yaml.YAMLError as exc:
        raise ConfigInvalida(f"lutz.yaml não é um YAML válido: {exc}") from exc
    atuais = dict((bruto.get("modelos") or {}) if isinstance(bruto, dict) else {})
    for rot, modelo in escolhas.items():
        if modelo is None or not modelo.strip():
            atuais.pop(rot, None)
            continue
        anterior = {k: v for k, v in dict(atuais.get(rot) or {}).items()
                    if k not in ("provedor", "modelo", "base_url")}
        atuais[rot] = {"provedor": "openrouter", "modelo": modelo.strip(), **anterior}
    novas = [_linha_papel(rot, atuais[rot]) for rot in _ORDEM_PAPEIS if atuais.get(rot)]

    linhas = texto.splitlines()
    pos = _bloco_modelos(linhas)
    if pos is None:
        resultado = linhas + ["", "modelos:", *novas]
    else:
        ini, fim = pos
        cabecalho = []
        for ln in linhas[ini + 1:fim + 1]:
            if ln.startswith("#"):
                cabecalho.append(ln)
            elif ln.strip():
                break
        resultado = linhas[:ini] + ["modelos:", *cabecalho, *novas] + linhas[fim + 1:]
    novo_texto = "\n".join(resultado) + "\n"
    s = validar_yaml(novo_texto)
    tmp = projeto.yaml.with_suffix(".yaml.tmp")
    tmp.write_text(novo_texto, encoding="utf-8")
    tmp.replace(projeto.yaml)
    return s
