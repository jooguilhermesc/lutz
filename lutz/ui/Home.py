"""Lutz — Dashboard principal."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _utils import find_project_root, get_vector_store
from _style import apply, TEAL, TEAL_LIGHT, TEAL_DARK, CHARCOAL, MUTED, BORDER

st.set_page_config(
    page_title="Lutz",
    page_icon=str(Path(__file__).resolve().parent / "lutz.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

project_root = find_project_root()
apply(project_root)

# ── Hero ──────────────────────────────────────────────────────────────────────
col_logo, col_text = st.columns([1, 5], gap="large")
with col_logo:
    logo = Path(__file__).resolve().parent / "lutz.png"
    if logo.exists():
        st.image(str(logo), width=110)

with col_text:
    st.markdown(
        f"""
        <div style="padding-top:0.8rem;">
            <h1 style="border:none !important; padding:0 !important;
                       font-size:2rem !important; margin-bottom:0.15rem !important;">
                Lutz
            </h1>
            <p style="color:{MUTED}; font-size:0.95rem; margin:0;">
                Triagem de artigos acadêmicos com IA
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)

# ── Status do projeto ─────────────────────────────────────────────────────────
if project_root is None:
    st.warning(
        "Nenhum projeto Lutz encontrado no diretório atual. "
        "Execute o app a partir de um diretório com `articles/` ou `.lutz/`."
    )
    st.code("lutz init meu-projeto", language="bash")
    st.stop()

st.markdown(
    f"""
    <div style="background:{TEAL_LIGHT}; border:1px solid {BORDER}; border-radius:10px;
                padding:0.55rem 1rem; font-size:0.83rem; color:{TEAL_DARK};
                margin-bottom:1.4rem; display:inline-block;">
        Projeto: <strong>{project_root.name}</strong>
        &nbsp;·&nbsp;
        <code style="background:transparent; color:{TEAL_DARK}; font-size:0.8rem;">
        {project_root}</code>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Métricas ──────────────────────────────────────────────────────────────────
articles_dir = project_root / "articles"
pdf_count = sum(
    1 for p in articles_dir.iterdir()
    if p.suffix.lower() == ".pdf" and p.name != ".gitkeep"
) if articles_dir.exists() else 0

vs_chunks, vs_articles = 0, 0
try:
    store = get_vector_store(project_root)
    vs_info = store.info()
    vs_chunks = vs_info["total_records"]
    vs_articles = vs_info["unique_documents"]
except Exception:
    pass

reports_dir = project_root / "analysis" / "execution_reports"
report_count = len(list(reports_dir.glob("*.json"))) if reports_dir.exists() else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("PDFs em articles/", pdf_count)
c2.metric("Artigos vetorizados", vs_articles)
c3.metric("Chunks no índice", f"{vs_chunks:,}")
c4.metric("Análises executadas", report_count)

st.divider()

# ── Cartões de navegação ──────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="margin-top:0 !important; margin-bottom:1rem !important;">Fluxo de trabalho</h2>',
    unsafe_allow_html=True,
)

_pages = [
    ("Vetorização",   "Upload de PDFs e indexação na base vetorial com verificação de segurança.", TEAL),
    ("Vector Store",  "Inspecione artigos indexados, chunks, embedding e distribuição de seções.", "#2ABDB8"),
    ("Análise",       "Execute análises por prompt (RAG ou por artigo) ou lotes via YAML.",        TEAL_DARK),
    ("Relatórios",    "Visualize e baixe análises com veredictos INCLUDE/EXCLUDE e HTML.",         "#4A9B97"),
    ("Citações",      "Extraia passagens relevantes com nível de confiança e justificativa.",      "#166B68"),
    ("Configurações", "Configure provedores de LLM/embedding e chaves de API no .env.",           "#3A5858"),
]

row1 = st.columns(3, gap="medium")
row2 = st.columns(3, gap="medium")

for i, (name, desc, color) in enumerate(_pages):
    col = row1[i] if i < 3 else row2[i - 3]
    with col:
        st.markdown(
            f"""
            <div style="background:white; border-radius:14px; padding:1.1rem 1.2rem;
                        border-top:4px solid {color};
                        box-shadow:0 2px 10px rgba(0,0,0,0.06); height:120px;
                        display:flex; flex-direction:column; justify-content:space-between;">
                <div style="font-weight:700; color:{CHARCOAL}; font-size:0.9rem;
                            margin-bottom:0.4rem;">{name}</div>
                <div style="color:{MUTED}; font-size:0.78rem; line-height:1.45;">
                    {desc}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)
st.divider()

# ── Rodapé ────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div style="text-align:center; color:{MUTED}; font-size:0.76rem; padding:0.25rem 0;">
        Lutz · Triagem acadêmica com IA ·
        <a href="https://github.com/jooguilhermesc/lutz" target="_blank"
           style="color:{TEAL}; text-decoration:none;">GitHub</a>
    </div>
    """,
    unsafe_allow_html=True,
)
