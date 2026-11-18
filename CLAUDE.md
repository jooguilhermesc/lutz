# Lutz 1.0 — Pipeline de desenvolvimento

Este arquivo configura o contexto e os agentes para **desenvolvimento do Lutz** (a ferramenta em si).

## Contexto do projeto

Lutz é um CLI Python com interface web que produz a **tabela de extração validada** de uma revisão sistemática: cada célula com valor, trecho literal, página e nível de confiança (Alta, Média, Baixa), e um relatório de confiabilidade para Métodos, PRISMA 2020 e RAISE.

Fonte única de requisitos: `docs/spec-1.0.md` (decisões em `docs/designs/lutz-1.0-concepts-brief.md` e `docs/adr/`). Estatística: `docs/metodos-estatisticos.md`.

**Stack principal:**
- CLI: Click + Rich (`lutz/cli/`)
- Estado: SQLite por projeto (`lutz.db`, migrações em `lutz/core/db.py`, WAL, lock de escrita em `.lutz/lock`)
- PDF: PyMuPDF (texto visível por página, colunas, tabelas, unidades citáveis)
- LLM: Anthropic (SDK oficial), OpenAI, OpenRouter, Docker Model Runner, via `lutz/llm/cliente.py`
- Estatística: numpy, krippendorff, rapidfuzz (scikit-learn e statsmodels só como oráculo nos testes)
- Web: FastAPI (`lutz/server/app.py`, só 127.0.0.1) + SPA React/Vite (`web/`); MCP somente leitura (`lutz/server/mcp.py`)
- Sem índice vetorial e sem Postgres na 1.0.0

**Comandos do usuário final:**
```
lutz init PASTA                 # cria projeto (lutz.yaml + .env + lutz.db)
lutz load PDFS                  # ingestão por página
lutz codebook new|import|test|freeze
lutz pilot plan|sample|import|consensus|compare
lutz extract [--retomar ID]     # Modo Autônomo
lutz adjudicate export|import   # decisão humana
lutz audit sample|import        # conferência das células Alta
lutz report                     # relatório de confiabilidade
lutz web | lutz mcp | lutz doctor
```

**Configuração:** `.env` só com chaves e URLs (mecanismo mantido da 0.5: modal de Configurações e `/api/v1/config`); modelos por papel, limiares, orçamento e sementes no `lutz.yaml`.

**Distribuição:**
- `pip install --pre lutz-research` (1.0.0a1) — PyPI
- Windows: PyInstaller (`lutz.spec`) → `lutz.exe`

**CI/CD:** `.github/workflows/ci.yml` (testes com cobertura ≥ 80%, ruff, build da SPA e do pacote, Bandit, pip-audit), `release.yml`, `build-binaries.yml`, `deploy-docs.yml`.

## Pipeline de desenvolvimento

```
USUÁRIO
   │
   ▼
orquestrador-dev (este arquivo)
   │
   ├─ [GATE 1] → desenvolve-lutz          (implementa features/fixes, TDD)
   ├─ [GATE 2] → testa-lutz               (pytest ≥ 80% cobertura, ruff)
   ├─ [GATE 3] → explora-vulnerabilidades (Bandit + detect-secrets + pip-audit)
   ├─ [GATE 4] → corrige-seguranca        (loop: fix → testa, máx 3x)
   └─ [GATE 5] → deploy-lutz              (valida release, não faz push direto)
```

## Gates obrigatórios

| Gate | Transição | Condição de bloqueio |
|------|-----------|----------------------|
| G1 | usuario → desenvolve | Requisito vago ou sem critérios de aceitação claros |
| G2 | desenvolve → testa | Build quebrado ou nenhum teste escrito |
| G3 | testa → explora | Cobertura < 80%, falha de teste ou erro do ruff |
| G4 | explora → corrige ou deploy | Qualquer finding CVSS ≥ 7.0 ou secret hardcoded |
| G5 | corrige → testa (loop) | 4ª iteração → escala para humano |

## Quando chamar cada agente

- **desenvolve-lutz**: implementar funcionalidade nova, corrigir bug, refatorar
- **testa-lutz**: rodar suite de testes, verificar cobertura, validar integração
- **explora-vulnerabilidades**: análise SAST, auditoria de dependências
- **corrige-seguranca**: aplicar patches de segurança após findings do explora
- **deploy-lutz**: preparar release, validar CHANGELOG, PyPI e GitHub Release

## Protocolo de handoff

Cada agente encerra emitindo um bloco YAML. Handoff sem `gate_result` é considerado incompleto.

```yaml
agent: <nome>
phase: <fase>
artifacts:
  - path: <caminho>
    kind: <tipo>
gate: <GATE_N>
gate_result: PASS | FAIL | ESCALATE
security_events: []  # lista de {severity, detail}
status: success | partial | failed
next_agent: <nome ou null>
notes: "<1-3 linhas>"
```

## Restrições absolutas do orquestrador

1. Não fazer `git push` sem handoff aprovado do `deploy-lutz`
2. Escalar para humano após 3 falhas consecutivas no mesmo gate
3. Todo gate override, mudança de limiar padrão ou da regra de nível exige ADR em `docs/adr/`
4. Mudanças em requisitos atualizam `docs/spec-1.0.md` no mesmo PR

## Invariantes do produto (não quebrar)

- Só texto **visível** do PDF chega aos extratores, ao verificador e à verificação de evidência.
- Toda chamada LLM passa pelo `ClienteLLM` e fica registrada em `chamada_llm`.
- Uma execução retomada usa a configuração registrada nela, nunca o `lutz.yaml` atual.
- Respostas do Lutz para artigos do piloto ficam ocultas (web, API, MCP, exportações, relatório) até a importação das planilhas humanas.
- O texto para Métodos sem piloto sempre inclui a frase de limitação.
- Os exemplos numéricos de `docs/metodos-estatisticos.md` são testes; não alterar sem atualizar o documento.
