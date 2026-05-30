# ADR-001 — Gate G3 override: déficit de cobertura pré-existente

**Data:** 2026-05-30  
**Status:** Aceito  
**Decisores:** jooguilhermesc  

## Contexto

Ao final da implementação do US-0 (fit-once model registry), o agente `testa-lutz`
reportou cobertura global de **62.75%**, abaixo do threshold de 80% exigido pelo Gate G3.

A investigação revelou que o déficit é **pré-existente** e concentrado em módulos não
tocados pelo US-0:

| Módulo | Stmts | Cobertura |
|--------|-------|-----------|
| `lutz/server/app.py` | 1 497 | 51% |
| `lutz/core/vector_store.py` | 178 | 43% |
| `lutz/core/security_checker.py` | 190 | 40% |

O escopo direto do US-0 (`lutz/analytics/`) ficou em **81%** — acima do threshold.

## Decisão

Override do Gate G3 para o US-0. O pipeline avança para US-1, US-2 e US-5 sem
exigir que a cobertura global atinja 80% antes.

A dívida de cobertura será tratada em PR separado, priorizando `server/app.py`
(maior impacto unitário) antes do próximo ciclo de release.

## Consequências

- Desenvolvimento das histórias analíticas continua sem bloqueio.
- Um PR dedicado a testes de rotas (`server/app.py`) deve ser aberto antes de `v0.5.0`.
- Qualquer novo módulo criado nas próximas histórias **deve** manter cobertura ≥ 80%
  no seu escopo, como o US-0 fez.
