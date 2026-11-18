"""PyMuPDF is loaded lazily and a broken install gives an actionable message (no traceback)."""

from __future__ import annotations

import subprocess
import sys
import types

import pytest
from click.testing import CliRunner

from lutz.cli import cli
from lutz.core import dependencias as dep
from lutz.core.doctor import verificar
from lutz.core.ingestao import importar_pdf

ERRO_DLL = ImportError("DLL load failed while importing _extra: Não foi possível encontrar o módulo especificado.")


@pytest.fixture
def sem_pymupdf(monkeypatch):
    """Simulate Windows without the Visual C++ Redistributable."""

    def falha(nome):
        raise ERRO_DLL

    dep.carregar_pymupdf.cache_clear()
    monkeypatch.setattr(dep, "importlib", types.SimpleNamespace(import_module=falha))
    monkeypatch.setattr(dep, "_plataforma", lambda: "win32")
    monkeypatch.setattr(dep, "_msvcp140_ausente", lambda: True)
    yield
    dep.carregar_pymupdf.cache_clear()


def test_mensagem_aponta_o_redistributable_quando_falta_msvcp140(monkeypatch):
    monkeypatch.setattr(dep, "_plataforma", lambda: "win32")
    monkeypatch.setattr(dep, "_msvcp140_ausente", lambda: True)
    m = dep.mensagem_pymupdf(ERRO_DLL)
    assert "Visual C++ Redistributable" in m
    assert dep.URL_VCREDIST in m and dep.WINGET_VCREDIST in m
    assert "DLL load failed" in m  # original error kept for support


def test_mensagem_generica_quando_msvcp140_existe(monkeypatch):
    monkeypatch.setattr(dep, "_plataforma", lambda: "win32")
    monkeypatch.setattr(dep, "_msvcp140_ausente", lambda: False)
    m = dep.mensagem_pymupdf(ERRO_DLL)
    assert "Redistributable" not in m
    assert "pip install --force-reinstall pymupdf" in m


def test_mensagem_generica_fora_do_windows(monkeypatch):
    monkeypatch.setattr(dep, "_plataforma", lambda: "linux")
    m = dep.mensagem_pymupdf(ImportError("No module named 'pymupdf'"))
    assert "Redistributable" not in m and "No module named" in m


@pytest.mark.skipif(sys.platform != "win32", reason="ctypes.WinDLL só existe no Windows")
def test_msvcp140_ausente_reflete_o_carregamento_da_dll():
    assert isinstance(dep._msvcp140_ausente(), bool)


def test_carregar_pymupdf_levanta_dependencia_ausente(sem_pymupdf):
    with pytest.raises(dep.DependenciaAusente, match="Visual C\\+\\+ Redistributable"):
        dep.carregar_pymupdf()


def test_doctor_reporta_pymupdf_como_erro(projeto, sem_pymupdf):
    linha = next(r for r in verificar(projeto) if r["item"] == "PyMuPDF")
    assert linha["status"] == "erro"
    assert "Visual C++ Redistributable" in linha["detalhe"]


def test_cli_doctor_explica_sem_traceback(projeto, sem_pymupdf):
    r = CliRunner().invoke(cli, ["doctor", "--projeto", str(projeto.raiz)])
    assert r.exit_code == 1
    assert "Redistributable" in r.output
    assert "Traceback" not in r.output


def test_importar_pdf_nao_confunde_dependencia_com_pdf_ilegivel(projeto, con, tmp_path, sem_pymupdf):
    falso = tmp_path / "a.pdf"
    falso.write_bytes(b"%PDF-1.4\n%fake\n")
    with pytest.raises(dep.DependenciaAusente):
        importar_pdf(projeto, con, falso)


def test_cli_web_e_mcp_abrem_sem_pymupdf():
    """Importing the CLI and the servers must not import pymupdf (lutz web/doctor must start)."""
    codigo = ("import sys; sys.modules['pymupdf'] = None\n"
              "import lutz.cli, lutz.server.app, lutz.server.mcp\n"
              "assert sys.modules['pymupdf'] is None\n")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
