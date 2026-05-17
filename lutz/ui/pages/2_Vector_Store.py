"""Lutz — Metadados do Vector Store."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root, get_vector_store, run_command
from _style import apply, page_title, info_card, TEAL, TEAL_DARK, MUTED, CHARCOAL
from lutz.utils.html_report import generate_html_vector_store_report

st.set_page_config(
    page_title="Lutz — Vector Store",
    page_icon=str(Path(__file__).resolve().parent.parent / "lutz.png"),
    layout="wide",
)

project_root = find_project_root()
apply(project_root)
page_title("Vector Store", "Metadados e estatísticas da base vetorial")

if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

try:
    store = get_vector_store(project_root)
    info = store.summarize()
except Exception as e:
    st.error(f"Erro ao acessar o vector store: {e}")
    st.stop()

if info["total_records"] == 0:
    st.warning(
        "Vector store vazio. Execute a vetorização na página **Vetorização** primeiro."
    )
    st.stop()

# ── Métricas ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Chunks indexados", f"{info['total_records']:,}")
c2.metric("Artigos únicos", info["unique_documents"])
c3.metric("Modelo de embedding", info["embedding_model"] or "—")
c4.metric("Provedor", info["embedding_provider"] or "—")

st.markdown(
    f'<p style="color:{MUTED}; font-size:0.78rem; margin-top:0.3rem;">'
    f'Última atualização: {info["last_updated"] or "—"}</p>',
    unsafe_allow_html=True,
)
st.divider()

# ── Artigos indexados ─────────────────────────────────────────────────────────
st.markdown(
    f'<h3 style="margin-bottom:0.6rem;">Artigos indexados</h3>',
    unsafe_allow_html=True,
)
df_articles = pd.DataFrame([{
    "Artigo": a["filename"],
    "Chunks": a["chunk_count"],
    "Vetorizado em": a["vectorized_at"],
    "Modelo": a["embedding_model"],
    "Provedor": a["embedding_provider"],
} for a in info["articles"]])
st.dataframe(df_articles, use_container_width=True, hide_index=True)

# ── Distribuição por seções ───────────────────────────────────────────────────
st.markdown(
    f'<h3 style="margin-bottom:0.6rem; margin-top:1.4rem;">Distribuição por seções</h3>',
    unsafe_allow_html=True,
)
try:
    breakdown = store.section_breakdown()
    has_sections = any(k for counts in breakdown.values() for k in counts if k)

    if has_sections:
        rows = []
        for fname, counts in sorted(breakdown.items()):
            row = {"Artigo": fname}
            row.update({(k or "(sem seção)"): v for k, v in counts.items()})
            rows.append(row)
        df_sec = pd.DataFrame(rows).fillna(0)
        st.dataframe(df_sec, use_container_width=True, hide_index=True)
    else:
        st.info(
            "Artigos vetorizados sem análise de seções. "
            "Use a opção **Análise por seções** na vetorização para ativar."
        )
except Exception as e:
    st.warning(f"Não foi possível carregar o breakdown de seções: {e}")

# ── Exportar resumo ───────────────────────────────────────────────────────────
st.divider()
try:
    db_path = project_root / ".lutz" / "vector_store"
    db_size_mb = (
        sum(f.stat().st_size for f in db_path.rglob("*") if f.is_file()) / (1024 * 1024)
        if db_path.exists() else 0.0
    )
    export_payload = {
        "db_size_mb": round(db_size_mb, 3),
        **{k: v for k, v in info.items() if k != "articles"},
        "articles": info["articles"],
    }
    col_vs1, col_vs2 = st.columns(2)
    col_vs1.download_button(
        "Exportar resumo JSON",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2),
        file_name="vector_store_summary.json",
        mime="application/json",
    )
    col_vs2.download_button(
        "Exportar resumo HTML",
        data=generate_html_vector_store_report(export_payload),
        file_name="vector_store_summary.html",
        mime="text/html",
    )
except Exception:
    pass

# ── Zona de Perigo ────────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
with st.expander("Zona de Perigo"):
    st.warning(
        "Esta operação remove **todos** os dados do vector store de forma irreversível. "
        "Os arquivos PDF em `articles/` não são afetados, mas será necessário "
        "executar a vetorização novamente."
    )
    confirm = st.text_input("Digite **CONFIRMAR** para habilitar a exclusão")
    if st.button("Apagar Vector Store", type="primary", disabled=(confirm != "CONFIRMAR")):
        rc, output = run_command(["lutz", "unvectorize", "--yes"], project_root)
        if rc == 0:
            st.success("Vector store apagado com sucesso.")
            st.rerun()
        else:
            st.error("Erro ao apagar o vector store.")
            if output:
                st.code(output, language=None)
