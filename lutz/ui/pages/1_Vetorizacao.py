"""Lutz — Vetorização de PDFs."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root, is_valid_pdf, run_command, safe_filename
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

        with st.spinner("Vetorizando artigos... Isso pode demorar alguns minutos."):
            rc, output = run_command(cmd, project_root)

        if rc == 0:
            st.success("Vetorização concluída com sucesso!")
        else:
            st.error("Erro durante a vetorização.")

        if output:
            with st.expander("Saída do processo", expanded=(rc != 0)):
                st.code(output, language=None)
