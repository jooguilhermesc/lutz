"""Append-only audit log with HMAC chain integrity for Lutz pipelines.

Threat model
------------
An adversary (or a compromised agent) may attempt to modify past audit entries
to hide malicious activity. This module implements a tamper-evident log where
each entry is signed with HMAC-SHA256 and chained to the previous entry's
signature. Any retroactive modification invalidates the chain from that point
forward.

Security properties
-------------------
- Append-only file writes (no in-place modification)
- Each entry carries its predecessor's signature in the signed payload
- Chain verification detects both modification and insertion/deletion of entries
- Key derivation from project path (stable, no secret required from user)

ATLAS: AML.TA0007 (Defense Evasion) — audit trail detects attempts to cover
tracks after agent compromise or indirect injection.

OWASP LLM08: Excessive Agency — every agent action is recorded with its scope,
providing accountability for autonomous decisions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel used as the "previous signature" for the very first entry.
_GENESIS = "genesis"


class AuditLog:
    """Tamper-evident append-only audit log.

    Usage
    -----
    >>> log = AuditLog(Path(".lutz/audit"))
    >>> log.record("sentinela-pdf", "quarantine",
    ...            artifact="articles/paper.pdf",
    ...            sha256="abc123",
    ...            reason="injection_pattern_detected",
    ...            atlas="AML.T0051.001",
    ...            owasp="LLM01",
    ...            severity="HIGH")
    """

    def __init__(self, log_dir: Path, key: bytes | None = None) -> None:
        self._dir = log_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._key = key if key is not None else _derive_key(log_dir)
        self._log_file = log_dir / "audit.jsonl"
        self._prev_sig = self._load_last_signature()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        agent: str,
        action: str,
        **kwargs: Any,
    ) -> str:
        """Append a signed audit entry.

        Parameters
        ----------
        agent:
            Name of the agent recording the event (e.g. "sentinela-pdf").
        action:
            Short verb describing what happened (e.g. "quarantine", "approve",
            "gate_fail", "gate_pass", "inject_detected", "pii_redact").
        **kwargs:
            Any additional structured fields to include in the entry.
            Common fields: artifact, sha256, reason, atlas, owasp, severity,
            gate, cost_usd.

        Returns
        -------
        str
            The HMAC-SHA256 signature of the recorded entry.
        """
        data: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "action": action,
            **kwargs,
        }

        # The signed payload includes the previous signature to form a chain.
        payload = json.dumps(
            {"prev": self._prev_sig, "data": data},
            sort_keys=True,
            ensure_ascii=False,
        )
        sig = hmac.new(self._key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

        entry = {**data, "prev_sig": self._prev_sig, "sig": sig}

        with open(self._log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        self._prev_sig = sig
        return sig

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify the integrity of every entry in the audit log.

        Returns
        -------
        tuple[bool, list[str]]
            (True, []) if the chain is intact.
            (False, [error_messages]) if any entry is missing, modified, or
            if the chain is broken.
        """
        if not self._log_file.exists():
            return True, []

        errors: list[str] = []
        prev_sig = _GENESIS

        with open(self._log_file, "r", encoding="utf-8") as fh:
            for line_num, raw_line in enumerate(fh, start=1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    errors.append(f"Line {line_num}: invalid JSON — {exc}")
                    continue

                entry_prev_sig = entry.get("prev_sig")
                entry_sig = entry.get("sig")

                if entry_prev_sig != prev_sig:
                    errors.append(
                        f"Line {line_num}: chain broken — "
                        f"expected prev_sig={prev_sig!r}, got {entry_prev_sig!r}"
                    )

                # Re-derive the data payload (everything except sig and prev_sig).
                data = {k: v for k, v in entry.items() if k not in ("sig", "prev_sig")}
                payload = json.dumps(
                    {"prev": entry_prev_sig, "data": data},
                    sort_keys=True,
                    ensure_ascii=False,
                )
                expected_sig = hmac.new(
                    self._key, payload.encode("utf-8"), hashlib.sha256
                ).hexdigest()

                if entry_sig != expected_sig:
                    errors.append(
                        f"Line {line_num}: signature mismatch — "
                        f"entry may have been tampered with"
                    )

                prev_sig = entry_sig or prev_sig

        return len(errors) == 0, errors

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the last *n* audit entries (without sig/prev_sig fields)."""
        if not self._log_file.exists():
            return []
        lines: list[str] = []
        with open(self._log_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    lines.append(line)
        entries = []
        for raw in lines[-n:]:
            try:
                entry = json.loads(raw)
                entries.append({k: v for k, v in entry.items() if k not in ("sig", "prev_sig")})
            except json.JSONDecodeError:
                pass
        return entries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_last_signature(self) -> str:
        """Read the signature of the last entry for chain continuity."""
        if not self._log_file.exists():
            return _GENESIS
        last_sig = _GENESIS
        try:
            with open(self._log_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        last_sig = entry.get("sig", _GENESIS)
                    except json.JSONDecodeError:
                        pass
        except OSError as exc:
            logger.warning("Could not read audit log: %s", exc)
        return last_sig


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _derive_key(log_dir: Path) -> bytes:
    """Derive a stable signing key from the project path.

    This is not a cryptographic secret — it prevents casual text-editor
    tampering and ensures the signature is tied to this specific project.
    For stronger guarantees, pass an explicit *key* to AuditLog.__init__.
    """
    seed = str(log_dir.resolve()).encode("utf-8")
    return hashlib.sha256(seed).digest()


def get_audit_log(project_root: Path) -> AuditLog:
    """Return an AuditLog rooted at *project_root*/.lutz/audit/."""
    return AuditLog(project_root / ".lutz" / "audit")
