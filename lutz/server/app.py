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
import tempfile
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles

from lutz.core.vector_store import VectorStore
from lutz.core.context_store import ContextStore
from lutz.utils.project import find_project_root, load_env
from lutz.agent.conversation import ConversationManager

# Singleton ConversationManager — session state lives in the process.
_conversation_manager = ConversationManager()

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
        extraction = body.get("extraction_backend") or body.get("extraction")
        if extraction and extraction in ("pymupdf", "marker", "auto"):
            args += ["--extraction", extraction]
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    from lutz.server import db as _db
    try:
        root = _get_root()
        _db.init_db(root)
    except Exception:
        pass  # root may not exist yet (first run before lutz init)
    yield


app = FastAPI(docs_url=None, redoc_url=None, title="lutz", lifespan=lifespan)
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


def _json_val(v: object) -> object:
    """Serialize a single DataFrame cell to a JSON-safe Python value.

    Handles numpy scalar types and list columns produced by lutz UDFs
    (e.g. ``pca_project``, ``embedding_normalize``) so they reach the
    frontend as proper JSON arrays rather than string representations.
    """
    if v is None:
        return None
    if isinstance(v, bool):        # bool before int — it's a subclass
        return v
    if isinstance(v, (int, float, str)):
        return v
    if isinstance(v, list):
        return v                   # UDF list outputs: pass through as JSON array
    # numpy scalars — avoid top-level import
    mod = type(v).__module__
    if mod == "numpy" or mod.startswith("numpy."):
        import numpy as _np
        if isinstance(v, _np.integer):
            return int(v)
        if isinstance(v, _np.floating):
            return float(v)
        if isinstance(v, _np.bool_):
            return bool(v)
        if isinstance(v, _np.ndarray):
            return v.tolist()
    return str(v)


_SQL_BLOCKED_STATEMENTS = re.compile(
    r"""^\s*(COPY|ATTACH|DETACH|LOAD|INSTALL|IMPORT|EXPORT|INSERT|UPDATE|DELETE|
          CREATE|DROP|ALTER|TRUNCATE|REPLACE|MERGE|CALL|PRAGMA|SET|RESET|
          USE|SHOW|DESCRIBE|EXPLAIN|ANALYZE|VACUUM|CHECKPOINT|TRANSACTION|
          BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b""",
    re.IGNORECASE | re.VERBOSE,
)

_SQL_BLOCKED_FUNCTIONS = re.compile(
    r"""\b(read_csv|read_parquet|read_json|read_text|read_blob|glob|
          parquet_scan|csv_scan|json_scan|delta_scan|iceberg_scan|
          read_csv_auto|read_json_auto|scan_csv|scan_parquet)\s*\(""",
    re.IGNORECASE | re.VERBOSE,
)


def _validate_select_only(sql: str) -> None:
    """Raise ValueError if sql is not a safe single SELECT statement.

    Uses sqlglot for structural parse when available; falls back to
    regex keyword blocking if sqlglot is not installed.
    """
    try:
        import sqlglot
        import sqlglot.exp as exp

        statements = sqlglot.parse(sql)
        if not statements or len(statements) != 1:
            raise ValueError("Exactly one SQL statement is required")
        stmt = statements[0]
        if not isinstance(stmt, exp.Select):
            raise ValueError("Only SELECT statements are allowed")
        _BLOCKED_FUNCS = {
            "read_csv", "read_parquet", "read_json", "read_text", "read_blob",
            "glob", "parquet_scan", "csv_scan", "delta_scan", "iceberg_scan",
            "read_csv_auto", "read_json_auto", "scan_csv", "scan_parquet",
        }
        for func in stmt.find_all(exp.Anonymous):
            if func.name.lower() in _BLOCKED_FUNCS:
                raise ValueError(f"Function '{func.name}' is not allowed")
        for func in stmt.find_all(exp.Func):
            if type(func).__name__.lower() in _BLOCKED_FUNCS:
                raise ValueError(f"Function '{type(func).__name__}' is not allowed")
    except ImportError:
        # sqlglot not available — fall back to regex-based validation
        if _SQL_BLOCKED_STATEMENTS.match(sql):
            raise ValueError("Only SELECT statements are allowed")
        if _SQL_BLOCKED_FUNCTIONS.search(sql):
            raise ValueError("SQL contains a disallowed table-valued function")
        # Require the query to start with SELECT (after optional comments/whitespace)
        clean = re.sub(r"--[^\n]*", "", sql)   # strip line comments
        clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)  # strip block comments
        if not re.match(r"^\s*SELECT\b", clean, re.IGNORECASE):
            raise ValueError("Only SELECT statements are allowed")


@api.post("/vector-store/query")
async def query_vector_store(body: dict) -> dict:
    """Execute a DuckDB SQL query against the main vector store table.

    The table is named ``vectors``.  By default the ``embedding`` column is
    excluded for performance; pass ``"include_embeddings": true`` in the
    request body to expose it and unlock the lutz analytical UDFs
    (``cosine_distance``, ``kmeans_label``, ``pca_project``, …).

    Returns columns, rows, count and elapsed time in ms.
    """
    import asyncio

    sql: str = (body.get("sql") or "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="sql required")

    try:
        _validate_select_only(sql)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    include_embeddings: bool = bool(body.get("include_embeddings", False))
    root = _get_root()

    def _run() -> dict:
        import time
        import pyarrow as pa
        from lutz.analytics import create_connection
        from lutz.core.vector_store import VectorStore

        vs = VectorStore(root / ".lutz" / "vector_store")
        if "articles" not in vs._db.list_tables().tables:
            return {"columns": [], "rows": [], "count": 0, "elapsed_ms": 0.0,
                    "error": "Vector store is empty — vectorize some articles first."}

        tbl = vs._db.open_table("articles")
        arrow_tbl = tbl.to_arrow()
        available = set(arrow_tbl.schema.names)

        # Build the column list: metadata always included, embeddings optional.
        cols = [c for c in _VS_COLUMNS if c in available]
        if include_embeddings and "embedding" in available:
            # Cast from list<float32> → list<float64> so the lutz UDFs
            # (which expect DOUBLE[]) can operate without implicit coercion.
            emb_col = arrow_tbl.column("embedding")
            emb_f64 = emb_col.cast(pa.list_(pa.float64()))
            # Drop the original float32 column and append the cast version.
            emb_idx = arrow_tbl.schema.get_field_index("embedding")
            arrow_tbl = (
                arrow_tbl
                .remove_column(emb_idx)
                .append_column(pa.field("embedding", pa.list_(pa.float64())), emb_f64)
            )
            cols = cols + ["embedding"]

        arrow_tbl = arrow_tbl.select(cols)

        # create_connection() returns a DuckDB connection with all lutz UDFs.
        con = create_connection()
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
                _json_val(v)
                for v in row
            ])

        return {"columns": columns, "rows": rows, "count": len(rows), "elapsed_ms": elapsed}

    result = await asyncio.get_event_loop().run_in_executor(None, _run)
    return result


@api.get("/vector-store/udfs")
async def list_vector_store_udfs() -> dict:
    """Return the list of lutz analytical UDFs available in SQL queries."""
    from lutz.analytics.registry import list_udfs
    return {"udfs": list_udfs()}


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


def _filter_chunks_by_active_files(chunks: list[dict], active_names: set[str] | None) -> list[dict]:
    """Post-filter RAG chunks to exclude inactive files.

    active_names semantics (from db.get_active_filenames):
    - None  → no files registered for session → pass all chunks through unchanged
    - set   → filter to only chunks whose filename is in active_names
    """
    if active_names is None:
        return chunks
    return [c for c in chunks if c.get("filename") in active_names]


@api.patch("/chat/sessions/{session_id}/files/{file_id}")
async def patch_chat_file_active(session_id: str, file_id: int, body: dict) -> dict:
    """Toggle a file's active state for RAG retrieval within a session."""
    from lutz.server import db as _db

    if "active" not in body:
        raise HTTPException(status_code=400, detail="'active' field is required")
    active_val = body["active"]
    if not isinstance(active_val, bool):
        raise HTTPException(status_code=400, detail="'active' must be a boolean")

    root = _get_root()
    record = _db.get_chat_file(root, file_id, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found in this session")

    _db.set_file_active(root, file_id, active_val)
    return {"id": file_id, "active": 1 if active_val else 0}


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
    from lutz.server import db as _db
    existing = _db.list_memory(root)
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

        from lutz.server import db as _db
        _db.replace_auto_memory(root, session_id, facts, len(messages))
    except Exception:
        pass  # Never crash the main request on background extraction failure



@api.get("/chat/sessions")
async def list_chat_sessions() -> dict:
    from lutz.server import db as _db
    root = _get_root()
    return {"sessions": _db.list_sessions(root)}


@api.post("/chat/sessions")
async def create_chat_session(body: dict = {}) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    title = body.get("title", "Nova conversa")
    session = _db.create_session(root, title)
    return {"session": session}


@api.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    session = _db.get_session(root, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@api.put("/chat/sessions/{session_id}/title")
async def rename_chat_session(session_id: str, body: dict) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    session = _db.get_session(root, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _db.update_session_title(root, session_id, body.get("title", session["title"]))
    return {"ok": True}


@api.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    _db.delete_session(root, session_id)
    return {"ok": True}


# ── Chat memory ────────────────────────────────────────────────────────────────

@api.get("/chat/memory")
async def list_chat_memory() -> dict:
    from lutz.server import db as _db
    root = _get_root()
    return {"memories": _db.list_memory(root)}


@api.post("/chat/memory")
async def add_chat_memory(body: dict) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    entry = _db.add_memory(
        root,
        text,
        body.get("session_id") or None,
        "manual",  # always manual via API — 'auto' is created only by _auto_extract_memories
    )
    return {"memory": entry}


@api.put("/chat/memory/{memory_id}")
async def update_chat_memory(memory_id: str, body: dict) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    try:
        updated = _db.update_memory(root, memory_id, content)
    except KeyError:
        raise HTTPException(status_code=404, detail="Memory not found")
    return updated


@api.delete("/chat/memory/{memory_id}")
async def delete_chat_memory(memory_id: str) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    _db.delete_memory(root, memory_id)
    return {"ok": True}


@api.get("/chat/sessions/{session_id}/memory")
async def get_session_memory(session_id: str) -> dict:
    from lutz.server import db as _db
    root = _get_root()
    memories = _db.get_memories(root, session_id=session_id)
    estimated_tokens = int(sum(len(m["content"].split()) * 1.3 for m in memories))
    return {
        "memories": memories,
        "count": len(memories),
        "estimated_tokens": estimated_tokens,
    }


def _get_llm_for_compaction(root: Path):
    """Return an LLMClient for memory compaction. Extracted for testability."""
    from lutz.core.llm_client import LLMClient
    from lutz.utils.project import load_env
    env = load_env(root)
    return LLMClient.from_env(env)


def _compact_memories(root: Path, session_id: str) -> bool:
    """Compact session memories when total token count exceeds 1500 tokens.

    Returns True if compaction was performed, False if skipped.
    """
    from lutz.server import db as _db

    memories = _db.get_memories(root, session_id=session_id)
    if not memories:
        return False

    estimated_tokens = sum(len(m["content"].split()) * 1.3 for m in memories)
    if estimated_tokens <= 1500:
        return False

    try:
        llm = _get_llm_for_compaction(root)
        all_text = "\n".join(f"- {m['content']}" for m in memories)
        system = (
            "You are a memory compactor for a research assistant. "
            "Summarize the following memory entries into at most 5 concise bullet points. "
            "Preserve the most important facts. Return ONLY bullet points, one per line, "
            "starting each with '- '."
        )
        user_msg = f"Memory entries to summarize:\n\n{all_text}\n\nSummarized bullets:"
        raw, _ = llm.complete(system, user_msg)

        bullets = [
            line.lstrip("- ").strip()
            for line in raw.splitlines()
            if line.strip().startswith("-")
        ]
        if not bullets:
            bullets = [raw.strip()[:500]]

        # Replace all session memories with compacted ones
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        with _db.get_db(root) as conn:
            conn.execute(
                "DELETE FROM chat_memory WHERE session_id=?",
                (session_id,),
            )
            for bullet in bullets:
                conn.execute(
                    "INSERT INTO chat_memory "
                    "(id, text, session_id, source, extracted_at_count, created_at, content, updated_at) "
                    "VALUES (?, ?, ?, 'auto', NULL, ?, ?, ?)",
                    (str(uuid.uuid4()), bullet, session_id, now, bullet, now),
                )
        return True
    except Exception:
        return False


# ── Chat LLM core ─────────────────────────────────────────────────────────────

_CHAT_LANG_INSTRUCTIONS: dict[str, str] = {
    "pt": "Responda sempre em português (pt-BR).",
    "en": "Always respond in English.",
    "es": "Responde siempre en español.",
}


_REASONING_SETTINGS: dict[str, dict] = {
    "fast": {"temperature": 0.1, "system_append": None},
    "balanced": {
        "temperature": 0.2,
        "system_append": "Justifique brevemente sua resposta.",
    },
    "deep": {
        "temperature": 0.3,
        "system_append": (
            "Antes de responder, analise o problema passo a passo, considere múltiplas "
            "perspectivas e argumente contra as premissas quando relevante."
        ),
    },
}


_REPORT_CONTEXT_MAX_CHARS = 8000


def _build_report_context(root: Path, report_ids: list[str]) -> tuple[str, list[dict]]:
    """Carrega JSONs de relatórios e monta texto estruturado para injeção no prompt.

    Retorna (texto_contexto, lista_fontes).
    O texto é limitado a _REPORT_CONTEXT_MAX_CHARS caracteres.
    IDs de relatórios que não existem ou falham ao carregar são ignorados silenciosamente.
    """
    reports_dir = root / "analysis" / "execution_reports"
    lines: list[str] = []
    sources: list[dict] = []
    total_chars = 0

    for report_id in report_ids:
        try:
            report_path = _safe_child(reports_dir, f"{report_id}.json")
        except HTTPException:
            continue  # ID fora do diretório — ignora silenciosamente
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue  # arquivo ausente ou inválido — ignora silenciosamente

        analysis_type = str(data.get("analysis_type") or data.get("type") or "analysis")[:50]
        created_at = data.get("created_at") or ""
        results = data.get("results") or []

        header = f"[Relatório: {report_id}.json — {created_at}]"
        header += f"\nTipo: {analysis_type} | Artigos: {len(results)}\n"

        block_lines: list[str] = [header]
        for item in results:
            filename = str(item.get("filename", ""))[:200]
            decision = str(item.get("decision", ""))[:50]
            justification = str(item.get("justification", ""))[:500]
            title = str(item.get("title", ""))[:200]
            entry = f"- [DATA: filename] {filename}"
            if title:
                entry += f' [DATA: title] "{title}"'
            entry += f" [DATA: decision] [{decision}]"
            if justification:
                entry += f" [DATA: justification] {justification}"
            block_lines.append(entry)

        block = "\n".join(block_lines)

        # Truncar se ultrapassar o limite de caracteres
        remaining = _REPORT_CONTEXT_MAX_CHARS - total_chars
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining] + "\n[... truncado ...]"
            lines.append(block)
            sources.append({"filename": f"{report_id}.json", "page": 0})
            break

        lines.append(block)
        sources.append({"filename": f"{report_id}.json", "page": 0})
        total_chars += len(block)

    if not lines:
        return "", []

    return "\n\n---\n\n".join(lines), sources


def _build_chat_context(
    root: Path,
    messages: list[dict],
    options: dict,
    language: str,
    memories: list[dict],
) -> dict:
    """Build system prompt, retrieve RAG chunks, and return context dict.

    Returns a dict with keys:
        system: str — the system prompt
        temperature: float
        sources: list[dict] — all RAG/library/report source chunks
        thinking_config: dict | None
    """
    from lutz.core.embedding_client import EmbeddingClient

    use_rag: bool = options.get("use_rag", True)
    use_model_knowledge: bool = options.get("use_model_knowledge", True)
    use_context_files: bool = options.get("use_context_files", False)
    use_library: bool = options.get("use_library", False)
    top_k: int = int(options.get("top_k", 5))
    reasoning_level: str = options.get("reasoning_level", "balanced")
    selected_report_ids: list[str] = options.get("selected_report_ids") or []
    VALID_REASONING_LEVELS = {"fast", "balanced", "deep"}
    if reasoning_level not in VALID_REASONING_LEVELS:
        reasoning_level = "balanced"
    current_query = messages[-1]["content"]

    env = load_env(root)

    rag_chunks: list[dict] = []
    library_chunks: list[dict] = []
    query_emb: list[float] | None = None

    if use_rag or use_context_files or use_library:
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

    if use_library and query_emb is not None:
        try:
            lib_store = VectorStore(root / ".lutz" / "vector_store")
            library_chunks = lib_store.search(query_emb, top_k=top_k) or []
        except Exception:
            library_chunks = []

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

    report_sources: list[dict] = []
    if selected_report_ids:
        report_context, report_sources = _build_report_context(root, selected_report_ids)
        if report_context:
            parts.append(f"## Relatórios de Análise\n\n{report_context}")

    if rag_chunks:
        ctx_text = "\n\n---\n\n".join(
            f"[{c['filename']} — page {c['page']}]\n{c['text']}"
            for c in rag_chunks
        )
        parts.append(f"## Context from uploaded files\n\n{ctx_text}")

    if library_chunks:
        lib_text = "\n\n---\n\n".join(
            f"[Biblioteca: {c['filename']} — p.{c['page']}]\n{c['text']}"
            for c in library_chunks
        )
        parts.append(f"## Biblioteca de artigos\n\n{lib_text}")

    lang_instr = _CHAT_LANG_INSTRUCTIONS.get(language, _CHAT_LANG_INSTRUCTIONS["pt"])
    parts.append(f"## Language\n\n{lang_instr}")

    reasoning = _REASONING_SETTINGS.get(reasoning_level, _REASONING_SETTINGS["balanced"])
    if reasoning["system_append"]:
        parts.append(reasoning["system_append"])

    system = "\n\n".join(parts)
    temperature: float = reasoning["temperature"]

    thinking_config: dict | None = None
    if env.get("LLM_PROVIDER", "").lower() == "anthropic" and reasoning_level == "deep":
        thinking_config = {"type": "enabled", "budget_tokens": 8000}

    return {
        "system": system,
        "temperature": temperature,
        "sources": rag_chunks + library_chunks + report_sources,
        "thinking_config": thinking_config,
    }


def _run_chat(
    root: Path,
    messages: list[dict],
    options: dict,
    language: str,
    memories: list[dict],
) -> dict:
    from lutz.core.llm_client import LLMClient

    context = _build_chat_context(root, messages, options, language, memories)
    system: str = context["system"]
    temperature: float = context["temperature"]
    all_sources: list[dict] = context["sources"]
    thinking_config: dict | None = context.get("thinking_config")

    env = load_env(root)
    llm = LLMClient.from_env(env)

    text, usage = llm.complete_messages(
        system=system,
        messages=messages,
        temperature=temperature,
        thinking=thinking_config,
    )

    thinking_content: str | None = usage.pop("thinking_content", None)

    result = {
        "response": text,
        "usage": usage,
        "sources": [{"filename": c["filename"], "page": c["page"]} for c in all_sources],
    }
    if thinking_content is not None:
        result["thinking_content"] = thinking_content
    return result


@api.post("/chat/sessions/{session_id}/message")
async def chat_session_message(session_id: str, body: dict) -> dict:
    """Send a message in a session — saves history and returns LLM response."""
    import asyncio

    from lutz.server import db as _db

    root = _get_root()
    session = _db.get_session(root, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_content: str = (body.get("content") or "").strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="content required")

    options: dict = body.get("options", {})
    language: str = body.get("language", "pt")

    _db.add_message(root, session_id, "user", user_content)

    # Auto-title from first user message
    current_title: str = session["title"]
    if current_title in ("Nova conversa", "New conversation", "Nueva conversación", ""):
        current_title = user_content[:60] + ("…" if len(user_content) > 60 else "")
        _db.update_session_title(root, session_id, current_title)

    # Build full message list for LLM context
    chat_messages = _db.get_messages(root, session_id)
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in chat_messages]

    memories = _db.list_memory(root)
    result = await asyncio.get_event_loop().run_in_executor(
        None, _run_chat, root, llm_messages, options, language, memories
    )

    sources = result.get("sources")
    _db.add_message(root, session_id, "assistant", result["response"], sources=sources)
    _db.update_session_updated_at(root, session_id)

    # Background: extract memorable facts from this conversation
    final_messages = _db.get_messages(root, session_id)
    plain_messages = [{"role": m["role"], "content": m["content"]} for m in final_messages]
    asyncio.get_event_loop().run_in_executor(
        None, _auto_extract_memories, root, session_id, plain_messages
    )

    return {**result, "title": current_title}


@api.post("/chat/sessions/{session_id}/message/stream")
async def chat_session_message_stream(session_id: str, body: dict) -> StreamingResponse:
    """Send a message in a session and stream the LLM response via SSE."""
    from lutz.server import db as _db

    root = _get_root()
    session = _db.get_session(root, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_content: str = (body.get("message") or body.get("content") or "").strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="message required")

    options: dict = body.get("options", {})
    language: str = body.get("language", "pt")

    _db.add_message(root, session_id, "user", user_content)

    current_title: str = session["title"]
    if current_title in ("Nova conversa", "New conversation", "Nueva conversación", ""):
        current_title = user_content[:60] + ("\u2026" if len(user_content) > 60 else "")
        _db.update_session_title(root, session_id, current_title)

    chat_messages = _db.get_messages(root, session_id)
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in chat_messages]
    memories = _db.list_memory(root)

    async def _generate():
        import json as _json

        # Run context-building (RAG, embedding) in executor — it's blocking
        loop = asyncio.get_event_loop()
        context = await loop.run_in_executor(
            None, _build_chat_context, root, llm_messages, options, language, memories
        )

        system: str = context["system"]
        temperature: float = context["temperature"]
        all_sources: list[dict] = context["sources"]
        thinking_config: dict | None = context.get("thinking_config")

        from lutz.core.llm_client import LLMClient
        env = load_env(root)
        llm = LLMClient.from_env(env)

        accumulated = ""
        try:
            for chunk in llm.stream_messages(system, llm_messages, temperature=temperature):
                accumulated += chunk
                event = _json.dumps({"type": "token", "content": chunk})
                yield f"data: {event}\n\n"
        except Exception:
            # Fallback: call complete_messages if streaming fails
            text, _ = await loop.run_in_executor(
                None,
                lambda: llm.complete_messages(
                    system=system,
                    messages=llm_messages,
                    temperature=temperature,
                    thinking=thinking_config,
                ),
            )
            accumulated = text
            event = _json.dumps({"type": "token", "content": text})
            yield f"data: {event}\n\n"

        # Persist assistant message with sources
        sources_simple = [{"filename": c["filename"], "page": c["page"]} for c in all_sources]
        _db.add_message(root, session_id, "assistant", accumulated, sources=sources_simple)
        _db.update_session_updated_at(root, session_id)

        # Emit sources event
        if sources_simple:
            event = _json.dumps({"type": "sources", "sources": sources_simple})
            yield f"data: {event}\n\n"

        # Emit done event
        event = _json.dumps({"type": "done", "title": current_title})
        yield f"data: {event}\n\n"

        # Background: extract memories
        final_messages = _db.get_messages(root, session_id)
        plain_messages = [{"role": m["role"], "content": m["content"]} for m in final_messages]
        asyncio.get_event_loop().run_in_executor(
            None, _auto_extract_memories, root, session_id, plain_messages
        )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/chat/message")
async def chat_message(body: dict) -> dict:
    """Stateless chat — no session persistence. Kept for backwards compatibility."""
    import asyncio

    from lutz.server import db as _db

    messages: list[dict] = body.get("messages", [])
    if not messages or not messages[-1].get("content", "").strip():
        raise HTTPException(status_code=400, detail="messages required")
    root = _get_root()
    memories = _db.list_memory(root)
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


@api.get("/chat/reports")
async def list_chat_reports() -> dict:
    """Lista os relatórios disponíveis para injeção no chat.

    Retorna uma lista de { id, filename, timestamp, analysis_type, article_count }.
    Se o diretório não existe, retorna {"reports": []}.
    """
    root = _get_root()
    reports_dir = root / "analysis" / "execution_reports"
    if not reports_dir.exists():
        return {"reports": []}

    reports: list[dict] = []
    for f in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        analysis_type = (
            data.get("analysis_type")
            or data.get("type")
            or "analysis"
        )
        results = data.get("results")
        article_count = len(results) if isinstance(results, list) else 0
        timestamp = data.get("created_at") or ""
        if not timestamp:
            import datetime as _dt
            timestamp = _dt.datetime.fromtimestamp(
                f.stat().st_mtime, tz=_dt.timezone.utc
            ).isoformat()

        reports.append({
            "id": f.stem,
            "filename": f.name,
            "timestamp": timestamp,
            "analysis_type": analysis_type,
            "article_count": article_count,
        })

    return {"reports": reports}


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
    extraction = body.get("extraction_backend") or body.get("extraction")
    if extraction and extraction in ("pymupdf", "marker", "auto"):
        args += ["--extraction", extraction]

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


# ── Store catalog metadata ────────────────────────────────────────────────────

_CATALOG_COLUMN_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "articles": {
        "filename": "Nome do arquivo PDF",
        "chunk_index": "Índice do chunk no documento",
        "page": "Página do PDF",
        "char_start": "Posição do caractere inicial no texto",
        "section": "Seção inferida do documento",
        "text": "Conteúdo textual do chunk",
        "embedding": "Vetor de embedding semântico",
        "vectorized_at": "Timestamp de vetorização (ISO 8601)",
        "embedding_model": "Modelo usado para gerar o embedding",
        "embedding_provider": "Provedor do modelo de embedding",
        "extraction_backend": "Backend usado para extrair texto do PDF",
    },
    "context": {
        "filename": "Nome do arquivo de contexto",
        "chunk_index": "Índice do chunk",
        "page": "Página do arquivo",
        "text": "Conteúdo do chunk",
        "embedding": "Vetor de embedding",
        "vectorized_at": "Timestamp de vetorização (ISO 8601)",
        "embedding_model": "Modelo usado para gerar o embedding",
        "embedding_provider": "Provedor do modelo de embedding",
    },
    "chat_files": {
        "filename": "Nome do arquivo carregado no chat",
        "chunk_index": "Índice do chunk",
        "page": "Página do arquivo",
        "text": "Conteúdo do chunk",
        "embedding": "Vetor de embedding",
        "vectorized_at": "Timestamp de vetorização (ISO 8601)",
        "embedding_model": "Modelo usado para gerar o embedding",
        "embedding_provider": "Provedor do modelo de embedding",
    },
}

_CATALOG_TABLE_DESCRIPTIONS: dict[str, str] = {
    "articles": "Chunks de artigos científicos vetorizados",
    "context": "Arquivos de contexto para análise",
    "chat_files": "Arquivos carregados em sessões de chat",
}

_CATALOG_FALLBACK_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "articles": [
        ("filename", "string"),
        ("chunk_index", "int32"),
        ("page", "int32"),
        ("char_start", "int32"),
        ("section", "string"),
        ("text", "string"),
        ("embedding", "float32[N]"),
        ("vectorized_at", "string"),
        ("embedding_model", "string"),
        ("embedding_provider", "string"),
        ("extraction_backend", "string"),
    ],
    "context": [
        ("filename", "string"),
        ("chunk_index", "int32"),
        ("page", "int32"),
        ("text", "string"),
        ("embedding", "float32[N]"),
        ("vectorized_at", "string"),
        ("embedding_model", "string"),
        ("embedding_provider", "string"),
    ],
    "chat_files": [
        ("filename", "string"),
        ("chunk_index", "int32"),
        ("page", "int32"),
        ("text", "string"),
        ("embedding", "float32[N]"),
        ("vectorized_at", "string"),
        ("embedding_model", "string"),
        ("embedding_provider", "string"),
    ],
}


def _pa_type_to_str(field) -> str:
    """Convert a PyArrow field type to a human-readable string."""
    import pyarrow as pa

    t = field.type
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "string"
    if pa.types.is_int32(t):
        return "int32"
    if pa.types.is_int64(t):
        return "int64"
    if pa.types.is_float32(t):
        return "float32"
    if pa.types.is_float64(t):
        return "float64"
    if pa.types.is_boolean(t):
        return "bool"
    if pa.types.is_list(t) or pa.types.is_large_list(t) or pa.types.is_fixed_size_list(t):
        vtype = t.value_type
        if pa.types.is_float32(vtype):
            return "float32[N]"
        if pa.types.is_float64(vtype):
            return "float64[N]"
        return f"list[{vtype}]"
    return str(t)


def _build_catalog_table(
    table_key: str,
    db_path: Path,
    lancedb_table_name: str,
) -> dict:
    """Build a single catalog table entry, falling back to static metadata on error."""
    desc_map = _CATALOG_COLUMN_DESCRIPTIONS.get(table_key, {})
    fallback_cols = _CATALOG_FALLBACK_COLUMNS.get(table_key, [])
    table_description = _CATALOG_TABLE_DESCRIPTIONS.get(table_key, table_key)

    try:
        import lancedb

        db = lancedb.connect(str(db_path))
        if lancedb_table_name not in db.list_tables().tables:
            raise ValueError("table not present")

        tbl = db.open_table(lancedb_table_name)
        record_count: int = tbl.count_rows()

        last_updated: str | None = None
        schema = tbl.schema
        if "vectorized_at" in schema.names:
            arrow_tbl = tbl.to_arrow().select(["vectorized_at"])
            timestamps = [v for v in arrow_tbl.column("vectorized_at").to_pylist() if v]
            last_updated = max(timestamps) if timestamps else None

        columns = [
            {
                "name": field.name,
                "type": _pa_type_to_str(field),
                "description": desc_map.get(field.name, ""),
            }
            for field in schema
        ]
    except Exception:
        record_count = 0
        last_updated = None
        columns = [
            {"name": name, "type": typ, "description": desc_map.get(name, "")}
            for name, typ in fallback_cols
        ]

    return {
        "name": table_key,
        "description": table_description,
        "record_count": record_count,
        "last_updated": last_updated,
        "columns": columns,
    }


@api.get("/store/catalog")
async def get_store_catalog() -> dict:
    """Return schema and record counts for all LanceDB stores."""
    root = _get_root()
    lutz_dir = root / ".lutz"

    store_configs = [
        ("articles", lutz_dir / "vector_store", "articles"),
        ("context", lutz_dir / "context_store", "context"),
        ("chat_files", lutz_dir / "chat_store", "context"),
    ]

    tables = [_build_catalog_table(k, p, t) for k, p, t in store_configs]
    return {"tables": tables}


# ── Agent ─────────────────────────────────────────────────────────────────────


@api.get("/agent/tools")
async def list_agent_tools() -> dict:
    """Return all registered agent tools with their JSON Schema definitions."""
    from lutz.agent.tools import get_tool_registry
    registry = get_tool_registry()
    return {"tools": registry.list_tools()}


@api.get("/agent/model-profiles")
async def list_model_profiles() -> dict:
    """Return all model profiles from the ModelSelector catalogue."""
    from lutz.agent.model_router import ModelRouter
    router = ModelRouter()
    return {"profiles": router.selector._profiles}


@api.get("/agent/sessions")
async def list_agent_sessions() -> dict:
    """List all chat sessions (agent sessions share the same table)."""
    from lutz.server import db as _db
    root = _get_root()
    return {"sessions": _db.list_sessions(root)}


@api.get("/agent/sessions/{session_id}")
async def get_agent_session(session_id: str) -> dict:
    """Return a single agent session with its message history."""
    from lutz.server import db as _db
    root = _get_root()
    session = _db.get_session(root, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


_MAX_AGENT_MESSAGE_CHARS = 8000


def _run_agent(session_id: str, user_message: str, root: "Path") -> dict:
    """Execute AgentOrchestrator synchronously and return the raw result dict.

    Intended to be called from a thread-executor so it does not block the
    asyncio event loop.  Persists the exchange to SQLite best-effort.
    """
    from lutz.agent.orchestrator import AgentOrchestrator
    from lutz.agent.tools import get_tool_registry
    from lutz.agent.model_router import ModelRouter
    from lutz.core.llm_client import LLMClient
    from lutz.server import db as _db

    env = load_env(root)
    llm = LLMClient.from_env(env)
    registry = get_tool_registry()
    router = ModelRouter()
    orch = AgentOrchestrator(llm, registry, router, _conversation_manager)
    result = orch.process_message(
        session_id, user_message, vector_store=None, job_manager=_job_manager
    )

    # Persist exchange to SQLite (best-effort)
    try:
        session = _db.get_session(root, session_id)
        if session is None:
            _db.create_session(root, user_message[:60])
        _db.add_message(root, session_id, "user", user_message)
        _db.add_message(root, session_id, "assistant", result.get("response", ""))
        _db.update_session_updated_at(root, session_id)
    except Exception:
        pass

    return result


@api.post("/agent/chat")
async def agent_chat(request: Request) -> dict:
    """Process a message through the AgentOrchestrator and return the response.

    Body fields:
      message (str, required): the user's natural language message
      session_id (str, optional): existing session UUID; a new one is generated if absent

    Returns:
      session_id, response, state, plan, awaiting_confirmation, step_result
    """
    body = await request.json()
    user_message: str = (body.get("message") or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message required")
    if len(user_message) > _MAX_AGENT_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"message exceeds {_MAX_AGENT_MESSAGE_CHARS} characters",
        )

    session_id: str = body.get("session_id") or str(uuid.uuid4())
    root = _get_root()

    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_agent(session_id, user_message, root)
    )

    return {
        "session_id": session_id,
        **result,
    }


@api.post("/agent/chat/stream")
async def agent_chat_stream(request: Request) -> StreamingResponse:
    """Stream the AgentOrchestrator response as Server-Sent Events.

    SSE event sequence:
      1. {type: 'session', session_id}  — always first
      2. {type: 'token', content}       — one per word of the response text
      3. {type: 'done', state, plan, step_result, awaiting_confirmation}

    Body fields:
      message (str, required)
      session_id (str, optional)
    """
    body = await request.json()
    session_id: str = body.get("session_id") or str(uuid.uuid4())
    user_message: str = (body.get("message") or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")
    if len(user_message) > _MAX_AGENT_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"message exceeds {_MAX_AGENT_MESSAGE_CHARS} chars",
        )

    root = _get_root()

    async def generate():
        # 1. Session event
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        # 2. Run the synchronous orchestrator in a thread executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _run_agent(session_id, user_message, root)
        )

        # 3. Stream response text token-by-token (word chunks, capped to avoid DoS)
        _MAX_STREAM_WORDS = 5000
        response_text = result.get("response", "")
        words = response_text.split(" ")[:_MAX_STREAM_WORDS]
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            await asyncio.sleep(0.01)

        # 4. Done event with full metadata
        yield f"data: {json.dumps({'type': 'done', 'state': result.get('state'), 'plan': result.get('plan'), 'step_result': result.get('step_result'), 'awaiting_confirmation': result.get('awaiting_confirmation', False)})}\n\n"

    return StreamingResponse(
        generate(),
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
