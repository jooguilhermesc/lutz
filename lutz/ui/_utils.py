"""Utilitários compartilhados para a aplicação Streamlit do Lutz."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Generator, Optional

# Garante que lutz/ui/ esteja no sys.path para que as páginas possam importar _utils
_ui_dir = Path(__file__).resolve().parent
if str(_ui_dir) not in sys.path:
    sys.path.insert(0, str(_ui_dir))


def find_project_root() -> Optional[Path]:
    """Detecta o diretório raiz de um projeto Lutz."""
    try:
        from lutz.utils.project import find_project_root as _find
        return _find()
    except Exception:
        return None


def get_vector_store(project_root: Path):
    """Retorna uma instância de VectorStore para o projeto."""
    from lutz.core.vector_store import VectorStore
    return VectorStore(project_root / ".lutz" / "vector_store")


def is_valid_pdf(data: bytes) -> bool:
    """Verifica os bytes mágicos de um PDF."""
    return len(data) >= 4 and data[:4] == b"%PDF"


def safe_filename(name: str) -> str:
    """Retorna um nome de arquivo seguro, removendo componentes de caminho e caracteres perigosos."""
    name = os.path.basename(name)
    name = re.sub(r"[^\w\s\-.]", "", name).strip()
    return name or "upload.pdf"


_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07]*\x07|[()][0-9A-Za-z])')
_RICH_MARKUP_RE = re.compile(r'\[/?[a-zA-Z0-9_ #/]*\]')
_PROGRESS_BAR_RE = re.compile(r'[━█▓░]{4,}')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes, Rich markup and carriage returns from a string."""
    text = text.replace('\r', '')
    text = _ANSI_RE.sub('', text)
    text = _RICH_MARKUP_RE.sub('', text)
    return text.strip()


def is_meaningful_line(line: str) -> bool:
    """Return True if the line contains content worth displaying."""
    if not line.strip():
        return False
    # Skip lines that are mostly progress-bar block characters
    if _PROGRESS_BAR_RE.search(line) and len(line.strip()) < 80:
        stripped_blocks = _PROGRESS_BAR_RE.sub('', line).strip()
        if len(stripped_blocks) < 10:
            return False
    return True


def stream_command(
    cmd: list[str], cwd: Path
) -> Generator[tuple[str | None, int | None], None, None]:
    """Stream subprocess output line by line.

    Yields ``(line, None)`` for each output line (ANSI-stripped).
    Yields ``(None, returncode)`` when the process terminates.
    """
    if cmd and cmd[0] == "lutz":
        resolved = shutil.which("lutz") or cmd[0]
        cmd = [resolved] + cmd[1:]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(cwd),
            bufsize=1,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            yield strip_ansi(raw), None
        proc.wait()
        yield None, proc.returncode
    except FileNotFoundError:
        yield f"Comando '{cmd[0]}' não encontrado. Certifique-se de que o lutz está instalado.", None
        yield None, 1


def run_command(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Executa um comando de forma segura e retorna (returncode, saída_combinada)."""
    if cmd and cmd[0] == "lutz":
        resolved = shutil.which("lutz") or cmd[0]
        cmd = [resolved] + cmd[1:]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return 1, (
            f"Comando '{cmd[0]}' não encontrado. "
            "Certifique-se de que o lutz está instalado e disponível no PATH."
        )
