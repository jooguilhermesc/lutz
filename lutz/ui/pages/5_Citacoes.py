"""Lutz — Extração de citações e roteiro de leitura."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root, run_command
from _style import apply, page_title, relevance_badge, section_badge, TEAL, TEAL_LIGHT, MUTED, CHARCOAL

st.set_page_config(
    page_title="Lutz — Citações",
    page_icon=str(Path(__file__).resolve().parent.parent / "lutz.png"),
    layout="wide",
)

project_root = find_project_root()
apply(project_root)
page_title(
    "Citações",
    "Extraia passagens relevantes dos artigos ou gere um roteiro de leitura baseado em embeddings",
)

if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

reports_dir = project_root / "analysis" / "execution_reports"

# ── Buscar apenas relatórios gerados no modo por artigo ───────────────────────
per_article_files: list[Path] = []
if reports_dir.exists():
    for f in sorted(
        reports_dir.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    ):
        try:
            meta = json.loads(f.read_text(encoding="utf-8")).get("metadata", {})
            if meta.get("mode") == "per_article":
                per_article_files.append(f)
        except Exception:
            continue

if not per_article_files:
    st.warning(
        "Nenhum relatório de análise **por artigo** encontrado. "
        "Execute uma análise no modo **Por artigo** na página **Análise**."
    )
    st.stop()

# ── Seleção do relatório ──────────────────────────────────────────────────────
selected_name = st.selectbox(
    "Relatório de análise",
    [f.name for f in per_article_files],
    help="Apenas relatórios no modo 'por artigo' são compatíveis com extração de citações.",
)
selected_file = next(f for f in per_article_files if f.name == selected_name)

# ── Resumo do relatório selecionado ───────────────────────────────────────────
try:
    data = json.loads(selected_file.read_text(encoding="utf-8"))
    articles = data.get("articles", [])

    rel_counts: dict[str, int] = {}
    for a in articles:
        lbl = a.get("relevance", "UNKNOWN")
        rel_counts[lbl] = rel_counts.get(lbl, 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de artigos", len(articles))
    c2.metric("INCLUDE", rel_counts.get("INCLUDE", 0))
    c3.metric("EXCLUDE", rel_counts.get("EXCLUDE", 0))
    c4.metric(
        "UNCERTAIN / UNKNOWN",
        rel_counts.get("UNCERTAIN", 0) + rel_counts.get("UNKNOWN", 0),
    )

    include_count = rel_counts.get("INCLUDE", 0)
    if include_count == 0:
        st.warning(
            "Nenhum artigo classificado como **INCLUDE** neste relatório. "
            "A extração de citações requer ao menos um artigo incluído."
        )
except Exception as e:
    st.warning(f"Não foi possível carregar o resumo do relatório: {e}")
    include_count = 0

st.divider()

# ── Seleção do tipo de relatório ──────────────────────────────────────────────
report_type = st.radio(
    "Tipo de relatório",
    ["Apenas citações", "Roteiro de leitura"],
    help=(
        "**Apenas citações**: extrai as passagens mais relevantes de cada artigo incluído.\n\n"
        "**Roteiro de leitura**: usa a distância dos embeddings para ordenar os artigos do mais "
        "fundamental ao mais especializado, e gera um guia de leitura estruturado em etapas."
    ),
    horizontal=True,
)

is_roadmap = report_type == "Roteiro de leitura"

if is_roadmap:
    st.info(
        "O roteiro de leitura ordena os artigos pela **distância cossenoidal** em relação ao centroide "
        "do corpus — artigos mais próximos ao centro são fundacionais, os mais distantes são especializados. "
        "Um LLM gera um guia estruturado em etapas de leitura.",
        icon="🗺️",
    )

# ── Opções ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    if not is_roadmap:
        workers = st.number_input(
            "Workers (chamadas LLM paralelas)",
            min_value=1,
            max_value=32,
            value=1,
            help="Aumente para APIs remotas. Mantenha em 1 para modelos locais.",
        )
    only_relevant = st.checkbox(
        "Incluir apenas artigos relevantes no relatório de saída",
        help="Por padrão, todos os artigos aparecem no relatório (incluídos, excluídos e incertos).",
    )
with col2:
    output_name = st.text_input(
        "Nome do arquivo de saída (opcional)",
        placeholder="Ex: revisao_citacoes_v1",
        help="Deixe em branco para gerar automaticamente com timestamp.",
    )

st.divider()

btn_label = "Gerar Roteiro de Leitura" if is_roadmap else "Extrair Citações"

if st.button(btn_label, type="primary", disabled=(include_count == 0)):
    cmd = [
        "lutz", "citations",
        "--analysis", str(selected_file),
    ]
    if not is_roadmap:
        cmd.extend(["--workers", str(workers)])
    if only_relevant:
        cmd.append("--only-relevant")
    if output_name.strip():
        safe = "".join(c for c in output_name.strip() if c.isalnum() or c in "-_")
        if safe:
            cmd.extend(["--output-name", safe])
    if is_roadmap:
        cmd.append("--reading-roadmap")

    spinner_msg = (
        "Gerando roteiro de leitura... Isso pode levar alguns minutos."
        if is_roadmap
        else "Extraindo citações... Isso pode levar alguns minutos."
    )
    with st.spinner(spinner_msg):
        rc, output = run_command(cmd, project_root)

    if rc == 0:
        success_msg = (
            "Roteiro de leitura gerado com sucesso! "
            "Acesse a página **Relatórios** para baixar o resultado."
            if is_roadmap
            else "Citações extraídas com sucesso! "
            "Acesse a página **Relatórios** para baixar o resultado."
        )
        st.success(success_msg)
        st.rerun()
    else:
        st.error("Erro durante o processamento.")

    if output:
        with st.expander("Saída do processo", expanded=(rc != 0)):
            st.code(output, language=None)

# ── Exibir relatórios existentes ──────────────────────────────────────────────
citations_files = sorted(
    (f for f in reports_dir.glob("*_citations_*.json") if f.exists()),
    key=lambda f: f.stat().st_mtime,
    reverse=True,
)
roadmap_files = sorted(
    (f for f in reports_dir.glob("*_roadmap_*.json") if f.exists()),
    key=lambda f: f.stat().st_mtime,
    reverse=True,
)

# ── Relatórios de citações ─────────────────────────────────────────────────────
if citations_files:
    st.divider()
    st.markdown(
        '<h3 style="margin-bottom:0.6rem;">Relatórios de citações gerados</h3>',
        unsafe_allow_html=True,
    )

    chosen_cit = st.selectbox(
        "Visualizar relatório de citações",
        [f.name for f in citations_files],
    )
    cit_file = next(f for f in citations_files if f.name == chosen_cit)

    try:
        cit_data = json.loads(cit_file.read_text(encoding="utf-8"))
        cit_meta = cit_data.get("metadata", {})

        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Artigos relevantes", cit_meta.get("relevant", "—"))
        cc2.metric("Tokens LLM", f"{(cit_meta.get('llm') or {}).get('total_tokens', 0):,}")
        cc3.metric("Duração (s)", cit_meta.get("elapsed_seconds", "—"))

        relevant_articles = cit_data.get("relevant_articles", [])
        if relevant_articles:
            st.markdown(
                '<h3 style="margin-bottom:0.6rem; margin-top:1.2rem;">Artigos incluídos e citações</h3>',
                unsafe_allow_html=True,
            )
            for art in relevant_articles:
                label = art.get("label", "—")
                conf = art.get("confidence", "—")
                header = (
                    f'{art["filename"]} &nbsp;'
                    f'{relevance_badge(label)} &nbsp;'
                    f'<span style="color:{MUTED}; font-size:0.78rem;">conf. {conf}</span>'
                )
                with st.expander(art["filename"]):
                    st.markdown(header, unsafe_allow_html=True)
                    if art.get("reasoning"):
                        st.markdown(f"**Justificativa:** {art['reasoning']}")
                    citations = art.get("citations", [])
                    if citations:
                        cit_rows = [{"Página": c.get("page", "—"), "Citação": c.get("text", "")}
                                    for c in citations]
                        st.dataframe(pd.DataFrame(cit_rows), use_container_width=True, hide_index=True)
                    else:
                        st.caption("Nenhuma citação extraída.")

        col_dl1, col_dl2 = st.columns(2)
        col_dl1.download_button(
            "Baixar relatório de citações JSON",
            data=json.dumps(cit_data, ensure_ascii=False, indent=2),
            file_name=chosen_cit,
            mime="application/json",
        )
        html_cit_file = cit_file.with_suffix(".html")
        if html_cit_file.exists():
            col_dl2.download_button(
                "Baixar relatório de citações HTML",
                data=html_cit_file.read_bytes(),
                file_name=html_cit_file.name,
                mime="text/html",
            )
    except Exception as e:
        st.warning(f"Não foi possível carregar o relatório de citações: {e}")

# ── Relatórios de roteiro de leitura ──────────────────────────────────────────
if roadmap_files:
    st.divider()
    st.markdown(
        '<h3 style="margin-bottom:0.6rem;">Roteiros de leitura gerados</h3>',
        unsafe_allow_html=True,
    )

    chosen_rm = st.selectbox(
        "Visualizar roteiro de leitura",
        [f.name for f in roadmap_files],
    )
    rm_file = next(f for f in roadmap_files if f.name == chosen_rm)

    try:
        rm_data = json.loads(rm_file.read_text(encoding="utf-8"))
        rm_meta = rm_data.get("metadata", {})
        roadmap = rm_data.get("roadmap", {})

        rm1, rm2, rm3 = st.columns(3)
        rm1.metric("Artigos relevantes", rm_meta.get("relevant", "—"))
        rm2.metric("Tokens LLM", f"{(rm_meta.get('llm') or {}).get('total_tokens', 0):,}")
        rm3.metric("Duração (s)", rm_meta.get("elapsed_seconds", "—"))

        overview = roadmap.get("overview")
        if overview:
            st.markdown(
                f'<div style="background:{TEAL_LIGHT}; border:1px solid {TEAL}; '
                f'border-radius:8px; padding:0.8rem 1rem; margin:1rem 0; '
                f'font-size:0.9rem; color:{CHARCOAL};">'
                f'<strong>Visão geral:</strong> {overview}</div>',
                unsafe_allow_html=True,
            )

        stages = roadmap.get("stages") or []
        if stages:
            st.markdown(
                '<h4 style="margin:1.2rem 0 0.6rem;">Etapas de leitura</h4>',
                unsafe_allow_html=True,
            )
            stage_bg = ["#dbeafe", "#dcfce7", "#fef3c7", "#fce7f3", "#ede9fe"]
            for i, stage in enumerate(stages):
                num = stage.get("stage_number", i + 1)
                name = stage.get("stage_name", f"Etapa {num}")
                desc = stage.get("description", "")
                arts_in_stage = stage.get("articles") or []
                bg = stage_bg[i % len(stage_bg)]

                with st.expander(f"Etapa {num}: {name}", expanded=(i == 0)):
                    if desc:
                        st.markdown(f"*{desc}*")
                    if arts_in_stage:
                        for art in arts_in_stage:
                            fn = art.get("filename", "")
                            note = art.get("reading_note", "")
                            st.markdown(
                                f'<div style="background:{bg}; border-radius:6px; '
                                f'padding:0.5rem 0.8rem; margin:0.4rem 0;">'
                                f'<strong>{fn}</strong>'
                                + (f'<br><span style="font-size:0.85rem;color:#475569;">{note}</span>' if note else "")
                                + '</div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("Nenhum artigo nesta etapa.")

        distances = roadmap.get("article_distances") or []
        if distances:
            st.markdown(
                '<h4 style="margin:1.2rem 0 0.6rem;">Ranking por distância semântica</h4>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Artigos ordenados do mais fundacional (distância ≈ 0, no centro do corpus) "
                "ao mais especializado (distância maior)."
            )
            dist_df = pd.DataFrame([{
                "Rank": d.get("rank", "—"),
                "Artigo": d.get("filename", ""),
                "Distância do centroide": round(d["distance"], 4) if d.get("distance") is not None else None,
            } for d in distances])
            st.dataframe(dist_df, use_container_width=True, hide_index=True)

        col_dl1, col_dl2 = st.columns(2)
        col_dl1.download_button(
            "Baixar roteiro JSON",
            data=json.dumps(rm_data, ensure_ascii=False, indent=2),
            file_name=chosen_rm,
            mime="application/json",
        )
        html_rm_file = rm_file.with_suffix(".html")
        if html_rm_file.exists():
            col_dl2.download_button(
                "Baixar roteiro HTML",
                data=html_rm_file.read_bytes(),
                file_name=html_rm_file.name,
                mime="text/html",
            )
    except Exception as e:
        st.warning(f"Não foi possível carregar o roteiro de leitura: {e}")
