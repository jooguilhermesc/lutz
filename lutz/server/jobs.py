"""Background jobs of the web server (no Redis, no Celery: threads in the server process).

Every job holds the project write lock while it runs, so a CLI command writing to the same
project at the same time fails with a clear message instead of corrupting the run. Only one
extraction job runs at a time per project.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from lutz.core.errors import LutzError
from lutz.core.lock import bloqueio
from lutz.core.project import Projeto


@dataclass
class Job:
    id: str
    tipo: str
    descricao: str
    status: str = "rodando"  # rodando | concluido | falhou
    eventos: list[dict] = field(default_factory=list)
    resultado: object = None
    erro: str = ""
    criado: float = field(default_factory=time.time)
    terminado: float | None = None
    parar: threading.Event = field(default_factory=threading.Event)
    execucao_id: int | None = None

    def publico(self) -> dict:
        return {"id": self.id, "tipo": self.tipo, "descricao": self.descricao, "status": self.status,
                "erro": self.erro, "criado": self.criado, "terminado": self.terminado,
                "execucao_id": self.execucao_id, "n_eventos": len(self.eventos),
                "resultado": self.resultado if isinstance(self.resultado, (dict, list, str, int, float)) else None}


class GerenciadorJobs:
    def __init__(self, projeto: Projeto):
        self.projeto = projeto
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def iniciar(self, tipo: str, descricao: str, funcao: Callable[[Callable[[dict], None], threading.Event], object],
                execucao_id: int | None = None) -> Job:
        with self._lock:
            if tipo == "extracao" and any(j.tipo == "extracao" and j.status == "rodando" for j in self.jobs.values()):
                raise LutzError("Já há uma extração em andamento neste projeto. Pause-a ou espere terminar.")
            job = Job(uuid.uuid4().hex[:12], tipo, descricao, execucao_id=execucao_id)
            self.jobs[job.id] = job

        def publicar(ev: dict) -> None:
            ev = {"t": time.time(), **ev}
            job.eventos.append(ev)
            if len(job.eventos) > 5000:
                del job.eventos[:1000]

        def alvo() -> None:
            try:
                with bloqueio(self.projeto, f"lutz web: {descricao}"):
                    job.resultado = funcao(publicar, job.parar)
                job.status = "concluido"
            except LutzError as exc:
                job.status, job.erro = "falhou", str(exc)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                job.status, job.erro = "falhou", f"{type(exc).__name__}: {exc}"
                publicar({"tipo": "erro", "detalhe": traceback.format_exc(limit=5)})
            finally:
                job.terminado = time.time()
                publicar({"tipo": "job_fim", "status": job.status, "erro": job.erro})

        threading.Thread(target=alvo, daemon=True, name=f"job-{job.id}").start()
        return job

    def obter(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def listar(self) -> list[dict]:
        return [j.publico() for j in sorted(self.jobs.values(), key=lambda j: -j.criado)]
