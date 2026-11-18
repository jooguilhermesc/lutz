"""lutz adjudicate / audit."""

from __future__ import annotations

from pathlib import Path

import click

from lutz.calibrated import piloto as pil
from lutz.cli.comum import abrir, console, erros, fmt, opcao_projeto, settings_de, tabela
from lutz.core.errors import LutzError
from lutz.revisao import adjudicacao as adj
from lutz.revisao import auditoria as aud


def _ultima_execucao(con, execucao_id):
    if execucao_id:
        return execucao_id
    r = con.execute("SELECT id FROM execucao WHERE tipo='autonoma' AND status='concluida' ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        r = con.execute("SELECT id FROM execucao WHERE tipo!='teste' AND status='concluida' ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        raise LutzError("Nenhuma execução concluída.")
    return r[0]


opcao_exec = click.option("--execucao", "execucao_id", type=int, default=None,
                          help="Padrão: a última execução autônoma concluída.")


@click.group("adjudicate")
def adjudicate():
    """Adjudicação: decisão humana sobre as células duvidosas."""


@adjudicate.command("queue")
@opcao_exec
@click.option("--limite", default=30, show_default=True)
@opcao_projeto
@erros
def queue(execucao_id, limite, projeto_dir):
    """Mostra a fila, da pior para a melhor célula."""
    with abrir(projeto_dir) as (_, con):
        eid = _ultima_execucao(con, execucao_id)
        f = adj.fila(con, eid, ocultos=pil.artigos_ocultos(con))
        tabela(["Célula", "Artigo", "Campo", "Nível", "Escore", "Valor", "Motivo"],
               [[c["id"], c["chave"], c["campo_chave"], c["nivel"], fmt(c["escore"]),
                 "não reportado" if c["nao_reportado"] else (c["valor_final"] or "—"),
                 "; ".join(c["motivos"])[:80]] for c in f[:limite]],
               f"Fila de adjudicação da execução {eid}: {len(f)} célula(s)")


@adjudicate.command("decide")
@click.argument("celula_id", type=int)
@click.option("--valor", default=None)
@click.option("--nao-reportado", is_flag=True)
@click.option("--aceitar", is_flag=True, help="Aceita o valor proposto pelo Lutz.")
@click.option("--justificativa", default="")
@opcao_projeto
@erros
def decide(celula_id, valor, nao_reportado, aceitar, justificativa, projeto_dir):
    """Registra a decisão sobre uma célula."""
    with abrir(projeto_dir, escrita="lutz adjudicate decide") as (_, con):
        if aceitar:
            cel = con.execute("SELECT valor_final, nao_reportado FROM celula WHERE id=?", (celula_id,)).fetchone()
            if cel is None:
                raise LutzError(f"Célula {celula_id} não existe.")
            valor, nao_reportado = cel[0], bool(cel[1])
            if valor is None and not nao_reportado:
                raise LutzError("Não há valor do Lutz para aceitar (empate). Informe --valor.")
        if not valor and not nao_reportado:
            raise click.UsageError("Informe --valor, --nao-reportado ou --aceitar.")
        c = adj.decidir(con, celula_id, valor=None if nao_reportado else valor, nao_reportado=nao_reportado,
                        justificativa=justificativa)
    console.print(f"Célula {celula_id}: {'não reportado' if c['nao_reportado'] else c['valor_final']}")


@adjudicate.command("export")
@opcao_exec
@click.option("-o", "--saida", default=None)
@click.option("--sep", default=",", show_default=True)
@opcao_projeto
@erros
def exportar(execucao_id, saida, sep, projeto_dir):
    """Exporta a fila para CSV (planilha)."""
    with abrir(projeto_dir) as (projeto, con):
        eid = _ultima_execucao(con, execucao_id)
        destino = Path(saida) if saida else projeto.exports / f"adjudicacao_{eid:04d}.csv"
        n = adj.exportar_csv(con, eid, destino, sep=sep, ocultos=pil.artigos_ocultos(con))
    console.print(f"{n} célula(s) em {destino}\n{adj.INSTRUCOES_CSV}")


@adjudicate.command("import")
@click.argument("arquivo", type=click.Path(exists=True))
@opcao_projeto
@erros
def importar(arquivo, projeto_dir):
    """Importa as decisões preenchidas na planilha."""
    with abrir(projeto_dir, escrita="lutz adjudicate import") as (_, con):
        r = adj.importar_csv(con, Path(arquivo))
    console.print(f"{r['aplicadas']} decisão(ões) aplicada(s), {r['ignoradas']} linha(s) em branco.")
    for e in r["erros"]:
        console.print(f"[red]linha {e['linha']}: {e['erro']}[/]")


@click.group("audit")
def audit():
    """Auditoria das células Alta (amostra aleatória conferida à mão)."""


@audit.command("sample")
@opcao_exec
@click.option("--n", type=int, default=None, help="Tamanho da amostra (padrão: calculado pelo IC de Wilson).")
@click.option("--fracao", type=float, default=None, help="Fração das células Alta (ex.: 0.05).")
@opcao_projeto
@erros
def sample(execucao_id, n, fracao, projeto_dir):
    """Sorteia a amostra de células Alta a conferir."""
    with abrir(projeto_dir, escrita="lutz audit sample") as (projeto, con):
        eid = _ultima_execucao(con, execucao_id)
        if fracao:
            n_alta = con.execute("SELECT count(*) FROM celula WHERE execucao_id=? AND nivel='alta'", (eid,)).fetchone()[0]
            n = max(1, round(n_alta * fracao))
        a = aud.criar(con, eid, settings_de(projeto), n=n, ocultos=pil.artigos_ocultos(con))
        destino = projeto.exports / f"auditoria_{eid:04d}.csv"
        aud.exportar_csv(con, a["id"], destino)
    console.print(f"Amostra de {a['n_amostra']} célula(s) Alta (de {a['n_alta']}), semente {a['semente']}. "
                  f"Planilha: {destino}. Preencha 'correto' (sim/nao) e importe com 'lutz audit import'.")


@audit.command("import")
@click.argument("arquivo", type=click.Path(exists=True))
@opcao_projeto
@erros
def importar_aud(arquivo, projeto_dir):
    """Importa a conferência da auditoria."""
    with abrir(projeto_dir, escrita="lutz audit import") as (_, con):
        r = aud.importar_csv(con, Path(arquivo))
    console.print(f"{r['aplicadas']} item(ns) registrado(s).")
    for e in r["erros"]:
        console.print(f"[red]linha {e['linha']}: {e['erro']}[/]")


@audit.command("status")
@opcao_exec
@opcao_projeto
@erros
def status_aud(execucao_id, projeto_dir):
    """Resultado da auditoria."""
    with abrir(projeto_dir) as (_, con):
        eid = _ultima_execucao(con, execucao_id)
        r = aud.resultado(con, eid)
    if r is None:
        console.print("Auditoria não iniciada. Rode 'lutz audit sample'.")
        return
    console.print(f"{r['conferidas']}/{r['n_amostra']} conferidas · {r['acertos']} corretas · acerto "
                  f"{fmt((r['taxa'] or 0) * 100, 1)}% (IC95% {fmt((r['ic_inf'] or 0) * 100, 1)}–{fmt((r['ic_sup'] or 0) * 100, 1)}%)")
