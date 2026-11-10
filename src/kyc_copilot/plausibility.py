"""Plausibility check (8 Nov 2026, after a noisy test case): facts that can't all be true get a doubt, so a wrong value
needs the RM's confirmation instead of passing silently.

Pure, like reconcile. Only general KYC logic, never tailored to a case. Each doubt names every fact involved,
because the wrong one could be any of them. Guards: the gold answers of every frozen case raise no doubt (tested),
and the scorecard counts doubts on correct facts as false warnings, so warning on everything can't game the score.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from kyc_copilot.domain.enums import FactStatus
from kyc_copilot.domain.models import Fact

PLAUSIBILITY_VERSION = "plausibility-v0.2"  # v0.2: low model confidence; superseded answers ignored
LOW_CONFIDENCE = 0.7
ADULT, OLDEST = 18, 110
_DATED = ("wealth_event.date", "structure.established", "identity.residence_since")


@dataclass(frozen=True)
class Doubt:
    fact_ids: tuple[str, ...]
    rule: str
    message: str


def _date(f: Fact) -> date | None:
    v = f.value
    return getattr(v, "value", None) if v.kind == "date" else getattr(v, "resolved", None) if v.kind == "relative_date" \
        else None


def _age(born: date, on: date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def check(facts: Sequence[Fact], as_of: date) -> list[Doubt]:
    doubts: list[Doubt] = []
    facts = [f for f in facts if f.status is not FactStatus.SUPERSEDED]  # an earlier answer is history, not a value

    # 0. The extractor itself was unsure (hedged, garbled, inferred speaker): the RM confirms it.
    for f in facts:
        if f.confidence < LOW_CONFIDENCE:
            doubts.append(Doubt((f.fact_id,), "low_confidence", f"{f.field}: the extraction was unsure of this value "
                                f"(confidence {f.confidence:.2f})"))

    # 1. The client plans to invest more than every stated source and asset adds up to, in that currency.
    sources: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        if f.field in ("wealth_event.amount", "asset.value") and f.value.kind == "money":
            sources[f.value.currency].append(f)
    for f in facts:
        if f.field == "expected.initial_funding_amount" and f.value.kind == "money":
            have = sources.get(f.value.currency, [])
            if have and f.value.amount > sum((s.value.amount for s in have), Decimal(0)):
                doubts.append(Doubt((f.fact_id, *(s.fact_id for s in have)), "funding_exceeds_sources",
                                    f"funding {f.value.amount} {f.value.currency} is more than all stated sources "
                                    f"and assets in {f.value.currency} add up to"))

    # 2. Past events can't be dated after the meeting.
    for f in facts:
        d = _date(f) if f.field in _DATED else None
        if d is not None and d > as_of:
            doubts.append(Doubt((f.fact_id,), "date_in_future", f"{f.field} {d} is after the meeting date {as_of}"))

    # 3. The client must be an adult of a believable age.
    for f in facts:
        d = _date(f) if f.field == "identity.date_of_birth" else None
        if d is not None and not ADULT <= _age(d, as_of) <= OLDEST:
            doubts.append(Doubt((f.fact_id,), "implausible_age",
                                f"date of birth {d} gives age {_age(d, as_of)} on {as_of}"))
    return doubts
