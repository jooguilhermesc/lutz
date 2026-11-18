"""Domain errors. Every message is meant to be shown to the researcher as is."""

from __future__ import annotations


class LutzError(Exception):
    """Base class for errors that the CLI, the API and the MCP server report verbatim."""


class ProjetoNaoEncontrado(LutzError):
    pass


class ProjetoIncompativel(LutzError):
    pass


class ProjetoOcupado(LutzError):
    """Another process holds the write lock of the project."""


class ConfigInvalida(LutzError):
    pass


class CodebookInvalido(LutzError):
    pass


class EstadoInvalido(LutzError):
    """The requested action is not allowed in the current state (e.g. codebook not frozen)."""


class OrcamentoExcedido(LutzError):
    pass


class ProvedorErro(LutzError):
    pass
