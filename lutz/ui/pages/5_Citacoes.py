"""Lutz — Extração de citações."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root, run_command

st.set_page_config(page_title="Lutz — Citações", layout="wide")
st.title("Extração de Citações")
st.caption(
    "Extraia as passagens mais relevantes dos artigos classificados como incluídos, "
    "com nível de confiança e raciocínio para cada citação."
)

project_root = find_project_root()
if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

reports_dir = project_root / "analysis" / "execution_reports"

# Buscar apenas relatórios gerados no modo por artigo
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

# --- Seleção do relatório ---
selected_name = st.selectbox(
    "Relatório de análise",
    [f.name for f in per_article_files],
    help="Apenas relatórios no modo 'por artigo' são compatíveis com extração de citações.",
)
selected_file = next(f for f in per_article_files if f.name == selected_name)

# --- Resumo do relatório selecionado ---
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

# --- Opções ---
col1, col2 = st.columns(2)
with col1:
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

if st.button("Extrair Citações", type="primary", disabled=(include_count == 0)):
    cmd = [
        "lutz", "citations",
        "--analysis", str(selected_file),
        "--workers", str(workers),
    ]
    if only_relevant:
        cmd.append("--only-relevant")
    if output_name.strip():
        safe = "".join(c for c in output_name.strip() if c.isalnum() or c in "-_")
        if safe:
            cmd.extend(["--output-name", safe])

    with st.spinner("Extraindo citações... Isso pode levar alguns minutos."):
        rc, output = run_command(cmd, project_root)

    if rc == 0:
        st.success(
            "Citações extraídas com sucesso! "
            "Acesse a página **Relatórios** para baixar o resultado."
        )
    else:
        st.error("Erro durante a extração de citações.")

    if output:
        with st.expander("Saída do processo", expanded=(rc != 0)):
            st.code(output, language=None)

# --- Exibir relatório de citações existente (se houver) ---
citations_files = sorted(
    (f for f in reports_dir.glob("*_citations_*.json") if f.exists()),
    key=lambda f: f.stat().st_mtime,
    reverse=True,
)
if citations_files:
    st.divider()
    st.subheader("Relatórios de citações gerados")

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
            st.subheader("Artigos incluídos e citações")
            for art in relevant_articles:
                with st.expander(f"{art['filename']} — {art.get('label', '—')} (conf. {art.get('confidence', '—')})"):
                    if art.get("reasoning"):
                        st.markdown(f"**Justificativa:** {art['reasoning']}")
                    citations = art.get("citations", [])
                    if citations:
                        cit_rows = [{"Página": c.get("page", "—"), "Citação": c.get("text", "")}
                                    for c in citations]
                        st.dataframe(pd.DataFrame(cit_rows), use_container_width=True, hide_index=True)
                    else:
                        st.caption("Nenhuma citação extraída.")

        st.download_button(
            "Baixar relatório de citações JSON",
            data=json.dumps(cit_data, ensure_ascii=False, indent=2),
            file_name=chosen_cit,
            mime="application/json",
        )
    except Exception as e:
        st.warning(f"Não foi possível carregar o relatório de citações: {e}")
