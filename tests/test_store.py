from datetime import date
import sqlite3

import pytest

from kyc_copilot.domain.models import (Actor, AuditEvent, Case, ChecklistItem, Contradiction, Finding, GateEvent,
                                   Resolution, StepRun)
from kyc_copilot.domain.enums import CaseState, GateKind, Role
from kyc_copilot.store.base import GateConflict
from kyc_copilot.store.sqlite import TABLES, SQLiteStore
from conftest import make_fact


@pytest.fixture
def seeded():
    s = SQLiteStore()
    case = Case(lead_ref="lead-1", rm_id="rm.alice", as_of_date=date(2026, 11, 1))
    s.create_case(case)
    s.append_transition(case.case_id, None, CaseState.CREATED, "create", None, "evt-0")
    s.append_fact(make_fact(case.case_id))
    s.append_audit(AuditEvent(case_id=case.case_id, actor=Actor(kind="system", id="t"), action="x"))
    s.append_gate_event(GateEvent(case_id=case.case_id, gate=GateKind.RM, actor_id="rm.alice",
                                  role=Role.RM, decision="submit", rule_version="r0"))
    # beta 0 tables: one row each, so the append-only checks below have something to refuse
    s.append_checklist_item(case.case_id, ChecklistItem(item_id="chk-01", document_type="passport", present=True))
    s.append_step_run(StepRun(case_id=case.case_id, step="S3_extract", attempt=0, input_hash="a" * 64,
                              model_id="m", prompt_version="p", status="started"))
    k = Contradiction(case_id=case.case_id, field="wealth_event.amount", fact_ids=("f-1", "f-2"), rule_version="r")
    s.append_contradiction(k)
    s.append_resolution(Resolution(case_id=case.case_id, contradiction_id=k.contradiction_id, outcome="open",
                                   reason="for compliance", actor_id="rm.alice"))
    s.append_finding(Finding(case_id=case.case_id, attempt=0, source="rule", source_id="BR-ID-DOB",
                             source_version="br-v0.1", outcome="fire", effect="bounce"))
    return s


@pytest.mark.parametrize("table", TABLES)
def test_invariant_I2_update_refused(seeded, table):
    col = {"case_transitions": "trigger", "audit_events": "payload"}.get(table, "payload")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        seeded.conn.execute(f"UPDATE {table} SET {col} = 'tampered'")


@pytest.mark.parametrize("table", TABLES)
def test_invariant_I2_delete_refused(seeded, table):
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        seeded.conn.execute(f"DELETE FROM {table}")


def test_supersession_keeps_history(seeded):
    case_id = seeded.conn.execute("SELECT case_id FROM cases").fetchone()[0]
    old = seeded.facts(case_id)[0]
    new = make_fact(case_id, supersedes_fact_id=old.fact_id, confidence=0.99)
    seeded.append_fact(new)
    assert [f.fact_id for f in seeded.facts(case_id)] == [new.fact_id]
    assert {f.fact_id for f in seeded.facts(case_id, current_only=False)} == {old.fact_id, new.fact_id}


def test_gate_event_idempotent_and_conflict(seeded):
    case_id = seeded.conn.execute("SELECT case_id FROM cases").fetchone()[0]
    g = seeded.gate_events(case_id)[0]
    assert seeded.append_gate_event(g) is False  # identical replay
    with pytest.raises(GateConflict):
        seeded.append_gate_event(g.model_copy(update={"decision": "submit", "reason_text": "changed"}))


def test_roundtrip_preserves_types(seeded):
    case_id = seeded.conn.execute("SELECT case_id FROM cases").fetchone()[0]
    f = seeded.facts(case_id)[0]
    assert f.value.kind == "money" and str(f.value.amount) == "2400000"
