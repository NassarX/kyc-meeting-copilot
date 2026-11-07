"""S4 reconcile: the only component that decides a contradiction (invariant I6, design "who decides what").

Pure and deterministic. It compares current facts that share a field and subject (from the transcript, the
dossier stub and the checklist) and reports each group whose values disagree. It never picks a winner: the
service records the contradiction and the RM resolves it.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from kyc_copilot.domain.enums import FactStatus
from kyc_copilot.domain.models import Fact
from kyc_copilot.domain.values import values_match

RECONCILE_VERSION = "reconcile-v0.1"

# Fields where several different values are normal, not a contradiction (a person can hold two nationalities).
MULTI_VALUED = frozenset({"identity.nationality"})


@dataclass(frozen=True)
class Conflict:
    field: str
    subject_ref: str | None
    fact_ids: tuple[str, ...]  # sorted, two or more


def _lineage(fact_id: str, by_id: dict[str, Fact]) -> set[str]:
    seen: set[str] = set()
    cur: str | None = fact_id
    while cur and cur not in seen:
        seen.add(cur)
        f = by_id.get(cur)
        cur = f.supersedes_fact_id if f else None
    return seen


def find_conflicts(all_facts: Sequence[Fact], known: Iterable[frozenset[str]]) -> list[Conflict]:
    """all_facts: every fact of the case, superseded ones included (for lineage).
    known: the original fact IDs of contradictions already recorded; they are never raised again."""
    by_id = {f.fact_id: f for f in all_facts}
    replaced = {f.supersedes_fact_id for f in all_facts if f.supersedes_fact_id}
    current = [f for f in all_facts if f.fact_id not in replaced and f.status not in
               (FactStatus.SUPERSEDED, FactStatus.CONTRADICTED) and f.field not in MULTI_VALUED]
    known = [set(k) for k in known]

    groups: dict[tuple[str, str], list[Fact]] = {}
    for f in current:
        groups.setdefault((f.field, f.subject_ref or ""), []).append(f)

    out = []
    for (field, subject), facts in sorted(groups.items()):
        distinct: list[Fact] = []
        for f in facts:
            if not any(values_match(f.value, d.value) for d in distinct):
                distinct.append(f)
        if len(distinct) < 2:
            continue
        ids = sorted(f.fact_id for f in facts)
        if any(all(_lineage(i, by_id) & k for i in ids) for k in known):
            continue  # this disagreement is already on record
        out.append(Conflict(field=field, subject_ref=subject or None, fact_ids=tuple(ids)))
    return out
