import itertools

import pytest

from kyc_copilot.domain.enums import CaseState as S, GateKind, Role
from kyc_copilot.domain.models import GateEvent
from kyc_copilot.workflow.state_machine import (
    ALL_TRIGGERS, GATE_STATES, GATE_TRANSITIONS, GLOBAL, TERMINAL, TRANSITIONS, IllegalTransition, next_state,
)


def rm_submit():
    return GateEvent(case_id="c", gate=GateKind.RM, actor_id="rm.alice", role=Role.RM,
                     decision="submit", rule_version="r0")


def compliance(decision):
    return GateEvent(case_id="c", gate=GateKind.COMPLIANCE, actor_id="co.carla", role=Role.COMPLIANCE,
                     decision=decision, reason_text="reason", rule_version="r0")


HAPPY = [
    ("dossier_built", S.DOSSIER_READY), ("transcript_ingested", S.TRANSCRIPT_INGESTED),
    ("facts_extracted", S.FACTS_EXTRACTED), ("presubmit_check_completed", S.PRESUBMIT_CHECKED),
    ("ready_for_rm_gate", S.AWAITING_RM_CONFIRMATION),
]


def test_happy_path_to_approved():
    s = S.CREATED
    for trig, expected in HAPPY:
        s = next_state(s, trig)
        assert s is expected
    s = next_state(s, "gate", gate_event=rm_submit())
    assert s is S.FACTS_CONFIRMED
    for trig in ("analysis_started", "analysis_joined", "check_completed", "sent_for_review"):
        s = next_state(s, trig)
    assert s is S.AWAITING_COMPLIANCE_REVIEW
    assert next_state(s, "gate", gate_event=compliance("approve")) is S.APPROVED


def test_every_plain_trigger_outside_the_table_is_refused():
    """Exhaustive: every (state, plain trigger) pair not in the table or GLOBAL raises."""
    plain = ALL_TRIGGERS - {"gate", "resume"}
    for state, trig in itertools.product(S, plain):
        allowed = state not in TERMINAL and state is not S.SUSPENDED and (
            (state, trig) in TRANSITIONS or trig in GLOBAL)
        allowed = allowed or (state is S.SUSPENDED and trig == "fail")
        if allowed:
            next_state(state, trig)
        else:
            with pytest.raises(IllegalTransition):
                next_state(state, trig)


def test_invariant_I4_gate_states_exit_only_by_gate_or_global():
    for state in GATE_STATES:
        exits = {t for (s, t) in TRANSITIONS if s is state}
        assert exits == set(), f"{state} has a non-gate exit: {exits}"


def test_invariant_I4_gate_trigger_needs_event():
    with pytest.raises(IllegalTransition):
        next_state(S.AWAITING_RM_CONFIRMATION, "gate")


def test_gate_event_for_wrong_gate_is_refused():
    with pytest.raises(IllegalTransition):
        next_state(S.AWAITING_RM_CONFIRMATION, "gate", gate_event=compliance("approve"))
    with pytest.raises(IllegalTransition):
        next_state(S.AWAITING_COMPLIANCE_REVIEW, "gate", gate_event=rm_submit())


def test_gate_event_outside_gate_state_is_refused():
    with pytest.raises(IllegalTransition):
        next_state(S.ANALYSING, "gate", gate_event=compliance("approve"))


@pytest.mark.parametrize("decision,expected", [
    ("approve", S.APPROVED), ("amend", S.APPROVED), ("return", S.RETURNED_TO_RM), ("escalate", S.ESCALATED)])
def test_compliance_decisions(decision, expected):
    assert next_state(S.AWAITING_COMPLIANCE_REVIEW, "gate", gate_event=compliance(decision)) is expected


def test_return_goes_back_through_the_check():
    """D15: rework re-enters at facts_extracted, so a returned file is re-checked before the RM gate."""
    assert next_state(S.RETURNED_TO_RM, "rework_started") is S.FACTS_EXTRACTED


# ---------- beta 0 pre-submission check and fix loop (D2, D3) ----------

def test_fix_loop_runs_before_the_rm_gate():
    s = next_state(S.FACTS_EXTRACTED, "presubmit_check_completed")
    assert s is S.PRESUBMIT_CHECKED and s not in GATE_STATES  # a working state, not a gate
    assert next_state(s, "rm_fixed") is S.FACTS_EXTRACTED
    assert next_state(s, "ready_for_rm_gate") is S.AWAITING_RM_CONFIRMATION


def test_prompts_issued_is_gone():
    assert "prompts_issued" not in ALL_TRIGGERS
    with pytest.raises(IllegalTransition):
        next_state(S.FACTS_EXTRACTED, "prompts_issued")


def test_rm_fixed_refused_at_the_rm_gate():
    with pytest.raises(IllegalTransition):
        next_state(S.AWAITING_RM_CONFIRMATION, "rm_fixed")


def test_every_route_into_the_rm_gate_passes_the_check():
    """The only plain edge into awaiting_rm_confirmation comes from presubmit_checked,
    and the only edge into presubmit_checked comes from facts_extracted."""
    into_gate = {src for (src, _), dst in TRANSITIONS.items() if dst is S.AWAITING_RM_CONFIRMATION}
    into_check = {src for (src, _), dst in TRANSITIONS.items() if dst is S.PRESUBMIT_CHECKED}
    assert into_gate == {S.PRESUBMIT_CHECKED} and into_check == {S.FACTS_EXTRACTED}


@pytest.mark.parametrize("terminal", sorted(TERMINAL))
def test_terminal_states_refuse_everything(terminal):
    for trig in ALL_TRIGGERS:
        with pytest.raises(IllegalTransition):
            next_state(terminal, trig, gate_event=compliance("approve"), resume_state=S.CREATED)


def test_suspend_and_resume_to_same_state():
    assert next_state(S.ANALYSING, "suspend") is S.SUSPENDED
    assert next_state(S.SUSPENDED, "resume", resume_state=S.ANALYSING) is S.ANALYSING


def test_suspended_refuses_other_triggers():
    for trig in ("suspend", "analysis_joined", "prohibited_rule_fired"):
        with pytest.raises(IllegalTransition):
            next_state(S.SUSPENDED, trig)
    with pytest.raises(IllegalTransition):
        next_state(S.SUSPENDED, "resume", resume_state=None)


def test_resume_only_from_suspended():
    with pytest.raises(IllegalTransition):
        next_state(S.ANALYSING, "resume", resume_state=S.CREATED)


def test_prohibited_rule_blocks_from_any_live_state():
    for state in set(S) - TERMINAL - {S.SUSPENDED}:
        assert next_state(state, "prohibited_rule_fired") is S.BLOCKED
