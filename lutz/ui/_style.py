"""Estilos e componentes visuais compartilhados da interface Lutz.

Paleta extraída do logo lutz.png:
  #1D8B87  — teal primário (fundo do logo)
  #166B68  — teal escuro   (hover / profundidade)
  #2ABDB8  — teal claro    (acento)
  #3A5858  — charcoal      (letras do logo)
  #E8F7F7  — teal pastel   (fundos suaves)
"""
from __future__ import annotations

from pathlib import Path

# ── Paleta ────────────────────────────────────────────────────────────────────
TEAL       = "#1D8B87"
TEAL_DARK  = "#166B68"
TEAL_LIGHT = "#E8F7F7"
TEAL_MID   = "#2ABDB8"
CHARCOAL   = "#3A5858"
MUTED      = "#6B8A8A"
BORDER     = "#C8E6E5"

_LOGO = Path(__file__).resolve().parent / "lutz.png"
LOGO_PATH = str(_LOGO) if _LOGO.exists() else None

# ── CSS global ────────────────────────────────────────────────────────────────
GLOBAL_CSS = f"""
<style>
/* ── Base ──────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] {{
    background: #F4F9F9;
}}
[data-testid="stHeader"] {{
    background: transparent !important;
    border-bottom: none !important;
}}

/* ── Texto principal (impede herança de branco do tema escuro) ────── */
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] span,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] small,
[data-testid="stAppViewContainer"] .stMarkdown,
[data-testid="stAppViewContainer"] .stRadio label,
[data-testid="stAppViewContainer"] .stCheckbox label,
[data-testid="stAppViewContainer"] .stSelectbox label,
[data-testid="stAppViewContainer"] .stMultiSelect label,
[data-testid="stAppViewContainer"] .stNumberInput label,
[data-testid="stAppViewContainer"] .stTextInput label,
[data-testid="stAppViewContainer"] .stTextArea label,
[data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"],
[data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] p,
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"],
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] p {{
    color: {CHARCOAL} !important;
}}

/* ── Sidebar ────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: linear-gradient(175deg, {TEAL} 0%, {TEAL_DARK} 100%);
}}
[data-testid="stSidebarContent"] {{
    background: transparent !important;
}}
/* Texto geral na sidebar */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] small {{
    color: rgba(255,255,255,0.9) !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,0.2) !important;
    margin: 0.75rem 0 !important;
}}

/* ── Botão de colapso / expansão ────────────────────────────────────
   O botão vive FORA da sidebar (no header do app) nas versões
   recentes do Streamlit, então o estilo padrão precisa ser visível
   sobre o fundo claro. O seletor mais específico (dentro da sidebar)
   aplica ícone branco quando a sidebar está aberta. */
[data-testid="stSidebarCollapseButton"] {{
    background: transparent !important;
}}
[data-testid="stSidebarCollapseButton"] button {{
    color: {TEAL} !important;
    background: white !important;
    border: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1) !important;
    border-radius: 6px !important;
    transition: all 0.18s ease !important;
}}
[data-testid="stSidebarCollapseButton"] button:hover {{
    color: {TEAL_DARK} !important;
    box-shadow: 0 2px 8px rgba(29,139,135,0.25) !important;
}}
[data-testid="stSidebarCollapseButton"] svg {{
    fill: currentColor !important;
    color: inherit !important;
}}
/* Dentro da sidebar aberta — ícone branco sobre fundo teal */
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button {{
    color: rgba(255,255,255,0.8) !important;
    background: transparent !important;
    box-shadow: none !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button:hover {{
    color: white !important;
    background: rgba(255,255,255,0.15) !important;
}}

/* Links de navegação entre páginas (Streamlit 1.36+ usa stSidebarNavLink) */
[data-testid="stSidebarNavLink"] {{
    border-radius: 8px !important;
    margin: 1px 4px !important;
    color: rgba(255,255,255,0.80) !important;
    font-size: 0.88rem !important;
}}
[data-testid="stSidebarNavLink"]:hover {{
    background: rgba(255,255,255,0.12) !important;
    color: white !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(255,255,255,0.2) !important;
    color: white !important;
    font-weight: 600 !important;
}}
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p {{
    color: inherit !important;
}}
/* Compatibilidade com versões que ainda usam stSidebarNav */
[data-testid="stSidebarNav"] a span {{
    color: rgba(255,255,255,0.80) !important;
    font-size: 0.88rem !important;
}}
[data-testid="stSidebarNav"] a:hover span {{
    color: white !important;
}}
[data-testid="stSidebarNav"] [aria-selected="true"] span,
[data-testid="stSidebarNav"] [aria-current="page"] span {{
    color: white !important;
    font-weight: 600 !important;
}}
[data-testid="stSidebarNav"] li {{
    border-radius: 8px !important;
    margin: 1px 4px !important;
}}
[data-testid="stSidebarNav"] li:hover {{
    background: rgba(255,255,255,0.12) !important;
}}
[data-testid="stSidebarNav"] [aria-selected="true"],
[data-testid="stSidebarNav"] [aria-current="page"] {{
    background: rgba(255,255,255,0.2) !important;
}}

/* ── Layout ─────────────────────────────────────────────────────────── */
.block-container {{
    padding-top: 1.8rem !important;
    padding-bottom: 2rem !important;
    max-width: 1080px !important;
}}

/* ── Títulos ────────────────────────────────────────────────────────── */
h1 {{
    color: {CHARCOAL} !important;
    font-weight: 700 !important;
    font-size: 1.7rem !important;
    margin-bottom: 0.2rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 3px solid {TEAL} !important;
}}
h2 {{
    color: {CHARCOAL} !important;
    font-weight: 600 !important;
    font-size: 1.2rem !important;
    margin-top: 1.4rem !important;
}}
h3 {{
    color: {TEAL_DARK} !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
}}

/* ── Botões ─────────────────────────────────────────────────────────── */
.stButton > button {{
    border-radius: 8px !important;
    border: 1.5px solid {BORDER} !important;
    font-weight: 500 !important;
    padding: 0.4rem 1.2rem !important;
    transition: all 0.18s ease !important;
    background: white !important;
    color: {CHARCOAL} !important;
}}
.stButton > button:hover {{
    border-color: {TEAL} !important;
    color: {TEAL} !important;
    box-shadow: 0 2px 8px rgba(29,139,135,0.15) !important;
}}
/* Primary — múltiplos seletores para cobrir versões do Streamlit */
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"],
.stFormSubmitButton > button {{
    background: {TEAL} !important;
    border-color: {TEAL} !important;
    color: white !important;
}}
.stButton > button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover,
.stFormSubmitButton > button:hover {{
    background: {TEAL_DARK} !important;
    border-color: {TEAL_DARK} !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(29,139,135,0.35) !important;
    color: white !important;
}}
/* Disabled — legível mesmo desabilitado */
.stButton > button:disabled {{
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}}
.stButton > button[kind="primary"]:disabled,
[data-testid="stBaseButton-primary"]:disabled,
.stFormSubmitButton > button:disabled {{
    background: {TEAL} !important;
    color: rgba(255,255,255,0.75) !important;
    opacity: 0.55 !important;
}}

/* ── Métricas ───────────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: white !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    border-left: 4px solid {TEAL} !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
}}
[data-testid="stMetricLabel"] > div {{
    color: {MUTED} !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}}
[data-testid="stMetricValue"] {{
    color: {CHARCOAL} !important;
    font-weight: 700 !important;
    font-size: 1.6rem !important;
}}

/* ── Tabs ───────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 2px !important;
    border-bottom: 2px solid {BORDER} !important;
    background: transparent !important;
    padding: 0 !important;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0 !important;
    padding: 0.55rem 1.3rem !important;
    font-weight: 500 !important;
    color: {MUTED} !important;
    border: none !important;
    background: transparent !important;
    font-size: 0.88rem !important;
}}
.stTabs [aria-selected="true"] {{
    color: {TEAL} !important;
    background: {TEAL_LIGHT} !important;
    border-bottom: 2px solid {TEAL} !important;
    font-weight: 600 !important;
}}

/* ── Expanders ──────────────────────────────────────────────────────── */
details summary {{
    background: white !important;
    border-radius: 8px !important;
    border: 1px solid {BORDER} !important;
    padding: 0.6rem 1rem !important;
    font-weight: 500 !important;
    color: {CHARCOAL} !important;
    cursor: pointer !important;
}}
details[open] summary {{
    border-radius: 8px 8px 0 0 !important;
    border-bottom-color: transparent !important;
}}
details > div {{
    border: 1px solid {BORDER} !important;
    border-top: none !important;
    border-radius: 0 0 8px 8px !important;
    background: #FAFEFE !important;
    padding: 1rem !important;
}}

/* ── DataFrames ─────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] > div {{
    border-radius: 10px !important;
    overflow: hidden !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
    border: 1px solid {BORDER} !important;
}}

/* ── Inputs ─────────────────────────────────────────────────────────── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {{
    border-radius: 8px !important;
    border-color: {BORDER} !important;
    background: white !important;
    color: {CHARCOAL} !important;
}}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {{
    border-color: {TEAL} !important;
    box-shadow: 0 0 0 2px rgba(29,139,135,0.18) !important;
}}
/* Botões stepper (+/−) do number input */
[data-testid="stNumberInput"] button {{
    background: white !important;
    color: {CHARCOAL} !important;
    border: 1px solid {BORDER} !important;
}}
[data-testid="stNumberInput"] button:hover {{
    border-color: {TEAL} !important;
    color: {TEAL} !important;
}}
[data-testid="stNumberInput"] button svg {{
    fill: currentColor !important;
}}
/* Checkbox — caixa visual e label */
[data-testid="stCheckbox"] label {{
    color: {CHARCOAL} !important;
}}
[data-testid="stCheckbox"] label span,
[data-testid="stCheckbox"] label p {{
    color: {CHARCOAL} !important;
}}
[data-testid="stCheckbox"] label > span:first-child,
[data-testid="stCheckbox"] [role="checkbox"] {{
    background: white !important;
    border: 2px solid {BORDER} !important;
    border-radius: 4px !important;
}}
[data-testid="stCheckbox"] [role="checkbox"][aria-checked="true"],
[data-testid="stCheckbox"] label > span:first-child[aria-checked="true"] {{
    background: {TEAL} !important;
    border-color: {TEAL} !important;
}}
/* Radio */
.stRadio label,
.stRadio [role="radiogroup"] label,
.stRadio [role="radiogroup"] label span,
.stRadio [role="radiogroup"] label p {{
    color: {CHARCOAL} !important;
}}
/* Selectbox */
.stSelectbox > div > div,
[data-testid="stSelectbox"] > div > div {{
    border-radius: 8px !important;
    border-color: {BORDER} !important;
    background: white !important;
    color: {CHARCOAL} !important;
}}
.stSelectbox > div > div span,
[data-testid="stSelectbox"] span {{
    color: {CHARCOAL} !important;
}}
/* MultiSelect — força fundo claro */
.stMultiSelect > div > div,
[data-testid="stMultiSelect"] > div > div {{
    border-radius: 8px !important;
    border-color: {BORDER} !important;
    background: white !important;
    color: {CHARCOAL} !important;
}}
[data-testid="stMultiSelect"] span {{
    color: {CHARCOAL} !important;
}}
/* Textarea — texto visível */
.stTextArea textarea {{
    color: {CHARCOAL} !important;
}}
.stTextArea textarea::placeholder {{
    color: {MUTED} !important;
    opacity: 0.7 !important;
}}

/* ── File uploader ──────────────────────────────────────────────────── */
[data-testid="stFileUploaderDropzone"] {{
    border: 2px dashed {BORDER} !important;
    border-radius: 12px !important;
    background: white !important;
    transition: border-color 0.2s !important;
}}
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] p {{
    color: {MUTED} !important;
}}
[data-testid="stFileUploaderDropzone"]:hover {{
    border-color: {TEAL} !important;
    background: {TEAL_LIGHT} !important;
}}

/* ── Baseweb dropdowns / popover (força tema claro) ────────────────── */
[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="select"] > div,
[data-baseweb="input"] {{
    background: white !important;
    color: {CHARCOAL} !important;
}}
[data-baseweb="select"] > div {{
    background: white !important;
    border-color: {BORDER} !important;
}}
[data-baseweb="select"] span,
[data-baseweb="select"] div[role="option"],
[data-baseweb="menu"] li {{
    color: {CHARCOAL} !important;
}}
[data-baseweb="menu"] li:hover {{
    background: {TEAL_LIGHT} !important;
}}
/* Tooltip / help icon */
[data-testid="stTooltipIcon"] svg {{
    color: {TEAL} !important;
    fill: {TEAL} !important;
}}

/* ── Alertas ────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {{
    border-radius: 10px !important;
}}
[data-testid="stAlert"] p,
[data-testid="stAlert"] span,
[data-testid="stAlert"] code,
[data-testid="stAlert"] strong,
[data-testid="stAlert"] a {{
    color: {CHARCOAL} !important;
}}

/* ── Download button ────────────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {{
    border-radius: 8px !important;
    border: 1.5px solid {BORDER} !important;
    background: white !important;
    color: {CHARCOAL} !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
}}
[data-testid="stDownloadButton"] > button:hover {{
    border-color: {TEAL} !important;
    color: {TEAL} !important;
    box-shadow: 0 2px 8px rgba(29,139,135,0.15) !important;
}}

/* ── Divider ────────────────────────────────────────────────────────── */
hr {{
    border: none !important;
    border-top: 1px solid {BORDER} !important;
    margin: 1.5rem 0 !important;
}}

/* ── Spinner ────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {{
    border-top-color: {TEAL} !important;
}}

/* ── Catch-all: texto escuro fora da sidebar ───────────────────────── */
[data-testid="stMainBlockContainer"] {{
    color: {CHARCOAL} !important;
}}
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] li,
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] span {{
    color: inherit !important;
}}

</style>
"""


# ── Helpers de componentes ────────────────────────────────────────────────────

def apply(project_root=None) -> None:
    """Injeta o CSS global e renderiza o cabeçalho da sidebar."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    _sidebar_header(project_root)


def _sidebar_header(project_root=None) -> None:
    import streamlit as st
    from pathlib import Path as _Path

    if LOGO_PATH:
        st.sidebar.image(LOGO_PATH, width=130)

    st.sidebar.markdown(
        f"""
        <div style="font-size:0.68rem; color:rgba(255,255,255,0.55);
                    text-transform:uppercase; letter-spacing:0.12em;
                    margin-top:-0.2rem; margin-bottom:0.6rem;">
            Triagem acadêmica com IA
        </div>
        """,
        unsafe_allow_html=True,
    )

    if project_root is not None:
        proj_name = _Path(str(project_root)).name
        st.sidebar.markdown(
            f"""
            <div style="background:rgba(255,255,255,0.13); border-radius:8px;
                        padding:0.45rem 0.75rem; font-size:0.75rem;
                        color:rgba(255,255,255,0.85); margin-bottom:0.25rem;">
                <span style="opacity:0.6; font-size:0.65rem; display:block;
                             text-transform:uppercase; letter-spacing:0.08em;">
                    projeto
                </span>
                <strong>{proj_name}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.sidebar.markdown("---")


def page_title(title: str, subtitle: str = "") -> None:
    """Cabeçalho padronizado de página."""
    import streamlit as st
    sub_html = (
        f'<p style="color:{MUTED}; margin:0.2rem 0 0; font-size:0.88rem;">'
        f'{subtitle}</p>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="margin-bottom:1.4rem;"><h1>{title}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def info_card(label: str, value: str, accent: str = TEAL) -> str:
    """HTML de um cartão de informação."""
    return (
        f'<div style="background:white; border-radius:12px; padding:1rem 1.2rem; '
        f'border-left:4px solid {accent}; box-shadow:0 2px 8px rgba(0,0,0,0.05); '
        f'margin-bottom:0.75rem;">'
        f'<div style="font-size:0.7rem; color:{MUTED}; text-transform:uppercase; '
        f'letter-spacing:0.07em; font-weight:600; margin-bottom:0.3rem;">{label}</div>'
        f'<div style="color:{CHARCOAL}; font-size:0.9rem; line-height:1.5;">{value}</div>'
        f'</div>'
    )


def section_badge(text: str, color: str = TEAL) -> str:
    """Badge/tag inline."""
    return (
        f'<span style="background:{color}18; color:{color}; border:1px solid {color}44; '
        f'border-radius:20px; padding:0.15rem 0.65rem; font-size:0.75rem; '
        f'font-weight:600;">{text}</span>'
    )


def relevance_badge(label: str) -> str:
    """Badge colorido por veredicto de relevância."""
    colors = {
        "INCLUDE":   ("#1D8B87", "#E8F7F7"),
        "EXCLUDE":   ("#C0392B", "#FDEDEC"),
        "UNCERTAIN": ("#B7770D", "#FEF9E7"),
        "UNKNOWN":   ("#7F8C8D", "#F2F3F4"),
    }
    fg, bg = colors.get(label.upper(), ("#7F8C8D", "#F2F3F4"))
    return (
        f'<span style="background:{bg}; color:{fg}; border:1px solid {fg}44; '
        f'border-radius:20px; padding:0.2rem 0.75rem; font-size:0.8rem; '
        f'font-weight:700; white-space:nowrap;">{label}</span>'
    )
