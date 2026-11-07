"""Case lifecycle (docs/spec.md). The transition table is the only way a case changes state.
No model ever chooses a transition: callers pass a named trigger, and anything not in the table is refused."""
from __future__ import annotations

from kyc_copilot.domain.enums import CaseState as S, GateKind
from kyc_copilot.domain.models import GateEvent

TERMINAL: frozenset[S] = frozenset({S.APPROVED, S.ESCALATED, S.BLOCKED, S.FAILED_NEEDS_HUMAN})
GATE_STATES: frozenset[S] = frozenset({S.AWAITING_RM_CONFIRMATION, S.AWAITING_COMPLIANCE_REVIEW})

# Plain (non-gate) triggers.
TRANSITIONS: dict[tuple[S, str], S] = {
    (S.CREATED, "dossier_built"): S.DOSSIER_READY,
    (S.DOSSIER_READY, "transcript_ingested"): S.TRANSCRIPT_INGESTED,
    (S.TRANSCRIPT_INGESTED, "facts_extracted"): S.FACTS_EXTRACTED,
    # Beta 0 pre-submission check and fix loop. presubmit_checked is a working state,
    # not a gate, so the RM can loop through fixes without touching I4. The old prompts_issued shortcut is gone:
    # every route to the RM gate passes the check.
    (S.FACTS_EXTRACTED, "presubmit_check_completed"): S.PRESUBMIT_CHECKED,
    (S.PRESUBMIT_CHECKED, "rm_fixed"): S.FACTS_EXTRACTED,
    (S.PRESUBMIT_CHECKED, "ready_for_rm_gate"): S.AWAITING_RM_CONFIRMATION,
    (S.FACTS_CONFIRMED, "analysis_started"): S.ANALYSING,
    (S.ANALYSING, "analysis_joined"): S.ANALYSED,
    (S.ANALYSED, "check_completed"): S.CHECKED,
    (S.CHECKED, "sent_for_review"): S.AWAITING_COMPLIANCE_REVIEW,
    (S.RETURNED_TO_RM, "rework_started"): S.FACTS_EXTRACTED,  # D15: a returned file is re-checked
}

# Gate exits: only a valid, signed GateEvent moves a case out of a gate state (I4).
GATE_TRANSITIONS: dict[tuple[S, GateKind, str], S] = {
    (S.AWAITING_RM_CONFIRMATION, GateKind.RM, "submit"): S.FACTS_CONFIRMED,
    (S.AWAITING_COMPLIANCE_REVIEW, GateKind.COMPLIANCE, "approve"): S.APPROVED,
    (S.AWAITING_COMPLIANCE_REVIEW, GateKind.COMPLIANCE, "amend"): S.APPROVED,
    (S.AWAITING_COMPLIANCE_REVIEW, GateKind.COMPLIANCE, "return"): S.RETURNED_TO_RM,
    (S.AWAITING_COMPLIANCE_REVIEW, GateKind.COMPLIANCE, "escalate"): S.ESCALATED,
}

# Allowed from any non-terminal state.
GLOBAL: dict[str, S] = {
    "suspend": S.SUSPENDED,
    "fail": S.FAILED_NEEDS_HUMAN,
    "prohibited_rule_fired": S.BLOCKED,
}

ALL_TRIGGERS: frozenset[str] = frozenset({t for _, t in TRANSITIONS} | set(GLOBAL) | {"gate", "resume"})


class IllegalTransition(Exception):
    pass


def next_state(
    current: S,
    trigger: str,
    *,
    gate_event: GateEvent | None = None,
    resume_state: S | None = None,
) -> S:
    if current in TERMINAL:
        raise IllegalTransition(f"case is terminal ({current}); no trigger allowed")

    if current is S.SUSPENDED:
        if trigger == "resume":
            if resume_state is None or resume_state in TERMINAL or resume_state is S.SUSPENDED:
                raise IllegalTransition("suspended case has no valid state to resume to")
            return resume_state
        if trigger == "fail":
            return S.FAILED_NEEDS_HUMAN
        raise IllegalTransition(f"suspended case accepts only resume or fail, not {trigger!r}")

    if trigger == "resume":
        raise IllegalTransition("resume is only valid from suspended")

    if trigger in GLOBAL:
        return GLOBAL[trigger]

    if trigger == "gate":
        if gate_event is None:
            raise IllegalTransition("gate trigger needs a gate event")
        key = (current, gate_event.gate, gate_event.decision)
        if key not in GATE_TRANSITIONS:
            raise IllegalTransition(f"{gate_event.gate} gate decision {gate_event.decision!r} not valid in {current}")
        return GATE_TRANSITIONS[key]

    if (current, trigger) not in TRANSITIONS:
        raise IllegalTransition(f"trigger {trigger!r} not allowed in state {current}")
    return TRANSITIONS[(current, trigger)]
