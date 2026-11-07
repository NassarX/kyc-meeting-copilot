import pytest

from kyc_copilot.domain.enums import CaseState as S, GateKind, Purpose, Role
from kyc_copilot.domain.models import GateEvent
from kyc_copilot.service import CaseService, FactRejected, GateRejected
from kyc_copilot.store.base import GateConflict
from kyc_copilot.store.sqlite import SQLiteStore
from kyc_copilot.workflow.state_machine import IllegalTransition
from conftest import AGENT, AS_OF, RM, ROLES, make_fact


def to_rm_gate(service, case_id):
    for trig in ("dossier_built", "transcript_ingested", "facts_extracted", "presubmit_check_completed",
                 "ready_for_rm_gate"):
        service.advance(case_id, trig, AGENT)


def rm_gate(case_id, actor="rm.alice", **kw):
    return GateEvent(case_id=case_id, gate=GateKind.RM, actor_id=actor, role=Role.RM,
                     decision="submit", rule_version="rules-0", **kw)


def co_gate(case_id, actor="co.carla", decision="approve", **kw):
    return GateEvent(case_id=case_id, gate=GateKind.COMPLIANCE, actor_id=actor, role=Role.COMPLIANCE,
                     decision=decision, reason_text="SoW narrative supported by evidence", rule_version="rules-0", **kw)


def to_compliance_gate(service, case_id):
    to_rm_gate(service, case_id)
    service.record_gate(rm_gate(case_id))
    for trig in ("analysis_started", "analysis_joined", "check_completed", "sent_for_review"):
        service.advance(case_id, trig, AGENT)


def actions(service, case_id):
    return [e.action for e in service.store.audit(case_id)]


def test_end_to_end_happy_path_is_fully_audited(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    to_compliance_gate(service, case.case_id)
    assert service.record_gate(co_gate(case.case_id)) is S.APPROVED
    acts = actions(service, case.case_id)
    assert acts[0] == "case_created"
    assert acts.count("gate_decision") == 2
    assert acts.count("transition") == 9  # beta 0 adds presubmit_checked to the route


def test_rejected_transition_is_audited(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    with pytest.raises(IllegalTransition):
        service.advance(case.case_id, "sent_for_review", AGENT)
    assert actions(service, case.case_id)[-1] == "transition_rejected"
    assert service.state(case.case_id) is S.CREATED


def test_invariant_I4_cannot_skip_rm_gate(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    to_rm_gate(service, case.case_id)
    for trig in ("analysis_started", "sent_for_review", "check_completed"):
        with pytest.raises(IllegalTransition):
            service.advance(case.case_id, trig, AGENT)
    with pytest.raises(IllegalTransition):
        service.advance(case.case_id, "gate", AGENT)
    assert service.state(case.case_id) is S.AWAITING_RM_CONFIRMATION


def test_invariant_I4_forged_role_rejected_and_audited(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    to_compliance_gate(service, case.case_id)
    with pytest.raises(GateRejected, match="does not hold role"):
        service.record_gate(co_gate(case.case_id, actor="rm.bob"))  # an RM claiming compliance
    assert actions(service, case.case_id)[-1] == "gate_rejected"
    assert service.state(case.case_id) is S.AWAITING_COMPLIANCE_REVIEW


def test_invariant_I11_rm_cannot_approve_own_case(service):
    case = service.open_case("lead-001", "dual.dana", AS_OF)  # dana holds RM and compliance roles
    to_rm_gate(service, case.case_id)
    service.record_gate(rm_gate(case.case_id, actor="dual.dana"))
    for trig in ("analysis_started", "analysis_joined", "check_completed", "sent_for_review"):
        service.advance(case.case_id, trig, AGENT)
    with pytest.raises(GateRejected, match="I11"):
        service.record_gate(co_gate(case.case_id, actor="dual.dana"))
    assert service.record_gate(co_gate(case.case_id, actor="co.carla")) is S.APPROVED


def test_only_the_cases_rm_submits_rm_gate(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    to_rm_gate(service, case.case_id)
    with pytest.raises(GateRejected, match="case's RM"):
        service.record_gate(rm_gate(case.case_id, actor="rm.bob"))


def test_gate_at_wrong_state_rejected_and_not_stored(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    g = rm_gate(case.case_id)
    with pytest.raises(GateRejected):
        service.record_gate(g)  # case is still 'created'
    assert service.store.get_gate_event(g.gate_id) is None


def test_gate_replay_is_idempotent(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    to_rm_gate(service, case.case_id)
    g = rm_gate(case.case_id)
    assert service.record_gate(g) is S.FACTS_CONFIRMED
    assert service.record_gate(g) is S.FACTS_CONFIRMED  # replay: no second transition
    assert actions(service, case.case_id).count("gate_decision") == 1
    with pytest.raises(GateConflict):
        service.record_gate(g.model_copy(update={"fact_ids_relied_on": ("f-tampered",)}))


def test_return_then_rework_then_approve(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    to_compliance_gate(service, case.case_id)
    assert service.record_gate(co_gate(case.case_id, decision="return")) is S.RETURNED_TO_RM
    service.advance(case.case_id, "rework_started", RM)
    assert service.state(case.case_id) is S.FACTS_EXTRACTED  # D15: re-checked before the RM gate


def test_suspend_resume_via_service(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    service.advance(case.case_id, "dossier_built", AGENT)
    op = AGENT.model_copy(update={"id": "op.omar"})
    assert service.advance(case.case_id, "suspend", op) is S.SUSPENDED
    assert service.advance(case.case_id, "resume", op) is S.DOSSIER_READY


def test_invariant_I9_advice_purpose_refused_in_poc(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    with pytest.raises(FactRejected, match="purpose"):
        service.add_fact(make_fact(case.case_id, purpose=(Purpose.AML, Purpose.ADVICE)), AGENT)
    assert actions(service, case.case_id)[-1] == "fact_rejected"


def test_fact_checked_against_taxonomy(service):
    case = service.open_case("lead-001", "rm.alice", AS_OF)
    with pytest.raises(FactRejected, match="unknown field"):
        service.add_fact(make_fact(case.case_id, field="nope"), AGENT)
    f = service.add_fact(make_fact(case.case_id), AGENT)
    assert service.store.facts(case.case_id) == [f]


def test_supersede_must_be_same_case(service):
    a = service.open_case("lead-a", "rm.alice", AS_OF)
    b = service.open_case("lead-b", "rm.alice", AS_OF)
    fa = service.add_fact(make_fact(a.case_id), AGENT)
    with pytest.raises(FactRejected, match="superseded"):
        service.add_fact(make_fact(b.case_id, supersedes_fact_id=fa.fact_id), AGENT)


def test_open_case_requires_rm(service):
    with pytest.raises(PermissionError):
        service.open_case("lead-1", "co.carla", AS_OF)


def test_state_survives_restart(tmp_path, taxonomy):
    """Mini crash drill: a fresh service on the same file sees the same state and history."""
    db = tmp_path / "cases.db"
    s1 = CaseService(SQLiteStore(db), taxonomy, ROLES)
    case = s1.open_case("lead-001", "rm.alice", AS_OF)
    to_rm_gate(s1, case.case_id)
    n_events = len(s1.store.audit(case.case_id))
    s2 = CaseService(SQLiteStore(db), taxonomy, ROLES)
    assert s2.state(case.case_id) is S.AWAITING_RM_CONFIRMATION
    assert len(s2.store.audit(case.case_id)) == n_events
