# ADR-003 — Rascunhos de especificação fora do versionamento

* **Data:** 2026-11-18
* **Estado:** aceita
* **Decisão de:** João Guilherme Silva Cabral

## Contexto

A pasta `specs/` guarda os rascunhos que deram origem ao Lutz 1.0: a especificação inicial, os diagramas, o documento de estratégia de validação (`.docx`), os mockups das telas (HTML empacotado de cerca de 1 MB) e o brief de conceito. Esses arquivos foram escritos como "Lutz 2.0", antes da renumeração para 1.0, e em vários pontos divergem do que foi implementado (por exemplo, PGVector e chaves de API com escopo).

Versioná-los ao lado da documentação oficial cria duas fontes de requisitos que se contradizem e pesa no repositório.

## Decisão

1. O conteúdo de `specs/` fica fora do git. O `.gitignore` ignora `specs/*` e só libera `specs/.gitkeep` e os ADRs desta pasta (`specs/ADR-*.md`).
2. A fonte única de requisitos é `docs/spec-1.0.md`. As decisões tomadas a partir dos rascunhos estão em `docs/designs/lutz-1.0-concepts-brief.md` e nos ADRs de `docs/adr/`.
3. Os rascunhos continuam disponíveis localmente para consulta da equipe de pesquisa.

## Consequências

* Quem clona o repositório não vê os rascunhos; precisa consultar a equipe se quiser o material original.
* Os arquivos já entraram no histórico da branch `feat/lutz-1.0` no commit `14bc369` e foram retirados no commit seguinte. Para removê-los do histórico seria preciso reescrever a branch antes do merge (por exemplo, com squash merge do PR).
* Novos rascunhos podem ser colocados em `specs/` sem risco de serem versionados por engano.
