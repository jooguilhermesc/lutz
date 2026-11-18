from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("COLUMNS", "250")  # wide Rich tables in CLI tests

import pytest

from lutz.core.db import conectar
from lutz.core.inicializar import criar_projeto
from lutz.core.project import Projeto

YAML_FAKE = """\
versao: 1
modelos:
  E1: {provedor: fake, modelo: fake-a}
  E2: {provedor: fake, modelo: fake-b}
  E3: {provedor: fake, modelo: fake-c}
  V:  {provedor: fake, modelo: fake-v}
custo: {orcamento_usd: 10, confirmar: false}
relatorio: {idiomas: [pt, en], formatos: [md, pdf]}
metricas: {bootstrap_repeticoes: 200}
precos:
  fake-a: {entrada: 1.0, saida: 2.0}
  fake-b: {entrada: 1.0, saida: 2.0}
  fake-c: {entrada: 1.0, saida: 2.0}
  fake-v: {entrada: 1.0, saida: 2.0}
"""


@pytest.fixture
def projeto(tmp_path: Path) -> Projeto:
    return criar_projeto(tmp_path / "proj", nome="teste", pergunta="LLM na educação?",
                         lutz_yaml=YAML_FAKE)


@pytest.fixture
def con(projeto: Projeto):
    c = conectar(projeto)
    yield c
    c.close()


@pytest.fixture
def pasta_pdfs(tmp_path: Path) -> Path:
    p = tmp_path / "entrada"
    p.mkdir()
    return p
