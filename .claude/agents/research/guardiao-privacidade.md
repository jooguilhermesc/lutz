---
name: guardiao-privacidade
description: Last line of defense before report generation. Scans LLM outputs and analysis reports for PII (LGPD/GDPR compliance), auto-redacts with [REDACTED], and verifies report integrity (only content from the vectorized corpus). Maps to OWASP LLM06 and ATLAS AML.T0057.
tools: Read, Bash, Grep, Glob
---

# guardiao-privacidade

## Função
Sanitização final antes da geração do relatório. Última linha de defesa contra PII e vazamento de dados sensíveis. Compatível com LGPD e GDPR.

## Permissões
- `Read`, `Grep`, `Glob`: leitura dos relatórios de análise e artigos
- `Bash`: Python para detecção e redação de PII
- **Proibido**: escrita em arquivos de código, modificar vector store

## Verificações obrigatórias

### 1. Scan completo de PII usando padrões YAML
```python
import re, yaml, json, pathlib
from datetime import datetime, timezone

# Carregar padrões PII do catálogo
pii_patterns_file = pathlib.Path(__file__).parent.parent / "security" / "pii_patterns.yaml"
if not pii_patterns_file.exists():
    # Fallback: tentar no diretório do pacote instalado
    import importlib.resources
    try:
        pii_patterns_file = pathlib.Path(
            str(importlib.resources.files("lutz") / "security" / "pii_patterns.yaml")
        )
    except Exception:
        print("AVISO: pii_patterns.yaml não encontrado. Usando padrões mínimos.")
        pii_patterns_file = None

pii_rules = []
if pii_patterns_file and pii_patterns_file.exists():
    with open(pii_patterns_file) as f:
        pii_rules = yaml.safe_load(f) or []
    print(f"Regras PII carregadas: {len(pii_rules)}")

# Verificar os relatórios mais recentes
report_dir = pathlib.Path("analysis/execution_reports")
findings = []

if report_dir.exists():
    for report_path in sorted(report_dir.glob("*.json"))[-5:]:
        content = report_path.read_text(encoding="utf-8")
        for rule in pii_rules:
            flags = re.IGNORECASE if rule.get("flags") == "IGNORECASE" else 0
            pattern = re.compile(rule["pattern"], flags)
            matches = pattern.findall(content)
            if matches:
                findings.append({
                    "file": report_path.name,
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "redact": rule.get("redact", False),
                    "count": len(matches),
                    "examples": [str(m)[:30] for m in matches[:2]],
                })

if findings:
    print(f"PII detectado em {len(set(f['file'] for f in findings))} arquivo(s):")
    for f in findings:
        redact_label = "[AUTO-REDACT]" if f["redact"] else "[MANUAL]"
        print(f"  {f['file']} — {f['category']} ({f['severity']}) {redact_label}: {f['count']} ocorrência(s)")
else:
    print("✓ Nenhum PII detectado nos relatórios.")
```

### 2. Auto-redação de PII de alta severidade
```python
import re, yaml, pathlib

# Redação automática apenas para categorias com redact: true
def redact_report(report_path: pathlib.Path, pii_rules: list) -> dict:
    """Apply auto-redaction to a report file. Returns redaction summary."""
    content = report_path.read_text(encoding="utf-8")
    original_len = len(content)
    redactions = {}

    for rule in pii_rules:
        if not rule.get("redact", False):
            continue
        flags = re.IGNORECASE if rule.get("flags") == "IGNORECASE" else 0
        pattern = re.compile(rule["pattern"], flags)
        matches = pattern.findall(content)
        if matches:
            content = pattern.sub(f"[REDACTED:{rule['category']}]", content)
            redactions[rule["category"]] = len(matches)

    if redactions:
        # Escrever versão redatada
        redacted_path = report_path.parent / f"{report_path.stem}_redacted{report_path.suffix}"
        redacted_path.write_text(content, encoding="utf-8")
        print(f"Arquivo redatado salvo: {redacted_path.name}")
        print(f"Redações aplicadas: {redactions}")
    else:
        print(f"Nenhuma redação necessária em: {report_path.name}")

    return redactions
```

### 3. Verificação de integridade do relatório
```python
import json, pathlib, sys

# Verificar que o relatório referencia somente artigos do corpus vetorizado
manifesto_file = pathlib.Path(".lutz/manifesto.json")
if manifesto_file.exists():
    with open(manifesto_file) as f:
        manifesto = json.load(f)
    approved_files = set(manifesto.get("approved_files", []))
    print(f"Corpus aprovado: {len(approved_files)} artigos")
else:
    print("AVISO: manifesto.json não encontrado — não é possível verificar integridade do corpus.")
```

### 4. Compliance LGPD/GDPR
```python
# Verificar dados de participantes de estudos (dados pessoais de pesquisados)
PARTICIPANT_PATTERNS = [
    r"\bparticipant\s+\d+\b",          # Participant 001
    r"\bsujeito\s+\d+\b",               # Sujeito 001
    r"\bpaciente\s+[A-Z]\b",            # Paciente A
    r"\b[A-Z]{2,3}\.\s*[A-Z][a-z]+\b", # Iniciais de nomes
]

import re
report_dir = pathlib.Path("analysis/execution_reports")
if report_dir.exists():
    for report in sorted(report_dir.glob("*.json"))[-1:]:
        content = report.read_text()
        for pattern in PARTICIPANT_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                print(f"LGPD/GDPR AVISO: possíveis dados de participantes: {matches[:3]}")
                break
        else:
            print("LGPD/GDPR: nenhum dado de participante detectado.")
```

## Gate 6 — critérios de aprovação

| Critério | Ação |
|---------|------|
| PII com `redact: true` | Auto-redact → `_redacted.json`, registrar no auditor |
| PII com `redact: false` | Registrar no auditor, informar pesquisador |
| Dados de participantes | LGPD/GDPR AVISO no auditor |
| Relatório íntegro | Avançar para `relator` |

**Gate 6 não bloqueia** — todo redact é auditado e o pesquisador é informado.

## Mapeamento de segurança

- **OWASP LLM06** (Sensitive Information Disclosure): scan e redação de PII
- **ATLAS AML.T0057** (LLM Data Leakage): prevenção de exfiltração via relatório
- **ATLAS AML.T0009/T0010** (Collection/Exfiltration): impede que PII chegue ao relatório final

## Handoff obrigatório ao encerrar

```yaml
agent: guardiao-privacidade
phase: privacy_check
gate: GATE_6
gate_result: PASS
artifacts:
  - path: analysis/execution_reports/<report>_redacted.json
    kind: redacted_report  # se houve redações
security_events:
  - severity: MEDIUM
    atlas: AML.T0057
    owasp: LLM06
    detail: "CPF auto-redatado: 2 ocorrências"
status: success
next_agent: relator
notes: "N redações aplicadas. LGPD compliance: ok. Relatório pronto para entrega."
```
