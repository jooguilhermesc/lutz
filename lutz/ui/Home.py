"""Lutz — Dashboard principal."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _utils import find_project_root, get_vector_store

st.set_page_config(
    page_title="Lutz — Triagem de Artigos",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Lutz — Triagem de Artigos Acadêmicos")
st.caption("Interface de pesquisa para triagem sistemática de artigos com IA")

project_root = find_project_root()

if project_root is None:
    st.error(
        "Nenhum projeto Lutz encontrado no diretório atual ou em seus pais. "
        "Certifique-se de executar o app a partir de um diretório de projeto Lutz "
        "(que contenha `articles/` ou `.lutz/`)."
    )
    st.code("lutz init meu-projeto  # cria um novo projeto", language="bash")
    st.stop()

st.success(f"Projeto em: `{project_root}`")
st.divider()

# --- Métricas rápidas ---
col1, col2, col3 = st.columns(3)

articles_dir = project_root / "articles"
pdf_count = 0
if articles_dir.exists():
    pdf_count = sum(
        1 for p in articles_dir.iterdir()
        if p.suffix.lower() == ".pdf" and p.name != ".gitkeep"
    )

with col1:
    st.metric("PDFs em articles/", pdf_count)

try:
    store = get_vector_store(project_root)
    vs_info = store.info()
    with col2:
        st.metric("Chunks vetorizados", f"{vs_info['total_records']:,}")
except Exception:
    with col2:
        st.metric("Chunks vetorizados", "—")

reports_dir = project_root / "analysis" / "execution_reports"
report_count = len(list(reports_dir.glob("*.json"))) if reports_dir.exists() else 0
with col3:
    st.metric("Análises executadas", report_count)

st.divider()

# --- Guia de navegação ---
st.subheader("Como usar")
col1, col2, col3 = st.columns(3)

with col1:
    st.info(
        "**Vetorização**\n\n"
        "Faça upload de PDFs e indexe-os na base vetorial. "
        "Suporta verificação de segurança contra injeção de prompt em PDFs maliciosos."
    )
    st.info(
        "**Vector Store**\n\n"
        "Inspecione os metadados da base vetorial: artigos indexados, "
        "número de chunks, modelo de embedding e distribuição por seções."
    )

with col2:
    st.info(
        "**Análise**\n\n"
        "Escreva ou carregue um prompt de triagem e execute a análise. "
        "Suporta modo RAG (síntese global) e modo por artigo (INCLUDE/EXCLUDE). "
        "Também aceita múltiplos experimentos via YAML."
    )
    st.info(
        "**Relatórios**\n\n"
        "Visualize e baixe todas as análises executadas. "
        "Veja resultados por artigo, tokens consumidos e duração."
    )

with col3:
    st.info(
        "**Citações**\n\n"
        "Extraia as passagens mais relevantes dos artigos classificados como incluídos, "
        "com confiança e raciocínio para cada citação."
    )
    st.info(
        "**Configurações**\n\n"
        "Configure os provedores de LLM e embeddings e as chaves de API. "
        "As credenciais são armazenadas somente no arquivo `.env` do projeto."
    )
