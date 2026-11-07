from datetime import date
from decimal import Decimal

import pytest

from kyc_copilot.domain.enums import Purpose, Role, SourceType
from kyc_copilot.domain.models import Actor, Fact, Money, Provenance, SpanOffset, Text
from kyc_copilot.service import CaseService
from kyc_copilot.store.sqlite import SQLiteStore
from kyc_copilot.taxonomy import load_taxonomy

# Synthetic people only (I12).
ROLES = {
    "rm.alice": frozenset({Role.RM}),
    "rm.bob": frozenset({Role.RM}),
    "co.carla": frozenset({Role.COMPLIANCE}),
    "dual.dana": frozenset({Role.RM, Role.COMPLIANCE}),  # holds both roles: used to test I11
    "op.omar": frozenset({Role.OPERATOR}),
}
AS_OF = date(2026, 11, 1)  # every test case is judged on this date (D8)
RM = Actor(kind="human", id="rm.alice", role=Role.RM)
AGENT = Actor(kind="agent_step", id="S3_extract")


@pytest.fixture
def taxonomy():
    return load_taxonomy()


@pytest.fixture
def store():
    return SQLiteStore()


@pytest.fixture
def service(store, taxonomy):
    return CaseService(store, taxonomy, ROLES)


def transcript_prov(*utts: str) -> Provenance:
    offsets = tuple(SpanOffset(utt_id=u, start=0, end=1) for u in (utts or ("u-01",)))
    return Provenance(source_type=SourceType.TRANSCRIPT, source_ref="transcript/v1",
                      span_offsets=offsets, extractor_version="extract-v0")


def make_fact(case_id: str, **kw) -> Fact:
    base = dict(
        case_id=case_id, field="wealth_event.amount", subject_ref="wealth_event/1",
        value=Money(amount=Decimal("2400000"), currency="EUR"), confidence=0.9,
        purpose=(Purpose.AML,), provenance=(transcript_prov("u-07"),), created_by="S3_extract",
    )
    base.update(kw)
    return Fact(**base)
