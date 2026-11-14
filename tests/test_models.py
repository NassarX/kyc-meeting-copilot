from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kyc_copilot.domain.enums import GateKind, Role, SourceType
from kyc_copilot.domain.models import Actor, Case, GateEvent, Money, Provenance
from conftest import make_fact


def test_invariant_I1_fact_without_provenance_is_rejected():
    with pytest.raises(ValidationError):
        make_fact("case-x", provenance=())


def test_transcript_provenance_must_cite_an_utterance():
    with pytest.raises(ValidationError):
        Provenance(source_type=SourceType.TRANSCRIPT, source_ref="t", extractor_version="v")


def test_dossier_provenance_needs_no_span():
    Provenance(source_type=SourceType.DOSSIER, source_ref="stub/registry/123", extractor_version="v")


def test_invariant_I9_fact_without_purpose_is_rejected():
    with pytest.raises(ValidationError):
        make_fact("case-x", purpose=())


def test_invariant_I12_non_synthetic_case_is_rejected():
    with pytest.raises(ValidationError):
        Case(lead_ref="lead-1", rm_id="rm.alice", as_of_date=date(2026, 11, 1), synthetic=False)


@pytest.mark.parametrize("currency", ["eur", "EURO", "E1R", ""])
def test_money_requires_iso_currency(currency):
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1"), currency=currency)


def test_records_are_frozen():
    f = make_fact("case-x")
    with pytest.raises(ValidationError):
        f.confidence = 0.1  # type: ignore[misc]


def test_unknown_fields_are_forbidden():
    with pytest.raises(ValidationError):
        make_fact("case-x", score=99)


def test_human_actor_needs_role():
    with pytest.raises(ValidationError):
        Actor(kind="human", id="x")


def gate(**kw):
    base = dict(case_id="c", gate=GateKind.COMPLIANCE, actor_id="co.carla", role=Role.COMPLIANCE,
                decision="approve", reason_text="SoW evidenced by sale agreement", rule_version="rules-0")
    base.update(kw)
    return GateEvent(**base)


def test_compliance_gate_needs_reason():
    with pytest.raises(ValidationError):
        gate(reason_text="   ")


def test_gate_decision_must_fit_gate():
    with pytest.raises(ValidationError):
        gate(decision="submit")
    with pytest.raises(ValidationError):
        gate(gate=GateKind.RM, role=Role.RM, decision="approve")


def test_gate_role_must_fit_gate():
    with pytest.raises(ValidationError):
        gate(role=Role.RM)
