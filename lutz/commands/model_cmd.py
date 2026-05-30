"""lutz model — train, list and remove fit-once sklearn models.

Sub-commands
------------
  lutz model fit kmeans --k N [--random-state 42]
  lutz model fit pca    --n N [--random-state 42]
  lutz model list
  lutz model rm <model_id>
  lutz model explore kmeans --k-range A..B [--random-state 42] [--sample N]
                            [--format table|json]
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click
import numpy as np
from rich.console import Console
from rich.table import Table

from lutz.analytics.model_store import FittedModelStore
from lutz.core.vector_store import VectorStore
from lutz.utils.kmeans_explore import explore_kmeans, parse_k_range
from lutz.utils.project import require_project_root

console = Console()


def _models_dir(project_root: Path) -> Path:
    d = project_root / ".lutz" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vector_store(project_root: Path) -> VectorStore:
    return VectorStore(project_root / ".lutz" / "vector_store")


# ---------------------------------------------------------------------------
# lutz model (group)
# ---------------------------------------------------------------------------

@click.group(name="model")
def model() -> None:
    """Manage fit-once models for stable predict_cluster / predict_coords UDFs."""


# ---------------------------------------------------------------------------
# lutz model fit (sub-group)
# ---------------------------------------------------------------------------

@model.group(name="fit")
def fit() -> None:
    """Fit a model on the current corpus and persist it."""


# ---------------------------------------------------------------------------
# lutz model fit kmeans
# ---------------------------------------------------------------------------

@fit.command(name="kmeans")
@click.option("--k", "n_clusters", required=True, type=int, help="Number of clusters.")
@click.option(
    "--random-state",
    default=42,
    show_default=True,
    type=int,
    help="Random state for reproducibility.",
)
def fit_kmeans(n_clusters: int, random_state: int) -> None:
    """Train KMeans on all chunk embeddings and persist the fitted model."""
    from sklearn.cluster import KMeans

    from lutz.analytics.model_store import FittedModelStore

    project_root = require_project_root()
    store = _vector_store(project_root)
    matrix, meta = store.get_all_embeddings()

    if matrix.shape[0] == 0:
        console.print(
            "[yellow]Vector store is empty.[/] Run [bold]lutz vectorize[/] first."
        )
        return

    n_rows = meta["n_rows"]
    embedding_model = meta["embedding_model"]
    corpus_hash = meta["corpus_hash"]

    model_store = FittedModelStore(_models_dir(project_root))

    # Generate model_id — append timestamp if base id already taken
    base_id = f"kmeans_{n_clusters}"
    model_id = base_id
    if model_store.exists(base_id):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        model_id = f"{base_id}_{ts}"
        console.print(
            f"[dim]Model '{base_id}' already exists — saving as '{model_id}'.[/]"
        )

    with console.status(f"[cyan]Training KMeans (k={n_clusters}) on {n_rows:,} chunks…[/]"):
        km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
        km.fit(matrix)

    metadata = {
        "model_id": model_id,
        "algorithm": "kmeans",
        "params": {"n_clusters": n_clusters},
        "embedding_model": embedding_model,
        "n_rows": n_rows,
        "corpus_hash": corpus_hash,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "random_state": random_state,
    }
    model_store.save(model_id, km, metadata)

    console.print(
        f"[green]Model saved:[/] {model_id} "
        f"(trained on {n_rows:,} chunks, embedding_model={embedding_model})"
    )


# ---------------------------------------------------------------------------
# lutz model fit pca
# ---------------------------------------------------------------------------

@fit.command(name="pca")
@click.option("--n", "n_components", required=True, type=int, help="Number of PCA components.")
@click.option(
    "--random-state",
    default=42,
    show_default=True,
    type=int,
    help="Random state for reproducibility.",
)
def fit_pca(n_components: int, random_state: int) -> None:
    """Train PCA on all chunk embeddings and persist the fitted model."""
    from sklearn.decomposition import PCA

    from lutz.analytics.model_store import FittedModelStore

    project_root = require_project_root()
    store = _vector_store(project_root)
    matrix, meta = store.get_all_embeddings()

    if matrix.shape[0] == 0:
        console.print(
            "[yellow]Vector store is empty.[/] Run [bold]lutz vectorize[/] first."
        )
        return

    n_rows = meta["n_rows"]
    embedding_model = meta["embedding_model"]
    corpus_hash = meta["corpus_hash"]

    model_store = FittedModelStore(_models_dir(project_root))

    base_id = f"pca_{n_components}"
    model_id = base_id
    if model_store.exists(base_id):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        model_id = f"{base_id}_{ts}"
        console.print(
            f"[dim]Model '{base_id}' already exists — saving as '{model_id}'.[/]"
        )

    # Clamp n_components to valid range
    max_components = min(n_components, matrix.shape[0] - 1, matrix.shape[1])
    if max_components < n_components:
        console.print(
            f"[yellow]Reducing n_components from {n_components} to {max_components} "
            f"(corpus has {matrix.shape[0]} rows, {matrix.shape[1]} dimensions).[/]"
        )

    with console.status(f"[cyan]Training PCA (n={max_components}) on {n_rows:,} chunks…[/]"):
        pca = PCA(n_components=max_components, random_state=random_state)
        pca.fit(matrix)

    metadata = {
        "model_id": model_id,
        "algorithm": "pca",
        "params": {"n_components": max_components},
        "embedding_model": embedding_model,
        "n_rows": n_rows,
        "corpus_hash": corpus_hash,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "random_state": random_state,
    }
    model_store.save(model_id, pca, metadata)

    console.print(
        f"[green]Model saved:[/] {model_id} "
        f"(trained on {n_rows:,} chunks, embedding_model={embedding_model})"
    )


# ---------------------------------------------------------------------------
# lutz model fit centroid
# ---------------------------------------------------------------------------

@fit.command(name="centroid")
@click.option(
    "--name",
    "model_name",
    default="corpus_centroid",
    show_default=True,
    help="Model ID under which the centroid is stored.",
)
def fit_centroid(model_name: str) -> None:
    """Compute the corpus centroid and persist it as a fit-once model.

    The centroid is the mean of all chunk embeddings.  Use it as the stable
    reference for predict_centroid_distance() — unlike corpus_centroid_distance(),
    this approach is not affected by DuckDB batch boundaries.
    """
    from lutz.analytics.model_store import FittedModelStore

    project_root = require_project_root()
    store = _vector_store(project_root)
    matrix, meta = store.get_all_embeddings()

    if matrix.shape[0] == 0:
        console.print(
            "[yellow]Vector store is empty.[/] Run [bold]lutz vectorize[/] first."
        )
        return

    n_rows = meta["n_rows"]
    embedding_model = meta["embedding_model"]
    corpus_hash = meta["corpus_hash"]

    centroid = matrix.mean(axis=0)  # (D,) float32 -> persisted as-is

    model_store = FittedModelStore(_models_dir(project_root))

    metadata = {
        "model_id": model_name,
        "algorithm": "centroid",
        "embedding_model": embedding_model,
        "n_rows": n_rows,
        "corpus_hash": corpus_hash,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    model_store.save(model_name, centroid, metadata)

    console.print(
        f"[green]Centroid saved:[/] {model_name} "
        f"(computed over {n_rows:,} chunks, embedding_model={embedding_model})"
    )


# ---------------------------------------------------------------------------
# lutz model list
# ---------------------------------------------------------------------------

@model.command(name="list")
def model_list() -> None:
    """List all persisted models with corpus validity status."""
    from lutz.analytics.model_store import FittedModelStore

    project_root = require_project_root()
    model_store = FittedModelStore(_models_dir(project_root))
    models = model_store.list_models()

    if not models:
        console.print(
            "[yellow]No models found.[/] Run [bold]lutz model fit[/] to train one."
        )
        return

    # Compute current corpus hash once
    try:
        vs = _vector_store(project_root)
        _, corpus_meta = vs.get_all_embeddings()
        current_hash = corpus_meta.get("corpus_hash", "")
    except Exception:
        current_hash = ""

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("model_id")
    table.add_column("algorithm")
    table.add_column("params")
    table.add_column("n_rows", justify="right")
    table.add_column("trained_at")
    table.add_column("corpus_valid", justify="center")

    for m in models:
        mid = m.get("model_id", "?")
        alg = m.get("algorithm", "?")
        params = ", ".join(f"{k}={v}" for k, v in m.get("params", {}).items())
        n_rows = str(m.get("n_rows", "?"))
        trained = m.get("trained_at", "?")

        saved_hash = m.get("corpus_hash", "")
        if not current_hash or saved_hash == current_hash:
            valid_str = "[green]✓[/]"
        else:
            valid_str = "[red]✗[/]"

        table.add_row(mid, alg, params, n_rows, trained, valid_str)

    console.print(table)


# ---------------------------------------------------------------------------
# lutz model explore (sub-group)
# ---------------------------------------------------------------------------

@model.group(name="explore")
def explore() -> None:
    """Explore hyper-parameters before committing to a fit."""


# ---------------------------------------------------------------------------
# lutz model explore kmeans
# ---------------------------------------------------------------------------

@explore.command(name="kmeans")
@click.option(
    "--k-range",
    "k_range_str",
    required=True,
    help="Range of k values to evaluate, format 'A..B' inclusive (e.g. '2..15').",
)
@click.option(
    "--random-state",
    default=42,
    show_default=True,
    type=int,
    help="Random state for KMeans and sampling reproducibility.",
)
@click.option(
    "--sample",
    "sample_n",
    default=None,
    type=int,
    help="Limit evaluation to N randomly sampled rows (for large corpora).",
)
@click.option(
    "--format",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"], case_sensitive=False),
    show_default=True,
    help="Output format.",
)
def explore_kmeans_cmd(
    k_range_str: str,
    random_state: int,
    sample_n: int | None,
    output_format: str,
) -> None:
    """Sweep k values for KMeans and report silhouette + inertia.

    This command does NOT persist any model — it is a diagnostic tool.
    The suggested k is a guide based on the highest silhouette score;
    the final choice of k is always yours.
    """
    import json as _json

    try:
        k_range = parse_k_range(k_range_str)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--k-range") from exc

    project_root = require_project_root()
    store = _vector_store(project_root)
    matrix, meta = store.get_all_embeddings()

    if matrix.shape[0] == 0:
        console.print(
            "[yellow]Vector store is empty.[/] Run [bold]lutz vectorize[/] first."
        )
        return

    total_rows = matrix.shape[0]

    if sample_n is not None and sample_n < total_rows:
        rng = np.random.default_rng(random_state)
        idx = rng.choice(total_rows, size=sample_n, replace=False)
        idx.sort()
        matrix = matrix[idx]
        console.print(
            f"[dim]Metrics computed on a sample of {sample_n}/{total_rows} chunks "
            f"(seed={random_state}).[/]"
        )

    with console.status(
        f"[cyan]Evaluating k={k_range.start}..{k_range.stop - 1} "
        f"on {matrix.shape[0]:,} chunks…[/]"
    ):
        results = explore_kmeans(matrix, k_range=k_range, random_state=random_state)

    best = max(results, key=lambda r: r["silhouette"])

    if output_format == "json":
        console.print_json(_json.dumps(results))
        return

    # Rich table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("k", justify="right")
    table.add_column("Silhouette", justify="right")
    table.add_column("Inertia", justify="right")
    table.add_column("Suggestion", justify="left")

    for r in results:
        sug = "[green]← suggested[/]" if r["k"] == best["k"] else ""
        table.add_row(
            str(r["k"]),
            f"{r['silhouette']:.3f}",
            f"{r['inertia']:.1f}",
            sug,
        )

    console.print(table)
    console.print(
        f"\n[bold green]Suggested k={best['k']}[/] "
        f"(highest silhouette: {best['silhouette']:.3f})."
    )
    console.print(
        f"To confirm: [bold]lutz model fit kmeans --k {best['k']}[/]"
    )
    console.print(
        "[dim]Note: the choice of k is yours — silhouette is a guide, not a verdict.[/]"
    )


# ---------------------------------------------------------------------------
# lutz model rm
# ---------------------------------------------------------------------------

@model.command(name="rm")
@click.argument("model_id")
def model_rm(model_id: str) -> None:
    """Remove a persisted model by MODEL_ID."""
    project_root = require_project_root()
    model_store = FittedModelStore(_models_dir(project_root))

    if not model_store.exists(model_id):
        console.print(f"[yellow]Model '{model_id}' not found.[/]")
        return

    model_store.remove(model_id)
    console.print(f"[green]Removed:[/] {model_id}")


# ---------------------------------------------------------------------------
# lutz model cluster-report
# ---------------------------------------------------------------------------

@model.command(name="cluster-report")
@click.option(
    "--model",
    "model_id",
    required=True,
    help="Model ID to use for cluster assignment (e.g. 'kmeans_8').",
)
@click.option(
    "--top-chunks",
    default=5,
    show_default=True,
    type=int,
    help="Number of representative chunks to show per cluster.",
)
@click.option(
    "--format",
    "output_format",
    default="table",
    type=click.Choice(["table", "json", "html"], case_sensitive=False),
    show_default=True,
    help="Output format.",
)
def cluster_report(model_id: str, top_chunks: int, output_format: str) -> None:
    """Synthesise a cluster report: articles per cluster + representative chunks.

    Uses a previously fitted KMeans model (via ``lutz model fit kmeans``) to
    assign cluster labels to all vectorised chunks without re-training.
    """
    import json as _json

    from lutz.utils.cluster_report import build_cluster_report

    project_root = require_project_root()
    model_store = FittedModelStore(_models_dir(project_root))

    # Load the fitted model
    try:
        km, meta = model_store.load(model_id)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"Model '{model_id}' not found. Run: lutz model fit kmeans --k <N>"
        ) from exc

    model_embedding_model = meta.get("embedding_model", "")

    # Load all embeddings + metadata from the vector store (aligned)
    vs = VectorStore(project_root / ".lutz" / "vector_store")
    mat, rows = vs.get_all_embeddings_with_metadata()

    if mat.shape[0] == 0:
        console.print(
            "[yellow]Vector store is empty.[/] Run [bold]lutz vectorize[/] first."
        )
        return

    # Verify embedding model compatibility
    corpus_embedding_model: str = ""
    try:
        _, corpus_meta = vs.get_all_embeddings()
        corpus_embedding_model = corpus_meta.get("embedding_model", "")
    except Exception:
        pass

    if (
        model_embedding_model
        and corpus_embedding_model
        and model_embedding_model != corpus_embedding_model
    ):
        console.print(
            f"[yellow]Warning:[/] embedding model mismatch — model was trained on "
            f"'{model_embedding_model}' but corpus uses '{corpus_embedding_model}'. "
            f"Distances may differ from training. Re-run [bold]lutz model fit kmeans[/] "
            f"to retrain on the current corpus."
        )

    # Predict cluster labels without re-training
    labels = km.predict(mat)
    cluster_centers = km.cluster_centers_

    report = build_cluster_report(mat, rows, cluster_centers, labels, top_chunks=top_chunks)

    if output_format == "json":
        output = {
            "model_id": model_id,
            "clusters": report,
        }
        console.print_json(_json.dumps(output, ensure_ascii=False))
        return

    if output_format == "html":
        _render_html(model_id, report, console)
        return

    # Default: table / text format
    _render_table(model_id, report, console)


def _render_table(model_id: str, report: list[dict], con: Console) -> None:
    """Render the cluster report as a Rich text output."""
    con.print(f"\n[bold cyan]Cluster Report[/] — model [bold]{model_id}[/]\n")
    for entry in report:
        k = entry["cluster_id"]
        n_art = entry["n_articles"]
        con.print(f"[bold green]Cluster {k}[/] — {n_art} article{'s' if n_art != 1 else ''}")
        con.print("  [dim]Representatives:[/]")
        for chunk in entry["representative_chunks"]:
            dist = chunk["distance_to_centroid"]
            fn = chunk["filename"]
            sec = chunk["section"] or "—"
            text_preview = chunk["text"][:80].replace("\n", " ")
            con.print(f"    [{dist:.3f}] [italic]{fn}[/] ({sec}): \"{text_preview}\"")
        filenames = ", ".join(entry["article_filenames"]) if entry["article_filenames"] else "(none)"
        con.print(f"  [dim]Articles:[/] {filenames}\n")


def _render_html(model_id: str, report: list[dict], con: Console) -> None:
    """Render the cluster report as a basic HTML accordion."""
    import html as _html

    lines = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>Cluster Report — {_html.escape(model_id)}</title>",
        "<style>",
        "  body { font-family: sans-serif; max-width: 900px; margin: 2em auto; }",
        "  details { border: 1px solid #ccc; border-radius: 4px; margin: 0.5em 0; padding: 0.5em; }",
        "  summary { font-weight: bold; cursor: pointer; }",
        "  .rep { font-family: monospace; font-size: 0.85em; margin: 0.25em 0; }",
        "  .articles { color: #555; font-size: 0.9em; }",
        "</style></head><body>",
        f"<h1>Cluster Report — <code>{_html.escape(model_id)}</code></h1>",
    ]

    for entry in report:
        k = entry["cluster_id"]
        n_art = entry["n_articles"]
        lines.append(f"<details><summary>Cluster {k} — {n_art} article(s)</summary>")
        lines.append("<h4>Representative Chunks</h4><ul>")
        for chunk in entry["representative_chunks"]:
            dist = chunk["distance_to_centroid"]
            fn = _html.escape(chunk["filename"])
            sec = _html.escape(chunk["section"] or "—")
            text = _html.escape(chunk["text"][:120])
            lines.append(
                f"  <li class='rep'>[{dist:.3f}] <b>{fn}</b> ({sec}): &ldquo;{text}&rdquo;</li>"
            )
        lines.append("</ul>")
        art_list = ", ".join(_html.escape(f) for f in entry["article_filenames"]) or "(none)"
        lines.append(f"<p class='articles'>Articles: {art_list}</p>")
        lines.append("</details>")

    lines.append("</body></html>")
    con.print("\n".join(lines))
