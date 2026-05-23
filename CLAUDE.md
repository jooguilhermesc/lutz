# Lutz Research — Pipeline de Desenvolvimento

Este arquivo configura o contexto e os agentes para **desenvolvimento do Lutz** (a ferramenta em si).
Para o pipeline de pesquisa (vetorizar artigos, analisar corpus), use os agentes em `.claude/agents/`.

## Contexto do projeto

Lutz é um CLI Python para triagem e análise de artigos científicos via RAG + LLM.

**Stack principal:**
- CLI: Click + Rich
- Vector store: LanceDB (embedded, `.lutz/vector_store/`)
- PDF: pymupdf (primário) → pypdf (fallback)
- Segurança: `lutz/core/security_checker.py` — 6 camadas de defesa
- LLM/Embedding: OpenAI / Anthropic / Docker Model Runner / sentence-transformers
- Web: FastAPI + React SPA

**Comandos do usuário final:**
```
lutz init [nome]          # cria projeto de pesquisa
lutz load --f PATH        # copia PDFs para articles/
lutz vectorize            # scan segurança → extração → embedding → LanceDB
lutz analysis --p FILE    # RAG + LLM → relatório
lutz web                  # abre interface web
```

**Distribuição:**
- `pip install lutz-research` — PyPI
- Windows: PyInstaller + Inno Setup → `lutz-setup-windows-x64.exe`
- Linux: PyInstaller + `build-deb.sh` → `.deb`

**CI/CD:** `.github/workflows/ci.yml` (checks + security + agents), `release.yml`, `build-binaries.yml`

## Pipeline de desenvolvimento

```
USUÁRIO
   │
   ▼
orquestrador-dev (este arquivo)
   │
   ├─ [GATE 1] → desenvolve-lutz     (implementa features/fixes, TDD)
   │                    │
   ├─ [GATE 2] → testa-lutz          (pytest ≥ 80% cobertura)
   │                    │
   ├─ [GATE 3] → explora-vulnerabilidades  (Bandit + detect-secrets + pip-audit)
   │                    │
   ├─ [GATE 4] → corrige-seguranca   (loop: fix → testa, máx 3x)
   │                    │
   ├─ [GATE 5] → deploy-lutz         (valida release, não faz push direto)
   │
   └─ (transversal) → auditor-dev    (recebe handoff de todos os agentes)
```

## Gates obrigatórios

| Gate | Transição | Condição de bloqueio |
|------|-----------|----------------------|
| G1 | usuario → desenvolve | Requisito vago ou sem critérios de aceitação claros |
| G2 | desenvolve → testa | Build quebrado ou nenhum teste escrito |
| G3 | testa → explora | Cobertura < 80% ou falhas de teste abertas |
| G4 | explora → corrige ou deploy | Qualquer finding CVSS ≥ 7.0 ou secret hardcoded |
| G5 | corrige → testa (loop) | 4ª iteração → escala para humano |
| G6 | testa → deploy | Score de segurança < 80 |

## Quando chamar cada agente

- **desenvolve-lutz**: implementar funcionalidade nova, corrigir bug, refatorar
- **testa-lutz**: rodar suite de testes, verificar cobertura, validar integração
- **explora-vulnerabilidades**: análise SAST/DAST, auditoria de dependências
- **corrige-seguranca**: aplicar patches de segurança após findings do explora
- **auditor-dev**: manter registro imutável das decisões de desenvolvimento
- **deploy-lutz**: preparar release, validar CHANGELOG, PyPI e GitHub Release

## Protocolo de handoff

Cada agente encerra emitindo um bloco YAML com o seguinte formato.
Handoff sem `gate_result` é considerado incompleto.

```yaml
agent: <nome>
phase: <fase>
started_at: <ISO 8601>
ended_at: <ISO 8601>
artifacts:
  - path: <caminho>
    kind: <tipo>
gate: <GATE_N>
gate_result: PASS | FAIL | ESCALATE
security_events: []  # lista de {severity, atlas, owasp, detail}
status: success | partial | failed
cost:
  input_tokens: <n>
  output_tokens: <n>
  estimated_usd: <float>
next_agent: <nome ou null>
notes: "<1-3 linhas>"
```

## Restrições absolutas do orquestrador

1. Não executar ações técnicas diretamente — apenas coordenar agentes
2. Não fazer `git push` sem handoff aprovado do `deploy-lutz`
3. Não sobrescrever `.lutz/audit/` — append-only via `lutz/core/audit.py`
4. Escalar para humano após 3 falhas consecutivas no mesmo gate
5. Todo gate override exige ADR documentado em `docs/adr/`

## Segurança

O Lutz implementa defesa em profundidade para PDFs não confiáveis:
- `lutz/core/security_checker.py` — 6 camadas (estrutura, injeção, RAG poisoning, Unicode, estrutura acadêmica, anomalia de corpus)
- `lutz/security/*.yaml` — catálogos de padrões ATLAS T0051/T0054/T0070
- `lutz/core/audit.py` — log HMAC append-only para rastreabilidade
- CI: Bandit + detect-secrets + validação de agentes

Ao modificar qualquer componente de segurança, sempre acionar `explora-vulnerabilidades`
antes de qualquer merge.
