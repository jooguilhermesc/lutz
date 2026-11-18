"""ADR-004: every model runs through OpenRouter; catalog, account usage and the models screen."""

from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient

from lutz.config.settings import ModeloPapel, carregar_settings, gravar_modelos, validar_yaml
from lutz.core.doctor import verificar
from lutz.core.errors import ConfigInvalida, ProvedorErro
from lutz.llm import cliente as cli_llm
from lutz.llm import openrouter as orr
from lutz.llm import provedores
from lutz.llm.provedores import ErroDefinitivo, Requisicao, Resposta
from lutz.server.app import criar_app
from tests.conftest import YAML_FAKE

CATALOGO = {"data": [
    {"id": "openai/gpt-x", "name": "OpenAI: GPT X", "context_length": 128000,
     "pricing": {"prompt": "0.0000004", "completion": "0.0000016"}, "supported_parameters": ["temperature", "seed"]},
    {"id": "anthropic/claude-y", "name": "Anthropic: Claude Y", "context_length": 200000,
     "pricing": {"prompt": "0.000003", "completion": "0.000015"}},
    {"id": "openrouter/auto", "name": "Auto", "pricing": {"prompt": "-1", "completion": "-1"}},
    {"name": "sem id"},
]}


@pytest.fixture
def rede(monkeypatch):
    """Route _get_json by URL suffix; record the calls."""
    respostas: dict[str, object] = {"/models": CATALOGO}
    chamadas: list[tuple[str, str | None]] = []

    def get(url, chave=None, timeout=20):
        chamadas.append((url, chave))
        for sufixo, r in respostas.items():
            if url.endswith(sufixo):
                if isinstance(r, Exception):
                    raise r
                return r
        raise ProvedorErro(f"sem rota para {url}")

    monkeypatch.setattr(orr, "_get_json", get)
    return types.SimpleNamespace(respostas=respostas, chamadas=chamadas)


# ── catalog ──────────────────────────────────────────────────────────────────

def test_catalogo_normaliza_precos_e_grava_cache(projeto, rede):
    c = orr.catalogo(projeto, {})
    assert c["origem"] == "rede" and c["erro"] == ""
    ids = [m["id"] for m in c["modelos"]]
    assert ids == ["anthropic/claude-y", "openai/gpt-x", "openrouter/auto"]
    gpt = next(m for m in c["modelos"] if m["id"] == "openai/gpt-x")
    assert gpt["entrada"] == pytest.approx(0.4) and gpt["saida"] == pytest.approx(1.6)
    assert gpt["fornecedor"] == "openai" and gpt["contexto"] == 128000
    auto = next(m for m in c["modelos"] if m["id"] == "openrouter/auto")
    assert auto["entrada"] is None  # negative price = variable, not free
    assert (projeto.estado / orr.ARQUIVO_CATALOGO).exists()
    assert rede.chamadas[0] == ("https://openrouter.ai/api/v1/models", None)  # public: no key sent


def test_catalogo_usa_cache_fresco_e_atualiza_quando_pedido(projeto, rede):
    orr.catalogo(projeto, {}, agora=lambda: 1000.0)
    rede.respostas["/models"] = ProvedorErro("fora do ar")
    c = orr.catalogo(projeto, {}, agora=lambda: 1000.0 + 60)
    assert c["origem"] == "cache" and c["erro"] == "" and len(rede.chamadas) == 1
    c = orr.catalogo(projeto, {}, atualizar=True, agora=lambda: 1000.0 + 60)
    assert c["origem"] == "cache" and "fora do ar" in c["erro"] and c["modelos"]
    velho = orr.catalogo(projeto, {}, agora=lambda: 1000.0 + orr.VALIDADE_CATALOGO_S + 1)
    assert velho["origem"] == "cache" and velho["erro"]  # stale cache still served when offline


def test_catalogo_sem_cache_e_sem_rede(projeto, rede):
    assert orr.catalogo(projeto, rede=False)["origem"] == "vazio"
    rede.respostas["/models"] = ProvedorErro("fora do ar")
    c = orr.catalogo(projeto, {})
    assert c["origem"] == "vazio" and c["modelos"] == [] and "fora do ar" in c["erro"]


def test_base_url_valida_o_esquema():
    assert orr.base_url({}) == orr.URL_PADRAO
    assert orr.base_url({"OPENROUTER_BASE_URL": "http://localhost:8080/v1/"}) == "http://localhost:8080/v1"
    with pytest.raises(ProvedorErro):
        orr.base_url({"OPENROUTER_BASE_URL": "file:///etc/passwd"})


def test_precos_do_catalogo_e_sobrescrita_no_yaml(projeto, rede):
    orr.catalogo(projeto, {})
    s = validar_yaml(YAML_FAKE + "  openai/gpt-x: {entrada: 9.0, saida: 9.0}\n")
    tab = cli_llm.tabela_precos(s, projeto)
    assert tab["anthropic/claude-y"] == pytest.approx((3.0, 15.0))
    assert tab["openai/gpt-x"] == (9.0, 9.0)  # lutz.yaml wins
    assert "openrouter/auto" not in tab
    assert cli_llm.preco_de(ModeloPapel(modelo="anthropic/claude-y"), tab) == pytest.approx((3.0, 15.0))
    assert cli_llm.tabela_precos(s) == {k: (p.entrada, p.saida) for k, p in s.precos.items()}


# ── account ──────────────────────────────────────────────────────────────────

def test_conta_com_saldo(rede):
    rede.respostas["/key"] = {"data": {"label": "lutz", "usage": 1.5, "usage_daily": 0.25, "limit": 10,
                                       "limit_remaining": 8.5, "is_free_tier": False}}
    rede.respostas["/credits"] = {"data": {"total_credits": 20, "total_usage": 4.5}}
    c = orr.conta({"OPENROUTER_API_KEY": "sk-or-x"})
    assert c["uso_usd"] == 1.5 and c["limite_restante_usd"] == 8.5 and c["uso_dia_usd"] == 0.25
    assert c["saldo_usd"] == 15.5 and c["creditos_usd"] == 20
    assert all(chave == "sk-or-x" for _, chave in rede.chamadas)


def test_conta_sem_acesso_ao_saldo_e_sem_chave(rede):
    rede.respostas["/key"] = {"data": {"usage": 2, "limit": None}}
    rede.respostas["/credits"] = ProvedorErro("403")
    c = orr.conta({"OPENROUTER_API_KEY": "sk-or-x"})
    assert c["uso_usd"] == 2 and c["limite_usd"] is None and c["saldo_usd"] is None
    with pytest.raises(ProvedorErro, match="OPENROUTER_API_KEY"):
        orr.conta({})


# ── lutz.yaml ────────────────────────────────────────────────────────────────

def test_provedor_padrao_e_temperatura_de_modelos_anthropic():
    assert ModeloPapel(modelo="openai/gpt-x").provedor == "openrouter"
    assert ModeloPapel(modelo="anthropic/claude-y", temperatura=0.2).temperatura_efetiva() is None
    assert ModeloPapel(modelo="google/gemini", temperatura=0.2).temperatura_efetiva() == 0.2


@pytest.mark.parametrize("antigo, sugestao", [
    ("provedor: anthropic, modelo: claude-sonnet-5-5", "anthropic/claude-sonnet-5-5"),
    ("provedor: openai, modelo: gpt-4.1-mini", "openai/gpt-4.1-mini"),
    ("provedor: docker_model_runner, modelo: ai/qwen", "o id do modelo no catálogo"),
])
def test_provedor_removido_explica_a_migracao(antigo, sugestao):
    with pytest.raises(ConfigInvalida, match="OpenRouter") as e:
        validar_yaml(YAML_FAKE.replace("provedor: fake, modelo: fake-a", antigo))
    assert sugestao in str(e.value) and "E1" in str(e.value)


def test_gravar_modelos_preserva_o_resto_do_arquivo(projeto):
    projeto.yaml.write_text(
        "# cabeçalho\nversao: 1\nmodelos:\n# comentário do bloco\n"
        "  E1: {provedor: fake, modelo: fake-a, temperatura: 0.2, variante_prompt: reescrita_a}\n"
        "  E2: {provedor: fake, modelo: fake-b}\n  E3: {provedor: fake, modelo: fake-c}\n"
        "  V:  {provedor: fake, modelo: fake-v}\n  # E1: {provedor: docker_model_runner, modelo: x}\n\n"
        "# Orçamento do projeto\ncusto: {orcamento_usd: 7, confirmar: false}\n", encoding="utf-8")
    s = gravar_modelos(projeto, {"E1": "openai/gpt-x", "V": None})
    texto = projeto.yaml.read_text(encoding="utf-8")
    assert s.modelos.E1.modelo == "openai/gpt-x" and s.modelos.E1.provedor == "openrouter"
    assert s.modelos.E1.temperatura == 0.2 and s.modelos.E1.variante_prompt == "reescrita_a"
    assert s.modelos.E2.modelo == "fake-b" and s.modelos.V is None
    assert s.custo.orcamento_usd == 7
    assert "# cabeçalho" in texto and "# comentário do bloco" in texto and "# Orçamento do projeto" in texto
    assert "docker_model_runner" not in texto
    assert carregar_settings(projeto).hash() == s.hash()


def test_gravar_modelos_corrige_projeto_antigo_e_valida(projeto):
    projeto.yaml.write_text(YAML_FAKE.replace("provedor: fake, modelo: fake-a", "provedor: anthropic, modelo: claude-a"),
                            encoding="utf-8")
    with pytest.raises(ConfigInvalida):
        carregar_settings(projeto)
    s = gravar_modelos(projeto, {"E1": "anthropic/claude-y", "E2": "openai/gpt-x", "E3": "google/g", "V": "x/v"})
    assert [m.modelo for m in s.modelos.extratores().values()] == ["anthropic/claude-y", "openai/gpt-x", "google/g"]
    antes = projeto.yaml.read_text(encoding="utf-8")
    with pytest.raises(ConfigInvalida, match="E1 precisa"):
        gravar_modelos(projeto, {"E1": ""})
    with pytest.raises(ConfigInvalida, match="J"):
        gravar_modelos(projeto, {"J": "x/y"})
    assert projeto.yaml.read_text(encoding="utf-8") == antes  # failed save leaves the file untouched


def test_gravar_modelos_no_modelo_padrao_mantem_comentarios(projeto):
    from lutz.config.settings import LUTZ_YAML_MODELO

    projeto.yaml.write_text(LUTZ_YAML_MODELO, encoding="utf-8")
    assert validar_yaml(LUTZ_YAML_MODELO).modelos.E1.provedor == "openrouter"
    gravar_modelos(projeto, {"E1": "openai/gpt-x", "E2": "anthropic/claude-y", "E3": "google/g", "V": "x/v"})
    texto = projeto.yaml.read_text(encoding="utf-8")
    assert "# Model ids are examples" in texto and "# Thresholds are project decisions" in texto
    assert "orcamento_usd: 20" in texto


# ── provider adapter and client ──────────────────────────────────────────────

class _OpenAIFalso:
    ultimo: dict = {}

    def __init__(self, **kw):
        _OpenAIFalso.cliente_kw = kw
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._criar))

    def _criar(self, **params):
        _OpenAIFalso.ultimo = params
        msg = types.SimpleNamespace(content='{"ok": true}')
        uso = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=0.0123)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
                                     usage=uso, model="anthropic/claude-y-20260101", provider="Anthropic")


def test_adaptador_openrouter(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "OpenAI", _OpenAIFalso)
    cfg = ModeloPapel(modelo="anthropic/claude-y", temperatura=0.5, esforco="low")
    r = provedores.completar(cfg, Requisicao("s", "u", schema={"type": "object"}), {"OPENROUTER_API_KEY": "k"}, 30)
    p = _OpenAIFalso.ultimo
    assert "temperature" not in p and p["model"] == "anthropic/claude-y"
    assert p["extra_body"] == {"usage": {"include": True}, "reasoning": {"effort": "low"}}
    assert p["response_format"]["type"] == "json_schema"
    assert _OpenAIFalso.cliente_kw["base_url"] == orr.URL_PADRAO
    assert r.extra == {"custo_usd": 0.0123} and r.fingerprint == "Anthropic" and r.tokens_entrada == 10
    provedores.completar(ModeloPapel(modelo="openai/gpt-x"), Requisicao("s", "u"), {"OPENROUTER_API_KEY": "k"}, 30)
    assert _OpenAIFalso.ultimo["temperature"] == 0.0 and "response_format" not in _OpenAIFalso.ultimo
    with pytest.raises(ErroDefinitivo, match="OPENROUTER_API_KEY"):
        provedores.completar(cfg, Requisicao("s", "u"), {}, 30)


def test_cliente_registra_o_custo_cobrado_pelo_openrouter(projeto, monkeypatch):
    monkeypatch.setattr(cli_llm, "completar", lambda cfg, req, env, t: Resposta("{}", 100, 50, extra={"custo_usd": 0.5}))
    c = cli_llm.ClienteLLM(projeto, carregar_settings(projeto), usar_cache=False)
    try:
        r = c.chamar(papel="teste", rotulo="E1", cfg=ModeloPapel(modelo="x/sem-preco"), req=Requisicao("s", "u"),
                     execucao_id=None, artigo_id=None)
        custo = c._con().execute("SELECT custo_usd FROM chamada_llm WHERE id=?", (r.chamada_id,)).fetchone()[0]
    finally:
        c.fechar()
    assert custo == 0.5


def test_doctor_aponta_modelo_fora_do_catalogo(projeto, rede, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    projeto.yaml.write_text(YAML_FAKE.replace("provedor: fake, modelo: fake-a", "provedor: openrouter, modelo: x/nao-existe"),
                            encoding="utf-8")
    orr.catalogo(projeto, {})
    linha = next(r for r in verificar(projeto) if r["item"].startswith("E1"))
    assert linha["status"] == "erro"  # missing key comes first
    projeto.env.write_text("OPENROUTER_API_KEY=sk-or-x\n", encoding="utf-8")
    linha = next(r for r in verificar(projeto) if r["item"].startswith("E1"))
    assert linha["status"] == "erro" and "catálogo" in linha["detalhe"]


# ── API ──────────────────────────────────────────────────────────────────────

def test_api_catalogo_conta_e_modelos(projeto, rede, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    c = TestClient(criar_app(projeto))
    cat = c.get("/api/v1/openrouter/modelos").json()
    assert cat["origem"] == "rede" and len(cat["modelos"]) == 3
    r = c.get("/api/v1/openrouter/conta")
    assert r.status_code == 400 and "OPENROUTER_API_KEY" in r.json()["erro"]
    rede.respostas["/key"] = {"data": {"usage": 3}}
    projeto.env.write_text("OPENROUTER_API_KEY=sk-or-x\n", encoding="utf-8")
    assert c.get("/api/v1/openrouter/conta").json()["uso_usd"] == 3
    cfg = c.put("/api/v1/config/modelos", json={"E1": "anthropic/claude-y", "E2": "openai/gpt-x",
                                                 "E3": "google/g", "V": None}).json()
    papeis = {p["rotulo"]: p for p in cfg["lutz_yaml"]["papeis"]}
    assert papeis["E1"]["modelo"] == "anthropic/claude-y" and "V" not in papeis
    assert cfg["lutz_yaml"]["estrategia"] == "fornecedores_diferentes"
    r = c.put("/api/v1/config/modelos", json={"E1": ""})
    assert r.status_code in (400, 422) and "E1" in r.json()["erro"]
    nomes = {v["nome"] for v in c.get("/api/v1/config").json()["env"]}
    assert nomes == {"OPENROUTER_API_KEY", "OPENROUTER_BASE_URL"}


def test_temperatura_aplicada_e_na_para_modelos_anthropic():
    from lutz.config.settings import temperatura_aplicada

    assert temperatura_aplicada("openrouter", "anthropic/claude-opus-5.5", 0.0) is None
    assert temperatura_aplicada("anthropic", "claude-sonnet-5-5", 0.0) is None  # runs before ADR-004
    assert temperatura_aplicada("openrouter", "openai/gpt-4.1-mini", 0.0) == 0.0
    assert temperatura_aplicada("fake", "fake-a", 0.3) == 0.3
