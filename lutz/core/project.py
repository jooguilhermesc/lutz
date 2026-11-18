"""A Lutz 1.0 project on disk.

Layout (all paths relative to the project root, so the folder can be copied or zipped):

    lutz.yaml          models, thresholds, budget, seeds (versionable, part of every run hash)
    .env               secrets and provider URLs only (never committed)
    lutz.db            SQLite: the whole review state
    pdfs/              original PDFs, renamed to <chave>.pdf
    texto/<chave>/     visible text per page (p0001.txt) and raw-order text (p0001.raw.txt)
    codebook.yaml      import/export copy of the codebook (the database is the source of truth)
    exports/           CSV sheets (extraction tables, adjudication, pilot sheets)
    relatorios/        generated reliability reports
    .lutz/             lock file and runtime state
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lutz.core.errors import ProjetoIncompativel, ProjetoNaoEncontrado

MARCADOR = "lutz.yaml"


@dataclass(frozen=True)
class Projeto:
    raiz: Path

    @property
    def yaml(self) -> Path:
        return self.raiz / MARCADOR

    @property
    def env(self) -> Path:
        return self.raiz / ".env"

    @property
    def db(self) -> Path:
        return self.raiz / "lutz.db"

    @property
    def pdfs(self) -> Path:
        return self.raiz / "pdfs"

    @property
    def texto(self) -> Path:
        return self.raiz / "texto"

    @property
    def exports(self) -> Path:
        return self.raiz / "exports"

    @property
    def relatorios(self) -> Path:
        return self.raiz / "relatorios"

    @property
    def estado(self) -> Path:
        return self.raiz / ".lutz"

    @property
    def codebook_yaml(self) -> Path:
        return self.raiz / "codebook.yaml"

    def rel(self, caminho: Path) -> str:
        """Path relative to the root, with forward slashes (stored in the database)."""
        return caminho.resolve().relative_to(self.raiz.resolve()).as_posix()

    def abs(self, relativo: str) -> Path:
        return self.raiz / relativo

    def garantir_pastas(self) -> None:
        for p in (self.pdfs, self.texto, self.exports, self.relatorios, self.estado):
            p.mkdir(parents=True, exist_ok=True)


def encontrar_projeto(inicio: Path | None = None) -> Projeto:
    """Walk up from *inicio* until a folder with lutz.yaml is found."""
    atual = (inicio or Path.cwd()).resolve()
    for pasta in [atual, *atual.parents]:
        if (pasta / MARCADOR).is_file():
            return Projeto(pasta)
        if (pasta / "articles").is_dir() and (pasta / ".lutz" / "vector_store").exists():
            raise ProjetoIncompativel(
                f"A pasta {pasta} é um projeto do Lutz 0.5.x. O Lutz 1.0 não lê projetos 0.5. "
                "Crie um projeto novo com 'lutz init' e importe os PDFs com 'lutz load', "
                "ou instale a versão antiga com: pip install \"lutz-research<1\"."
            )
    raise ProjetoNaoEncontrado(
        "Nenhum projeto do Lutz encontrado nesta pasta ou nas pastas acima. "
        "Crie um com 'lutz init <pasta>'."
    )
