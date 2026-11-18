"""SQLite storage: one ``lutz.db`` per project.

Schema versions are tracked with ``PRAGMA user_version`` and applied by numbered migrations.
Nothing is deleted by the pipeline: a new run creates new rows, so the history stays auditable.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from lutz.core.errors import ProjetoIncompativel
from lutz.core.project import Projeto

APP_ID = 0x4C55545A  # "LUTZ"

MIGRACOES: list[str] = [
    # ── 1: initial 1.0 schema ────────────────────────────────────────────────
    """
    CREATE TABLE projeto (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        nome TEXT NOT NULL,
        pergunta TEXT NOT NULL DEFAULT '',
        tipo_revisao TEXT NOT NULL DEFAULT 'sistematica',
        criado_em TEXT NOT NULL
    );

    CREATE TABLE artigo (
        id INTEGER PRIMARY KEY,
        chave TEXT NOT NULL UNIQUE,
        titulo TEXT NOT NULL DEFAULT '',
        autores TEXT NOT NULL DEFAULT '',
        ano INTEGER,
        revista TEXT NOT NULL DEFAULT '',
        hash_pdf TEXT NOT NULL UNIQUE,
        caminho_pdf TEXT NOT NULL,
        nome_original TEXT NOT NULL DEFAULT '',
        n_paginas INTEGER NOT NULL DEFAULT 0,
        n_chars INTEGER NOT NULL DEFAULT 0,
        tokens_estimados INTEGER NOT NULL DEFAULT 0,
        duas_colunas INTEGER NOT NULL DEFAULT 0,
        frac_oculto REAL NOT NULL DEFAULT 0,
        n_tabelas INTEGER NOT NULL DEFAULT 0,
        secoes TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL CHECK (status IN ('pronto','sem_texto','erro')),
        erro TEXT,
        importado_em TEXT NOT NULL
    );

    CREATE TABLE pagina (
        id INTEGER PRIMARY KEY,
        artigo_id INTEGER NOT NULL REFERENCES artigo(id),
        numero INTEGER NOT NULL,
        rotulo TEXT NOT NULL DEFAULT '',
        caminho_texto TEXT NOT NULL,
        caminho_texto_bruto TEXT NOT NULL,
        n_chars INTEGER NOT NULL DEFAULT 0,
        frac_oculto REAL NOT NULL DEFAULT 0,
        texto_oculto TEXT NOT NULL DEFAULT '',
        secao TEXT NOT NULL DEFAULT '',
        UNIQUE (artigo_id, numero)
    );

    -- Addressable text units: sentences and table rows, with a stable id per article.
    CREATE TABLE unidade (
        artigo_id INTEGER NOT NULL REFERENCES artigo(id),
        uid TEXT NOT NULL,
        pagina INTEGER NOT NULL,
        ordem INTEGER NOT NULL,
        tipo TEXT NOT NULL CHECK (tipo IN ('frase','linha_tabela')),
        secao TEXT NOT NULL DEFAULT '',
        texto TEXT NOT NULL,
        PRIMARY KEY (artigo_id, uid)
    );
    CREATE INDEX unidade_ordem ON unidade(artigo_id, ordem);

    CREATE TABLE codebook (
        id INTEGER PRIMARY KEY,
        versao INTEGER NOT NULL UNIQUE,
        hash TEXT NOT NULL,
        yaml TEXT NOT NULL,
        origem TEXT NOT NULL DEFAULT 'manual',
        congelado INTEGER NOT NULL DEFAULT 0,
        versao_anterior_id INTEGER REFERENCES codebook(id),
        nota TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL,
        congelado_em TEXT
    );

    CREATE TABLE campo (
        id INTEGER PRIMARY KEY,
        codebook_id INTEGER NOT NULL REFERENCES codebook(id),
        chave TEXT NOT NULL,
        rotulo TEXT NOT NULL,
        tipo TEXT NOT NULL,
        definicao TEXT NOT NULL,
        hash TEXT NOT NULL,
        origem TEXT NOT NULL DEFAULT 'manual',
        ordem INTEGER NOT NULL,
        UNIQUE (codebook_id, chave)
    );

    CREATE TABLE teste_rapido (
        id INTEGER PRIMARY KEY,
        artigo_id INTEGER NOT NULL REFERENCES artigo(id),
        campo_chave TEXT NOT NULL,
        execucao_id INTEGER REFERENCES execucao(id),
        criado_em TEXT NOT NULL
    );

    CREATE TABLE piloto (
        id INTEGER PRIMARY KEY,
        n_total INTEGER NOT NULL,
        n_ajuste INTEGER NOT NULL,
        n_validacao INTEGER NOT NULL,
        n_reserva INTEGER NOT NULL DEFAULT 0,
        estratos TEXT NOT NULL DEFAULT '',
        semente INTEGER NOT NULL,
        avaliadores TEXT NOT NULL DEFAULT '[]',
        plano TEXT NOT NULL,
        hash_plano TEXT NOT NULL,
        codebook_id INTEGER REFERENCES codebook(id),
        sorteado_em TEXT,
        cegamento_aberto INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE piloto_amostra (
        id INTEGER PRIMARY KEY,
        piloto_id INTEGER NOT NULL REFERENCES piloto(id),
        artigo_id INTEGER NOT NULL REFERENCES artigo(id),
        conjunto TEXT NOT NULL CHECK (conjunto IN ('ajuste','validacao','reserva')),
        estrato TEXT NOT NULL DEFAULT '',
        UNIQUE (piloto_id, artigo_id)
    );

    CREATE TABLE avaliador (
        id INTEGER PRIMARY KEY,
        nome TEXT NOT NULL UNIQUE,
        tipo TEXT NOT NULL CHECK (tipo IN ('humano','consenso'))
    );

    CREATE TABLE extracao_humana (
        id INTEGER PRIMARY KEY,
        piloto_id INTEGER NOT NULL REFERENCES piloto(id),
        avaliador_id INTEGER NOT NULL REFERENCES avaliador(id),
        artigo_id INTEGER NOT NULL REFERENCES artigo(id),
        campo_chave TEXT NOT NULL,
        campo_hash TEXT NOT NULL,
        valor TEXT,
        nao_reportado INTEGER NOT NULL DEFAULT 0,
        pagina INTEGER,
        importado_em TEXT NOT NULL,
        UNIQUE (piloto_id, avaliador_id, artigo_id, campo_chave)
    );

    CREATE TABLE execucao (
        id INTEGER PRIMARY KEY,
        tipo TEXT NOT NULL CHECK (tipo IN ('autonoma','piloto','teste')),
        codebook_id INTEGER NOT NULL REFERENCES codebook(id),
        piloto_id INTEGER REFERENCES piloto(id),
        conjunto_piloto TEXT CHECK (conjunto_piloto IN ('ajuste','validacao')),
        estrategia_diversidade TEXT NOT NULL,
        config TEXT NOT NULL,
        hash_config TEXT NOT NULL,
        hash_prompts TEXT NOT NULL,
        versao_lutz TEXT NOT NULL,
        artigos TEXT NOT NULL,
        campos TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('planejada','rodando','pausada','concluida','falhou')),
        motivo_status TEXT NOT NULL DEFAULT '',
        custo_estimado_usd REAL,
        criada_em TEXT NOT NULL,
        iniciada_em TEXT,
        atualizada_em TEXT,
        concluida_em TEXT
    );

    CREATE TABLE extrator (
        id INTEGER PRIMARY KEY,
        execucao_id INTEGER NOT NULL REFERENCES execucao(id),
        papel TEXT NOT NULL CHECK (papel IN ('extrator','verificador','juiz')),
        rotulo TEXT NOT NULL,
        provedor TEXT NOT NULL,
        modelo TEXT NOT NULL,
        temperatura REAL NOT NULL,
        max_tokens INTEGER NOT NULL,
        variante_prompt TEXT NOT NULL,
        UNIQUE (execucao_id, rotulo)
    );

    CREATE TABLE chamada_llm (
        id INTEGER PRIMARY KEY,
        execucao_id INTEGER REFERENCES execucao(id),
        papel TEXT NOT NULL,
        rotulo TEXT NOT NULL,
        artigo_id INTEGER REFERENCES artigo(id),
        grupo TEXT NOT NULL DEFAULT '',
        provedor TEXT NOT NULL,
        modelo_pedido TEXT NOT NULL,
        modelo_observado TEXT NOT NULL DEFAULT '',
        fingerprint TEXT NOT NULL DEFAULT '',
        tokens_entrada INTEGER NOT NULL DEFAULT 0,
        tokens_saida INTEGER NOT NULL DEFAULT 0,
        custo_usd REAL,
        latencia_ms INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL CHECK (status IN ('ok','erro','malformada')),
        erro TEXT NOT NULL DEFAULT '',
        tentativas INTEGER NOT NULL DEFAULT 1,
        cache INTEGER NOT NULL DEFAULT 0,
        hash_requisicao TEXT NOT NULL,
        requisicao TEXT NOT NULL,
        resposta TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL
    );
    CREATE INDEX chamada_hash ON chamada_llm(hash_requisicao, status);
    CREATE INDEX chamada_exec ON chamada_llm(execucao_id);

    CREATE TABLE celula (
        id INTEGER PRIMARY KEY,
        execucao_id INTEGER NOT NULL REFERENCES execucao(id),
        artigo_id INTEGER NOT NULL REFERENCES artigo(id),
        campo_id INTEGER NOT NULL REFERENCES campo(id),
        campo_chave TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'pendente'
            CHECK (estado IN ('pendente','extraida','verificada','consolidada','adjudicada')),
        valor_final TEXT,
        nao_reportado INTEGER NOT NULL DEFAULT 0,
        a REAL,
        e REAL,
        v REAL,
        escore REAL,
        nivel TEXT CHECK (nivel IN ('alta','media','baixa')),
        motivos TEXT NOT NULL DEFAULT '[]',
        regras_ok INTEGER,
        extrator_vencedor TEXT,
        trecho TEXT,
        pagina INTEGER,
        unidades TEXT NOT NULL DEFAULT '[]',
        v_justificativa TEXT NOT NULL DEFAULT '',
        origem TEXT NOT NULL DEFAULT 'maioria' CHECK (origem IN ('maioria','adjudicacao')),
        atualizada_em TEXT,
        UNIQUE (execucao_id, artigo_id, campo_id)
    );
    CREATE INDEX celula_nivel ON celula(execucao_id, nivel);

    CREATE TABLE extracao_bruta (
        id INTEGER PRIMARY KEY,
        celula_id INTEGER NOT NULL REFERENCES celula(id),
        rotulo TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('ok','falha')),
        valor TEXT,
        valor_normalizado TEXT,
        nao_reportado INTEGER NOT NULL DEFAULT 0,
        trecho TEXT,
        pagina INTEGER,
        unidades TEXT NOT NULL DEFAULT '[]',
        e REAL,
        e_detalhe TEXT NOT NULL DEFAULT '',
        regras_ok INTEGER,
        regras_detalhe TEXT NOT NULL DEFAULT '',
        erro TEXT NOT NULL DEFAULT '',
        chamada_id INTEGER REFERENCES chamada_llm(id),
        UNIQUE (celula_id, rotulo)
    );

    CREATE TABLE adjudicacao (
        id INTEGER PRIMARY KEY,
        celula_id INTEGER NOT NULL REFERENCES celula(id),
        motivo TEXT NOT NULL CHECK (motivo IN ('baixa','media','auditoria','manual')),
        valor_anterior TEXT,
        nao_reportado_anterior INTEGER NOT NULL DEFAULT 0,
        valor_decidido TEXT,
        nao_reportado INTEGER NOT NULL DEFAULT 0,
        alterou INTEGER NOT NULL,
        justificativa TEXT NOT NULL DEFAULT '',
        decidido_em TEXT NOT NULL
    );

    CREATE TABLE envio_manual (
        celula_id INTEGER PRIMARY KEY REFERENCES celula(id),
        nota TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL
    );

    CREATE TABLE auditoria (
        id INTEGER PRIMARY KEY,
        execucao_id INTEGER NOT NULL REFERENCES execucao(id),
        semente INTEGER NOT NULL,
        meia_largura_alvo REAL NOT NULL,
        n_alta INTEGER NOT NULL,
        n_amostra INTEGER NOT NULL,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE auditoria_item (
        id INTEGER PRIMARY KEY,
        auditoria_id INTEGER NOT NULL REFERENCES auditoria(id),
        celula_id INTEGER NOT NULL REFERENCES celula(id),
        correto INTEGER,
        valor_correto TEXT,
        nao_reportado_correto INTEGER,
        nota TEXT NOT NULL DEFAULT '',
        conferido_em TEXT,
        UNIQUE (auditoria_id, celula_id)
    );

    CREATE TABLE decisao_campo (
        id INTEGER PRIMARY KEY,
        piloto_id INTEGER NOT NULL REFERENCES piloto(id),
        execucao_id INTEGER NOT NULL REFERENCES execucao(id),
        campo_chave TEXT NOT NULL,
        metrica TEXT NOT NULL,
        valor REAL,
        ic_inf REAL,
        ic_sup REAL,
        decisao TEXT NOT NULL CHECK (decisao IN
            ('lutz_sozinho','revisar_media_baixa','reescrever','indefinida')),
        nota TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL,
        UNIQUE (piloto_id, execucao_id, campo_chave)
    );

    CREATE TABLE metrica (
        id INTEGER PRIMARY KEY,
        execucao_id INTEGER REFERENCES execucao(id),
        piloto_id INTEGER REFERENCES piloto(id),
        campo_chave TEXT,
        escopo TEXT NOT NULL,
        nome TEXT NOT NULL,
        valor REAL,
        ic_inf REAL,
        ic_sup REAL,
        n INTEGER,
        par TEXT NOT NULL DEFAULT '',
        nota TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL
    );
    CREATE INDEX metrica_exec ON metrica(execucao_id, escopo);

    CREATE TABLE relatorio (
        id INTEGER PRIMARY KEY,
        execucao_id INTEGER NOT NULL REFERENCES execucao(id),
        idioma TEXT NOT NULL,
        formato TEXT NOT NULL,
        caminho TEXT NOT NULL,
        hash TEXT NOT NULL,
        gerado_em TEXT NOT NULL
    );
    """,
]

VERSAO_SCHEMA = len(MIGRACOES)


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar(projeto: Projeto, *, criar: bool = False) -> sqlite3.Connection:
    """Open the project database, applying pending migrations.

    Refuses a database whose schema version is newer than this Lutz or that does not belong
    to Lutz 1.x (for example the chat database of 0.5.x).
    """
    existe = projeto.db.exists()
    if not existe and not criar:
        raise ProjetoIncompativel(
            f"Banco {projeto.db} não encontrado. O projeto foi criado com 'lutz init'?"
        )
    con = sqlite3.connect(projeto.db, timeout=30, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys=ON")
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    app_id = con.execute("PRAGMA application_id").fetchone()[0]
    if versao > 0 and app_id != APP_ID:
        con.close()
        raise ProjetoIncompativel(f"{projeto.db} não é um banco do Lutz 1.x.")
    if versao == 0:
        tabelas = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        if tabelas:
            con.close()
            raise ProjetoIncompativel(
                f"{projeto.db} tem tabelas desconhecidas (projeto 0.5.x?). O Lutz 1.0 não o lê."
            )
    if versao > VERSAO_SCHEMA:
        con.close()
        raise ProjetoIncompativel(
            f"O banco usa o esquema {versao}, mais novo que o deste Lutz ({VERSAO_SCHEMA}). "
            "Atualize o Lutz."
        )
    for numero in range(versao, VERSAO_SCHEMA):
        con.execute("BEGIN")
        try:
            for stmt in _split(MIGRACOES[numero]):
                con.execute(stmt)
            con.execute(f"PRAGMA user_version={numero + 1}")
            con.execute(f"PRAGMA application_id={APP_ID}")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            con.close()
            raise
    return con


def _split(script: str) -> list[str]:
    """Split a migration script into statements (no semicolons inside our DDL strings)."""
    partes = []
    atual: list[str] = []
    for linha in script.splitlines():
        if linha.strip().startswith("--"):
            continue
        atual.append(linha)
        if linha.rstrip().endswith(";"):
            stmt = "\n".join(atual).strip()
            if stmt:
                partes.append(stmt)
            atual = []
    resto = "\n".join(atual).strip()
    if resto:
        partes.append(resto)
    return partes


@contextmanager
def transacao(con: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def linhas(cur: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in cur]


def um(con: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    r = con.execute(sql, tuple(params)).fetchone()
    return dict(r) if r is not None else None


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def jload(texto: str | None, padrao: Any = None) -> Any:
    if texto is None or texto == "":
        return padrao
    return json.loads(texto)
