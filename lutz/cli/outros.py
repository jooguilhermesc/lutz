"""lutz report / config / doctor / usage / bundle / web / mcp."""

from __future__ import annotations

from pathlib import Path

import click

from lutz.cli.comum import abrir, console, erros, fmt, lista_opcao, opcao_projeto, tabela
from lutz.config.env import salvar_env, valores_com_origem
from lutz.config.settings import avisos, carregar_settings, estrategia_diversidade
from lutz.core import bundle as bnd
from lutz.core.doctor import verificar
from lutz.core.errors import LutzError
from lutz.core.project import encontrar_projeto
from lutz.llm.cliente import consumo
from lutz.report.gerar import gerar


@click.command("report")
@click.option("--execucao", "execucao_id", type=int, default=None, help="Padrão: a última execução autônoma concluída.")
@click.option("--idioma", default=None, help="pt, en ou pt,en (padrão: lutz.yaml).")
@click.option("--formato", default=None, help="md, pdf ou md,pdf (padrão: lutz.yaml).")
@opcao_projeto
@erros
def report(execucao_id, idioma, formato, projeto_dir):
    """Gera o relatório de confiabilidade (sete partes) e os anexos A, B e C."""
    with abrir(projeto_dir, escrita="lutz report") as (projeto, con):
        if execucao_id is None:
            r = con.execute("SELECT id FROM execucao WHERE tipo='autonoma' AND status='concluida' ORDER BY id DESC LIMIT 1").fetchone()
            if r is None:
                raise LutzError("Nenhuma execução autônoma concluída.")
            execucao_id = r[0]
        idiomas, formatos = lista_opcao(idioma), lista_opcao(formato)
        for i in idiomas or []:
            if i not in ("pt", "en"):
                raise click.UsageError("Idiomas: pt, en.")
        for f in formatos or []:
            if f not in ("md", "pdf"):
                raise click.UsageError("Formatos: md, pdf.")
        r = gerar(projeto, con, execucao_id, idiomas=idiomas, formatos=formatos)
    console.print(f"Relatório gerado em {r['pasta']}")
    for a in r["arquivos"]:
        console.print(f"  {a}")


@click.group("config")
def config():
    """Configuração: segredos e URLs no .env; modelos e limiares no lutz.yaml."""


@config.command("show")
@opcao_projeto
@erros
def config_show(projeto_dir):
    """Mostra o .env (com a origem de cada valor) e o resumo do lutz.yaml."""
    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    tabela(["Chave", "Valor", "Origem"],
           [[v["nome"], v["valor"] or "—", v["origem"] + (" (sombreia o .env)" if v["sombreado"] else "")]
            for v in valores_com_origem(projeto)], ".env")
    s = carregar_settings(projeto)
    linhas = [[rot, m.provedor, m.modelo, m.temperatura_efetiva() if m.temperatura_efetiva() is not None else "n/a",
               m.variante_prompt] for rot, m in s.modelos.extratores().items()]
    for rot in ("V", "J"):
        m = getattr(s.modelos, rot)
        if m:
            linhas.append([rot, m.provedor, m.modelo, m.temperatura_efetiva() if m.temperatura_efetiva() is not None
                           else "n/a", m.variante_prompt])
    tabela(["Papel", "Provedor", "Modelo", "Temp.", "Prompt"], linhas,
           f"lutz.yaml · diversidade: {estrategia_diversidade(s.modelos)} · hash {s.hash()[:16]}")
    for a in avisos(s):
        console.print(f"[yellow]{a}[/]")


@config.command("set")
@click.argument("chave")
@click.argument("valor")
@opcao_projeto
@erros
def config_set(chave, valor, projeto_dir):
    """Grava CHAVE=VALOR no .env (só chaves de provedor e URLs)."""
    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    sombra = salvar_env(projeto, {chave: valor})
    console.print(f"{chave} gravada no .env.")
    if sombra:
        console.print(f"[yellow]{chave} também está definida no ambiente do terminal, que tem precedência.[/]")


@config.command("unset")
@click.argument("chave")
@opcao_projeto
@erros
def config_unset(chave, projeto_dir):
    """Remove CHAVE do .env."""
    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    salvar_env(projeto, {chave: None})
    console.print(f"{chave} removida do .env.")


@click.command("doctor")
@click.option("--chamar", is_flag=True, help="Faz uma chamada mínima a cada modelo (custa centavos).")
@opcao_projeto
@erros
def doctor(chamar, projeto_dir):
    """Verifica configuração, chaves, provedores, banco e interface web."""
    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    cor = {"ok": "green", "aviso": "yellow", "erro": "red"}
    res = verificar(projeto, chamar=chamar)
    tabela(["Item", "Status", "Detalhe"], [[r["item"], f"[{cor[r['status']]}]{r['status']}[/]", r["detalhe"]] for r in res])
    if any(r["status"] == "erro" for r in res):
        raise click.ClickException("Há problemas a corrigir.")


@click.command("usage")
@click.option("--execucao", "execucao_id", type=int, default=None)
@opcao_projeto
@erros
def usage(execucao_id, projeto_dir):
    """Consumo de tokens e custo por papel e modelo."""
    with abrir(projeto_dir) as (_, con):
        c = consumo(con, execucao_id)
    tabela(["Papel", "Rótulo", "Provedor", "Modelo pedido", "Modelo observado", "Chamadas", "Tokens entrada",
            "Tokens saída", "US$", "Falhas"],
           [[r["papel"], r["rotulo"], r["provedor"], r["modelo_pedido"], r["modelo_observado"], r["chamadas"],
             f"{r['tokens_entrada'] or 0:,}", f"{r['tokens_saida'] or 0:,}",
             "?" if r["custo_usd"] is None else fmt(r["custo_usd"], 4), r["falhas"]] for r in c["por_papel"]])
    t = c["total"]
    console.print(f"Total: {t['chamadas']} chamadas ({t['em_cache'] or 0} em cache) · US$ {fmt(t['custo_usd'] or 0, 4)}")


@click.group("bundle")
def bundle():
    """Pacote do projeto para material suplementar (sem .env)."""


@bundle.command("export")
@click.option("-o", "--saida", default=None)
@click.option("--com-pdfs", is_flag=True, help="Inclui os PDFs (cuidado com direitos autorais).")
@opcao_projeto
@erros
def bundle_export(saida, com_pdfs, projeto_dir):
    """Exporta o projeto num .zip com manifesto de hashes."""
    with abrir(projeto_dir, escrita="lutz bundle export") as (projeto, _):
        destino = Path(saida) if saida else projeto.exports / f"{projeto.raiz.name}.lutz.zip"
        r = bnd.exportar(projeto, destino, incluir_pdfs=com_pdfs)
    console.print(f"{r['arquivos']} arquivo(s) em {r['destino']}")


@click.command("web")
@click.option("--porta", default=8000, show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--sem-navegador", is_flag=True)
@click.option("--permitir-rede", is_flag=True, hidden=True,
              help="Aceita --host diferente de 127.0.0.1 (só dentro de um container publicado em 127.0.0.1).")
@opcao_projeto
@erros
def web(porta, host, sem_navegador, permitir_rede, projeto_dir):
    """Abre a interface web local."""
    if host not in ("127.0.0.1", "localhost", "::1") and not permitir_rede:
        raise click.UsageError("A API não tem autenticação e dispara custos: só escuta em 127.0.0.1.")
    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    import threading
    import webbrowser

    import uvicorn

    from lutz.server.app import criar_app

    app = criar_app(projeto)
    url = f"http://{host}:{porta}"
    console.print(f"Lutz em {url}  (Ctrl+C para sair)")
    if not sem_navegador:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=porta, log_level="warning")


@click.command("mcp")
@click.option("--projeto", "projeto_dir", default=None, metavar="PASTA")
@erros
def mcp(projeto_dir):
    """Servidor MCP (stdio, somente leitura) para Claude Desktop, Cursor, VS Code e outros clientes."""
    from lutz.server.mcp import servidor

    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    servidor(projeto).run("stdio")
