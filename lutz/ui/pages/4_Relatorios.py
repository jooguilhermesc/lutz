"""Lutz — Relatórios de análise."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root
from _style import apply, page_title, relevance_badge, TEAL, TEAL_LIGHT, MUTED, CHARCOAL

st.set_page_config(
    page_title="Lutz — Relatórios",
    page_icon=str(Path(__file__).resolve().parent.parent / "lutz.png"),
    layout="wide",
)

project_root = find_project_root()
apply(project_root)
page_title("Relatórios", "Visualize e baixe todas as análises executadas")

if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

reports_dir = project_root / "analysis" / "execution_reports"
if not reports_dir.exists():
    st.info("Nenhum relatório encontrado. Execute uma análise na página **Análise**.")
    st.stop()

json_files = sorted(
    reports_dir.glob("*.json"),
    key=lambda f: f.stat().st_mtime,
    reverse=True,
)
if not json_files:
    st.info("Nenhum relatório encontrado. Execute uma análise na página **Análise**.")
    st.stop()

# ── Carregar metadados de todos os relatórios ─────────────────────────────────
rows: list[dict] = []
report_map: dict[str, tuple[Path, dict]] = {}

for f in json_files:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        meta = data.get("metadata", {})
        llm = meta.get("llm") or {}
        vs = meta.get("vector_store") or {}
        rows.append({
            "Nome": f.stem,
            "Modo": meta.get("mode", "—"),
            "Data": (meta.get("started_at") or "")[:10] or "—",
            "Artigos": vs.get("unique_documents", "—"),
            "Modelo LLM": llm.get("model", "—"),
            "Tokens totais": f"{llm.get('total_tokens', 0):,}",
            "Duração (s)": meta.get("elapsed_seconds", "—"),
        })
        report_map[f.stem] = (f, data)
    except Exception:
        continue

if not rows:
    st.warning("Nenhum relatório pôde ser carregado.")
    st.stop()

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.divider()

# ── Visualizador de relatório individual ──────────────────────────────────────
st.markdown(
    f'<h3 style="margin-bottom:0.6rem;">Visualizar relatório</h3>',
    unsafe_allow_html=True,
)
selected = st.selectbox("Selecionar relatório", [r["Nome"] for r in rows])

if selected and selected in report_map:
    report_file, data = report_map[selected]
    meta = data.get("metadata", {})
    mode = meta.get("mode", "—")
    llm = meta.get("llm") or {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modo", mode)
    c2.metric("Modelo LLM", llm.get("model", "—"))
    c3.metric("Tokens totais", f"{llm.get('total_tokens', 0):,}")
    c4.metric("Duração", f"{meta.get('elapsed_seconds', 0):.1f}s")

    if mode == "per_article":
        articles = data.get("articles", [])

        # Contagem de relevância com badges
        rel_counts: dict[str, int] = {}
        for a in articles:
            lbl = a.get("relevance", "UNKNOWN")
            rel_counts[lbl] = rel_counts.get(lbl, 0) + 1

        if rel_counts:
            cols = st.columns(len(rel_counts))
            for col, (label, count) in zip(cols, sorted(rel_counts.items())):
                col.metric(label, count)

        st.markdown(
            f'<h3 style="margin-bottom:0.6rem; margin-top:1.2rem;">Resultados por artigo</h3>',
            unsafe_allow_html=True,
        )

        # Tabela com badges de relevância renderizados
        art_rows_html = []
        for a in articles:
            relevance = a.get("relevance", "—")
            badge = relevance_badge(relevance) if relevance in ("INCLUDE", "EXCLUDE", "UNCERTAIN", "UNKNOWN") else relevance
            art_rows_html.append((a["filename"], badge, a.get("chunks_used", 0),
                                   f"{a.get('llm_total_tokens', 0):,}", a.get("error") or ""))

        art_df = pd.DataFrame([{
            "Artigo": a["filename"],
            "Relevância": a.get("relevance", "—"),
            "Chunks": a.get("chunks_used", 0),
            "Tokens": f"{a.get('llm_total_tokens', 0):,}",
            "Erro": a.get("error") or "",
        } for a in articles])
        st.dataframe(art_df, use_container_width=True, hide_index=True)

        with st.expander("Ver análise individual por artigo"):
            article_names = [a["filename"] for a in articles]
            if article_names:
                chosen = st.selectbox("Artigo", article_names, key="art_sel")
                art = next((a for a in articles if a["filename"] == chosen), None)
                if art:
                    relevance = art.get("relevance", "—")
                    st.markdown(
                        f'<div style="margin-bottom:0.6rem;">'
                        f'<span style="color:{MUTED}; font-size:0.8rem; font-weight:600; '
                        f'text-transform:uppercase; letter-spacing:0.06em;">Relevância</span><br>'
                        f'{relevance_badge(relevance)}</div>',
                        unsafe_allow_html=True,
                    )
                    if art.get("error"):
                        st.error(f"Erro: {art['error']}")
                    st.markdown(art.get("analysis") or "_Sem análise disponível._")
    else:
        st.markdown(
            f'<h3 style="margin-bottom:0.6rem; margin-top:1.2rem;">Análise</h3>',
            unsafe_allow_html=True,
        )
        articles_covered = data.get("articles_covered", [])
        if articles_covered:
            st.markdown(
                f'<p style="color:{MUTED}; font-size:0.83rem;">Artigos cobertos: '
                f'{", ".join(articles_covered)}</p>',
                unsafe_allow_html=True,
            )
        st.markdown(data.get("analysis") or "_Sem conteúdo disponível._")

    st.divider()

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "Baixar relatório JSON",
            data=json.dumps(data, ensure_ascii=False, indent=2),
            file_name=f"{selected}.json",
            mime="application/json",
        )
    with col_dl2:
        html_file = report_file.with_suffix(".html")
        if html_file.exists():
            st.download_button(
                "Baixar relatório HTML",
                data=html_file.read_bytes(),
                file_name=f"{selected}.html",
                mime="text/html",
            )
