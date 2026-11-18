from __future__ import annotations

import json
import os
import time

import pytest

from lutz.config import env as envm
from lutz.config.settings import ModeloPapel, Modelos, avisos, estrategia_diversidade, validar_yaml
from lutz.core import lock as lk
from lutz.core.db import conectar
from lutz.core.errors import ConfigInvalida, ProjetoIncompativel, ProjetoNaoEncontrado, ProjetoOcupado
from lutz.core.inicializar import criar_projeto
from lutz.core.project import Projeto, encontrar_projeto
from tests.conftest import YAML_FAKE


def test_lock_exclusivo_entre_processos_e_reentrante(projeto):
    with lk.bloqueio(projeto, "a"):
        with lk.bloqueio(projeto, "b"):  # same process: re-entrant
            assert lk.ler_lock(projeto)["comando"] == "a"
        assert lk.ler_lock(projeto) is not None
    assert lk.ler_lock(projeto) is None
    # Another live process holds it.
    (projeto.estado / "lock").write_text(json.dumps(
        {"pid": os.getppid(), "host": __import__("socket").gethostname(), "comando": "x",
         "heartbeat": time.time()}))
    with pytest.raises(ProjetoOcupado):
        with lk.bloqueio(projeto, "c"):
            pass
    # Dead process: stale lock is taken over.
    (projeto.estado / "lock").write_text(json.dumps(
        {"pid": 999999, "host": __import__("socket").gethostname(), "comando": "x", "heartbeat": time.time()}))
    with lk.bloqueio(projeto, "d") as trava:
        assert trava.assumiu_obsoleto["comando"] == "x"


def test_projeto_encontrado_e_incompativel(tmp_path, projeto):
    sub = projeto.raiz / "pdfs"
    assert encontrar_projeto(sub).raiz == projeto.raiz
    with pytest.raises(ProjetoNaoEncontrado):
        encontrar_projeto(tmp_path / "nada")
    velho = tmp_path / "velho"
    (velho / "articles").mkdir(parents=True)
    (velho / ".lutz" / "vector_store").mkdir(parents=True)
    with pytest.raises(ProjetoIncompativel, match="0.5"):
        encontrar_projeto(velho)
    from lutz.core.errors import LutzError

    with pytest.raises(LutzError):
        criar_projeto(projeto.raiz)


def test_banco_recusa_esquema_estranho(tmp_path):
    import sqlite3

    p = Projeto(tmp_path)
    c = sqlite3.connect(p.db)
    c.execute("CREATE TABLE chat_session (id int)")
    c.commit()
    c.close()
    with pytest.raises(ProjetoIncompativel):
        conectar(p)
    p2 = Projeto(tmp_path / "x")
    with pytest.raises(ProjetoIncompativel):
        conectar(p2)


def test_env_origem_mascara_e_lista_branca(projeto, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    envm.salvar_env(projeto, {"ANTHROPIC_API_KEY": "sk-ant-1234567890"})
    v = {x["nome"]: x for x in envm.valores_com_origem(projeto)}
    assert v["ANTHROPIC_API_KEY"]["origem"] == ".env" and "••••" in v["ANTHROPIC_API_KEY"]["valor"]
    assert v["DOCKER_MODEL_HOST"]["origem"] == "padrao"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-shell")
    assert envm.salvar_env(projeto, {"ANTHROPIC_API_KEY": "outra"}) == ["ANTHROPIC_API_KEY"]
    v = {x["nome"]: x for x in envm.valores_com_origem(projeto)}
    assert v["ANTHROPIC_API_KEY"]["origem"] == "processo" and v["ANTHROPIC_API_KEY"]["sombreado"]
    assert envm.carregar_env(projeto)["ANTHROPIC_API_KEY"] == "do-shell"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    envm.salvar_env(projeto, {"ANTHROPIC_API_KEY": None})
    assert "ANTHROPIC_API_KEY" not in envm.carregar_env(projeto)
    with pytest.raises(ConfigInvalida):
        envm.salvar_env(projeto, {"LLM_MODEL": "x"})
    with pytest.raises(ConfigInvalida):
        envm.salvar_env(projeto, {"OPENAI_API_KEY": "a\nb"})


def test_settings_validacao_e_diversidade():
    s = validar_yaml(YAML_FAKE)
    assert s.hash() == validar_yaml(YAML_FAKE).hash()
    with pytest.raises(ConfigInvalida, match="modelos"):
        validar_yaml("versao: 1\n")
    with pytest.raises(ConfigInvalida):
        validar_yaml("modelos: [")
    with pytest.raises(ConfigInvalida, match="E1"):
        validar_yaml(YAML_FAKE.replace("provedor: fake, modelo: fake-a", "provedor: nada, modelo: x"))

    def m(p, mod, v="padrao"):
        return ModeloPapel(provedor=p, modelo=mod, variante_prompt=v)

    assert estrategia_diversidade(Modelos(E1=m("anthropic", "a"), E2=m("openai", "b"), E3=m("openrouter", "google/c"))) == "fornecedores_diferentes"
    assert estrategia_diversidade(Modelos(E1=m("openai", "a"), E2=m("openai", "b"), E3=m("anthropic", "c"))) == "modelos_diferentes"
    assert estrategia_diversidade(Modelos(E1=m("openai", "a"), E2=m("openai", "a", "reescrita_a"),
                                          E3=m("openai", "a", "reescrita_b"))) == "instrucoes_reescritas"
    assert estrategia_diversidade(Modelos(E1=m("openai", "a"), E2=m("openai", "a"), E3=m("openai", "a"))) == "nenhuma"
    s2 = validar_yaml(YAML_FAKE.replace("fake-b", "fake-a").replace("fake-c", "fake-a").replace(
        "  V:  {provedor: fake, modelo: fake-v}\n", ""))
    a = avisos(s2)
    assert any("mesmo modelo" in x for x in a) and any("Sem verificador" in x for x in a)
