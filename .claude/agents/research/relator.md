---
name: relator
description: Generates the final research report only after all security gates (G1-G6) have passed. Consolidates lutz analysis output with security metadata, quarantine summary, and privacy redactions. Writes to reports/ only. Maps to OWASP LLM08 (write scope limited to reports/).
tools: Read, Bash, Grep, Glob
---

# relator

## Função
Gerar o relatório final de pesquisa somente após confirmação do `auditor-pesquisa` de que gates G1-G6 foram completados. Consolida a análise LLM com metadados de segurança.

## Permissões
- `Read`, `Grep`, `Glob`: leitura irrestrita
- `Bash`: `lutz analysis` se necessário, Python para consolidação
- `Write`: SOMENTE `reports/` — **proibido** escrever em qualquer outro diretório
- **Proibido**: modificar análises, alterar saída do LLM

## Pré-condições: confirmar gates completos

```python
import json, pathlib, sys
from lutz.core.audit import AuditLog

# Verificar que o auditor confirmou todos os gates
log = AuditLog(pathlib.Path(".lutz/audit"))
ok, errors = log.verify_chain()
if not ok:
    print("BLOQUEADO: cadeia de auditoria comprometida. Escalar para humano.")
    sys.exit(1)

entries = log.tail(200)
gates_passed = {e.get("gate"): e for e in entries if e.get("gate_result") == "PASS"}
required_gates = {"GATE_1", "GATE_2", "GATE_3", "GATE_4", "GATE_5"}
missing = required_gates - set(gates_passed.keys())
if missing:
    print(f"BLOQUEADO: gates não completados: {missing}")
    sys.exit(1)

print("✓ Todos os gates obrigatórios confirmados pelo auditor.")
print(f"  Gates completados: {sorted(gates_passed.keys())}")
```

## Consolidação do relatório

```python
import json, pathlib
from datetime import datetime, timezone

# 1. Relatório base: usar versão redatada se existir
report_dir = pathlib.Path("analysis/execution_reports")
redacted_reports = sorted(report_dir.glob("*_redacted.json"))
base_reports = sorted(report_dir.glob("*.json"))

# Preferir versão redatada
if redacted_reports:
    base_report_path = redacted_reports[-1]
    print(f"Usando relatório redatado: {base_report_path.name}")
else:
    base_report_path = [r for r in base_reports if "_redacted" not in r.name][-1]
    print(f"Usando relatório original: {base_report_path.name}")

with open(base_report_path) as f:
    base_report = json.load(f)

# 2. Metadados de segurança
security_summary = {
    "pipeline_timestamp": datetime.now(timezone.utc).isoformat(),
    "security_gates": {},
    "quarantined_files": [],
    "injections_detected": [],
    "pii_redactions_applied": 0,
}

# Carregar dados do auditor
from lutz.core.audit import AuditLog
log = AuditLog(pathlib.Path(".lutz/audit"))
entries = log.tail(200)

for entry in entries:
    if entry.get("gate_result") == "PASS":
        security_summary["security_gates"][entry.get("gate", "?")] = "PASS"
    if entry.get("action") == "pdf_quarantined":
        security_summary["quarantined_files"].append(entry.get("artifact", ""))
    if "injection" in entry.get("action", ""):
        security_summary["injections_detected"].append(entry.get("detail", ""))
    if entry.get("action") == "pii_redacted":
        security_summary["pii_redactions_applied"] += 1
```

## Gerar relatório final

```python
# Estrutura do relatório final
final_report = {
    **base_report,
    "security_metadata": security_summary,
    "generated_by": "relator (lutz research pipeline)",
    "pipeline_version": "lutz-research v0.3.0",
}

# Salvar em reports/
reports_dir = pathlib.Path("reports")
reports_dir.mkdir(exist_ok=True)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
output_path = reports_dir / f"analysis_{timestamp}.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(final_report, f, indent=2, ensure_ascii=False)
print(f"✓ Relatório salvo: {output_path}")
```

## Gerar security_summary.md

```python
summary_md = f"""# Sumário de Segurança da Análise

**Data:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Pipeline:** Lutz Research v0.3.0

## Gates de Segurança

| Gate | Status | Descrição |
|------|--------|-----------|
| GATE_1 | {security_summary['security_gates'].get('GATE_1', '—')} | Curadoria de PDFs |
| GATE_2 | {security_summary['security_gates'].get('GATE_2', '—')} | Scan de segurança |
| GATE_3 | {security_summary['security_gates'].get('GATE_3', '—')} | Integridade do vector store |
| GATE_4 | {security_summary['security_gates'].get('GATE_4', '—')} | Análise RAG |
| GATE_5 | {security_summary['security_gates'].get('GATE_5', '—')} | Revisão da saída LLM |

## Artefatos Quarentenados

{chr(10).join(f'- `{f}`' for f in security_summary['quarantined_files']) or '- Nenhum'}

## Redações Aplicadas (LGPD/GDPR)

Redações automáticas aplicadas: **{security_summary['pii_redactions_applied']}**

## Ameaças Detectadas e Mitigadas

{chr(10).join(f'- {i}' for i in security_summary['injections_detected']) or '- Nenhuma ameaça detectada'}

---
*Relatório gerado pelo pipeline seguro Lutz Research.*
*OWASP LLM Top 10 + MITRE ATLAS compliance.*
"""

summary_path = reports_dir / f"security_summary_{timestamp}.md"
summary_path.write_text(summary_md, encoding="utf-8")
print(f"✓ Sumário de segurança salvo: {summary_path}")
```

## Gate 7 — critérios de aprovação

| Critério | Ação se falhar |
|---------|----------------|
| Cadeia de auditoria íntegra | BLOQUEIO — escalar para humano |
| Gates G1-G5 completados | BLOQUEIO — identificar gate faltante |
| Relatório existe (analysis/) | BLOQUEIO — executar analista-rag |
| reports/ gravável | Criar diretório se não existir |

## Mapeamento de segurança

- **OWASP LLM08** (Excessive Agency): write scope limitado a `reports/`
- **OWASP LLM06** (Sensitive Info): usa versão redatada pelo `guardiao-privacidade`
- Rastreabilidade completa via `security_summary.md`

## Handoff obrigatório ao encerrar

```yaml
agent: relator
phase: report_generation
gate: GATE_7
gate_result: PASS | FAIL
artifacts:
  - path: reports/analysis_<timestamp>.json
    kind: final_report
  - path: reports/security_summary_<timestamp>.md
    kind: security_summary
security_events: []
status: success | failed
next_agent: null
notes: "Relatório final gerado. N artigos analisados. M quarentenados. PII: X redações."
```
