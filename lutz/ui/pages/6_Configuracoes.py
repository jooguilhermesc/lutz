"""Lutz — Configuração de variáveis de ambiente."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root
from _style import apply, page_title, info_card, TEAL, TEAL_LIGHT, MUTED, CHARCOAL, BORDER

st.set_page_config(
    page_title="Lutz — Configurações",
    page_icon=str(Path(__file__).resolve().parent.parent / "lutz.png"),
    layout="wide",
)

project_root = find_project_root()
apply(project_root)
page_title(
    "Configurações",
    "Configure provedores de LLM/embedding e chaves de API no .env do projeto",
)

if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

st.markdown(
    f"""
    <div style="background:{TEAL_LIGHT}; border:1px solid {BORDER}; border-radius:10px;
                padding:0.55rem 1rem; font-size:0.83rem; color:#166B68;
                margin-bottom:1.2rem;">
        As credenciais são armazenadas <strong>somente</strong> no arquivo
        <code>.env</code> do projeto e nunca são expostas na interface.
    </div>
    """,
    unsafe_allow_html=True,
)

env_file = project_root / ".env"

from dotenv import dotenv_values

_current: dict[str, str] = {}
if env_file.exists():
    _current = {k: (v or "") for k, v in dotenv_values(env_file).items()}

_PROVIDERS_LLM = ["openai", "anthropic", "docker_model_runner"]
_PROVIDERS_EMBED = ["openai", "sentence_transformers", "docker_model_runner"]
_SENSITIVE_KEYS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}


def _idx(options: list[str], key: str, default: int = 0) -> int:
    val = _current.get(key, "")
    return options.index(val) if val in options else default


with st.form("config_form"):
    st.markdown(
        f'<h3 style="margin-bottom:0.6rem;">Provedor de LLM</h3>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        llm_provider = st.selectbox(
            "LLM_PROVIDER",
            _PROVIDERS_LLM,
            index=_idx(_PROVIDERS_LLM, "LLM_PROVIDER"),
            help="Provedor de linguagem para análise e extração de citações.",
        )
    with col2:
        llm_model = st.text_input(
            "LLM_MODEL",
            value=_current.get("LLM_MODEL", ""),
            placeholder="Ex: claude-haiku-4-5, gpt-4o-mini, ai/mistral-small-3.1",
        )

    st.markdown(
        f'<h3 style="margin-bottom:0.6rem; margin-top:1rem;">Provedor de Embeddings</h3>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        embed_provider = st.selectbox(
            "EMBEDDING_PROVIDER",
            _PROVIDERS_EMBED,
            index=_idx(_PROVIDERS_EMBED, "EMBEDDING_PROVIDER"),
            help="Provedor para geração de embeddings vetoriais dos artigos.",
        )
    with col2:
        embed_model = st.text_input(
            "EMBEDDING_MODEL",
            value=_current.get("EMBEDDING_MODEL", ""),
            placeholder="Ex: text-embedding-3-small, all-MiniLM-L6-v2",
        )

    st.markdown(
        f'<h3 style="margin-bottom:0.3rem; margin-top:1rem;">Chaves de API</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="color:{MUTED}; font-size:0.83rem; margin-bottom:0.8rem;">'
        f'Deixe em branco para manter o valor atual sem alterações. '
        f'Os campos são mascarados e os valores não ficam visíveis após o salvamento.</p>',
        unsafe_allow_html=True,
    )

    openai_key = st.text_input(
        "OPENAI_API_KEY",
        type="password",
        placeholder="sk-... (deixe em branco para não alterar)",
        help="Necessário quando LLM_PROVIDER=openai ou EMBEDDING_PROVIDER=openai. "
             "Também compatível com OpenRouter e outras APIs OpenAI-compatíveis.",
    )
    anthropic_key = st.text_input(
        "ANTHROPIC_API_KEY",
        type="password",
        placeholder="sk-ant-... (deixe em branco para não alterar)",
        help="Necessário quando LLM_PROVIDER=anthropic.",
    )

    st.markdown(
        f'<h3 style="margin-bottom:0.6rem; margin-top:1rem;">Configurações avançadas</h3>',
        unsafe_allow_html=True,
    )
    openai_base_url = st.text_input(
        "OPENAI_BASE_URL (opcional)",
        value=_current.get("OPENAI_BASE_URL", ""),
        placeholder="https://openrouter.ai/api/v1",
        help="URL base da API OpenAI-compatível. "
             "Use para OpenRouter ou outros provedores compatíveis. "
             "Deixe em branco para usar a API padrão da OpenAI.",
    )

    st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)
    submitted = st.form_submit_button("Salvar Configurações", type="primary")

if submitted:
    new_values: dict[str, str] = {
        "LLM_PROVIDER": llm_provider,
        "LLM_MODEL": llm_model.strip(),
        "EMBEDDING_PROVIDER": embed_provider,
        "EMBEDDING_MODEL": embed_model.strip(),
    }

    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if key in _current and _current[key]:
            new_values[key] = _current[key]

    if openai_key.strip():
        new_values["OPENAI_API_KEY"] = openai_key.strip()
    if anthropic_key.strip():
        new_values["ANTHROPIC_API_KEY"] = anthropic_key.strip()

    if openai_base_url.strip():
        new_values["OPENAI_BASE_URL"] = openai_base_url.strip()
    elif "OPENAI_BASE_URL" in _current and _current["OPENAI_BASE_URL"]:
        new_values["OPENAI_BASE_URL"] = _current["OPENAI_BASE_URL"]

    lines = []
    for k, v in new_values.items():
        if v:
            escaped = v.replace('"', '\\"')
            lines.append(f'{k}="{escaped}"')

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    st.success("Configurações salvas com sucesso em `.env`.")
    st.info(
        "As novas configurações serão aplicadas na próxima execução de análise ou vetorização."
    )

# ── Configuração atual (não sensível) ─────────────────────────────────────────
if env_file.exists() and _current:
    st.divider()
    st.markdown(
        f'<h3 style="margin-bottom:0.6rem;">Configuração atual</h3>',
        unsafe_allow_html=True,
    )
    display_rows = []
    for k, v in sorted(_current.items()):
        if k in _SENSITIVE_KEYS:
            display_rows.append({
                "Variável": k,
                "Valor": "••••••••••••" if v else "(não definido)",
            })
        else:
            display_rows.append({
                "Variável": k,
                "Valor": v if v else "(não definido)",
            })
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
elif not env_file.exists():
    st.info(
        "Arquivo `.env` não encontrado. "
        "Preencha as configurações acima e salve para criar o arquivo."
    )
