"""Beta 0 service: atomic writes, audits that survive rollback, contradictions and the RM loop."""
from datetime import date
from decimal import Decimal

import pytest

from kyc_copilot.domain.enums import CaseState as S, FactStatus, GateKind, Role, SourceType
from kyc_copilot.domain.models import Actor, ChecklistItem, GateEvent, Money, Provenance, Text
from kyc_copilot.service import CaseService, FactRejected, GateRejected, input_hash
from kyc_copilot.store.sqlite import TABLES
from kyc_copilot.workflow.state_machine import IllegalTransition
from conftest import AGENT, AS_OF, RM, ROLES, make_fact

BOB = Actor(kind="human", id="rm.bob", role=Role.RM)
RECONCILE = Actor(kind="agent_step", id="S4_reconcile")


class Crash(Exception):
    pass


def rows(service) -> dict[str, int]:
    return {t: service.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def actions(service, case_id):
    return [e.action for e in service.store.audit(case_id)]


def to_check(service, case_id):
    for trig in ("dossier_built", "transcript_ingested", "facts_extracted", "presubmit_check_completed"):
        service.advance(case_id, trig, AGENT)


def rm_submit(case_id, actor_id="rm.alice"):
    return GateEvent(case_id=case_id, gate=GateKind.RM, actor_id=actor_id, role=Role.RM, decision="submit",
                     rule_version="r0")


def money(v):
    return Money(amount=Decimal(v), currency="EUR")


@pytest.fixture
def case(service):
    return service.open_case("lead-001", "rm.alice", AS_OF)


@pytest.fixture
def contradiction(service, case):
    a = service.add_fact(make_fact(case.case_id, value=money("2400000")), AGENT)
    b = service.add_fact(make_fact(case.case_id, value=money("2100000")), AGENT)
    k = service.record_contradiction(case.case_id, "wealth_event.amount", (a.fact_id, b.fact_id), "recon-v0",
                                     RECONCILE, subject_ref="wealth_event/1")
    return k, a, b


# ---------- crash injection: every write path is all-or-nothing (D5) ----------

def crash_on(monkeypatch, service, method):
    def boom(*a, **kw):
        raise Crash
    monkeypatch.setattr(service.store, method, boom)


def test_open_case_crash_leaves_nothing(service, monkeypatch):
    before = rows(service)
    crash_on(monkeypatch, service, "append_transition")
    with pytest.raises(Crash):
        service.open_case("lead-x", "rm.alice", AS_OF)
    assert rows(service) == before


def test_advance_crash_leaves_nothing(service, case, monkeypatch):
    before = rows(service)
    crash_on(monkeypatch, service, "append_transition")
    with pytest.raises(Crash):
        service.advance(case.case_id, "dossier_built", AGENT)
    assert rows(service) == before and service.state(case.case_id) is S.CREATED


def test_record_gate_crash_leaves_nothing(service, case, monkeypatch):
    to_check(service, case.case_id)
    service.advance(case.case_id, "ready_for_rm_gate", RM)
    before = rows(service)
    crash_on(monkeypatch, service, "append_transition")
    with pytest.raises(Crash):
        service.record_gate(rm_submit(case.case_id))
    assert rows(service) == before  # no gate event stored without its transition


def test_add_fact_crash_leaves_nothing(service, case, monkeypatch):
    before = rows(service)
    crash_on(monkeypatch, service, "append_audit")
    with pytest.raises(Crash):
        service.add_fact(make_fact(case.case_id), AGENT)
    assert rows(service) == before  # no fact stored without its audit


def test_load_checklist_crash_leaves_nothing(service, case, monkeypatch):
    before = rows(service)
    crash_on(monkeypatch, service, "append_audit")
    with pytest.raises(Crash):
        service.load_checklist(case.case_id, [ChecklistItem(item_id="chk-01", document_type="passport",
                                                            present=True)], AGENT)
    assert rows(service) == before


def test_record_contradiction_crash_leaves_nothing(service, case, monkeypatch):
    a = service.add_fact(make_fact(case.case_id, value=money("1")), AGENT)
    b = service.add_fact(make_fact(case.case_id, value=money("2")), AGENT)
    before = rows(service)
    crash_on(monkeypatch, service, "append_contradiction")
    with pytest.raises(Crash):
        service.record_contradiction(case.case_id, "wealth_event.amount", (a.fact_id, b.fact_id), "r", RECONCILE)
    assert rows(service) == before  # no half-superseded facts


# ---------- rejection audits survive the rollback (D11) ----------

def test_rejected_transition_rolls_back_but_keeps_its_audit(service, case):
    with pytest.raises(IllegalTransition):
        service.advance(case.case_id, "sent_for_review", AGENT)
    assert actions(service, case.case_id)[-1] == "transition_rejected"
    assert not service.store.conn.in_transaction


def test_rejected_fact_keeps_its_audit(service, case):
    with pytest.raises(FactRejected):
        service.add_fact(make_fact(case.case_id, field="client.favourite_colour"), AGENT)
    assert actions(service, case.case_id)[-1] == "fact_rejected"
    assert service.store.facts(case.case_id) == []


# ---------- G1 waits for every contradiction to be resolved ----------

def test_g1_refused_while_a_contradiction_is_unresolved(service, case, contradiction):
    to_check(service, case.case_id)
    service.advance(case.case_id, "ready_for_rm_gate", RM)
    with pytest.raises(GateRejected, match="unresolved contradiction"):
        service.record_gate(rm_submit(case.case_id))
    assert actions(service, case.case_id)[-1] == "gate_rejected"
    assert service.state(case.case_id) is S.AWAITING_RM_CONFIRMATION


def test_open_for_compliance_counts_as_resolved(service, case, contradiction):
    k, _, _ = contradiction
    service.resolve_contradiction(k.contradiction_id, "open", None, "ask compliance", RM)
    to_check(service, case.case_id)
    service.advance(case.case_id, "ready_for_rm_gate", RM)
    assert service.record_gate(rm_submit(case.case_id)) is S.FACTS_CONFIRMED


# ---------- recording a contradiction (D4) ----------

def test_contradiction_supersedes_each_fact_with_a_contradicted_copy(service, case, contradiction):
    k, a, b = contradiction
    current = service.store.facts(case.case_id)
    assert {f.supersedes_fact_id for f in current} == {a.fact_id, b.fact_id}
    assert all(f.status is FactStatus.CONTRADICTED for f in current)
    assert {f.value for f in current} == {a.value, b.value}  # both values kept
    assert service.open_contradictions(case.case_id) == [k]


def test_contradiction_needs_facts_from_this_case(service, case):
    other = service.open_case("lead-2", "rm.alice", AS_OF)
    a = service.add_fact(make_fact(case.case_id), AGENT)
    b = service.add_fact(make_fact(other.case_id), AGENT)
    with pytest.raises(FactRejected):
        service.record_contradiction(case.case_id, "wealth_event.amount", (a.fact_id, b.fact_id), "r", RECONCILE)


# ---------- resolutions: only the case RM ----------

def test_only_the_case_rm_can_resolve(service, case, contradiction):
    k, a, _ = contradiction
    with pytest.raises(PermissionError):
        service.resolve_contradiction(k.contradiction_id, "stands", a.fact_id, "x", BOB)
    with pytest.raises(PermissionError):
        service.resolve_contradiction(k.contradiction_id, "open", None, "x", AGENT)
    assert actions(service, case.case_id)[-1] == "resolution_rejected"
    assert service.open_contradictions(case.case_id) == [k]


def test_standing_fact_must_be_one_of_the_contradicted_facts(service, case, contradiction):
    k, _, _ = contradiction
    stranger = service.add_fact(make_fact(case.case_id, field="identity.full_name", subject_ref=None,
                                          value=Text(value="X")),
                                AGENT)
    with pytest.raises(FactRejected, match="not part of"):
        service.resolve_contradiction(k.contradiction_id, "stands", stranger.fact_id, "x", RM)


def test_standing_fact_may_be_the_contradicted_copy(service, case, contradiction):
    k, a, _ = contradiction
    copy_of_a = next(f for f in service.store.facts(case.case_id) if f.supersedes_fact_id == a.fact_id)
    service.resolve_contradiction(k.contradiction_id, "stands", copy_of_a.fact_id, "registry stub", RM)
    assert service.open_contradictions(case.case_id) == []


# ---------- D13: an RM fix of a contradicted fact resolves it ----------

def test_rm_superseding_a_contradicted_fact_auto_resolves(service, case, contradiction):
    k, a, _ = contradiction
    copy_of_a = next(f for f in service.store.facts(case.case_id) if f.supersedes_fact_id == a.fact_id)
    fix = make_fact(case.case_id, value=money("2100000"), supersedes_fact_id=copy_of_a.fact_id,
                    provenance=(_rm_prov(),), created_by="rm.alice")
    service.add_fact(fix, RM)
    (res,) = service.store.resolutions(case.case_id)
    assert res.contradiction_id == k.contradiction_id and res.outcome == "stands"
    assert res.standing_fact_id == fix.fact_id and res.actor_id == "rm.alice"
    assert service.open_contradictions(case.case_id) == []


def test_agent_superseding_a_contradicted_fact_does_not_resolve(service, case, contradiction):
    _, a, _ = contradiction
    copy_of_a = next(f for f in service.store.facts(case.case_id) if f.supersedes_fact_id == a.fact_id)
    service.add_fact(make_fact(case.case_id, supersedes_fact_id=copy_of_a.fact_id), AGENT)
    assert service.store.resolutions(case.case_id) == []


def _rm_prov():
    return Provenance(source_type=SourceType.RM_ENTRY, source_ref="rm.alice", extractor_version="rm_entry")


# ---------- D14: rm_fixed, attempts, input hash ----------

def test_only_the_case_rm_fires_rm_fixed(service, case):
    to_check(service, case.case_id)
    for who in (BOB, AGENT):
        with pytest.raises(PermissionError):
            service.advance(case.case_id, "rm_fixed", who)
        assert actions(service, case.case_id)[-1] == "transition_rejected"
    assert service.state(case.case_id) is S.PRESUBMIT_CHECKED
    assert service.advance(case.case_id, "rm_fixed", RM) is S.FACTS_EXTRACTED


def test_attempt_counts_rm_fixed_rounds(service, case):
    assert service.attempt(case.case_id) == 0
    to_check(service, case.case_id)
    service.advance(case.case_id, "rm_fixed", RM)
    service.advance(case.case_id, "presubmit_check_completed", AGENT)
    service.advance(case.case_id, "rm_fixed", RM)
    assert service.attempt(case.case_id) == 2


def test_input_hash_is_canonical():
    h1 = input_hash({"b": 1, "a": [1, 2]}, model_id="m", prompt_version="p")
    h2 = input_hash({"a": [1, 2], "b": 1}, model_id="m", prompt_version="p")
    assert h1 == h2 and len(h1) == 64
    assert h1 != input_hash({"a": [1, 2], "b": 1}, model_id="m", prompt_version="p2")
    assert h1 != input_hash({"a": [2, 1], "b": 1}, model_id="m", prompt_version="p")


# ---------- D16: document facts come from the checklist ----------

def test_checklist_is_stored_and_derives_document_facts(service, case):
    item = ChecklistItem(item_id="chk-01", document_type="passport", present=True,
                         issue_date=date(2016, 10, 1), expiry_date=date(2026, 10, 1))
    facts = service.load_checklist(case.case_id, [item], AGENT)
    assert service.store.checklist(case.case_id) == [item]
    assert {f.field for f in facts} == {"document.type", "document.present", "document.issue_date",
                                        "document.expiry_date"}
    for f in facts:
        assert f.subject_ref == "document/chk-01"
        (p,) = f.provenance
        assert p.source_type is SourceType.DOCUMENT and p.source_ref == "chk-01"
        assert p.extractor_version.startswith("checklist-loader-") and p.run_id is None


def test_missing_dates_derive_no_date_facts(service, case):
    facts = service.load_checklist(case.case_id, [ChecklistItem(item_id="chk-02", document_type="sale_agreement",
                                                                present=False)], AGENT)
    assert {f.field for f in facts} == {"document.type", "document.present"}


def test_unknown_document_type_rejects_the_whole_checklist(service, case):
    items = [ChecklistItem(item_id="chk-01", document_type="passport", present=True),
             ChecklistItem(item_id="chk-02", document_type="selfie", present=True)]
    with pytest.raises(FactRejected, match="selfie"):
        service.load_checklist(case.case_id, items, AGENT)
    assert service.store.checklist(case.case_id) == [] and service.store.facts(case.case_id) == []
    assert actions(service, case.case_id)[-1] == "checklist_rejected"


def test_checklist_facts_feed_the_expiry_rule(service, case, taxonomy):
    from kyc_copilot.rules import evaluate, load_bounce_reasons
    service.load_checklist(case.case_id, [ChecklistItem(item_id="chk-01", document_type="passport", present=True,
                                                        expiry_date=date(2026, 10, 1))], AGENT)
    results = {r.reason_id: r.outcome for r in evaluate(load_bounce_reasons(taxonomy),
                                                        service.store.facts(case.case_id), case.as_of_date)}
    assert results["BR-DOC-ID-EXPIRED"] == "fire" and results["BR-DOC-ID-MISSING"] == "pass"
