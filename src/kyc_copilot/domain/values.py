"""When two fact values say the same thing. One rule shared by reconcile (contradictions) and the eval graders."""
from __future__ import annotations

import re
import unicodedata

from .models import FactValue


def normalize(text: str) -> str:
    """Unicode NFC, whitespace collapsed, case ignored. Used only for comparing, never for storing."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def values_match(a: FactValue, b: FactValue) -> bool:
    """Exact match on typed values, with text and dates normalised (docs/spec.md)."""
    dates = {"date": lambda v: v.value, "relative_date": lambda v: v.resolved}
    if a.kind in dates and b.kind in dates:
        da, db = dates[a.kind](a), dates[b.kind](b)
        if da is not None and db is not None:
            return da == db
        return a.kind == b.kind == "relative_date" and normalize(a.words) == normalize(b.words)  # type: ignore[union-attr]
    if a.kind != b.kind:
        return False
    if a.kind == "text":
        return normalize(a.value) == normalize(b.value)  # type: ignore[union-attr]
    return a == b
