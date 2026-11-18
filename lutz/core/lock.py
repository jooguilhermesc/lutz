"""Single-writer lock per project.

Only one process may write to a project at a time (CLI, web server job or anything else).
Readers never take the lock: SQLite in WAL mode lets them read while a writer works.

The lock is a JSON file in .lutz/lock with the owner PID, host, command and a heartbeat.
A lock is considered stale when its PID is gone on this host or its heartbeat is older than
``STALE_SECONDS``; a stale lock is taken over and the takeover is reported.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from lutz.core.errors import ProjetoOcupado
from lutz.core.project import Projeto

HEARTBEAT_SECONDS = 15
STALE_SECONDS = 90


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - process exists but belongs to another user
        return True
    except OSError:  # pragma: no cover - Windows without permission to signal
        return True
    return True


def ler_lock(projeto: Projeto) -> dict | None:
    caminho = projeto.estado / "lock"
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _obsoleto(info: dict) -> bool:
    if info.get("host") == socket.gethostname() and not _pid_vivo(int(info.get("pid", -1))):
        return True
    return time.time() - float(info.get("heartbeat", 0)) > STALE_SECONDS


class Lock:
    def __init__(self, projeto: Projeto, comando: str):
        self.projeto = projeto
        self.comando = comando
        self.caminho: Path = projeto.estado / "lock"
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.assumiu_obsoleto: dict | None = None

    def _info(self) -> dict:
        return {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "comando": self.comando,
            "iniciado": time.time(),
            "heartbeat": time.time(),
        }

    def adquirir(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                info = ler_lock(self.projeto)
                if info is None or _obsoleto(info) or (
                    info.get("pid") == os.getpid() and info.get("host") == socket.gethostname()
                ):
                    self.assumiu_obsoleto = info
                    self.caminho.unlink(missing_ok=True)
                    continue
                raise ProjetoOcupado(
                    f"O projeto está em uso por outro processo (PID {info.get('pid')}, "
                    f"comando '{info.get('comando')}'). Espere ele terminar ou pause a execução "
                    "pela interface web. Se esse processo não existe mais, o bloqueio expira em "
                    f"{STALE_SECONDS} segundos."
                ) from None
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._info(), fh)
            self._thread = threading.Thread(target=self._batimento, daemon=True)
            self._thread.start()
            return
        raise ProjetoOcupado("Não foi possível obter o bloqueio do projeto.")  # pragma: no cover

    def _batimento(self) -> None:
        while not self._parar.wait(HEARTBEAT_SECONDS):
            info = ler_lock(self.projeto)
            if not info or info.get("pid") != os.getpid():
                return
            info["heartbeat"] = time.time()
            tmp = self.caminho.with_suffix(".tmp")
            tmp.write_text(json.dumps(info), encoding="utf-8")
            os.replace(tmp, self.caminho)

    def liberar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        info = ler_lock(self.projeto)
        if info and info.get("pid") == os.getpid():
            self.caminho.unlink(missing_ok=True)


_REGISTRO: dict[str, list] = {}
_REGISTRO_LOCK = threading.Lock()


@contextmanager
def bloqueio(projeto: Projeto, comando: str):
    """Hold the project write lock. Re-entrant inside one process (threads of the web server
    share it; SQLite transactions serialize their writes); exclusive across processes."""
    chave = str(projeto.raiz.resolve())
    with _REGISTRO_LOCK:
        atual = _REGISTRO.get(chave)
        if atual is not None:
            atual[1] += 1
            lock = atual[0]
        else:
            lock = Lock(projeto, comando)
            lock.adquirir()
            _REGISTRO[chave] = [lock, 1]
    try:
        yield lock
    finally:
        with _REGISTRO_LOCK:
            atual = _REGISTRO[chave]
            atual[1] -= 1
            if atual[1] == 0:
                del _REGISTRO[chave]
                lock.liberar()
