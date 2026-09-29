"""Effect receipts: reserve before dispatch, settle after observation.

A receipt is how OLIVE knows, after Stop, a crash or a restart, whether an
effect happened. Rules:

- Every effect is reserved *before* it is dispatched, with what OLIVE expects
  to observe afterwards (for a file write, the exact resulting SHA-256).
- A reservation that was never settled is not assumed to have failed or to
  have succeeded. Recovery re-observes what can be re-observed (file hashes)
  and marks everything else uncertain.
- Uncertain external effects are never retried automatically.

Receipts hold digests and paths, never file contents or message bodies.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid

from ..models import now_iso

# Effect classes, from least to most consequential.
READ = "read"                 # observation only; never reserved
WORKSPACE_WRITE = "workspace_write"   # hash-checked file change inside a workspace
VALIDATION = "validation"     # bounded detected build/test process
PROCESS = "process"           # long-lived OLIVE-owned process (dev server)
DESKTOP_INPUT = "desktop_input"
EXTERNAL = "external"         # message/email/post/upload: leaves this device
EFFECT_CLASSES = {READ, WORKSPACE_WRITE, VALIDATION, PROCESS, DESKTOP_INPUT, EXTERNAL}

RESERVED, COMPLETED, FAILED, UNCERTAIN, NOT_APPLIED = "reserved", "completed", "failed", "uncertain", "not_applied"


def argument_digest(tool: str, arguments: dict) -> str:
    try:
        raw = json.dumps({"tool": tool, "arguments": arguments}, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        raw = tool + repr(sorted(arguments))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


def file_digest(path: str | Path) -> str | None:
    target = Path(path)
    if not target.is_file():
        return None
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def reserve(task, tool: str, arguments: dict, effect: str, *, step: str = "", target: str = "",
            before_hash: str | None = None, intended_hash: str | None = None) -> dict:
    if effect not in EFFECT_CLASSES:
        raise ValueError("Unknown effect class")
    receipt = {"id": uuid.uuid4().hex, "step": step, "tool": tool, "effect": effect,
               "digest": argument_digest(tool, arguments), "target": str(target)[:1000],
               "before_hash": before_hash, "intended_hash": intended_hash,
               "state": RESERVED, "reserved_at": now_iso(), "settled_at": None, "evidence": {}}
    task.receipts.append(receipt)
    del task.receipts[:-200]
    return receipt


def settle(receipt: dict, state: str, **evidence) -> dict:
    if state not in {COMPLETED, FAILED, UNCERTAIN, NOT_APPLIED}:
        raise ValueError("Unknown receipt state")
    receipt["state"] = state
    receipt["settled_at"] = now_iso()
    receipt["evidence"].update({k: v for k, v in evidence.items() if v is not None})
    return receipt


def completed_effect(task, tool: str, arguments: dict) -> dict | None:
    """The completed receipt for exactly this effect, if one exists (idempotency)."""
    digest = argument_digest(tool, arguments)
    return next((r for r in reversed(task.receipts) if r["digest"] == digest and r["state"] == COMPLETED), None)


def uncertain(task) -> list[dict]:
    return [r for r in task.receipts if r["state"] == UNCERTAIN]


def reconcile(task) -> dict:
    """Settle reservations left open by a crash or restart, by re-observation only.

    Returns a summary stored as the task's resume_state. Nothing is re-executed.
    """
    summary = {"verified": [], "not_applied": [], "uncertain": [], "processes_ended": []}
    for receipt in task.receipts:
        if receipt["state"] != RESERVED:
            continue
        effect, target = receipt["effect"], receipt.get("target", "")
        if effect == WORKSPACE_WRITE and target:
            current = file_digest(target)
            if receipt.get("intended_hash") and current == receipt["intended_hash"]:
                settle(receipt, COMPLETED, reconciled="hash matches the intended result")
                summary["verified"].append(target)
            elif current == receipt.get("before_hash"):
                # Includes creation that never happened (both None).
                settle(receipt, NOT_APPLIED, reconciled="file unchanged")
                summary["not_applied"].append(target)
            else:
                settle(receipt, UNCERTAIN, reconciled="file differs from both the original and the intended result")
                summary["uncertain"].append(target)
        elif effect in {PROCESS, VALIDATION}:
            # Owned child processes do not survive OLIVE's backend; the outcome
            # of an interrupted build/test is unknown, so it is simply re-run
            # only when a new explicit request asks for it.
            settle(receipt, NOT_APPLIED if effect == VALIDATION else COMPLETED,
                   reconciled="process ended with the application")
            summary["processes_ended"].append(receipt["tool"])
        else:
            settle(receipt, UNCERTAIN, reconciled="outcome could not be re-observed after restart")
            summary["uncertain"].append(receipt.get("target") or receipt["tool"])
    return summary
