"""Lutz — Configuração de variáveis de ambiente."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _utils import find_project_root

st.set_page_config(page_title="Lutz — Configurações", layout="wide")
st.title("Configurações")
st.caption(
    "Configure os provedores de LLM e embeddings e as chaves de API do projeto. "
    "As credenciais são armazenadas **somente** no arquivo `.env` do projeto "
    "e nunca são expostas na interface."
)

project_root = find_project_root()
if project_root is None:
    st.error("Nenhum projeto Lutz encontrado.")
    st.stop()

env_file = project_root / ".env"

# Carrega valores atuais (somente do .env, não de os.environ)
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
    st.subheader("Provedor de LLM")
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

    st.subheader("Provedor de Embeddings")
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

    st.subheader("Chaves de API")
    st.caption(
        "Deixe em branco para manter o valor atual sem alterações. "
        "Os campos são mascarados e os valores não ficam visíveis após o salvamento."
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

    st.subheader("Configurações avançadas")
    openai_base_url = st.text_input(
        "OPENAI_BASE_URL (opcional)",
        value=_current.get("OPENAI_BASE_URL", ""),
        placeholder="https://openrouter.ai/api/v1",
        help="URL base da API OpenAI-compatível. "
             "Use para OpenRouter ou outros provedores compatíveis. "
             "Deixe em branco para usar a API padrão da OpenAI.",
    )

    submitted = st.form_submit_button("Salvar Configurações", type="primary")

if submitted:
    # Constrói o novo .env com apenas as chaves conhecidas e seguras
    new_values: dict[str, str] = {
        "LLM_PROVIDER": llm_provider,
        "LLM_MODEL": llm_model.strip(),
        "EMBEDDING_PROVIDER": embed_provider,
        "EMBEDDING_MODEL": embed_model.strip(),
    }

    # Preserva chaves de API existentes se não foram fornecidas novas
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

    # Escreve apenas valores não vazios, escapando aspas duplas
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

# --- Configuração atual (não sensível) ---
if env_file.exists() and _current:
    st.divider()
    st.subheader("Configuração atual")
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
