"""FastAPI server for the lutz web UI.

Serves the pre-built React SPA from lutz/web/ and exposes /api/* endpoints
that delegate to lutz's Python internals directly (no subprocess for data calls)
or stream subprocess output as Server-Sent Events for long-running operations.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles

from lutz.core.vector_store import VectorStore
from lutz.core.context_store import ContextStore
from lutz.utils.project import find_project_root, load_env

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*[mK]")

# Resolve the web frontend directory.
# Priority: web/dist/ (source checkout / editable install) > lutz/web/ (installed wheel)
# This ensures `npm run build` in web/ is picked up immediately without any copy step.
_PACKAGE_DIR = Path(__file__).parent.parent  # .../lutz/
_source_dist = _PACKAGE_DIR.parent / "web" / "dist"
WEB_DIR = _source_dist if _source_dist.exists() else _PACKAGE_DIR / "web"


def _get_root() -> Path:
    # LUTZ_PROJECT_ROOT is set by `lutz web` at startup — reliable regardless
    # of what uvicorn does with the working directory.
    env_root = os.environ.get("LUTZ_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    # Fallback: walk up from cwd (useful when app is imported directly in tests)
    root = find_project_root()
    if root is None:
        raise HTTPException(
            status_code=404,
            detail="No lutz project found. Run 'lutz init' first.",
        )
    return root


def _safe_child(parent: Path, name: str) -> Path:
    """Resolve ``parent / name`` and raise 400 if it escapes ``parent``."""
    resolved = (parent / name).resolve()
    if not resolved.is_relative_to(parent.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return resolved


def _lutz_bin() -> str:
    """Resolve the lutz executable path."""
    b = shutil.which("lutz")
    if b:
        return b
    # Same interpreter's scripts directory (works in venvs)
    scripts = Path(sys.executable).parent
    for name in ("lutz", "lutz.exe"):
        candidate = scripts / name
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("lutz binary not found. Make sure lutz-research is installed.")


async def _sse_stream(args: list[str], project_root: Path) -> AsyncIterator[str]:
    """Run a lutz CLI command and yield SSE-formatted lines."""
    # Merge .env into the subprocess environment
    env = {**os.environ}
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import dotenv_values
        for k, v in dotenv_values(env_file).items():
            if v is not None and k not in os.environ:
                env[k] = v

    lutz = _lutz_bin()
    proc = await asyncio.create_subprocess_exec(
        lutz,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(project_root),
        env=env,
    )
    assert proc.stdout is not None

    async for raw in proc.stdout:
        text = _ANSI.sub("", raw.decode(errors="replace")).strip()
        if text:
            yield f"data: {text}\n\n"

    code = await proc.wait()
    if code == 0:
        yield "data: __done__\n\n"
    else:
        yield f"data: __error__:{code}\n\n"


# ---------------------------------------------------------------------------
# Background job manager + WebSocket notifications
# ---------------------------------------------------------------------------

JobType = Literal["vectorize", "analysis", "citations", "roadmap"]
JobStatus = Literal["queued", "running", "done", "error", "cancelled"]

_MAX_JOBS = 50
_MAX_LOG_LINES = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    type: str
    status: str
    title: str
    params: dict
    started_at: str | None = None
    ended_at: str | None = None
    error_code: int | None = None
    logs: deque = field(default_factory=lambda: deque(maxlen=_MAX_LOG_LINES))
    _proc: object | None = field(default=None, repr=False)
    _tmp_prompt: str | None = field(default=None, repr=False)

    def to_dict(self, include_logs: bool = False) -> dict:
        d = {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error_code": self.error_code,
        }
        if include_logs:
            d["logs"] = list(self.logs)
        return d


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def _evict(self) -> None:
        terminal = [
            jid for jid, j in self._jobs.items()
            if j.status in ("done", "error", "cancelled")
        ]
        while len(self._jobs) >= _MAX_JOBS and terminal:
            del self._jobs[terminal.pop(0)]

    def create(self, type_: str, title: str, params: dict) -> Job:
        self._evict()
        job = Job(id=str(uuid.uuid4()), type=type_, status="queued", title=title, params=params)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[dict]:
        return [j.to_dict() for j in reversed(list(self._jobs.values()))]

    def remove(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status in ("running", "queued") and job._proc:
            try:
                job._proc.terminate()  # type: ignore[union-attr]
            except Exception:
                pass
        del self._jobs[job_id]
        return True


_job_manager = JobManager()


class WSManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        dead: set[WebSocket] = set()
        msg = json.dumps(payload)
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.discard(ws)


_ws_manager = WSManager()


async def _run_job(job: Job, args: list[str], project_root: Path) -> None:
    """Execute a lutz CLI subprocess for a background job."""
    job.status = "running"
    job.started_at = _now_iso()
    await _ws_manager.broadcast({"event": "job_update", "job": job.to_dict()})

    env = {**os.environ}
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import dotenv_values
        for k, v in dotenv_values(env_file).items():
            if v is not None and k not in os.environ:
                env[k] = v

    try:
        lutz = _lutz_bin()
        proc = await asyncio.create_subprocess_exec(
            lutz, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(project_root),
            env=env,
        )
        job._proc = proc

        batch: list[str] = []
        assert proc.stdout is not None
        async for raw in proc.stdout:
            if job.status == "cancelled":
                proc.terminate()
                break
            text = _ANSI.sub("", raw.decode(errors="replace")).strip()
            if not text:
                continue
            job.logs.append(text)
            batch.append(text)
            if len(batch) >= 5:
                await _ws_manager.broadcast({"event": "job_log", "job_id": job.id, "lines": batch})
                batch = []

        if batch:
            await _ws_manager.broadcast({"event": "job_log", "job_id": job.id, "lines": batch})

        if job.status != "cancelled":
            code = await proc.wait()
            job._proc = None
            job.ended_at = _now_iso()
            job.status = "done" if code == 0 else "error"
            if code != 0:
                job.error_code = code
    except Exception as exc:
        job.status = "error"
        job.ended_at = _now_iso()
        job.logs.append(f"[internal error] {exc}")
    finally:
        if job._tmp_prompt:
            try:
                Path(job._tmp_prompt).unlink(missing_ok=True)
            except Exception:
                pass
            job._tmp_prompt = None

    await _ws_manager.broadcast({"event": "job_update", "job": job.to_dict()})


def _build_job_args(job_type: str, body: dict, root: Path) -> tuple[list[str], str]:
    """Build CLI args and a human-readable title for a job."""
    import tempfile

    if job_type == "vectorize":
        args: list[str] = ["vectorize"]
        if body.get("chunk_size"):
            args += ["--chunk-size", str(body["chunk_size"])]
        if body.get("chunk_overlap"):
            args += ["--chunk-overlap", str(body["chunk_overlap"])]
        if body.get("skip_security"):
            args.append("--skip-security")
        if body.get("section_parse"):
            args.append("--section-parse")
        if body.get("quarantine"):
            args.append("--quarantine")
        return args, "Processar biblioteca"

    if job_type == "analysis":
        prompts_dir = root / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        inline = body.get("inline_prompt", "").strip()
        prompt_name = body.get("prompt", "")

        if inline:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8",
                dir=prompts_dir,
            )
            tmp.write(inline)
            tmp.close()
            prompt_path = tmp.name
            title = "Análise (prompt personalizado)"
        elif prompt_name:
            prompt_path_obj = _safe_child(prompts_dir, f"{prompt_name}.md")
            if not prompt_path_obj.exists():
                raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' not found")
            prompt_path = str(prompt_path_obj)
            title = f"Análise: {prompt_name}"
        else:
            raise HTTPException(status_code=400, detail="prompt or inline_prompt required")

        args = ["analysis", "--p", prompt_path]
        language = body.get("language", "pt")
        if language in ("pt", "en", "es"):
            args += ["--language", language]
        mode = body.get("mode", "per_article")
        if mode == "per_article":
            args.append("--per-article")
            if body.get("workers"):
                args += ["--workers", str(body["workers"])]
            if body.get("max_chunks"):
                args += ["--max-chunks-per-article", str(body["max_chunks"])]
        else:
            if body.get("workers"):
                args += ["--top-k", str(body["workers"])]

        return args, title

    if job_type == "citations":
        report_name = body.get("report", "")
        if not report_name:
            raise HTTPException(status_code=400, detail="report required")
        report_path = _safe_child(root / "analysis" / "execution_reports", f"{report_name}.json")
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        args = ["citations", "--analysis", str(report_path)]
        if body.get("only_relevant"):
            args.append("--only-relevant")
        language = body.get("language", "pt")
        if language in ("pt", "en", "es"):
            args += ["--language", language]
        return args, f"Citações: {report_name}"

    if job_type == "roadmap":
        report_name = body.get("report", "")
        if not report_name:
            raise HTTPException(status_code=400, detail="report required")
        report_path = _safe_child(root / "analysis" / "execution_reports", f"{report_name}.json")
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        args = ["citations", "--analysis", str(report_path), "--reading-roadmap"]
        if body.get("only_relevant"):
            args.append("--only-relevant")
        language = body.get("language", "pt")
        if language in ("pt", "en", "es"):
            args += ["--language", language]
        user_instructions = body.get("user_instructions", "").strip()
        if user_instructions:
            args += ["--user-instructions", user_instructions]
        return args, f"Roteiro: {report_name}"

    raise HTTPException(status_code=400, detail=f"Unknown job type: {job_type}")


# ---------------------------------------------------------------------------
# App + API router
# ---------------------------------------------------------------------------

app = FastAPI(docs_url=None, redoc_url=None, title="lutz")
api = APIRouter(prefix="/api")

# ── Project ──────────────────────────────────────────────────────────────────


@api.get("/project")
async def get_project() -> dict:
    root = _get_root()
    articles_dir = root / "articles"
    reports_dir = root / "analysis" / "execution_reports"
    articles = len(list(articles_dir.glob("*.pdf"))) if articles_dir.exists() else 0
    reports = len(list(reports_dir.glob("*.json"))) if reports_dir.exists() else 0
    return {"root": str(root), "articles": articles, "reports": reports}


# ── Articles ─────────────────────────────────────────────────────────────────


@api.get("/articles")
async def list_articles() -> dict:
    root = _get_root()
    arts_dir = root / "articles"
    if not arts_dir.exists():
        return {"articles": []}
    arts = [
        {"name": f.name, "size": f.stat().st_size}
        for f in sorted(arts_dir.glob("*.pdf"))
    ]
    return {"articles": arts}


@api.post("/articles/upload")
async def upload_articles(files: list[UploadFile] = File(...)) -> dict:
    root = _get_root()
    arts_dir = root / "articles"
    arts_dir.mkdir(parents=True, exist_ok=True)
    uploaded = []
    for f in files:
        safe_name = Path(f.filename or "upload.pdf").name  # strip any directory component
        dest = _safe_child(arts_dir, safe_name)
        with dest.open("wb") as fh:
            shutil.copyfileobj(f.file, fh)
        uploaded.append(dest.name)
    return {"uploaded": uploaded}


@api.delete("/articles/{name}")
async def delete_article(name: str) -> dict:
    root = _get_root()
    target = _safe_child(root / "articles", name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Article not found")
    target.unlink()
    return {"ok": True}


@api.delete("/articles")
async def delete_all_articles() -> dict:
    """Delete every PDF in the articles directory."""
    root = _get_root()
    arts_dir = root / "articles"
    if not arts_dir.exists():
        return {"deleted": 0}
    count = 0
    for f in arts_dir.glob("*.pdf"):
        f.unlink()
        count += 1
    return {"deleted": count}


@api.post("/articles/{name}/suggest-rename")
async def suggest_article_rename(name: str) -> dict:
    """Use the LLM to suggest a clean filename by reading the PDF's first pages directly."""
    import re as _re

    root = _get_root()
    target = _safe_child(root / "articles", name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Article not found")

    def _suggest() -> str:
        from lutz.core.llm_client import LLMClient
        from lutz.utils.project import load_env

        # Extract text from the first 3 pages of the PDF directly — no vector store needed
        sample_text = ""
        try:
            import fitz  # pymupdf
            doc = fitz.open(str(target))
            pages_text = []
            for page_num in range(min(3, len(doc))):
                text = doc[page_num].get_text("text").strip()
                if text:
                    pages_text.append(text)
            doc.close()
            sample_text = "\n\n---\n\n".join(pages_text)
        except Exception:
            try:
                import pdfplumber
                with pdfplumber.open(str(target)) as pdf:
                    pages_text = []
                    for page in pdf.pages[:3]:
                        text = (page.extract_text() or "").strip()
                        if text:
                            pages_text.append(text)
                    sample_text = "\n\n---\n\n".join(pages_text)
            except Exception as exc:
                raise RuntimeError(f"Could not extract text from PDF: {exc}") from exc

        if not sample_text.strip():
            raise RuntimeError("PDF appears to have no extractable text (may be scanned image).")

        # Truncate to ~3000 chars — enough for title, authors, abstract
        sample_text = sample_text[:3000]

        env = load_env(root)
        llm = LLMClient.from_env(env)
        system = (
            "You suggest concise, descriptive filenames for academic PDF files. "
            "Rules: use only ASCII letters, digits, underscores and hyphens; "
            "no spaces, no dots, no extension; max 80 characters. "
            "Derive the name from: paper title keywords, first author surname, and year if visible. "
            "Return ONLY the filename string, nothing else — no quotes, no explanation."
        )
        user_msg = (
            f"Original filename: {name}\n\n"
            f"First pages of the PDF:\n\n{sample_text}\n\n"
            "Suggest a filename (no extension, no quotes):"
        )
        raw, _ = llm.complete_messages(system=system, messages=[{"role": "user", "content": user_msg}])
        suggested = raw.strip().strip("\"'").removesuffix(".pdf")
        suggested = _re.sub(r"[^a-zA-Z0-9_\-]", "_", suggested)
        suggested = _re.sub(r"_+", "_", suggested).strip("_")
        suggested = (suggested or "article")[:80]
        return suggested + ".pdf"

    suggested = await asyncio.get_event_loop().run_in_executor(None, _suggest)
    return {"original": name, "suggested": suggested}


@api.post("/articles/{name}/rename")
async def rename_article(name: str, body: dict) -> dict:
    """Rename an article file and update all vector store references."""
    root = _get_root()
    new_name = (body.get("new_name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="new_name required")
    if not new_name.lower().endswith(".pdf"):
        new_name += ".pdf"

    src = _safe_child(root / "articles", name)
    dst = _safe_child(root / "articles", new_name)

    if not src.exists():
        raise HTTPException(status_code=404, detail="Article not found")
    if dst.exists() and dst != src:
        raise HTTPException(status_code=409, detail="A file with this name already exists")

    src.rename(dst)
    VectorStore(root / ".lutz" / "vector_store").rename_filename(name, new_name)

    return {"ok": True, "new_name": new_name}


@api.get("/articles/{name}/file")
async def get_article_file(name: str):
    """Serve the raw PDF file for in-browser viewing."""
    root = _get_root()
    target = _safe_child(root / "articles", name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Article not found")
    return FileResponse(
        path=str(target),
        media_type="application/pdf",
        filename=name,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


# ── Vector Store ──────────────────────────────────────────────────────────────


@api.get("/vector-store")
async def get_vector_store() -> dict:
    root = _get_root()
    db_path = root / ".lutz" / "vector_store"
    store = VectorStore(db_path)
    return store.summarize()


@api.delete("/vector-store")
async def reset_vector_store() -> dict:
    root = _get_root()
    db_path = root / ".lutz" / "vector_store"
    if db_path.exists():
        shutil.rmtree(db_path)
    return {"ok": True}


_VS_COLUMNS = ["filename", "chunk_index", "page", "section", "text",
               "vectorized_at", "embedding_model", "embedding_provider"]


@api.post("/vector-store/query")
async def query_vector_store(body: dict) -> dict:
    """Execute a DuckDB SQL query against the main vector store table.

    The table is named ``vectors`` and exposes all columns except ``embedding``.
    Returns columns, rows, count and elapsed time in ms.
    """
    import asyncio

    sql: str = (body.get("sql") or "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="sql required")

    root = _get_root()

    def _run() -> dict:
        import time
        import duckdb
        from lutz.core.vector_store import VectorStore

        vs = VectorStore(root / ".lutz" / "vector_store")
        if "articles" not in vs._db.table_names():
            return {"columns": [], "rows": [], "count": 0, "elapsed_ms": 0.0,
                    "error": "Vector store is empty — vectorize some articles first."}

        tbl = vs._db.open_table("articles")
        arrow_tbl = tbl.to_arrow()
        # Expose only non-embedding columns, silently skipping missing ones
        available = set(arrow_tbl.schema.names)
        cols = [c for c in _VS_COLUMNS if c in available]
        arrow_tbl = arrow_tbl.select(cols)

        con = duckdb.connect()
        con.register("vectors", arrow_tbl)

        t0 = time.perf_counter()
        try:
            rel = con.execute(sql)
            df = rel.fetchdf()
        except Exception as exc:
            return {"columns": [], "rows": [], "count": 0, "elapsed_ms": 0.0,
                    "error": str(exc)}
        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        columns = list(df.columns)
        rows: list[list] = []
        for row in df.itertuples(index=False):
            rows.append([
                None if v is None else (
                    str(v) if not isinstance(v, (str, int, float, bool)) else v
                )
                for v in row
            ])

        return {"columns": columns, "rows": rows, "count": len(rows), "elapsed_ms": elapsed}

    result = await asyncio.get_event_loop().run_in_executor(None, _run)
    return result


# ── Prompts ───────────────────────────────────────────────────────────────────


@api.get("/prompts")
async def list_prompts() -> dict:
    root = _get_root()
    prompts_dir = root / "prompts"
    if not prompts_dir.exists():
        return {"prompts": []}
    prompts = [
        {"name": f.stem, "path": str(f.relative_to(root))}
        for f in sorted(prompts_dir.glob("*.md"))
    ]
    return {"prompts": prompts}


@api.get("/prompts/{name}")
async def get_prompt(name: str) -> dict:
    root = _get_root()
    f = _safe_child(root / "prompts", f"{name}.md")
    if not f.exists():
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": name, "content": f.read_text(encoding="utf-8")}


@api.put("/prompts/{name}")
async def save_prompt(name: str, body: dict) -> dict:
    root = _get_root()
    prompts_dir = root / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    f = _safe_child(prompts_dir, f"{name}.md")
    f.write_text(body.get("content", ""), encoding="utf-8")
    return {"ok": True}


# ── Context files ─────────────────────────────────────────────────────────────

_CONTEXT_ACCEPT = {".pdf", ".docx", ".xlsx", ".xls", ".pptx"}


@api.get("/context")
async def list_context_files() -> dict:
    root = _get_root()
    ctx_dir = root / "context"
    store = ContextStore(root / ".lutz" / "context_store")
    chunk_counts = store.count_by_filename()

    if not ctx_dir.exists():
        return {"files": []}

    files = []
    for f in sorted(ctx_dir.iterdir()):
        if f.suffix.lower() in _CONTEXT_ACCEPT:
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "vectorized": f.name in chunk_counts,
                "chunks": chunk_counts.get(f.name, 0),
            })
    return {"files": files}


@api.post("/context/upload")
async def upload_context_files(files: list[UploadFile] = File(...)) -> dict:
    """Upload reference files and vectorize them immediately."""
    import asyncio
    root = _get_root()
    ctx_dir = root / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    errors = []
    for f in files:
        safe_name = Path(f.filename or "upload.bin").name
        if Path(safe_name).suffix.lower() not in _CONTEXT_ACCEPT:
            errors.append(f"{safe_name}: unsupported format")
            continue
        dest = _safe_child(ctx_dir, safe_name)
        with dest.open("wb") as fh:
            shutil.copyfileobj(f.file, fh)
        saved.append(dest)

    if not saved:
        raise HTTPException(status_code=400, detail="; ".join(errors) or "No valid files uploaded")

    # Vectorize in a thread (CPU-bound embedding, not async-friendly)
    uploaded_names = await asyncio.get_event_loop().run_in_executor(
        None, _vectorize_context_files, root, saved
    )

    return {"uploaded": uploaded_names, "errors": errors}


def _vectorize_context_files(root: Path, paths: list[Path]) -> list[str]:
    """Extract, chunk, embed and store context files. Runs in a thread."""
    from datetime import datetime, timezone
    from lutz.utils.document_reader import extract_pages
    from lutz.core.embedding_client import EmbeddingClient

    env = load_env(root)
    embedding_client = EmbeddingClient.from_env(env)
    store = ContextStore(root / ".lutz" / "context_store")
    now = datetime.now(timezone.utc).isoformat()

    _CHUNK_WORDS = 400
    uploaded = []

    for path in paths:
        try:
            pages = extract_pages(path)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"{path.name}: {e}")

        # Simple word-based chunking (no overlap needed for context files)
        chunks_text: list[tuple[int, str]] = []
        for page_num, text in pages:
            words = text.split()
            for i in range(0, max(len(words), 1), _CHUNK_WORDS):
                chunk = " ".join(words[i : i + _CHUNK_WORDS])
                if chunk.strip():
                    chunks_text.append((page_num, chunk))

        if not chunks_text:
            continue

        texts = [t for _, t in chunks_text]
        embeddings, _ = embedding_client.embed(texts)

        records = [
            {
                "filename": path.name,
                "chunk_index": idx,
                "page": page_num,
                "text": text,
                "embedding": emb,
                "vectorized_at": now,
                "embedding_model": embedding_client.model_id,
                "embedding_provider": embedding_client.provider,
            }
            for idx, ((page_num, text), emb) in enumerate(zip(chunks_text, embeddings))
        ]
        # Remove old vectors for this file before inserting new ones
        store.delete_by_filename(path.name)
        store.upsert(records)
        uploaded.append(path.name)

    return uploaded


@api.delete("/context/{name}")
async def delete_context_file(name: str) -> dict:
    root = _get_root()
    ctx_dir = root / "context"
    target = _safe_child(ctx_dir, name)

    store = ContextStore(root / ".lutz" / "context_store")
    store.delete_by_filename(name)

    if target.exists():
        target.unlink()

    return {"ok": True}


# ── Chat ──────────────────────────────────────────────────────────────────────

_CHAT_ACCEPT = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".txt", ".md", ".markdown", ".csv"}


@api.get("/chat/files")
async def list_chat_files() -> dict:
    root = _get_root()
    store = ContextStore(root / ".lutz" / "chat_store")
    counts = store.count_by_filename()
    return {"files": [{"name": k, "chunks": v} for k, v in sorted(counts.items())]}


@api.post("/chat/files/upload")
async def upload_chat_files(files: list[UploadFile] = File(...)) -> dict:
    """Upload files to the chat vector store and vectorize them immediately."""
    import asyncio
    root = _get_root()

    saved: list[Path] = []
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        for f in files:
            safe_name = Path(f.filename or "upload.bin").name
            if Path(safe_name).suffix.lower() not in _CHAT_ACCEPT:
                errors.append(f"{safe_name}: formato não suportado")
                continue
            dest = tmp_path / safe_name
            with dest.open("wb") as fh:
                shutil.copyfileobj(f.file, fh)
            saved.append(dest)

        if not saved:
            raise HTTPException(status_code=400, detail="; ".join(errors) or "Nenhum arquivo válido")

        uploaded_names = await asyncio.get_event_loop().run_in_executor(
            None, _vectorize_chat_files, root, saved
        )

    return {"uploaded": uploaded_names, "errors": errors}


def _vectorize_chat_files(root: Path, paths: list[Path]) -> list[str]:
    """Extract, chunk, embed and store files in the chat vector store."""
    from datetime import datetime, timezone
    from lutz.utils.document_reader import extract_pages
    from lutz.core.embedding_client import EmbeddingClient

    env = load_env(root)
    embedding_client = EmbeddingClient.from_env(env)
    store = ContextStore(root / ".lutz" / "chat_store")
    now = datetime.now(timezone.utc).isoformat()

    _CHUNK_WORDS = 400
    uploaded = []

    for path in paths:
        try:
            pages = extract_pages(path)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"{path.name}: {e}")

        chunks_text: list[tuple[int, str]] = []
        for page_num, text in pages:
            words = text.split()
            for i in range(0, max(len(words), 1), _CHUNK_WORDS):
                chunk = " ".join(words[i : i + _CHUNK_WORDS])
                if chunk.strip():
                    chunks_text.append((page_num, chunk))

        if not chunks_text:
            continue

        texts = [t for _, t in chunks_text]
        embeddings, _ = embedding_client.embed(texts)

        records = [
            {
                "filename": path.name,
                "chunk_index": idx,
                "page": page_num,
                "text": text,
                "embedding": emb,
                "vectorized_at": now,
                "embedding_model": embedding_client.model_id,
                "embedding_provider": embedding_client.provider,
            }
            for idx, ((page_num, text), emb) in enumerate(zip(chunks_text, embeddings))
        ]
        store.delete_by_filename(path.name)
        store.upsert(records)
        uploaded.append(path.name)

    return uploaded


@api.delete("/chat/files/{name}")
async def delete_chat_file(name: str) -> dict:
    root = _get_root()
    store = ContextStore(root / ".lutz" / "chat_store")
    store.delete_by_filename(name)
    return {"ok": True}


@api.delete("/chat/store")
async def reset_chat_store() -> dict:
    root = _get_root()
    store = ContextStore(root / ".lutz" / "chat_store")
    store.drop_all()
    return {"ok": True}


# ── Chat sessions ──────────────────────────────────────────────────────────────

def _sessions_dir(root: Path) -> Path:
    d = root / ".lutz" / "chat_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _memory_path(root: Path) -> Path:
    return root / ".lutz" / "chat_memory.json"


def _read_session(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_session(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_memory(root: Path) -> list[dict]:
    p = _memory_path(root)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("memories", [])


def _write_memory(root: Path, memories: list[dict]) -> None:
    _memory_path(root).write_text(
        json.dumps({"memories": memories}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _auto_extract_memories(root: Path, session_id: str, messages: list[dict]) -> None:
    """Extract key facts from the conversation and save as auto-memories.

    Runs in a background thread after each message exchange.
    Facts are tagged with source='auto' so they can be distinguished from pinned ones.
    Only triggers every 4 messages (2 user+assistant pairs) to avoid excessive calls.
    """
    # Only extract when conversation has at least 4 messages
    if len(messages) < 4:
        return

    # Check if we already extracted at this message count to avoid duplicates
    existing = _read_memory(root)
    already_extracted_at = {
        m.get("extracted_at_count")
        for m in existing
        if m.get("source") == "auto" and m.get("session_id") == session_id
    }
    if len(messages) in already_extracted_at:
        return

    try:
        from lutz.core.llm_client import LLMClient
        from lutz.utils.project import load_env

        env = load_env(root)
        llm = LLMClient.from_env(env)

        # Build a compact conversation transcript for extraction
        transcript = "\n".join(
            f"{'Usuário' if m['role'] == 'user' else 'Assistente'}: {m['content'][:400]}"
            for m in messages[-10:]  # last 10 messages to keep prompt short
        )

        system = (
            "You extract memorable facts from conversations for a research assistant. "
            "Return ONLY a JSON array of short strings (max 120 chars each), e.g.: "
            '[\"fact 1\", \"fact 2\"]. '
            "Extract 1-3 facts that would be useful for future conversations — "
            "things like: the researcher's topic, decisions made, preferences, key findings mentioned. "
            "Omit trivial or generic content. If nothing is worth remembering, return []."
        )
        user_msg = f"Conversation:\n\n{transcript}\n\nExtract memorable facts as JSON array:"

        raw, _ = llm.complete_messages(system=system, messages=[{"role": "user", "content": user_msg}])

        # Parse JSON array from response
        import re as _re
        match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
        if not match:
            return
        facts: list[str] = json.loads(match.group())
        if not isinstance(facts, list):
            return

        from datetime import datetime, timezone
        import uuid

        memories = _read_memory(root)
        # Remove previous auto-memories for this session to avoid accumulation
        memories = [m for m in memories if not (m.get("source") == "auto" and m.get("session_id") == session_id)]

        now = datetime.now(timezone.utc).isoformat()
        for fact in facts:
            fact = str(fact).strip()[:200]
            if fact:
                memories.append({
                    "id": str(uuid.uuid4()),
                    "text": fact,
                    "session_id": session_id,
                    "source": "auto",
                    "extracted_at_count": len(messages),
                    "created_at": now,
                })

        _write_memory(root, memories)
    except Exception:
        pass  # Never crash the main request on background extraction failure



@api.get("/chat/sessions")
async def list_chat_sessions() -> dict:
    root = _get_root()
    sessions_dir = _sessions_dir(root)
    sessions = []
    for f in sorted(sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = _read_session(f)
            sessions.append({
                "id": data["id"],
                "title": data.get("title", "Nova conversa"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            pass
    return {"sessions": sessions}


@api.post("/chat/sessions")
async def create_chat_session(body: dict = {}) -> dict:
    from datetime import datetime, timezone
    root = _get_root()
    sessions_dir = _sessions_dir(root)
    sid = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": sid,
        "title": body.get("title", "Nova conversa"),
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _write_session(sessions_dir / f"{sid}.json", data)
    return {"session": data}


@api.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str) -> dict:
    root = _get_root()
    path = _safe_child(_sessions_dir(root), f"{session_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": _read_session(path)}


@api.put("/chat/sessions/{session_id}/title")
async def rename_chat_session(session_id: str, body: dict) -> dict:
    root = _get_root()
    path = _safe_child(_sessions_dir(root), f"{session_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    data = _read_session(path)
    data["title"] = body.get("title", data["title"])
    _write_session(path, data)
    return {"ok": True}


@api.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> dict:
    root = _get_root()
    path = _safe_child(_sessions_dir(root), f"{session_id}.json")
    if path.exists():
        path.unlink()
    return {"ok": True}


# ── Chat memory ────────────────────────────────────────────────────────────────

@api.get("/chat/memory")
async def list_chat_memory() -> dict:
    root = _get_root()
    return {"memories": _read_memory(root)}


@api.post("/chat/memory")
async def add_chat_memory(body: dict) -> dict:
    from datetime import datetime, timezone
    root = _get_root()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    memories = _read_memory(root)
    entry = {
        "id": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f"),
        "text": text,
        "session_id": body.get("session_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    memories.append(entry)
    _write_memory(root, memories)
    return {"memory": entry}


@api.delete("/chat/memory/{memory_id}")
async def delete_chat_memory(memory_id: str) -> dict:
    root = _get_root()
    memories = [m for m in _read_memory(root) if m["id"] != memory_id]
    _write_memory(root, memories)
    return {"ok": True}


# ── Chat LLM core ─────────────────────────────────────────────────────────────

_CHAT_LANG_INSTRUCTIONS: dict[str, str] = {
    "pt": "Responda sempre em português (pt-BR).",
    "en": "Always respond in English.",
    "es": "Responde siempre en español.",
}


def _run_chat(
    root: Path,
    messages: list[dict],
    options: dict,
    language: str,
    memories: list[dict],
) -> dict:
    from lutz.core.embedding_client import EmbeddingClient
    from lutz.core.llm_client import LLMClient

    use_rag: bool = options.get("use_rag", True)
    use_model_knowledge: bool = options.get("use_model_knowledge", True)
    use_context_files: bool = options.get("use_context_files", False)
    top_k: int = int(options.get("top_k", 5))
    current_query = messages[-1]["content"]

    env = load_env(root)

    rag_chunks: list[dict] = []
    query_emb: list[float] | None = None

    if use_rag or use_context_files:
        emb_client = EmbeddingClient.from_env(env)
        query_emb, _ = emb_client.embed([current_query])
        query_emb = query_emb[0]

    if use_rag and query_emb is not None:
        chat_store = ContextStore(root / ".lutz" / "chat_store")
        if not chat_store.is_empty():
            rag_chunks += chat_store.search(query_emb, top_k=top_k)

    if use_context_files and query_emb is not None:
        ctx_store = ContextStore(root / ".lutz" / "context_store")
        if not ctx_store.is_empty():
            rag_chunks += ctx_store.search(query_emb, top_k=3)

    parts: list[str] = [
        "You are a helpful research assistant that helps researchers understand "
        "and discuss academic literature."
    ]
    if not use_model_knowledge:
        parts.append(
            "Important: only use the information provided in the context below. "
            "If the context does not contain enough information to answer, say so clearly."
        )
    if memories:
        mem_text = "\n".join(f"- {m['text']}" for m in memories)
        parts.append(f"## Persistent memory (facts from previous conversations)\n\n{mem_text}")
    if rag_chunks:
        ctx_text = "\n\n---\n\n".join(
            f"[{c['filename']} — page {c['page']}]\n{c['text']}"
            for c in rag_chunks
        )
        parts.append(f"## Context from uploaded files\n\n{ctx_text}")

    lang_instr = _CHAT_LANG_INSTRUCTIONS.get(language, _CHAT_LANG_INSTRUCTIONS["pt"])
    parts.append(f"## Language\n\n{lang_instr}")

    system = "\n\n".join(parts)
    llm = LLMClient.from_env(env)
    text, usage = llm.complete_messages(system=system, messages=messages)

    return {
        "response": text,
        "usage": usage,
        "sources": [{"filename": c["filename"], "page": c["page"]} for c in rag_chunks],
    }


@api.post("/chat/sessions/{session_id}/message")
async def chat_session_message(session_id: str, body: dict) -> dict:
    """Send a message in a session — saves history and returns LLM response."""
    import asyncio
    from datetime import datetime, timezone

    root = _get_root()
    path = _safe_child(_sessions_dir(root), f"{session_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    user_content: str = (body.get("content") or "").strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="content required")

    options: dict = body.get("options", {})
    language: str = body.get("language", "pt")

    session = _read_session(path)
    session["messages"].append({"role": "user", "content": user_content})

    # Auto-title from first user message
    if session.get("title") in ("Nova conversa", "New conversation", "Nueva conversación", ""):
        session["title"] = user_content[:60] + ("…" if len(user_content) > 60 else "")

    memories = _read_memory(root)
    result = await asyncio.get_event_loop().run_in_executor(
        None, _run_chat, root, session["messages"], options, language, memories
    )

    session["messages"].append({"role": "assistant", "content": result["response"]})
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_session(path, session)

    # Background: extract memorable facts from this conversation
    final_messages = list(session["messages"])
    asyncio.get_event_loop().run_in_executor(
        None, _auto_extract_memories, root, session_id, final_messages
    )

    return {**result, "title": session["title"]}


@api.post("/chat/message")
async def chat_message(body: dict) -> dict:
    """Stateless chat — no session persistence. Kept for backwards compatibility."""
    import asyncio
    messages: list[dict] = body.get("messages", [])
    if not messages or not messages[-1].get("content", "").strip():
        raise HTTPException(status_code=400, detail="messages required")
    root = _get_root()
    memories = _read_memory(root)
    result = await asyncio.get_event_loop().run_in_executor(
        None, _run_chat, root, messages, body.get("options", {}), body.get("language", "pt"), memories
    )
    return result


# ── Reports ───────────────────────────────────────────────────────────────────


def _parse_report_meta(f: Path) -> dict:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        meta = data.get("metadata", {})
        llm = meta.get("llm", {})
        arts = data.get("articles", [])
        report_type = meta.get("report_type", "")
        # Use generated_at for roadmap/citations reports (no started_at)
        started_at = meta.get("started_at", "") or meta.get("generated_at", "")
        return {
            "name": f.stem,
            "mode": meta.get("mode", ""),
            "report_type": report_type,
            "started_at": started_at,
            "articles": len(arts) if arts else meta.get("relevant", 0),
            "tokens": llm.get("total_tokens", 0),
            "elapsed": meta.get("elapsed_seconds", 0.0),
            "model": llm.get("model", ""),
        }
    except Exception:
        return {
            "name": f.stem,
            "mode": "",
            "report_type": "",
            "started_at": "",
            "articles": 0,
            "tokens": 0,
            "elapsed": 0.0,
            "model": "",
        }


@api.get("/reports")
async def list_reports(mode: str = "") -> dict:
    """List analysis reports.

    By default returns only per_article and rag reports (analysis runs).
    Pass ``?mode=all`` to include citations/roadmap reports too.
    """
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    if not reports_dir.exists():
        return {"reports": []}
    all_reports = [
        _parse_report_meta(f)
        for f in sorted(reports_dir.glob("*.json"), reverse=True)
    ]
    if mode == "all":
        return {"reports": all_reports}
    # Default: only analysis reports (per_article / rag)
    analysis_reports = [r for r in all_reports if r["mode"] in ("per_article", "rag")]
    return {"reports": analysis_reports}


@api.get("/reports/{name}")
async def get_report(name: str) -> dict:
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    f = _safe_child(reports_dir, f"{name}.json")
    if not f.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return json.loads(f.read_text(encoding="utf-8"))


@api.delete("/reports/{name}")
async def delete_report(name: str) -> dict:
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    f = _safe_child(reports_dir, f"{name}.json")
    if not f.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    f.unlink()
    return {"ok": True}


@api.delete("/reports")
async def delete_all_reports(also_vector_store: bool = False) -> dict:
    """Delete every report JSON file. Optionally also wipe the vector store."""
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    deleted = 0
    if reports_dir.exists():
        for f in reports_dir.glob("*.json"):
            f.unlink()
            deleted += 1
    dropped = 0
    if also_vector_store:
        vs = VectorStore(root / ".lutz" / "vector_store")
        dropped = vs.drop_all()
    return {"deleted": deleted, "vector_store_dropped": dropped}


# ── Config ────────────────────────────────────────────────────────────────────

_CONFIG_KEYS = [
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_MAX_TOKENS",
    "LLM_TEMPERATURE",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "OPENAI_BASE_URL",
    "DOCKER_MODEL_HOST",
    "REPORT_LANGUAGE",
]


@api.get("/config")
async def get_config() -> dict:
    root = _get_root()
    env = load_env(root)
    cfg: dict = {k: env.get(k, "") for k in _CONFIG_KEYS}
    cfg["has_openai_key"] = bool(env.get("OPENAI_API_KEY"))
    cfg["has_anthropic_key"] = bool(env.get("ANTHROPIC_API_KEY"))
    return cfg


@api.put("/config")
async def save_config(body: dict) -> dict:
    root = _get_root()
    env_file = root / ".env"
    from dotenv import dotenv_values
    existing: dict[str, str] = {}
    if env_file.exists():
        existing = {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    for k, v in body.items():
        if isinstance(v, str) and v:
            existing[k] = v
    lines = [f"{k}={v}" for k, v in existing.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True}


# ── SSE streaming ─────────────────────────────────────────────────────────────


@api.post("/vectorize/stream")
async def vectorize_stream(body: dict) -> StreamingResponse:
    root = _get_root()
    args: list[str] = ["vectorize"]
    if body.get("chunk_size"):
        args += ["--chunk-size", str(body["chunk_size"])]
    if body.get("chunk_overlap"):
        args += ["--chunk-overlap", str(body["chunk_overlap"])]
    if body.get("skip_security"):
        args.append("--skip-security")
    if body.get("section_parse"):
        args.append("--section-parse")
    if body.get("quarantine"):
        args.append("--quarantine")

    return StreamingResponse(
        _sse_stream(args, root),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/analysis/stream")
async def analysis_stream(body: dict) -> StreamingResponse:
    import tempfile
    root = _get_root()

    inline = body.get("inline_prompt", "").strip()
    prompt_name = body.get("prompt", "")

    prompts_dir = root / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    if inline:
        # Write the inline prompt to a temp file so the CLI can read it
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8",
            dir=prompts_dir,
        )
        tmp.write(inline)
        tmp.close()
        prompt_path = Path(tmp.name)
    elif prompt_name:
        prompt_path = _safe_child(prompts_dir, f"{prompt_name}.md")
        if not prompt_path.exists():
            raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' not found")
    else:
        raise HTTPException(status_code=400, detail="prompt or inline_prompt required")

    args: list[str] = ["analysis", "--p", str(prompt_path)]

    language = body.get("language", "pt")
    if language in ("pt", "en", "es"):
        args += ["--language", language]

    mode = body.get("mode", "per_article")
    if mode == "per_article":
        args.append("--per-article")
        if body.get("workers"):
            args += ["--workers", str(body["workers"])]
        if body.get("max_chunks"):
            args += ["--max-chunks-per-article", str(body["max_chunks"])]
    else:
        if body.get("workers"):
            args += ["--top-k", str(body["workers"])]

    async def _stream_and_cleanup():
        try:
            async for chunk in _sse_stream(args, root):
                yield chunk
        finally:
            if inline:
                Path(prompt_path).unlink(missing_ok=True)

    return StreamingResponse(
        _stream_and_cleanup(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/citations/stream")
async def citations_stream(body: dict) -> StreamingResponse:
    root = _get_root()
    report_name = body.get("report", "")
    if not report_name:
        raise HTTPException(status_code=400, detail="report required")
    report_path = _safe_child(root / "analysis" / "execution_reports", f"{report_name}.json")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    args: list[str] = ["citations", "--analysis", str(report_path)]
    if body.get("only_relevant"):
        args.append("--only-relevant")
    language = body.get("language", "pt")
    if language in ("pt", "en", "es"):
        args += ["--language", language]

    return StreamingResponse(
        _sse_stream(args, root),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/roadmap/stream")
async def roadmap_stream(body: dict) -> StreamingResponse:
    root = _get_root()
    report_name = body.get("report", "")
    if not report_name:
        raise HTTPException(status_code=400, detail="report required")
    report_path = _safe_child(root / "analysis" / "execution_reports", f"{report_name}.json")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    args: list[str] = ["citations", "--analysis", str(report_path), "--reading-roadmap"]
    if body.get("only_relevant"):
        args.append("--only-relevant")
    language = body.get("language", "pt")
    if language in ("pt", "en", "es"):
        args += ["--language", language]
    user_instructions = body.get("user_instructions", "").strip()
    if user_instructions:
        args += ["--user-instructions", user_instructions]

    return StreamingResponse(
        _sse_stream(args, root),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.get("/reports/{name}/html")
async def get_report_html(name: str):
    """Serve the pre-generated HTML report file."""
    from fastapi.responses import HTMLResponse
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    f = _safe_child(reports_dir, f"{name}.html")
    if not f.exists():
        raise HTTPException(
            status_code=404,
            detail="HTML report not found. Run the analysis/citations first to generate it.",
        )
    return HTMLResponse(content=f.read_text(encoding="utf-8"))


@api.get("/reports/{name}/pdf")
async def get_report_pdf(name: str):
    """Convert the pre-generated HTML report to PDF via WeasyPrint and stream it."""
    from fastapi.responses import Response
    try:
        import weasyprint
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF export requires WeasyPrint. Install it with: uv pip install weasyprint",
        )
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    f = _safe_child(reports_dir, f"{name}.html")
    if not f.exists():
        raise HTTPException(
            status_code=404,
            detail="HTML report not found. Run the analysis/citations first to generate it.",
        )
    html = weasyprint.HTML(filename=str(f))
    pdf_bytes = html.write_pdf()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'},
    )


# ── Background jobs ────────────────────────────────────────────────────────────


@api.post("/jobs")
async def create_job(body: dict) -> dict:
    root = _get_root()
    job_type = body.get("type", "")
    if job_type not in ("vectorize", "analysis", "citations", "roadmap"):
        raise HTTPException(status_code=400, detail="Invalid job type")

    args, title = _build_job_args(job_type, body, root)
    job = _job_manager.create(job_type, title, body)

    # Store tempfile path in job so _run_job can clean it up
    if job_type == "analysis" and body.get("inline_prompt", "").strip():
        # args[-1] for inline is the temp file path (last non-flag arg after --p)
        p_idx = args.index("--p") + 1 if "--p" in args else None
        if p_idx is not None:
            job._tmp_prompt = args[p_idx]

    asyncio.create_task(_run_job(job, args, root))
    return {"job_id": job.id, "job": job.to_dict()}


@api.get("/jobs")
async def list_jobs() -> dict:
    return {"jobs": _job_manager.list_all()}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job.to_dict(include_logs=True)}


@api.delete("/jobs/{job_id}")
async def cancel_or_remove_job(job_id: str) -> dict:
    job = _job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("running", "queued"):
        # Cancel: update status and terminate process, keep in list
        if job._proc:
            try:
                job._proc.terminate()  # type: ignore[union-attr]
            except Exception:
                pass
        job.status = "cancelled"
        job.ended_at = _now_iso()
        await _ws_manager.broadcast({"event": "job_update", "job": job.to_dict()})
    else:
        # Remove terminal job from list entirely
        _job_manager.remove(job_id)
        await _ws_manager.broadcast({"event": "job_removed", "job_id": job_id})
    return {"ok": True}


@api.get("/jobs/{job_id}/stream")
async def job_log_stream(job_id: str) -> StreamingResponse:
    """SSE: replay buffered logs, then tail live output until the job finishes."""
    job = _job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def _gen() -> AsyncIterator[str]:
        for line in list(job.logs):
            yield f"data: {line}\n\n"
        last_len = len(job.logs)
        while job.status in ("queued", "running"):
            await asyncio.sleep(0.3)
            current = list(job.logs)
            for line in current[last_len:]:
                yield f"data: {line}\n\n"
            last_len = len(current)
        if job.status == "done":
            yield "data: __done__\n\n"
        else:
            yield f"data: __error__:{job.error_code or 1}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Register API router + SPA static files
# ---------------------------------------------------------------------------

app.include_router(api)


# ── WebSocket notifications ────────────────────────────────────────────────────

@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket) -> None:
    await _ws_manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "event": "init",
            "jobs": _job_manager.list_all(),
        }))
        while True:
            await websocket.receive_text()  # keep alive; client messages ignored
    except WebSocketDisconnect:
        pass
    finally:
        _ws_manager.disconnect(websocket)

# Serve pre-built React assets at /assets/*
_assets_dir = WEB_DIR / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    """Serve static files or fall back to index.html for SPA routing."""
    if not WEB_DIR.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Web UI not found. "
                "If running from source, build the frontend first: cd web && npm run build"
            ),
        )
    candidate = WEB_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(WEB_DIR / "index.html")
