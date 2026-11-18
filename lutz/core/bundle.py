"""Export the project folder as one zip with a manifest of SHA-256 hashes.

The bundle holds everything needed to regenerate every number of the report without any API
key: the database (with every model request and response), the page text, the configuration,
reports and exports. Secrets (.env) and runtime state (.lutz/) are never included. PDFs are
optional because they are usually copyrighted.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from lutz import __version__
from lutz.core.db import agora, conectar
from lutz.core.project import Projeto

NUNCA = {".env", ".lutz"}


def exportar(projeto: Projeto, destino: Path, incluir_pdfs: bool = False) -> dict:
    con = conectar(projeto)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    arquivos: list[Path] = []
    for p in sorted(projeto.raiz.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(projeto.raiz)
        if rel.parts[0] in NUNCA or p.name.startswith("lutz.db-"):
            continue
        if rel.parts[0] == "pdfs" and not incluir_pdfs:
            continue
        if p.resolve() == Path(destino).resolve():
            continue
        arquivos.append(p)
    manifesto = {}
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in arquivos:
            rel = p.relative_to(projeto.raiz).as_posix()
            dados = p.read_bytes()
            manifesto[rel] = hashlib.sha256(dados).hexdigest()
            z.writestr(rel, dados)
        meta = {"lutz": __version__, "gerado_em": agora(), "pdfs_incluidos": incluir_pdfs, "arquivos": manifesto}
        z.writestr("manifest.json", json.dumps(meta, indent=2))
    return {"destino": str(destino), "arquivos": len(manifesto), "pdfs_incluidos": incluir_pdfs}
