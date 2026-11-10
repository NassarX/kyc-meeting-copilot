"""Bounded windows for long transcripts (hardening, item 6).

A long meeting is shown to the model in windows that each fit a character budget, cut at turn boundaries. A turn too
long for one window is split at sentence boundaries (then words); each piece keeps the turn's id and speaker, so the
model's quotes are still checked against the full original turn. Every turn lands in exactly one window, in order.

Adapted from gbrain (src/core/facts/conversation-windows.ts), MIT License, Copyright (c) 2026 Garry Tan.
https://github.com/garrytan/gbrain
"""
from __future__ import annotations

import re

from kyc_copilot.eval.case_format import Transcript, Utterance

OVERHEAD = 12  # rendered "u-01 [rm]: " prefix, approximately


def _pieces(u: Utterance, budget: int) -> list[Utterance]:
    room = max(budget - OVERHEAD, 20)
    if len(u.text) <= room:
        return [u]
    parts, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", u.text):
        for word in ([sentence] if len(sentence) <= room else sentence.split()):
            if cur and len(cur) + 1 + len(word) > room:
                parts.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
    if cur:
        parts.append(cur)
    return [Utterance(utt_id=u.utt_id, speaker=u.speaker, text=p) for p in parts]


def split(transcript: Transcript, budget: int) -> list[Transcript]:
    if sum(len(u.text) + OVERHEAD for u in transcript.utterances) <= budget:
        return [transcript]
    windows: list[list[Utterance]] = [[]]
    used = 0
    for u in transcript.utterances:
        for piece in _pieces(u, budget):
            size = len(piece.text) + OVERHEAD
            if windows[-1] and used + size > budget:
                windows.append([])
                used = 0
            windows[-1].append(piece)
            used += size
    return [Transcript(meeting_date=transcript.meeting_date, utterances=tuple(w)) for w in windows if w]
