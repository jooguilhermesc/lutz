"""lutz extract / results."""

from __future__ import annotations

import csv
from pathlib import Path

import click
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from lutz.calibrated import piloto as pil
from lutz.cli.comum import abrir, console, erros, fmt, lista_opcao, opcao_projeto, settings_de, tabela
from lutz.config.settings import carregar_settings
from lutz.core.db import jload
from lutz.core.errors import LutzError
from lutz.extraction import executor as ex
from lutz.extraction.metricas_autonomo import metricas
from lutz.report.gerar import tabela_larga, tabela_longa


def _mostrar_estimativa(est: dict) -> None:
    linhas = [[d["rotulo"], d["provedor"], d["modelo"], d["chamadas"], f"{d['tokens_entrada']:,}",
               f"{d['tokens_saida']:,}", "?" if d.get("custo_usd") is None else f"US$ {d['custo_usd']:.4f}"]
              for d in est["por_papel"]]
    tabela(["Papel", "Provedor", "Modelo", "Chamadas", "Tokens entrada", "Tokens saída", "Custo"], linhas,
           f"Estimativa: {est['artigos']} artigos × {est['campos']} campos")
    custo = "desconhecido (preço não cadastrado para " + ", ".join(est["sem_preco"]) + ")" if est["sem_preco"] \
        else f"US$ {est['custo_usd']:.4f}"
    console.print(f"Custo estimado: {custo} · em cache: {est['em_cache']} chamada(s) · "
                  f"gasto do projeto: US$ {est['gasto_projeto_usd']:.4f}"
                  + (f" de US$ {est['orcamento_usd']:.2f}" if est["orcamento_usd"] is not None else ""))
    if est["excedem_contexto"]:
        console.print(f"[yellow]Excedem a janela de contexto: {', '.join(est['excedem_contexto'])}[/]")
    if not est["cabe_no_orcamento"]:
        console.print("[red]A estimativa ultrapassa o orçamento; a execução vai pausar ao atingi-lo.[/]")


def _rodar(projeto, eid: int) -> dict:
    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as prog:
        tarefa = prog.add_task("Artigos", total=None)

        def cb(ev):
            if ev["tipo"] == "inicio":
                prog.update(tarefa, total=ev["pendentes"])
            elif ev["tipo"] == "artigo":
                prog.advance(tarefa)
            elif ev["tipo"] == "falha":
                prog.console.print(f"[yellow]{ev['artigo']} {ev['extrator']}: {ev['erro']}[/]")
            elif ev["tipo"] == "pausa":
                prog.console.print(f"[yellow]Pausada: {ev['motivo']}[/]")

        return ex.executar(projeto, eid, progresso=cb)


def _resumo(res: dict) -> None:
    n = res["niveis"]
    console.print(f"Execução {res['id']}: [bold]{res['status']}[/]"
                  + (f" ({res['motivo']})" if res["motivo"] else ""))
    console.print(f"Células prontas: {res['celulas_prontas']}/{res['celulas']} · Alta {n.get('alta', 0)} · "
                  f"Média {n.get('media', 0)} · Baixa {n.get('baixa', 0)} · custo US$ {res['custo_usd']:.4f} "
                  f"({res['chamadas']} chamadas, {res['chamadas_cache']} em cache)")
    if res["status"] == "pausada":
        console.print(f"Para continuar: [bold]lutz extract --retomar {res['id']}[/]")


@click.group("extract", invoke_without_command=True)
@click.option("--campos", default=None, help="Subconjunto de campos (vírgulas).")
@click.option("--artigos", default=None, help="Subconjunto de artigos (chaves, vírgulas).")
@click.option("--piloto", "conjunto", type=click.Choice(["ajuste", "validacao"]), default=None,
              help="Roda no conjunto do piloto atual.")
@click.option("--codebook", "versao", type=int, default=None, help="Versão congelada (padrão: a última).")
@click.option("--retomar", type=int, default=None, metavar="ID", help="Continua uma execução pausada.")
@click.option("--estimar", "so_estimar", is_flag=True, help="Só mostra a estimativa de custo.")
@click.option("--sim", "-y", "confirmar", is_flag=True, help="Não pede confirmação.")
@click.option("--forcar", is_flag=True, help="Permite repetir a validação do piloto (fica registrado).")
@click.option("--extratores", type=int, default=3, hidden=True)
@opcao_projeto
@click.pass_context
@erros
def extract(ctx, campos, artigos, conjunto, versao, retomar, so_estimar, confirmar, forcar, extratores, projeto_dir):
    """Modo Autônomo: três extratores independentes, evidência, verificador, regras e níveis."""
    if ctx.invoked_subcommand:
        return
    if extratores != 3:
        raise click.UsageError("O Lutz 1.0 usa sempre três extratores (E1, E2, E3), configurados no lutz.yaml.")
    with abrir(projeto_dir, escrita="lutz extract") as (projeto, con):
        if retomar:
            eid = retomar
            ex.reparar_interrompidas(con)
            r = con.execute("SELECT status, hash_config FROM execucao WHERE id=?", (eid,)).fetchone()
            if r is None:
                raise LutzError(f"Execução {eid} não existe.")
            if r["hash_config"] != carregar_settings(projeto).hash()[:16]:
                console.print("[yellow]O lutz.yaml mudou desde o planejamento; a execução continua com a "
                              "configuração registrada nela.[/]")
        else:
            s = settings_de(projeto)
            p = pil.atual(con) if conjunto else None
            if conjunto and p is None:
                raise LutzError("Não há piloto. Use 'lutz pilot plan' e 'lutz pilot sample'.")
            eid = ex.planejar(projeto, con, s, codebook_versao=versao, campos=lista_opcao(campos),
                              artigos=lista_opcao(artigos), piloto_id=p["id"] if p else None, conjunto=conjunto,
                              forcar=forcar)
        est = ex.estimar(projeto, con, eid)
        _mostrar_estimativa(est)
        if so_estimar:
            console.print(f"Execução {eid} planejada, não iniciada. Rode 'lutz extract --retomar {eid}' para executar.")
            return
        s = carregar_settings(projeto)
        if s.custo.confirmar and not confirmar and not click.confirm("Iniciar a extração?", default=True):
            ex.pausar(con, eid)
            console.print(f"Execução {eid} não iniciada.")
            return
        res = _rodar(projeto, eid)
        _resumo(res)
        if res["status"] == "concluida" and res["tipo"] != "teste":
            _metricas_tabela(con, eid)


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def _metricas_tabela(con, eid: int) -> None:
    m = metricas(con, eid)
    linhas = []
    for campo, d in m.items():
        if campo is None:
            continue
        a = d.get("alfa")
        u = d.get("unanimes")
        linhas.append([campo, f"{fmt(a['valor'])} ({fmt(a['ic_inf'])}–{fmt(a['ic_sup'])})" if a else "—",
                       f"{fmt(u['valor'] * 100, 0)}%" if u and u["valor"] is not None else "—",
                       " · ".join(f"{k[0].upper()} {fmt((d.get(f'pct_{k}') or {}).get('valor', 0) * 100, 0)}%"
                                  for k in ("alta", "media", "baixa")),
                       _pct((d.get("pct_evidencia_exata") or {}).get("valor")),
                       f"{fmt((d.get('pct_nao_reportado') or {}).get('valor', 0) * 100, 0)}%"
                       + (" ⚠" if (d.get("pct_nao_reportado") or {}).get("nota") else "")])
    tabela(["Campo", "α (IC95%)", "Unânimes", "Níveis", "Evid. exata", "Não rep."], linhas,
           "Confiabilidade por campo (consistência, não acerto)")


@extract.command("list")
@opcao_projeto
@erros
def listar(projeto_dir):
    """Lista as execuções."""
    with abrir(projeto_dir) as (_, con):
        linhas = []
        for r in con.execute("SELECT id FROM execucao ORDER BY id"):
            s = ex.resumo(con, r[0])
            linhas.append([s["id"], s["tipo"] + (f" ({s['conjunto']})" if s["conjunto"] else ""), s["status"],
                           f"{s['celulas_prontas']}/{s['celulas']}", s["niveis"].get("alta", 0),
                           s["niveis"].get("media", 0), s["niveis"].get("baixa", 0), f"{s['custo_usd']:.4f}",
                           s["criada_em"]])
    tabela(["ID", "Tipo", "Status", "Células", "Alta", "Média", "Baixa", "US$", "Criada"], linhas)


@extract.command("status")
@click.argument("execucao_id", type=int)
@opcao_projeto
@erros
def status(execucao_id, projeto_dir):
    """Progresso, custo e métricas de uma execução."""
    with abrir(projeto_dir) as (_, con):
        _resumo(ex.resumo(con, execucao_id))
        if con.execute("SELECT 1 FROM metrica WHERE execucao_id=?", (execucao_id,)).fetchone():
            _metricas_tabela(con, execucao_id)


@extract.command("pause")
@click.argument("execucao_id", type=int)
@opcao_projeto
@erros
def pause(execucao_id, projeto_dir):
    """Pede a pausa de uma execução em andamento (vale também para a interface web)."""
    with abrir(projeto_dir) as (_, con):
        ex.pausar(con, execucao_id)
    console.print(f"Pausa solicitada para a execução {execucao_id}.")


@extract.command("recompute")
@click.argument("execucao_id", type=int)
@click.option("--limiares-atuais", is_flag=True, help="Usa os limiares do lutz.yaml atual (registrado na execução).")
@opcao_projeto
@erros
def recompute(execucao_id, limiares_atuais, projeto_dir):
    """Recalcula evidência, regras, níveis e métricas a partir das respostas gravadas, sem chamar modelos."""
    with abrir(projeto_dir, escrita="lutz extract recompute") as (projeto, _):
        res = ex.recalcular(projeto, execucao_id,
                            usar_limiares_atuais=carregar_settings(projeto) if limiares_atuais else None)
    _resumo(res)


@click.command("results")
@click.option("--execucao", "execucao_id", type=int, default=None, help="Padrão: a última execução autônoma concluída.")
@click.option("--formato", type=click.Choice(["longo", "largo"]), default="largo", show_default=True)
@click.option("-o", "--saida", default=None, help="CSV de saída (padrão: exports/resultados_<id>_<formato>.csv).")
@click.option("--sep", default=",", show_default=True, help="Separador do CSV.")
@opcao_projeto
@erros
def results(execucao_id, formato, saida, sep, projeto_dir):
    """Exporta a tabela de extração com nível de confiança e evidência."""
    with abrir(projeto_dir) as (projeto, con):
        if execucao_id is None:
            r = con.execute("SELECT id FROM execucao WHERE tipo!='teste' AND status='concluida' ORDER BY id DESC LIMIT 1").fetchone()
            if r is None:
                raise LutzError("Nenhuma execução concluída.")
            execucao_id = r[0]
        ocultos = pil.artigos_ocultos(con) & set(jload(con.execute("SELECT artigos FROM execucao WHERE id=?",
                                                                   (execucao_id,)).fetchone()[0]))
        if ocultos:
            raise LutzError("Há artigos do piloto cego nesta execução; importe as planilhas humanas antes de exportar.")
        cab, linhas = (tabela_larga if formato == "largo" else tabela_longa)(con, execucao_id)
        destino = Path(saida) if saida else projeto.exports / f"resultados_{execucao_id:04d}_{formato}.csv"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=sep)
            w.writerow(cab)
            w.writerows([["" if x is None else x for x in linha] for linha in linhas])
    console.print(f"{len(linhas)} linhas em {destino}")
