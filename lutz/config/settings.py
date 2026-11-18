"""``lutz.yaml``: models per role, thresholds, budget, seeds and concurrency.

The file is part of every run: the resolved settings are stored with the run and hashed, so
the reliability report can cite exactly which models and thresholds produced each number.
The web interface shows this file read-only; edit it in a text editor.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from lutz.core.errors import ConfigInvalida
from lutz.core.project import Projeto

Provedor = Literal["anthropic", "openai", "openrouter", "docker_model_runner", "fake"]
VARIANTES = ("padrao", "reescrita_a", "reescrita_b")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModeloPapel(_Base):
    provedor: Provedor
    modelo: str = Field(min_length=1)
    temperatura: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=256, le=200_000)
    variante_prompt: Literal["padrao", "reescrita_a", "reescrita_b"] = "padrao"
    janela_tokens: int | None = Field(
        default=None, ge=2048, description="Context window of the model, in tokens."
    )
    esforco: Literal["low", "medium", "high", "xhigh", "max"] | None = Field(
        default=None, description="Anthropic only: output_config.effort."
    )
    base_url: str | None = None

    def temperatura_efetiva(self) -> float | None:
        """Anthropic models do not accept sampling parameters; the value is not sent."""
        return None if self.provedor == "anthropic" else self.temperatura


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

    * ``fornecedores_diferentes``: three different providers (strongest);
    * ``modelos_diferentes``: different models, some sharing a provider;
    * ``instrucoes_reescritas``: same model, different prompt variants;
    * ``nenhuma``: same model and same prompt three times (reported as a limitation).
    """
    ex = list(modelos.extratores().values())
    provedores = {m.provedor if m.provedor != "openrouter" else m.modelo.split("/")[0] for m in ex}
    if len(provedores) == 3 and len({m.modelo for m in ex}) == 3:
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
            "Use fornecedores diferentes ou variantes de prompt diferentes."
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
        if m.provedor != "anthropic" and m.temperatura > 0.3:
            out.append(f"{rot} usa temperatura {m.temperatura}; extração costuma usar 0.")
    if s.custo.orcamento_usd is None:
        out.append("Sem orçamento (custo.orcamento_usd): nenhuma execução será interrompida por custo.")
    return out


LUTZ_YAML_MODELO = """\
# Lutz 1.0 — project configuration.
# This file is stored (resolved) with every extraction run and its hash appears in the
# reliability report. Secrets (API keys) go in .env, never here.
versao: 1

# Three independent extractors. Different providers give the strongest diversity:
# their errors are less correlated. The verifier (V) should differ from the extractors.
modelos:
# Model names are examples: check them against your provider before the first run
# ('lutz doctor' makes one small call per role). Anthropic models ignore 'temperatura'.
  E1: {provedor: anthropic, modelo: claude-opus-5-5}
  E2: {provedor: openai, modelo: gpt-4.1-mini, temperatura: 0}
  E3: {provedor: openrouter, modelo: google/gemini-2.5-flash, temperatura: 0}
  V:  {provedor: anthropic, modelo: claude-sonnet-5-5}
  # Local models through Docker Model Runner (no key, no cost). Set janela_tokens to the
  # context size configured in Docker (docker model configure --context-size 32768 ai/qwen2.5).
  # E1: {provedor: docker_model_runner, modelo: ai/qwen2.5:3B-Q4_K_M, janela_tokens: 32768}
  # E2: {provedor: docker_model_runner, modelo: ai/gemma3:4B-Q4_K_M, janela_tokens: 32768}
  # E3: {provedor: docker_model_runner, modelo: ai/llama3.2:3B-Q4_0, janela_tokens: 32768}

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

# Prices in USD per million tokens, to override or extend lutz/data/precos.yaml.
# precos:
#   gpt-4.1-mini: {entrada: 0.4, saida: 1.6}
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
