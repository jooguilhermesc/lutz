# ADR-002 — Reescrita do Lutz 1.0 e fim do pipeline de segurança da 0.5

* **Data:** 2026-11-18
* **Estado:** aceita
* **Decisão de:** João Guilherme Silva Cabral (autor), a partir de `docs/designs/lutz-1.0-concepts-brief.md`

## Contexto

A 0.5 era uma ferramenta de triagem e análise por RAG com prompt livre, com um pipeline de segurança em seis camadas para PDFs não confiáveis (`security_checker.py`), log de auditoria HMAC (`audit.py`) e gates de CI e de agentes construídos em torno disso (G3/G4 do `CLAUDE.md`: Bandit sobre o checker, detect-secrets, validação de agentes, agentes de pesquisa `sentinela-pdf`, `curador`, `guardiao-privacidade` e outros).

O Lutz 1.0 tem outro objetivo (tabela de extração validada para uma pessoa pesquisadora, no próprio computador) e foi reescrito do zero, mantendo da 0.5 só o mecanismo de configuração (`.env` + modal de configurações).

## Decisão

1. O 1.0 substitui a 0.5 no mesmo repositório e pacote, como pré-release `1.0.0a1`, sem migração de projetos.
2. Saem o scan de segurança em seis camadas, a quarentena, o log HMAC, os agentes de pesquisa e os gates G3/G4 baseados neles.
3. O risco que o scan cobria e que importa para a tese do produto — texto invisível no PDF virando valor de alta confiança — passa a ser tratado como **qualidade do texto** na ingestão: só o texto visível chega aos extratores e à verificação de evidência; o oculto é guardado à parte e listado no relatório.
4. A CI mantém uma etapa de segurança genérica (Bandit em severidade alta e `pip-audit` nas dependências) e passa a exigir testes com cobertura ≥ 80%, ruff e o build da interface.
5. O pipeline de agentes de desenvolvimento do `CLAUDE.md` é simplificado (desenvolve → testa → explora → deploy) e o `auditor-dev` sai junto com `audit.py`.

## Consequências

* Usuários da 0.5 que fizerem `pip install -U --pre` recebem um programa diferente; o 1.0 recusa abrir projetos 0.5 com instruções, e `docs/upgrade-0.5-para-1.0.md` explica como manter a 0.5 (`pip install "lutz-research<1"`).
* Prompt injection por texto **visível** continua possível; o prompt dos extratores trata o artigo como dado, o verificador vê só uma janela de texto, e a evidência literal e a adjudicação limitam o efeito. Isso é registrado como risco residual na spec.
