"""lutz pilot ..."""

from __future__ import annotations

from pathlib import Path

import click

from lutz.calibrated import piloto as pil
from lutz.cli.comum import abrir, console, erros, fmt, opcao_projeto, settings_de, tabela
from lutz.core import metricas as M
from lutz.core.db import jload
from lutz.core.errors import LutzError


@click.group("pilot")
def pilot():
    """Modo Calibrado: piloto cego com avaliadores humanos."""


@pilot.command("plan")
@click.option("--n", "n_total", type=int, default=30, show_default=True, help="Artigos de ajuste + validação.")
@click.option("--ajuste", type=int, default=10, show_default=True)
@click.option("--reserva", type=int, default=0, show_default=True, help="Bloco reserva de validação.")
@click.option("--estratos", type=click.Choice(["", "ano", "revista"]), default="")
@click.option("--avaliadores", default="A,B", show_default=True, help="Um ou dois nomes, separados por vírgula.")
@opcao_projeto
@erros
def plan(n_total, ajuste, reserva, estratos, avaliadores, projeto_dir):
    """Mostra a tabela de tamanho do piloto e pré-registra o plano (com hash)."""
    tabela(["Artigos", "Erro padrão", "Meia largura do IC95%"],
           [[r["n"], fmt(r["erro_padrao"]), f"±{fmt(r['meia_largura'])}"] for r in M.tabela_tamanho_piloto()],
           "Largura do IC95% do kappa (p_o = 0,90; p_e = 0,50)")
    with abrir(projeto_dir, escrita="lutz pilot plan") as (projeto, con):
        n_corpus = con.execute("SELECT count(*) FROM artigo WHERE status='pronto'").fetchone()[0]
        for a in pil.avisos_plano(n_corpus, n_total - ajuste):
            console.print(f"[yellow]{a}[/]")
        p = pil.planejar(con, settings_de(projeto), n_ajuste=ajuste, n_validacao=n_total - ajuste,
                         n_reserva=reserva, estratos=estratos,
                         avaliadores=[a.strip() for a in avaliadores.split(",") if a.strip()])
    console.print(f"Plano {p['id']} registrado · hash {p['hash_plano']} · {ajuste} ajuste + {n_total - ajuste} "
                  f"validação + {reserva} reserva. Próximo passo: 'lutz pilot sample'.")


@pilot.command("sample")
@click.option("--n", "n_total", type=int, default=None, help="Atalho: planeja e sorteia de uma vez.")
@click.option("--ajuste", type=int, default=10)
@click.option("--seed", type=int, default=None, help="Semente (padrão: sementes.piloto do lutz.yaml).")
@click.option("--estratos", type=click.Choice(["", "ano", "revista"]), default="")
@click.option("--avaliadores", default="A,B")
@opcao_projeto
@erros
def sample(n_total, ajuste, seed, estratos, avaliadores, projeto_dir):
    """Sorteia a amostra do piloto e gera as planilhas em branco (sem respostas do Lutz)."""
    with abrir(projeto_dir, escrita="lutz pilot sample") as (projeto, con):
        s = settings_de(projeto)
        if seed is not None:
            s = s.model_copy(update={"sementes": s.sementes.model_copy(update={"piloto": seed})})
        p = pil.atual(con)
        if n_total is not None or p is None or p["sorteado_em"]:
            if n_total is None:
                raise LutzError("Planeje o piloto ('lutz pilot plan') ou informe --n.")
            p = pil.planejar(con, s, n_ajuste=ajuste, n_validacao=n_total - ajuste, estratos=estratos,
                             avaliadores=[a.strip() for a in avaliadores.split(",") if a.strip()])
        r = pil.sortear(con, p["id"])
        pasta = projeto.exports / "piloto"
        for av in jload(p["avaliadores"]):
            pil.exportar_planilha(con, p["id"], av, pasta / f"humano_{av}.csv")
    console.print(f"Sorteio com semente {p['semente']}: {r['ajuste']} ajuste, {r['validacao']} validação, "
                  f"{r['reserva']} reserva ({r['excluidos_teste_rapido']} artigo(s) do teste rápido excluídos).")
    console.print(f"Planilhas em branco em {pasta}. As respostas do Lutz para esses artigos ficam ocultas "
                  "até a importação.")


@pilot.command("import")
@click.argument("arquivo", type=click.Path(exists=True))
@click.option("--avaliador", required=True)
@opcao_projeto
@erros
def importar(arquivo, avaliador, projeto_dir):
    """Importa a planilha preenchida por um avaliador."""
    with abrir(projeto_dir, escrita="lutz pilot import") as (_, con):
        p = pil.atual(con)
        r = pil.importar_planilha(con, p["id"], avaliador, Path(arquivo))
    if r["erros"]:
        for e in r["erros"][:50]:
            console.print(f"[red]linha {e['linha']}: {e['erro']}[/]")
        raise click.ClickException(f"{len(r['erros'])} erro(s); nada foi importado.")
    console.print(f"{r['gravadas']} célula(s) importada(s) do avaliador {avaliador}.")
    if r["faltando"]:
        console.print(f"[yellow]Artigos da amostra ausentes na planilha: {', '.join(r['faltando'])}[/]")


@pilot.command("consensus")
@click.option("--importar", "arquivo", default=None, type=click.Path(exists=True),
              help="Importa o consenso preenchido.")
@opcao_projeto
@erros
def consensus(arquivo, projeto_dir):
    """Gera (ou importa) a planilha de consenso entre os dois avaliadores."""
    with abrir(projeto_dir, escrita="lutz pilot consensus") as (projeto, con):
        p = pil.atual(con)
        s = settings_de(projeto)
        if arquivo:
            r = pil.importar_consenso(con, p["id"], Path(arquivo), s)
            if r["erros"]:
                for e in r["erros"][:50]:
                    console.print(f"[red]{e['erro']}[/]")
                raise click.ClickException("Consenso incompleto; nada foi gravado.")
            console.print(f"Consenso gravado ({r['gravadas']} células): é o padrão-ouro do piloto.")
            return
        destino = projeto.exports / "piloto" / "consenso.csv"
        r = pil.exportar_consenso(con, p["id"], destino, s)
    console.print(f"{r['divergentes']} divergência(s) em {destino}. Preencha consenso_valor ou "
                  "consenso_nao_reportado e rode 'lutz pilot consensus --importar <arquivo>'.")


@pilot.command("compare")
@click.option("--conjunto", type=click.Choice(["ajuste", "validacao"]), default="validacao", show_default=True)
@opcao_projeto
@erros
def compare(conjunto, projeto_dir):
    """Compara o Lutz com o padrão-ouro: κ, κ ponderado ou ICC por campo, decisão e calibração."""
    with abrir(projeto_dir, escrita="lutz pilot compare") as (projeto, con):
        p = pil.atual(con)
        r = pil.comparar(con, p["id"], conjunto, settings_de(projeto))
    linhas = []
    for c in r["campos"]:
        m, hh = c["lutz_ouro"], c["humano_humano"]
        linhas.append([c["campo"], c["tipo"], m["metrica"], fmt(m["valor"]), f"{fmt(m['ic'][0])}–{fmt(m['ic'][1])}",
                       fmt(hh["valor"]) if hh else "—", f"{fmt(m['pct_concordancia'] * 100, 0)}%",
                       c["decisao"] or "—", "; ".join(filter(None, [c["nota"], *m["notas"]]))])
    tabela(["Campo", "Tipo", "Métrica", "Valor", "IC95%", "Hum×hum", "Conc.", "Decisão", "Notas"], linhas,
           f"Lutz × {r['padrao_ouro']} · conjunto {conjunto} (execução {r['execucao_id']})")
    tabela(["Nível", "Células", "Acertos", "Taxa", "IC95% Wilson"],
           [[n["nivel"], n["n"], n["acertos"], f"{fmt((n['taxa'] or 0) * 100, 1)}%",
             f"{fmt((n['ic_inf'] or 0) * 100, 1)}–{fmt((n['ic_sup'] or 0) * 100, 1)}%"] for n in r["niveis"]],
           "Calibração dos níveis")
    for a in r["avisos"]:
        console.print(f"[yellow]{a}[/]")
    if conjunto == "ajuste":
        console.print("Métricas do conjunto de ajuste não vão para o relatório. Ajuste as instruções, congele uma "
                      "nova versão e rode 'lutz extract --piloto ajuste' de novo, ou siga para a validação.")


@pilot.command("status")
@opcao_projeto
@erros
def status(projeto_dir):
    """Etapas do piloto."""
    with abrir(projeto_dir) as (_, con):
        st = pil.estado(con)
    if st is None:
        console.print("Nenhum piloto. Comece com 'lutz pilot plan'.")
        return
    p = st["piloto"]
    console.print(f"Piloto {p['id']} · plano {p['hash_plano']} · semente {p['semente']} · "
                  f"{'sorteado' if p['sorteado_em'] else 'não sorteado'} · cegamento "
                  f"{'aberto' if p['cegamento_aberto'] else 'ativo'}")
    console.print(f"Amostra: {st['amostra']}")
    for av, cob in (st["cobertura"] or {}).items():
        if cob:
            console.print(f"Avaliador {av}: {cob['feito']}/{cob['esperado']} células")
    console.print(f"Consenso: {'sim' if st['consenso'] else 'não'}")
    for r in st["rodadas"]:
        console.print(f"Execução {r['id']} · {r['conjunto_piloto']} · codebook v{r['versao']} · {r['status']}")
    if st["decisoes"]:
        tabela(["Campo", "Métrica", "Valor", "Decisão"],
               [[d["campo_chave"], d["metrica"], fmt(d["valor"]), d["decisao"]] for d in st["decisoes"]])
