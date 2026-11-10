"""Prompt-injection guard for transcripts (hardening, item 1).

A transcript is untrusted input: anyone in the meeting, or a planted recording, can say an instruction. The model's
copy of the transcript is wrapped in <transcript> tags marked as data, and known attack phrases are neutralised in that
copy only. The stored transcript is never rewritten, and every quote is checked against the raw text, so a quote the
model copied from the neutralised copy is rejected rather than stored.

Patterns ported from gbrain (src/core/think/sanitize.ts, INJECTION_PATTERNS), MIT License, Copyright (c) 2026
Garry Tan. https://github.com/garrytan/gbrain
"""
from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple((re.compile(rx, flags), repl) for rx, flags, repl in (
    (r"ignore\s+(?:all\s+)?(?:prior|previous|above|earlier)\s+(?:instructions?|prompts?|messages?)", re.I, "[redacted]"),
    (r"forget\s+(?:everything|all\s+(?:of\s+)?the\s+above)", re.I, "[redacted]"),
    (r"disregard\s+(?:all\s+)?(?:prior|previous|above|earlier)\s+(?:instructions?|prompts?)", re.I, "[redacted]"),
    (r"(?:new|updated|revised)\s+instructions?:", re.I, "[redacted]:"),
    (r"system\s*:\s*(?:you\s+are|you\s+must|never|always)", re.I, "[redacted]"),
    (r"you\s+are\s+(?:now|actually|really)\s+(?:a|an)\s+\w+", re.I, "[redacted]"),
    (r"\bDAN\b", 0, "[redacted]"),
    (r"\b(?:do\s+anything\s+now|developer\s+mode\s+enabled?)\b", re.I, "[redacted]"),
    (r"<\s*/?\s*transcript\s*>", re.I, "[tag]"),  # can't close or reopen the data wrapper
))


def neutralize(text: str) -> str:
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text
