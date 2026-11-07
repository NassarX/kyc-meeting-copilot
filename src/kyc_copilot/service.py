"""CaseService: the single entry point that combines the state machine, the store and the audit trail.
Every accepted and every rejected action writes an audit event.

Beta 0: every write runs in one store transaction. A rejection rolls the
whole write back, then its audit is written in a transaction of its own, so the refusal is always on record.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from kyc_copilot.domain.checklist import document_facts
from kyc_copilot.domain.enums import CaseState, FactStatus, GateKind, Purpose, Role
from kyc_copilot.domain.models import (Actor, AuditEvent, Case, ChecklistItem, Contradiction, Fact, Finding, GateEvent,
                                   Resolution, Versions, new_id, utcnow)
from kyc_copilot.reconcile import RECONCILE_VERSION, find_conflicts
from kyc_copilot.rules import BounceReasons, evaluate
from kyc_copilot.store.base import GateConflict, Store
from kyc_copilot.taxonomy import Taxonomy, TaxonomyError
from kyc_copilot.workflow.state_machine import IllegalTransition, next_state

SYSTEM = Actor(kind="system", id="case-service")
T = TypeVar("T")


class GateRejected(Exception):
    pass


class FactRejected(Exception):
    pass


@dataclass(frozen=True)
class CheckReport:
    contradictions: tuple[Contradiction, ...]
    findings: tuple[Finding, ...]


class _Refused(Exception):
    """Internal: carries a refusal out of the transaction so it rolls back before the audit is written."""

    def __init__(self, error: Exception, action: str, reason: str, **audit_kw) -> None:
        super().__init__(reason)
        self.error, self.action, self.reason, self.audit_kw = error, action, reason, audit_kw


def input_hash(inputs: object, *, model_id: str, prompt_version: str) -> str:
    """D14: SHA-256 of canonical JSON (sorted keys, no whitespace) of a step's inputs plus its versions."""
    blob = json.dumps({"inputs": inputs, "model_id": model_id, "prompt_version": prompt_version},
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CaseService:
    def __init__(
        self,
        store: Store,
        taxonomy: Taxonomy,
        role_directory: Mapping[str, frozenset[Role]],
        allowed_purposes: frozenset[Purpose] = frozenset({Purpose.AML}),  # PoC writes AML only (I9)
    ) -> None:
        self.store = store
        self.taxonomy = taxonomy
        self.roles = role_directory
        self.allowed_purposes = allowed_purposes

    # ---- helpers ----
    def _audit(self, case_id: str, actor: Actor, action: str, **kw) -> AuditEvent:
        evt = AuditEvent(case_id=case_id, actor=actor, action=action,
                         versions=kw.pop("versions", Versions(taxonomy=self.taxonomy.version)), **kw)
        self.store.append_audit(evt)
        return evt

    def _write(self, case_id: str | None, actor: Actor, body: Callable[[], T]) -> T:
        """Run body in one transaction. On a refusal: roll back, then audit the refusal on its own.
        If a caller wraps this in an outer transaction, that caller owns the same rule (D11)."""
        try:
            with self.store.transaction():
                return body()
        except _Refused as r:
            if case_id is not None and self.store.get_case(case_id) is not None:
                with self.store.transaction():
                    self._audit(case_id, actor, r.action, decision=r.reason, **r.audit_kw)
            raise r.error from None

    def _case(self, case_id: str) -> Case:
        case = self.store.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        return case

    def _is_case_rm(self, case: Case, actor: Actor) -> bool:
        return (actor.kind == "human" and actor.id == case.rm_id
                and Role.RM in self.roles.get(actor.id, frozenset()))

    # ---- cases ----
    def open_case(self, lead_ref: str, rm_id: str, as_of_date: date) -> Case:
        if Role.RM not in self.roles.get(rm_id, frozenset()):
            raise PermissionError(f"{rm_id} is not an RM")

        def body() -> Case:
            case = Case(lead_ref=lead_ref, rm_id=rm_id, as_of_date=as_of_date)
            self.store.create_case(case)
            evt = self._audit(case.case_id, SYSTEM, "case_created", outputs_ref=(case.case_id,))
            self.store.append_transition(case.case_id, None, CaseState.CREATED, "create", None, evt.event_id)
            return case
        return self._write(None, SYSTEM, body)

    def state(self, case_id: str) -> CaseState:
        return self.store.current_state(case_id)[0]

    def attempt(self, case_id: str) -> int:
        """D14: the fix-loop round = number of stored rm_fixed transitions."""
        return self.store.count_transitions(case_id, "rm_fixed")

    def advance(self, case_id: str, trigger: str, actor: Actor) -> CaseState:
        if trigger == "gate":
            raise IllegalTransition("gate transitions go through record_gate()")

        def body() -> CaseState:
            if trigger == "rm_fixed" and not self._is_case_rm(self._case(case_id), actor):
                raise _Refused(PermissionError("only the case's RM can fire rm_fixed"), "transition_rejected",
                               f"{trigger}: only the case's RM can fire rm_fixed")
            current, resume = self.store.current_state(case_id)
            try:
                nxt = next_state(current, trigger, resume_state=resume)
            except IllegalTransition as exc:
                raise _Refused(exc, "transition_rejected", f"{trigger}: {exc}") from None
            evt = self._audit(case_id, actor, "transition", decision=f"{current}->{nxt} via {trigger}")
            new_resume = current if nxt is CaseState.SUSPENDED else None
            self.store.append_transition(case_id, current, nxt, trigger, new_resume, evt.event_id)
            return nxt
        return self._write(case_id, actor, body)

    # ---- gates (I4, I11, G1 contradiction precondition) ----
    def record_gate(self, gate: GateEvent) -> CaseState:
        actor = Actor(kind="human", id=gate.actor_id, role=gate.role)
        case = self._case(gate.case_id)

        def refuse(reason: str) -> _Refused:
            return _Refused(GateRejected(reason), "gate_rejected", reason, inputs_ref=(gate.gate_id,))

        def body() -> CaseState:
            if gate.role not in self.roles.get(gate.actor_id, frozenset()):
                raise refuse(f"{gate.actor_id} does not hold role {gate.role}")
            if gate.gate is GateKind.RM and gate.actor_id != case.rm_id:
                raise refuse("only the case's RM can submit the RM gate")
            if gate.gate is GateKind.COMPLIANCE and gate.actor_id == case.rm_id:
                raise refuse("the case's RM cannot approve their own case (I11)")

            current, _ = self.store.current_state(gate.case_id)
            existing = self.store.get_gate_event(gate.gate_id)
            if existing is not None:
                if existing.model_dump_json() == gate.model_dump_json():
                    return current  # idempotent replay: already applied, no second transition
                raise GateConflict(f"gate {gate.gate_id} already recorded with different content")
            try:
                nxt = next_state(current, "gate", gate_event=gate)
            except IllegalTransition as exc:
                raise refuse(str(exc)) from None
            if gate.gate is GateKind.RM:
                still_open = self.open_contradictions(gate.case_id)
                if still_open:
                    ids = ", ".join(k.contradiction_id for k in still_open)
                    raise refuse(f"{len(still_open)} unresolved contradiction(s): {ids}")
            self.store.append_gate_event(gate)
            evt = self._audit(
                gate.case_id, actor, "gate_decision", decision=f"{gate.gate}:{gate.decision}",
                inputs_ref=(gate.gate_id,), evidence_refs=gate.fact_ids_relied_on,
                versions=Versions(rules=gate.rule_version, taxonomy=self.taxonomy.version),
            )
            self.store.append_transition(gate.case_id, current, nxt, "gate", None, evt.event_id)
            return nxt
        return self._write(gate.case_id, actor, body)

    # ---- facts (I1 via schema, I9 here, D13 auto-resolution) ----
    def _check_fact(self, fact: Fact) -> None:
        def refuse(reason: str) -> _Refused:
            return _Refused(FactRejected(reason), "fact_rejected", reason)

        if self.store.get_case(fact.case_id) is None:
            raise refuse(f"no such case {fact.case_id}")
        try:
            self.taxonomy.validate_fact(fact)
        except TaxonomyError as exc:
            raise refuse(str(exc)) from None
        if not set(fact.purpose) <= self.allowed_purposes:
            raise refuse(f"purpose {sorted(fact.purpose)} not allowed; "
                         f"this deployment writes {sorted(self.allowed_purposes)}")
        if fact.supersedes_fact_id:
            old = self.store.get_fact(fact.supersedes_fact_id)
            if old is None or old.case_id != fact.case_id:
                raise refuse("superseded fact not found in this case")

    def _append_fact(self, fact: Fact, actor: Actor) -> Fact:
        self._check_fact(fact)
        self.store.append_fact(fact)
        self._audit(fact.case_id, actor, "fact_added", outputs_ref=(fact.fact_id,),
                    inputs_ref=tuple(p.source_ref for p in fact.provenance))
        return fact

    def add_fact(self, fact: Fact, actor: Actor) -> Fact:
        def body() -> Fact:
            self._append_fact(fact, actor)
            if fact.supersedes_fact_id and self._is_case_rm(self._case(fact.case_id), actor):
                self._auto_resolve(fact, actor)
            return fact
        return self._write(fact.case_id, actor, body)

    def _lineage(self, fact_id: str) -> set[str]:
        """The fact and every fact it supersedes, back to the original."""
        seen: set[str] = set()
        cur: str | None = fact_id
        while cur and cur not in seen:
            seen.add(cur)
            f = self.store.get_fact(cur)
            cur = f.supersedes_fact_id if f else None
        return seen

    def _auto_resolve(self, fix: Fact, actor: Actor) -> None:
        """D13: an RM fact that supersedes a contradicted fact settles that contradiction in the RM's favour."""
        lineage = self._lineage(fix.supersedes_fact_id)  # type: ignore[arg-type]
        for k in self.open_contradictions(fix.case_id):
            if lineage & set(k.fact_ids):
                r = Resolution(case_id=fix.case_id, contradiction_id=k.contradiction_id, outcome="stands",
                               standing_fact_id=fix.fact_id, reason="RM entered a corrected value",
                               actor_id=actor.id)
                self.store.append_resolution(r)
                self._audit(fix.case_id, actor, "contradiction_resolved", inputs_ref=(k.contradiction_id,),
                            outputs_ref=(r.resolution_id,), decision="stands (auto, RM fix)")

    # ---- contradictions (D4, D19; only reconcile decides them, I6) ----
    def record_contradiction(self, case_id: str, field: str, fact_ids: Sequence[str], rule_version: str,
                             actor: Actor, subject_ref: str | None = None) -> Contradiction:
        """Store the contradiction under the original fact IDs and supersede each fact with a copy marked
        contradicted, so both values stay current and visible."""
        def body() -> Contradiction:
            k = Contradiction(case_id=case_id, field=field, subject_ref=subject_ref, fact_ids=tuple(fact_ids),
                              rule_version=rule_version)
            for fid in k.fact_ids:
                old = self.store.get_fact(fid)
                if old is None or old.case_id != case_id:
                    msg = f"fact {fid} not found in this case"
                    raise _Refused(FactRejected(msg), "contradiction_rejected", msg)
                self._append_fact(old.model_copy(update={
                    "fact_id": new_id("f"), "status": FactStatus.CONTRADICTED, "supersedes_fact_id": old.fact_id,
                    "created_by": actor.id, "created_at": utcnow()}), actor)
            self.store.append_contradiction(k)
            self._audit(case_id, actor, "contradiction_recorded", inputs_ref=k.fact_ids,
                        outputs_ref=(k.contradiction_id,),
                        versions=Versions(rules=rule_version, taxonomy=self.taxonomy.version))
            return k
        return self._write(case_id, actor, body)

    def open_contradictions(self, case_id: str) -> list[Contradiction]:
        settled = {r.contradiction_id for r in self.store.resolutions(case_id)}
        return [k for k in self.store.contradictions(case_id) if k.contradiction_id not in settled]

    def resolve_contradiction(self, contradiction_id: str, outcome: str, standing_fact_id: str | None,
                              reason: str, actor: Actor) -> Resolution:
        """The RM settles a contradiction: a value stands, the value is unknown, or it is left open for
        compliance. Only the case's RM may do this."""
        k = self.store.get_contradiction(contradiction_id)
        if k is None:
            raise KeyError(contradiction_id)
        case = self._case(k.case_id)

        def body() -> Resolution:
            if not self._is_case_rm(case, actor):
                raise _Refused(PermissionError("only the case's RM can resolve a contradiction"),
                               "resolution_rejected", f"{actor.id} is not this case's RM")
            if standing_fact_id is not None and not (self._lineage(standing_fact_id) & set(k.fact_ids)):
                msg = f"fact {standing_fact_id} is not part of contradiction {contradiction_id}"
                raise _Refused(FactRejected(msg), "resolution_rejected", msg)
            r = Resolution(case_id=k.case_id, contradiction_id=contradiction_id, outcome=outcome,  # type: ignore[arg-type]
                           standing_fact_id=standing_fact_id, reason=reason, actor_id=actor.id)
            self.store.append_resolution(r)
            self._audit(k.case_id, actor, "contradiction_resolved", inputs_ref=(contradiction_id,),
                        outputs_ref=(r.resolution_id,), decision=outcome)
            return r
        return self._write(k.case_id, actor, body)

    # ---- document checklist (D16: the single source of document facts) ----
    def load_checklist(self, case_id: str, items: Sequence[ChecklistItem], actor: Actor) -> list[Fact]:
        """Store the checklist and derive its document facts, all or nothing."""
        def body() -> list[Fact]:
            out: list[Fact] = []
            for item in items:
                if item.document_type not in self.taxonomy.document_types:
                    msg = f"checklist {item.item_id}: unknown document type {item.document_type!r}"
                    raise _Refused(FactRejected(msg), "checklist_rejected", msg)
                self.store.append_checklist_item(case_id, item)
                for fact in document_facts(case_id, item, actor.id):
                    out.append(self._append_fact(fact, actor))
            return out
        return self._write(case_id, actor, body)

    # ---- the pre-submission check (beta 0 step 4: reconcile, then the rules) ----
    def rule_facts(self, case_id: str) -> list[Fact]:
        """What the rules may read: current facts, minus contradicted values nobody has settled. A value that
        'stands' feeds the rules; 'open' and 'unknown' count as missing (design, I6)."""
        standing = {r.standing_fact_id for r in self.store.resolutions(case_id) if r.outcome == "stands"}
        return [f for f in self.store.facts(case_id)
                if f.status is not FactStatus.CONTRADICTED or f.fact_id in standing]

    def run_presubmit_check(self, case_id: str, reasons: BounceReasons, actor: Actor) -> CheckReport:
        """One step, one transaction: record new contradictions, run every bounce rule and trigger on the facts
        the rules may read, store the results as findings for this fix-loop round, move to presubmit_checked.
        The checker (step 5) adds its own findings to the same round."""
        case = self._case(case_id)

        def body() -> CheckReport:
            current, resume = self.store.current_state(case_id)
            try:
                next_state(current, "presubmit_check_completed", resume_state=resume)
            except IllegalTransition as exc:
                raise _Refused(exc, "transition_rejected", f"presubmit_check_completed: {exc}") from None
            known = [frozenset(k.fact_ids) for k in self.store.contradictions(case_id)]
            new = tuple(self.record_contradiction(case_id, c.field, c.fact_ids, RECONCILE_VERSION, actor,
                                                  subject_ref=c.subject_ref)
                        for c in find_conflicts(self.store.facts(case_id, current_only=False), known))
            attempt = self.attempt(case_id)
            findings = []
            for r in evaluate(reasons, self.rule_facts(case_id), case.as_of_date):
                f = Finding(case_id=case_id, attempt=attempt, source="rule", source_id=r.reason_id,
                            source_version=reasons.version, outcome=r.outcome.value, effect=r.effect,  # type: ignore[arg-type]
                            fact_refs=r.fact_refs, detail=r.detail)
                self.store.append_finding(f)
                findings.append(f)
            self._audit(case_id, actor, "presubmit_check", decision=f"attempt {attempt}: {len(new)} new contradiction(s), "
                        f"{sum(f.outcome == 'fire' for f in findings)} rule(s) fired",
                        outputs_ref=tuple(f.finding_id for f in findings),
                        versions=Versions(rules=reasons.version, taxonomy=self.taxonomy.version))
            self.advance(case_id, "presubmit_check_completed", actor)
            return CheckReport(contradictions=new, findings=tuple(findings))
        return self._write(case_id, actor, body)
