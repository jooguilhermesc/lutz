"""Lutz — Análise de artigos."""
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root, get_vector_store, run_command

st.set_page_config(page_title="Lutz — Análise", layout="wide")
st.title("Análise de Artigos")

project_root = find_project_root()
if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

# Verificar vector store
try:
    store = get_vector_store(project_root)
    vs_info = store.info()
except Exception:
    vs_info = {"total_records": 0, "unique_documents": 0}

if vs_info["total_records"] == 0:
    st.warning(
        "Vector store vazio. Vetorize os artigos primeiro na página **Vetorização**."
    )
    st.stop()

st.info(
    f"Base vetorial: **{vs_info['total_records']:,}** chunks de "
    f"**{vs_info['unique_documents']}** artigo(s)"
)
st.divider()

tab_simples, tab_experimentos = st.tabs(["Análise Simples", "Múltiplos Experimentos"])

# ── Aba: Análise Simples ──────────────────────────────────────────────────────
with tab_simples:
    st.subheader("Prompt de análise")

    # Carregar prompt existente
    prompts_dir = project_root / "prompts"
    existing_prompts = sorted(prompts_dir.glob("*.md")) if prompts_dir.exists() else []

    default_prompt = ""

    col_load1, col_load2 = st.columns(2)
    with col_load1:
        if existing_prompts:
            chosen_existing = st.selectbox(
                "Usar prompt existente em prompts/",
                ["— selecionar —"] + [p.name for p in existing_prompts],
            )
            if chosen_existing != "— selecionar —":
                default_prompt = next(
                    p for p in existing_prompts if p.name == chosen_existing
                ).read_text(encoding="utf-8")
    with col_load2:
        uploaded_prompt = st.file_uploader(
            "Ou carregar arquivo de prompt (.md)",
            type=["md", "txt"],
            key="prompt_upload",
        )
        if uploaded_prompt is not None:
            default_prompt = uploaded_prompt.read().decode("utf-8")

    prompt_text = st.text_area(
        "Conteúdo do prompt (Markdown)",
        value=default_prompt,
        height=260,
        placeholder=(
            "Descreva os critérios de inclusão/exclusão para a triagem.\n\n"
            "Exemplo:\n"
            "## Critério de Relevância\n"
            "Inclua apenas estudos que reportem experimentos controlados randomizados (RCT)..."
        ),
    )

    st.subheader("Configurações de execução")
    col1, col2 = st.columns(2)

    with col1:
        mode = st.radio(
            "Modo de análise",
            ["RAG — síntese global", "Por artigo — triagem sistemática"],
            help=(
                "**RAG**: uma chamada ao LLM com os trechos mais relevantes da base. "
                "Ideal para síntese e perguntas abertas.\n\n"
                "**Por artigo**: uma chamada LLM por artigo com veredicto INCLUDE/EXCLUDE/UNCERTAIN. "
                "Recomendado para triagem sistemática."
            ),
        )
        per_article = "Por artigo" in mode

    with col2:
        output_name = st.text_input(
            "Nome do arquivo de saída (opcional)",
            placeholder="Ex: triagem_piloto_v1",
            help="Deixe em branco para gerar automaticamente com timestamp.",
        )

    with st.expander("Opções avançadas"):
        if per_article:
            workers = st.number_input(
                "Workers (chamadas LLM paralelas)", 1, 32, 1,
                help="Aumente para APIs remotas (OpenAI, Anthropic). "
                     "Mantenha em 1 para modelos locais (Docker Model Runner).",
            )
            max_chunks_raw = st.number_input(
                "Máx. chunks por artigo (0 = sem limite)", 0, 200, 0,
                help="Limita o contexto enviado ao LLM por artigo. "
                     "Útil para modelos com janela de contexto pequena.",
            )
            max_chunks: int | None = max_chunks_raw if max_chunks_raw > 0 else None
        else:
            top_k = st.number_input(
                "Top-K chunks", 1, 500, 10,
                help="Número de trechos mais similares ao prompt a recuperar da base vetorial.",
            )
            workers = 1
            max_chunks = None

        try:
            breakdown = store.section_breakdown()
            all_sections = sorted({s for counts in breakdown.values() for s in counts if s})
        except Exception:
            all_sections = []

        if all_sections:
            filter_sections = st.multiselect(
                "Filtrar seções",
                options=all_sections,
                help="Deixe em branco para usar todos os chunks, "
                     "independente da seção.",
            )
        else:
            filter_sections = []

    st.divider()

    run_disabled = not prompt_text.strip()
    if run_disabled:
        st.caption("Escreva ou carregue um prompt para habilitar a execução.")

    if st.button("Executar Análise", type="primary", disabled=run_disabled):
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="lutz_prompt_")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(prompt_text)

            cmd = ["lutz", "analysis", "--p", tmp_path]

            if per_article:
                cmd.append("--per-article")
                cmd.extend(["--workers", str(workers)])
                if max_chunks:
                    cmd.extend(["--max-chunks-per-article", str(max_chunks)])
            else:
                cmd.extend(["--top-k", str(top_k)])

            if filter_sections:
                cmd.extend(["--filter-sections", ",".join(filter_sections)])

            if output_name.strip():
                safe = "".join(c for c in output_name.strip() if c.isalnum() or c in "-_")
                if safe:
                    cmd.extend(["--output-name", safe])

            with st.spinner("Executando análise... Isso pode levar vários minutos."):
                rc, output = run_command(cmd, project_root)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if rc == 0:
            st.success(
                "Análise concluída! Acesse a página **Relatórios** para ver os resultados."
            )
        else:
            st.error("Erro durante a análise.")

        if output:
            with st.expander("Saída do processo", expanded=(rc != 0)):
                st.code(output, language=None)

# ── Aba: Múltiplos Experimentos ───────────────────────────────────────────────
with tab_experimentos:
    st.subheader("Múltiplos experimentos via YAML")
    st.caption(
        "Execute vários experimentos em sequência. "
        "Cada experimento define seu próprio prompt, modo e parâmetros. "
        "Os prompts referenciados no YAML devem existir em `prompts/` do projeto."
    )

    yaml_example = (
        "triagem_piloto:\n"
        "  prompt: prompts/screening.md\n"
        "  mode: per_article\n"
        "  workers: 2\n"
        "\n"
        "triagem_rag:\n"
        "  prompt: prompts/systematic_review.md\n"
        "  mode: top_k\n"
        "  top_k: 15\n"
    )

    col_y1, col_y2 = st.columns([3, 1])
    with col_y2:
        yaml_upload = st.file_uploader(
            "Carregar arquivo YAML",
            type=["yaml", "yml"],
            key="yaml_upload",
        )

    default_yaml = yaml_upload.read().decode("utf-8") if yaml_upload else yaml_example

    yaml_text = st.text_area(
        "Configuração YAML dos experimentos",
        value=default_yaml,
        height=300,
        help="Consulte a documentação do lutz para o schema completo.",
    )

    if st.button("Executar Experimentos", type="primary"):
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix="lutz_exp_")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(yaml_text)

            cmd = ["lutz", "analysis", "--multiple", tmp_path]

            with st.spinner("Executando experimentos... Isso pode levar vários minutos."):
                rc, output = run_command(cmd, project_root)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if rc == 0:
            st.success(
                "Experimentos concluídos! Acesse a página **Relatórios** para ver os resultados."
            )
        else:
            st.error("Erro durante a execução dos experimentos.")

        if output:
            with st.expander("Saída do processo", expanded=(rc != 0)):
                st.code(output, language=None)
