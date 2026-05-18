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

# ── Streamlit config.toml — força tema claro ──────────────────────────────────
_THEME_TOML = """\
[theme]
base = "light"
primaryColor = "#1D8B87"
backgroundColor = "#F4F9F9"
secondaryBackgroundColor = "#E8F7F7"
textColor = "#3A5858"
font = "sans serif"
"""


def _ensure_theme_config() -> None:
    """Cria .streamlit/config.toml com tema claro se necessário."""
    import sys
    main_script = sys.argv[0] if sys.argv else None
    if main_script:
        app_dir = Path(main_script).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent

    config_dir = app_dir / ".streamlit"
    config_file = config_dir / "config.toml"

    if config_file.exists():
        content = config_file.read_text(encoding="utf-8")
        if 'base = "light"' in content:
            return

    config_dir.mkdir(exist_ok=True)

    if config_file.exists():
        existing = config_file.read_text(encoding="utf-8")
        if "[theme]" in existing:
            import re
            existing = re.sub(
                r"\[theme\].*?(?=\n\[|\Z)", "", existing, flags=re.DOTALL
            )
        new_content = existing.rstrip() + "\n\n" + _THEME_TOML
    else:
        new_content = _THEME_TOML

    config_file.write_text(new_content, encoding="utf-8")


# ── CSS global (apenas identidade visual — o tema claro cuida das cores base) ─
GLOBAL_CSS = f"""
<style>
/* ── Header ────────────────────────────────────────────────────────── */
[data-testid="stHeader"] {{
    background: transparent !important;
    border-bottom: none !important;
}}

/* ── Sidebar ────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: linear-gradient(175deg, {TEAL} 0%, {TEAL_DARK} 100%);
}}
[data-testid="stSidebarContent"] {{
    background: transparent !important;
}}
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

/* ── Collapse button ──────────────────────────────────────────────── */
[data-testid="stSidebarCollapseButton"] {{
    background: transparent !important;
}}
[data-testid="stSidebarCollapseButton"] button {{
    color: {TEAL} !important;
    background: white !important;
    border: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1) !important;
    border-radius: 6px !important;
}}
[data-testid="stSidebarCollapseButton"] button:hover {{
    color: {TEAL_DARK} !important;
    box-shadow: 0 2px 8px rgba(29,139,135,0.25) !important;
}}
[data-testid="stSidebarCollapseButton"] svg {{
    fill: currentColor !important;
    color: inherit !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button {{
    color: rgba(255,255,255,0.8) !important;
    background: transparent !important;
    box-shadow: none !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button:hover {{
    color: white !important;
    background: rgba(255,255,255,0.15) !important;
}}

/* ── Nav links ─────────────────────────────────────────────────────── */
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
}}
.stButton > button:hover {{
    border-color: {TEAL} !important;
    color: {TEAL} !important;
    box-shadow: 0 2px 8px rgba(29,139,135,0.15) !important;
}}

/* ── Tabs ───────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0 !important;
    border-bottom: 2px solid {BORDER} !important;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0 !important;
    padding: 0.5rem 1.2rem !important;
    font-weight: 500 !important;
    color: {MUTED} !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: {TEAL} !important;
    background: {TEAL_LIGHT} !important;
}}
.stTabs [aria-selected="true"] {{
    color: {TEAL_DARK} !important;
    font-weight: 600 !important;
    background: white !important;
    border-bottom: 2px solid {TEAL} !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {TEAL} !important;
}}

/* ── Metrics ───────────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: white !important;
    border-radius: 12px !important;
    padding: 0.85rem 1rem !important;
    border: 1px solid {BORDER} !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}}
[data-testid="stMetricLabel"] p {{
    color: {MUTED} !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    font-size: 0.7rem !important;
    letter-spacing: 0.06em !important;
}}
[data-testid="stMetricValue"] {{
    color: {CHARCOAL} !important;
    font-weight: 700 !important;
}}

/* ── Dataframe ─────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border-radius: 10px !important;
    border: 1px solid {BORDER} !important;
    overflow: hidden !important;
}}

/* ── Expander ──────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border-radius: 12px !important;
    border: 1px solid {BORDER} !important;
    background: white !important;
}}
[data-testid="stExpander"] summary {{
    font-weight: 500 !important;
}}

/* ── Inputs ─────────────────────────────────────────────────────────── */
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {{
    border-color: {TEAL} !important;
    box-shadow: 0 0 0 2px rgba(29,139,135,0.18) !important;
}}

/* ── File uploader ──────────────────────────────────────────────────── */
[data-testid="stFileUploaderDropzone"] {{
    border: 2px dashed {BORDER} !important;
    border-radius: 12px !important;
}}
[data-testid="stFileUploaderDropzone"]:hover {{
    border-color: {TEAL} !important;
    background: {TEAL_LIGHT} !important;
}}

/* ── Tooltip / help icon ───────────────────────────────────────────── */
[data-testid="stTooltipIcon"] svg {{
    color: {TEAL} !important;
    fill: {TEAL} !important;
}}

/* ── Alertas ────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {{
    border-radius: 10px !important;
}}

/* ── Download button ────────────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {{
    border-radius: 8px !important;
    border: 1.5px solid {BORDER} !important;
    font-weight: 500 !important;
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

</style>
"""


# ── Helpers de componentes ────────────────────────────────────────────────────

def apply(project_root=None) -> None:
    """Injeta o CSS global e renderiza o cabeçalho da sidebar."""
    import streamlit as st
    _ensure_theme_config()
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
