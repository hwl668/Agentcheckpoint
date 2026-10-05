"""Best-effort secret redaction.

Applied to agent-reported semantic content and recorded command output before
anything is written to disk. Patches are NOT rewritten (that would corrupt
them); instead `scan_for_secrets` powers a warning when a patch looks like it
contains a credential. This is a safety net, not a guarantee.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key-block", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S
    )),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai-style-key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
]


def redact(text: str) -> str:
    for name, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED:{name}]", text)
    return text


def scan_for_secrets(text: str) -> list[str]:
    """Names of redaction patterns present in the text (without rewriting it)."""
    return [name for name, pattern in _PATTERNS if pattern.search(text)]
