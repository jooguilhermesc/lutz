"""Lutz — Vetorização de PDFs."""
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root, is_valid_pdf, is_meaningful_line, run_command, safe_filename, stream_command
from _style import apply, page_title, TEAL, TEAL_LIGHT, MUTED, BORDER, CHARCOAL

st.set_page_config(
    page_title="Lutz — Vetorização",
    page_icon=str(Path(__file__).resolve().parent.parent / "lutz.png"),
    layout="wide",
)

project_root = find_project_root()
apply(project_root)
page_title("Vetorização", "Indexe artigos PDF na base vetorial para buscas semânticas")

if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

articles_dir = project_root / "articles"
articles_dir.mkdir(exist_ok=True)

tab_artigos, tab_vetorizar = st.tabs(["Artigos", "Vetorizar"])

# ── Aba: Artigos ──────────────────────────────────────────────────────────────
with tab_artigos:
    pdfs = sorted(
        p for p in articles_dir.iterdir()
        if p.suffix.lower() == ".pdf" and p.name != ".gitkeep"
    )

    if pdfs:
        st.markdown(
            f'<p style="color:{MUTED}; font-size:0.85rem; margin-bottom:0.6rem;">'
            f'{len(pdfs)} arquivo(s) em <code>articles/</code></p>',
            unsafe_allow_html=True,
        )
        df = pd.DataFrame([{
            "Nome": p.name,
            "Tamanho": f"{p.stat().st_size / 1024:.1f} KB",
        } for p in pdfs])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum PDF encontrado em `articles/`. Faça upload abaixo.")

    st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<h3 style="margin-bottom:0.6rem;">Adicionar PDFs</h3>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Selecione arquivos PDF",
        type=["pdf"],
        accept_multiple_files=True,
        help="Os arquivos serão salvos em articles/ do projeto.",
    )

    if uploaded:
        if st.button("Salvar arquivos em articles/", type="primary"):
            saved, errors = [], []
            for f in uploaded:
                content = f.read()
                if not is_valid_pdf(content):
                    errors.append(f"`{f.name}`: arquivo inválido ou corrompido.")
                    continue
                name = safe_filename(f.name)
                dest = articles_dir / name
                dest.write_bytes(content)
                saved.append(name)
            if saved:
                st.success(f"{len(saved)} arquivo(s) salvos com sucesso.")
                st.rerun()
            for e in errors:
                st.warning(e)

# ── Padrões para parsing do output da vetorização ─────────────────────────────
_RE_FOUND = re.compile(r'Found\s+(\d+)\s+PDF')
_RE_PHASE1 = re.compile(r'Phase\s+1')
_RE_PHASE2 = re.compile(r'Phase\s+2')
_RE_PHASE3 = re.compile(r'Phase\s+3')
_RE_EMBEDDING = re.compile(r'Embedding\s+(.+?)\.\.\.')
_RE_QUARANTINE = re.compile(r'quarantined\s+(.+)', re.IGNORECASE)
_RE_COMPLETE = re.compile(r'Vectorization complete', re.IGNORECASE)
_RE_CHUNKS = re.compile(r'Extracted\s+(\d+)\s+chunk')

# ── Aba: Vetorizar ────────────────────────────────────────────────────────────
with tab_vetorizar:
    col1, col2 = st.columns(2)
    with col1:
        chunk_size = st.number_input(
            "Tamanho do chunk (palavras)", 64, 2048, 512, 64,
            help="512 palavras ≈ 680 tokens para texto em inglês. "
                 "Valores menores aumentam a granularidade, mas elevam o custo de embedding.",
        )
        chunk_overlap = st.number_input(
            "Sobreposição entre chunks (palavras)", 0, 512, 64, 16,
            help="Palavras compartilhadas entre chunks consecutivos. "
                 "Preserva contexto nas fronteiras. Deve ser menor que o tamanho do chunk.",
        )

    with col2:
        skip_security = st.checkbox(
            "Ignorar verificações de segurança",
            help="Não recomendado. Use apenas com PDFs de fontes totalmente confiáveis.",
        )
        section_parse = st.checkbox(
            "Análise por seções (abstract, introdução, etc.)",
            help="Detecta seções nos artigos e rotula cada chunk com o nome da seção. "
                 "Melhora a qualidade da triagem por seção.",
        )
        quarantine_mode = st.checkbox(
            "Modo quarentena",
            help="Processa arquivos de `articles/_quarantine/` (verificação de segurança ignorada). "
                 "Use após revisão manual dos arquivos.",
        )

    if chunk_overlap >= chunk_size:
        st.error("A sobreposição deve ser menor que o tamanho do chunk.")
        st.stop()

    pdf_count = sum(
        1 for p in articles_dir.iterdir()
        if p.suffix.lower() == ".pdf" and p.name != ".gitkeep"
    )
    if pdf_count == 0 and not quarantine_mode:
        st.warning("Nenhum PDF encontrado em `articles/`. Adicione arquivos na aba **Artigos**.")

    st.divider()

    if st.button("Iniciar Vetorização", type="primary"):
        cmd = [
            "lutz", "vectorize",
            "--chunk-size", str(chunk_size),
            "--chunk-overlap", str(chunk_overlap),
        ]
        if skip_security:
            cmd.append("--skip-security")
        if section_parse:
            cmd.append("--section-parse")
        if quarantine_mode:
            cmd.append("--quarantine")

        # ── Placeholders de progresso ──────────────────────────────────────
        phase_placeholder = st.empty()
        article_placeholder = st.empty()

        # Estado de progresso
        current_phase = "Iniciando..."
        current_article: str | None = None
        total_pdfs = 0
        processed_articles: list[str] = []
        quarantined: list[str] = []
        log_lines: list[str] = []
        returncode = None

        def _render_phase(phase: str, article: str | None, total: int, processed: list[str]) -> None:
            phase_icons = {
                "segurança": "🔍",
                "extração": "📄",
                "embedding": "🧠",
                "Iniciando": "⏳",
            }
            icon = next((v for k, v in phase_icons.items() if k in phase.lower()), "⚙️")
            progress_text = (
                f" — {len(processed)}/{total} artigos" if total > 0 else ""
            )
            phase_placeholder.markdown(
                f'<div style="background:{TEAL_LIGHT}; border:1px solid {TEAL}; '
                f'border-radius:8px; padding:0.6rem 1rem; margin-bottom:0.5rem;">'
                f'<span style="font-weight:600; color:{CHARCOAL};">'
                f'{icon} {phase}{progress_text}</span></div>',
                unsafe_allow_html=True,
            )
            if article:
                article_placeholder.markdown(
                    f'<div style="background:#f8f9fa; border-left:3px solid {TEAL}; '
                    f'padding:0.4rem 0.8rem; border-radius:0 6px 6px 0; '
                    f'color:{MUTED}; font-size:0.85rem;">'
                    f'Processando: <code>{article}</code></div>',
                    unsafe_allow_html=True,
                )
            else:
                article_placeholder.empty()

        # Expander de log fica abaixo do progresso
        log_expander = st.expander("Log detalhado", expanded=False)
        log_placeholder = log_expander.empty()

        _render_phase(current_phase, None, 0, [])

        for line, rc in stream_command(cmd, project_root):
            if rc is not None:
                returncode = rc
                break

            if not line or not is_meaningful_line(line):
                continue

            log_lines.append(line)

            # ── Detectar total de PDFs ─────────────────────────────────
            m = _RE_FOUND.search(line)
            if m:
                total_pdfs = int(m.group(1))

            # ── Detectar fase ──────────────────────────────────────────
            if _RE_PHASE1.search(line):
                current_phase = "Verificação de segurança"
                current_article = None
            elif _RE_PHASE2.search(line):
                current_phase = "Extração de texto"
                current_article = None
            elif _RE_PHASE3.search(line):
                current_phase = "Embedding e indexação"
                current_article = None

            # ── Detectar artigo atual (embedding) ──────────────────────
            m = _RE_EMBEDDING.search(line)
            if m:
                current_article = m.group(1).strip()
                processed_articles.append(current_article)

            # ── Detectar quarentena ────────────────────────────────────
            m = _RE_QUARANTINE.search(line)
            if m:
                quarantined.append(m.group(1).strip())

            _render_phase(current_phase, current_article, total_pdfs, processed_articles)
            log_placeholder.code("\n".join(log_lines[-60:]), language=None)

        # ── Resultado final ────────────────────────────────────────────
        phase_placeholder.empty()
        article_placeholder.empty()

        if returncode == 0:
            st.success("Vetorização concluída com sucesso!")
        else:
            st.error("Erro durante a vetorização.")

        if quarantined:
            st.warning(
                f"{len(quarantined)} arquivo(s) enviado(s) para quarentena: "
                + ", ".join(f"`{q}`" for q in quarantined)
            )

        if log_lines:
            with st.expander("Saída do processo", expanded=(returncode != 0)):
                st.code("\n".join(log_lines), language=None)
