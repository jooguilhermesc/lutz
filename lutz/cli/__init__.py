"""Lutz 1.0 command line."""

from __future__ import annotations

import click

from lutz import __version__
from lutz.cli.codebook import codebook
from lutz.cli.extracao import extract, results
from lutz.cli.outros import bundle, config, doctor, mcp, report, usage, web
from lutz.cli.piloto import pilot
from lutz.cli.projeto import init, library, load, project, status
from lutz.cli.revisao import adjudicate, audit


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="lutz")
def cli() -> None:
    """Lutz — extração validada para revisões sistemáticas.

    \b
    Fluxo:
      lutz init minha-revisao        cria o projeto
      lutz load pdfs/                importa os PDFs
      lutz codebook new              monta o formulário com o Assistente
      lutz codebook test --campo X   teste rápido em 3 artigos
      lutz codebook freeze           congela a versão
      lutz pilot plan / sample       (opcional) piloto cego com humanos
      lutz extract                   Modo Autônomo em todo o corpus
      lutz adjudicate export/import  decide as células duvidosas
      lutz audit sample              confere uma amostra das células Alta
      lutz report                    relatório de confiabilidade
    """


for comando in (init, project, status, load, library, codebook, extract, results, adjudicate, audit, pilot,
                report, config, doctor, usage, bundle, web, mcp):
    cli.add_command(comando)
