"""lutz codebook ..."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from lutz.cli.comum import abrir, console, erros, opcao_projeto, settings_de, tabela
from lutz.core import assistente
from lutz.core import codebook as cbk
from lutz.core.lock import bloqueio
from lutz.extraction import executor as ex


@click.group("codebook")
def codebook():
    """Codebook: criar, checar, testar, congelar e versionar o formulário de extração."""


def _mostrar_lint(achados):
    if not achados:
        console.print("[green]Lint: nenhum problema encontrado.[/]")
        return
    cor = {"erro": "red", "aviso": "yellow", "sugestao": "cyan"}
    tabela(["Campo", "Código", "Severidade", "Mensagem"],
           [[a["campo"] or "-", a["codigo"], f"[{cor.get(a['severidade'], 'white')}]{a['severidade']}[/]",
             a["mensagem"]] for a in achados])


@codebook.command("check")
@click.argument("arquivo", required=False, type=click.Path(exists=True))
@click.option("--semantico", is_flag=True, help="Também roda o lint semântico por LLM (gasta tokens).")
@opcao_projeto
@erros
def check(arquivo, semantico, projeto_dir):
    """Valida o codebook (ARQUIVO YAML ou a versão atual do projeto)."""
    if arquivo:
        cb = cbk.ler_yaml(Path(arquivo).read_text(encoding="utf-8"))
        achados = cbk.lint(cb)
        projeto = None
        if semantico:
            with abrir(projeto_dir) as (projeto, _):
                achados += assistente.lint_semantico(projeto, settings_de(projeto), cb)
    else:
        with abrir(projeto_dir) as (projeto, con):
            cb = cbk.carregar(con)
            achados = cbk.lint(cb)
            if semantico:
                achados += assistente.lint_semantico(projeto, settings_de(projeto), cb)
    _mostrar_lint(achados)
    if cbk.tem_erros(achados):
        raise click.ClickException("O codebook tem erros.")


@codebook.command("import")
@click.argument("arquivo", type=click.Path(exists=True))
@click.option("--nota", default="", help="O que mudou nesta versão.")
@opcao_projeto
@erros
def importar(arquivo, nota, projeto_dir):
    """Importa um codebook YAML como rascunho (nova versão se a última está congelada)."""
    cb = cbk.ler_yaml(Path(arquivo).read_text(encoding="utf-8"))
    _mostrar_lint(cbk.lint(cb))
    with abrir(projeto_dir, escrita="lutz codebook import") as (_, con):
        r = cbk.salvar_rascunho(con, cb, nota=nota)
    console.print(f"Rascunho v{r['versao']} · hash {r['hash']} · {len(cb.campos)} campos. "
                  "Teste com 'lutz codebook test' e congele com 'lutz codebook freeze'.")


@codebook.command("export")
@click.option("--versao", type=int, default=None)
@click.option("-o", "--saida", default=None, help="Arquivo de saída (padrão: codebook.yaml do projeto).")
@opcao_projeto
@erros
def exportar(versao, saida, projeto_dir):
    """Exporta o codebook para YAML."""
    with abrir(projeto_dir) as (projeto, con):
        cb = cbk.carregar(con, versao)
        destino = Path(saida) if saida else projeto.codebook_yaml
        destino.write_text(cb.para_yaml(), encoding="utf-8")
    console.print(f"Codebook v{cb.versao} exportado para {destino}")


@codebook.command("show")
@click.option("--versao", type=int, default=None)
@opcao_projeto
@erros
def show(versao, projeto_dir):
    """Mostra os campos do codebook."""
    with abrir(projeto_dir) as (_, con):
        cb = cbk.carregar(con, versao)
        row = cbk.linha_codebook(con, cb.versao)
    console.print(f"Codebook v{cb.versao} · {row['hash']} · {'congelado' if row['congelado'] else 'rascunho'}")
    tabela(["Campo", "Tipo", "Valores", "Instrução", "Origem"],
           [[c.nome, c.tipo, ", ".join(c.valores), c.instrucao, c.origem] for c in cb.campos])


@codebook.command("history")
@opcao_projeto
@erros
def history(projeto_dir):
    """Histórico de versões do codebook."""
    with abrir(projeto_dir) as (_, con):
        h = cbk.historico(con)
    tabela(["Versão", "Hash", "Estado", "Campos", "Do Assistente", "Execuções", "Nota"],
           [[f"v{x['versao']}", x["hash"], "congelada" if x["congelado"] else "rascunho", x["n_campos"],
             x["n_assistente"], " ".join(map(str, x["execucoes"])), x["nota"]] for x in h])


@codebook.command("diff")
@click.argument("v1", type=int)
@click.argument("v2", type=int)
@opcao_projeto
@erros
def diff(v1, v2, projeto_dir):
    """Diferenças entre duas versões."""
    with abrir(projeto_dir) as (_, con):
        d = cbk.diff(con, v1, v2)
    console.print(f"Adicionados: {', '.join(d['adicionados']) or '—'}")
    console.print(f"Removidos: {', '.join(d['removidos']) or '—'}")
    for a in d["alterados"]:
        console.print(f"[bold]{a['campo']}[/]")
        console.print(a["diff"], markup=False)


@codebook.command("freeze")
@click.option("--versao", type=int, default=None)
@opcao_projeto
@erros
def freeze(versao, projeto_dir):
    """Congela a versão (gera hash; passa a valer para extração e piloto)."""
    with abrir(projeto_dir, escrita="lutz codebook freeze") as (_, con):
        r = cbk.congelar(con, versao)
    console.print(f"[green]Codebook v{r['versao']} congelado[/] · hash {r['hash']}")


@codebook.command("test")
@click.option("--campo", "campos", required=True, help="Campo(s) a testar, separados por vírgula.")
@click.option("--n", default=3, show_default=True, help="Número de artigos.")
@click.option("--artigos", default=None, help="Chaves dos artigos (padrão: os primeiros N).")
@opcao_projeto
@erros
def test(campos, n, artigos, projeto_dir):
    """Teste rápido: roda o(s) campo(s) em poucos artigos com E1 e mostra valor, trecho e página.

    Não conta como piloto e não entra no relatório; os artigos usados ficam fora do sorteio do piloto.
    """
    with abrir(projeto_dir) as (projeto, con):
        s = settings_de(projeto)
        if artigos:
            chaves = [x.strip() for x in artigos.split(",")]
        else:
            chaves = [r[0] for r in con.execute("SELECT chave FROM artigo WHERE status='pronto' ORDER BY id LIMIT ?", (n,))]
    with bloqueio(projeto, "lutz codebook test"):
        from lutz.core.db import conectar

        con = conectar(projeto)
        try:
            eid = ex.planejar(projeto, con, s, tipo="teste", campos=[c.strip() for c in campos.split(",")],
                              artigos=chaves)
            est = ex.estimar(projeto, con, eid)
            console.print(f"Estimativa: {est['chamadas']} chamada(s), US$ "
                          f"{est['custo_usd'] if est['custo_usd'] is not None else '?'}")
            if est["excedem_contexto"]:
                console.print(f"[yellow]Excedem a janela de contexto de um extrator: {', '.join(est['excedem_contexto'])}. "
                              "Aumente janela_tokens (se o modelo permitir) ou indique 'secoes' nos campos.[/]")
            with console.status("Extraindo…"):
                ex.executar(projeto, eid)
            linhas = []
            for r in con.execute("""SELECT a.chave, c.campo_chave, c.valor_final, c.nao_reportado, c.trecho, c.pagina, c.e,
                                    b.e_detalhe, b.erro, b.regras_detalhe FROM celula c JOIN artigo a ON a.id=c.artigo_id
                                    LEFT JOIN extracao_bruta b ON b.celula_id=c.id WHERE c.execucao_id=?""", (eid,)):
                valor = "não reportado" if r["nao_reportado"] else (r["valor_final"] or f"[red]{r['erro'] or r['regras_detalhe']}[/]")
                linhas.append([r["chave"], r["campo_chave"], valor, (r["trecho"] or "")[:120], r["pagina"] or "",
                               f"e={r['e']:g} {r['e_detalhe']}" if r["e"] is not None else ""])
            tabela(["Artigo", "Campo", "Valor", "Trecho", "Pág.", "Evidência"], linhas, f"Teste rápido (execução {eid})")
        finally:
            con.close()


@codebook.command("new")
@click.option("--modelo", "area", type=click.Choice(sorted(assistente.MODELOS)), default=None,
              help="Modelo de partida por área.")
@click.option("--sem-llm", is_flag=True, help="Só o modelo de partida, sem sugestões por LLM.")
@opcao_projeto
@erros
def new(area, sem_llm, projeto_dir):
    """Assistente de Codebook: entrevista, sugestões, revisão campo a campo e lint.

    O Assistente sugere; você decide. Nada entra no codebook sem confirmação.
    """
    with abrir(projeto_dir) as (projeto, con):
        s = settings_de(projeto)
        info = dict(con.execute("SELECT * FROM projeto WHERE id=1").fetchone())
        existente = None
        try:
            existente = cbk.carregar(con)
        except Exception:  # noqa: BLE001 - no codebook yet
            existente = None
    console.print("[bold]Assistente de Codebook[/] — sugere; você decide.\n")
    pergunta = click.prompt("Pergunta de pesquisa", default=info.get("pergunta") or "", show_default=bool(info.get("pergunta")))
    estrutura = click.prompt("Estrutura da pergunta", type=click.Choice(["PICO", "PCC", "outra"]), default="PICO")
    comp = {}
    nomes = {"PICO": ["População", "Intervenção", "Comparação", "Desfecho"],
             "PCC": ["População", "Conceito", "Contexto"], "outra": []}[estrutura]
    for n in nomes:
        comp[n] = click.prompt(n, default="", show_default=False)
    variaveis = [v.strip() for v in click.prompt("Variáveis que você já tem em mente (vírgulas)", default="",
                                                 show_default=False).split(",") if v.strip()]
    if area is None:
        opcoes = ["nenhum", *sorted(assistente.MODELOS)]
        area = click.prompt("Modelo de partida", type=click.Choice(opcoes), default="nenhum")
    campos: list[cbk.Campo] = list(existente.campos) if existente else []
    sugestoes: list[cbk.Campo] = []
    if area and area != "nenhum":
        sugestoes += [c for c in assistente.modelo_de_partida(area) if c.nome not in {x.nome for x in campos}]
    if not sem_llm and pergunta:
        with console.status("Pedindo sugestões ao modelo…"):
            r = assistente.sugerir_campos(projeto, s, pergunta=pergunta, componentes=comp, variaveis=variaveis,
                                          tipo_revisao=info.get("tipo_revisao", "sistematica"),
                                          existentes=[c.nome for c in campos + sugestoes])
        sugestoes += r["campos"]
        for d in r["descartados"]:
            console.print(f"[yellow]Sugestão descartada ({d['campo']}): {d['motivo']}[/]")
    for c in sugestoes:
        console.rule(f"{c.nome} ({c.tipo})")
        console.print(yaml.safe_dump(c.model_dump(mode="json", exclude_defaults=True), allow_unicode=True,
                                     sort_keys=False), markup=False)
        acao = click.prompt("Aceitar, editar ou descartar?", type=click.Choice(["a", "e", "d"]), default="a")
        if acao == "d":
            continue
        if acao == "e":
            editado = click.edit(yaml.safe_dump(c.model_dump(mode="json", exclude_defaults=True), allow_unicode=True,
                                                sort_keys=False))
            if editado:
                try:
                    c = cbk.Campo.model_validate({**yaml.safe_load(editado), "origem": "assistente"})
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]Edição inválida, campo descartado: {exc}[/]")
                    continue
        campos.append(c)
    if not campos:
        raise click.ClickException("Nenhum campo aceito.")
    cb = cbk.Codebook(campos=campos, descricao=pergunta)
    achados = cbk.lint(cb)
    _mostrar_lint(achados)
    if cbk.tem_erros(achados):
        destino = projeto.codebook_yaml
        destino.write_text(cb.para_yaml(), encoding="utf-8")
        raise click.ClickException(f"Há erros de lint. O rascunho foi salvo em {destino} para correção; "
                                   "depois rode 'lutz codebook import'.")
    with abrir(projeto_dir, escrita="lutz codebook new") as (projeto, con):
        r = cbk.salvar_rascunho(con, cb, origem="assistente", nota="Assistente de Codebook")
        projeto.codebook_yaml.write_text(cb.para_yaml(), encoding="utf-8")
    console.print(f"Rascunho v{r['versao']} salvo ({len(campos)} campos). Próximo passo: 'lutz codebook test --campo <nome>'.")
