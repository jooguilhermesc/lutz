"""lutz init / project / status / load / library."""

from __future__ import annotations

from pathlib import Path

import click

from lutz.calibrated import piloto as pil
from lutz.cli.comum import abrir, console, erros, fmt, opcao_projeto, tabela
from lutz.core import codebook as cbk
from lutz.core.ingestao import importar_pdf, listar_pdfs
from lutz.core.inicializar import criar_projeto, info_projeto
from lutz.llm.cliente import consumo


def _criar(pasta: str, nome: str | None, pergunta: str, tipo: str) -> None:
    projeto = criar_projeto(Path(pasta), nome=nome, pergunta=pergunta, tipo_revisao=tipo)
    console.print(f"[green]Projeto criado em[/] {projeto.raiz}")
    console.print(
        "Próximos passos:\n"
        "  1. Ponha as chaves de API no [cyan].env[/] (ou use modelos locais do Docker Model Runner).\n"
        "  2. Ajuste os modelos E1, E2, E3 e V no [cyan]lutz.yaml[/] e rode [bold]lutz doctor[/].\n"
        "  3. Importe os PDFs: [bold]lutz load <pasta>[/].\n"
        "  4. Monte o codebook: [bold]lutz codebook new[/] ou [bold]lutz codebook import codebook.yaml[/]."
    )


@click.command("init")
@click.argument("pasta", default=".")
@click.option("--nome", default=None, help="Nome do projeto (padrão: nome da pasta).")
@click.option("--pergunta", default="", help="Pergunta de pesquisa.")
@click.option("--tipo", "tipo_revisao", default="sistematica",
              type=click.Choice(["sistematica", "escopo", "rapida", "outra"]), show_default=True)
@erros
def init(pasta, nome, pergunta, tipo_revisao):
    """Cria um projeto do Lutz na PASTA."""
    _criar(pasta, nome, pergunta, tipo_revisao)


@click.group("project")
def project():
    """Projeto: criar e ver."""


@project.command("new")
@click.argument("nome")
@click.option("--pergunta", default="", help="Pergunta de pesquisa.")
@click.option("--tipo", "tipo_revisao", default="sistematica",
              type=click.Choice(["sistematica", "escopo", "rapida", "outra"]), show_default=True)
@erros
def project_new(nome, pergunta, tipo_revisao):
    """Cria o projeto NOME numa pasta com esse nome."""
    _criar(nome, nome, pergunta, tipo_revisao)


@project.command("show")
@opcao_projeto
@erros
def project_show(projeto_dir):
    """Mostra o resumo do projeto (igual a 'lutz status')."""
    _status(projeto_dir)


def _status(projeto_dir):
    with abrir(projeto_dir) as (projeto, con):
        info = info_projeto(con)
        console.print(f"[bold]{info.get('nome')}[/]  ·  {projeto.raiz}")
        if info.get("pergunta"):
            console.print(f"Pergunta: {info['pergunta']}")
        cont = {r[0]: r[1] for r in con.execute("SELECT status, count(*) FROM artigo GROUP BY status")}
        console.print(f"Artigos: {sum(cont.values())} ({cont.get('pronto', 0)} prontos, "
                      f"{cont.get('sem_texto', 0)} sem texto)")
        cb = cbk.linha_codebook(con)
        if cb:
            console.print(f"Codebook: v{cb['versao']} · {cb['hash']} · "
                          f"{'congelado' if cb['congelado'] else 'rascunho'}")
        else:
            console.print("Codebook: nenhum")
        ex = [dict(r) for r in con.execute("SELECT id, tipo, status, conjunto_piloto FROM execucao ORDER BY id DESC LIMIT 5")]
        if ex:
            tabela(["Execução", "Tipo", "Status"], [[e["id"], e["tipo"] + (f" ({e['conjunto_piloto']})" if e["conjunto_piloto"] else ""),
                                                      e["status"]] for e in ex], "Execuções recentes")
        p = pil.atual(con)
        if p:
            console.print(f"Piloto: {p['id']} · {'sorteado' if p['sorteado_em'] else 'planejado'} · "
                          f"cegamento {'aberto' if p['cegamento_aberto'] else 'ativo'}")
        tot = consumo(con)["total"]
        console.print(f"Consumo: {tot['chamadas']} chamadas · US$ {fmt(tot['custo_usd'] or 0)}")


@click.command("status")
@opcao_projeto
@erros
def status(projeto_dir):
    """Resumo do projeto: artigos, codebook, execuções, piloto e custo."""
    _status(projeto_dir)


@click.command("load")
@click.argument("caminhos", nargs=-1, required=False, type=click.Path(exists=True))
@click.option("--f", "f_legado", default=None, type=click.Path(exists=True), hidden=True)
@opcao_projeto
@erros
def load(caminhos, f_legado, projeto_dir):
    """Importa PDFs (arquivos ou pastas): texto por página, ordem de leitura, unidades e seções."""
    alvos = list(caminhos) + ([f_legado] if f_legado else [])
    if not alvos:
        raise click.UsageError("Informe ao menos um arquivo ou pasta com PDFs.")
    with abrir(projeto_dir, escrita="lutz load") as (projeto, con):
        pdfs = listar_pdfs([Path(a) for a in alvos])
        if not pdfs:
            console.print("[yellow]Nenhum PDF encontrado.[/]")
            return
        linhas = []
        with console.status(f"Importando {len(pdfs)} PDF(s)…"):
            for p in pdfs:
                r = importar_pdf(projeto, con, p)
                linhas.append([Path(r.caminho).name, r.status, r.chave or "", r.mensagem])
        tabela(["Arquivo", "Resultado", "Chave", "Observação"], linhas)
        n = sum(1 for linha in linhas if linha[1] == "importado")
        console.print(f"{n} importado(s).")


@click.command("library")
@click.option("--status", "filtro", type=click.Choice(["pronto", "sem_texto", "erro"]), default=None)
@opcao_projeto
@erros
def library(filtro, projeto_dir):
    """Lista os artigos da biblioteca."""
    with abrir(projeto_dir) as (_, con):
        sql = "SELECT * FROM artigo" + (" WHERE status=?" if filtro else "") + " ORDER BY chave"
        linhas = []
        for a in con.execute(sql, (filtro,) if filtro else ()):
            import json

            linhas.append([a["chave"], (a["titulo"] or "")[:60], a["ano"] or "", a["n_paginas"],
                           "2 col" if a["duas_colunas"] else "1 col", ", ".join(json.loads(a["secoes"]))[:40],
                           a["n_tabelas"], f"{a['frac_oculto']:.1%}" if a["frac_oculto"] >= 0.001 else "", a["status"]])
        tabela(["Chave", "Título", "Ano", "Págs", "Layout", "Seções", "Tabelas", "Oculto", "Status"], linhas)
