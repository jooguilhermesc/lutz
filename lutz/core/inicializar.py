"""Create a Lutz 1.0 project folder."""

from __future__ import annotations

from pathlib import Path

from lutz.config.env import ENV_EXEMPLO
from lutz.config.settings import LUTZ_YAML_MODELO
from lutz.core.db import agora, conectar
from lutz.core.errors import LutzError
from lutz.core.project import Projeto

GITIGNORE = """\
# Lutz 1.0 project
.env
.lutz/
# PDFs are usually copyrighted: keep them out of public repositories.
pdfs/
"""


def criar_projeto(
    pasta: Path,
    nome: str | None = None,
    pergunta: str = "",
    tipo_revisao: str = "sistematica",
    lutz_yaml: str | None = None,
) -> Projeto:
    pasta = Path(pasta).resolve()
    if (pasta / "lutz.yaml").exists():
        raise LutzError(f"Já existe um projeto do Lutz em {pasta}.")
    if pasta.exists() and any(p for p in pasta.iterdir() if not p.name.startswith(".")):
        raise LutzError(f"A pasta {pasta} já existe e não está vazia.")
    pasta.mkdir(parents=True, exist_ok=True)
    projeto = Projeto(pasta)
    projeto.garantir_pastas()
    projeto.yaml.write_text(lutz_yaml or LUTZ_YAML_MODELO, encoding="utf-8")
    (pasta / ".env.example").write_text(ENV_EXEMPLO, encoding="utf-8")
    if not projeto.env.exists():
        projeto.env.write_text(ENV_EXEMPLO, encoding="utf-8")
    (pasta / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    con = conectar(projeto, criar=True)
    try:
        con.execute(
            "INSERT INTO projeto (id, nome, pergunta, tipo_revisao, criado_em) VALUES (1,?,?,?,?)",
            (nome or pasta.name, pergunta, tipo_revisao, agora()),
        )
    finally:
        con.close()
    return projeto


def info_projeto(con) -> dict:
    r = con.execute("SELECT * FROM projeto WHERE id=1").fetchone()
    return dict(r) if r else {}
