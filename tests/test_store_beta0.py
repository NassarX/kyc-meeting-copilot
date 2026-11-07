"""Beta 0 store: re-entrant transaction (D5, D11), new append-only tables, indexes (D10)."""
import sqlite3
from datetime import date

import pytest

from kyc_copilot.domain.enums import CaseState
from kyc_copilot.domain.models import Case, ChecklistItem, Contradiction, Finding, Resolution, StepRun
from kyc_copilot.store.sqlite import TABLES, SQLiteStore
from conftest import make_fact

NEW_TABLES = {"step_runs", "contradictions", "resolutions", "checklist_items", "findings"}


class Boom(Exception):
    pass


@pytest.fixture
def store_and_case():
    s = SQLiteStore()
    case = Case(lead_ref="lead-1", rm_id="rm.alice", as_of_date=date(2026, 11, 1))
    s.create_case(case)
    s.append_transition(case.case_id, None, CaseState.CREATED, "create", None, "evt-0")
    return s, case.case_id


def run(case_id, attempt=0, h="a", status="started", out=None):
    return StepRun(case_id=case_id, step="S3_extract", attempt=attempt, input_hash=h * 64, model_id="m",
                   prompt_version="p", status=status, output_ref=out)


def test_new_tables_are_registered_as_append_only():
    assert NEW_TABLES <= set(TABLES)


# ---------- transaction ----------

def test_transaction_commits_all_rows(store_and_case):
    s, cid = store_and_case
    with s.transaction():
        s.append_fact(make_fact(cid))
        s.append_fact(make_fact(cid))
    assert len(s.facts(cid)) == 2


def test_exception_rolls_back_every_row(store_and_case):
    s, cid = store_and_case
    with pytest.raises(Boom):
        with s.transaction():
            s.append_fact(make_fact(cid))
            s.append_transition(cid, CaseState.CREATED, CaseState.DOSSIER_READY, "dossier_built", None, "e1")
            raise Boom
    assert s.facts(cid) == [] and s.current_state(cid)[0] is CaseState.CREATED


def test_nested_transactions_commit_once_at_the_outermost(store_and_case):
    s, cid = store_and_case
    with s.transaction():
        with s.transaction():
            s.append_fact(make_fact(cid))
        assert s.conn.in_transaction  # inner exit did not commit
        s.append_fact(make_fact(cid))
    assert not s.conn.in_transaction and len(s.facts(cid)) == 2


def test_inner_failure_caught_inside_keeps_outer_rows(store_and_case):
    s, cid = store_and_case
    with s.transaction():
        s.append_fact(make_fact(cid))
        with pytest.raises(Boom):
            with s.transaction():
                s.append_fact(make_fact(cid))
                raise Boom
    assert len(s.facts(cid)) == 1  # only the inner savepoint rolled back


def test_inner_failure_escaping_rolls_back_the_whole_step(store_and_case):
    s, cid = store_and_case
    with pytest.raises(Boom):
        with s.transaction():
            s.append_fact(make_fact(cid))
            with s.transaction():
                s.append_fact(make_fact(cid))
                raise Boom
    assert s.facts(cid) == [] and not s.conn.in_transaction


def test_store_is_usable_after_a_rollback(store_and_case):
    s, cid = store_and_case
    with pytest.raises(Boom):
        with s.transaction():
            raise Boom
    with s.transaction():
        s.append_fact(make_fact(cid))
    assert len(s.facts(cid)) == 1


def test_writes_outside_a_transaction_still_autocommit(store_and_case):
    s, cid = store_and_case
    s.append_fact(make_fact(cid))
    assert not s.conn.in_transaction and len(s.facts(cid)) == 1


def test_file_store_rollback_survives_reopen(tmp_path):
    path = tmp_path / "c.db"
    s = SQLiteStore(path)
    case = Case(lead_ref="lead-1", rm_id="rm.alice", as_of_date=date(2026, 11, 1))
    s.create_case(case)
    with pytest.raises(Boom):
        with s.transaction():
            s.append_fact(make_fact(case.case_id))
            raise Boom
    s.conn.close()
    assert SQLiteStore(path).facts(case.case_id) == []


# ---------- new records round-trip ----------

def test_checklist_round_trip_in_order(store_and_case):
    s, cid = store_and_case
    a = ChecklistItem(item_id="chk-01", document_type="passport", present=True, expiry_date=date(2030, 1, 1))
    b = ChecklistItem(item_id="chk-02", document_type="sale_agreement", present=False)
    s.append_checklist_item(cid, a)
    s.append_checklist_item(cid, b)
    assert s.checklist(cid) == [a, b]


def test_checklist_item_id_unique_per_case(store_and_case):
    s, cid = store_and_case
    item = ChecklistItem(item_id="chk-01", document_type="passport", present=True)
    s.append_checklist_item(cid, item)
    with pytest.raises(sqlite3.IntegrityError):
        s.append_checklist_item(cid, item)


def test_completed_run_lookup_matches_step_attempt_and_hash(store_and_case):
    s, cid = store_and_case
    s.append_step_run(started := run(cid))
    assert s.completed_run(cid, "S3_extract", 0, "a" * 64) is None  # started is not reusable
    done = started.model_copy(update={"status": "completed", "output_ref": "out-1"})
    s.append_step_run(done)
    assert s.completed_run(cid, "S3_extract", 0, "a" * 64) == done
    assert s.completed_run(cid, "S3_extract", 1, "a" * 64) is None  # new attempt runs fresh
    assert s.completed_run(cid, "S3_extract", 0, "b" * 64) is None  # different inputs run fresh
    assert [r.status for r in s.step_runs(cid)] == ["started", "completed"]


def test_contradictions_resolutions_findings_round_trip(store_and_case):
    s, cid = store_and_case
    k = Contradiction(case_id=cid, field="wealth_event.amount", fact_ids=("f-1", "f-2"), rule_version="r")
    s.append_contradiction(k)
    r = Resolution(case_id=cid, contradiction_id=k.contradiction_id, outcome="stands", standing_fact_id="f-2",
                   reason="registry stub", actor_id="rm.alice")
    s.append_resolution(r)
    f0 = Finding(case_id=cid, attempt=0, source="rule", source_id="BR-ID-DOB", source_version="v",
                 outcome="fire", effect="bounce")
    f1 = f0.model_copy(update={"finding_id": "fd-2", "attempt": 1, "outcome": "pass"})
    s.append_finding(f0)
    s.append_finding(f1)
    assert s.contradictions(cid) == [k] and s.resolutions(cid) == [r]
    assert s.findings(cid) == [f0, f1] and s.findings(cid, attempt=1) == [f1]


def test_resolution_must_point_at_a_stored_contradiction(store_and_case):
    s, cid = store_and_case
    with pytest.raises(sqlite3.IntegrityError):
        s.append_resolution(Resolution(case_id=cid, contradiction_id="k-missing", outcome="open",
                                       reason="x", actor_id="rm.alice"))


def test_count_transitions_by_trigger(store_and_case):
    s, cid = store_and_case
    assert s.count_transitions(cid, "rm_fixed") == 0
    s.append_transition(cid, CaseState.CREATED, CaseState.CREATED, "rm_fixed", None, "e1")
    s.append_transition(cid, CaseState.CREATED, CaseState.CREATED, "rm_fixed", None, "e2")
    assert s.count_transitions(cid, "rm_fixed") == 2


# ---------- indexes (D10) ----------

def test_indexes_exist(store_and_case):
    s, _ = store_and_case
    idx = {r[0]: r[1] for r in s.conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")}
    assert any("facts" in sql and "supersedes_fact_id" in sql for sql in idx.values())
    assert any("step_runs" in sql and "case_id, step, attempt, input_hash" in sql for sql in idx.values())


def test_reuse_lookup_uses_the_step_runs_index(store_and_case):
    s, cid = store_and_case
    plan = " ".join(r[3] for r in s.conn.execute(
        "EXPLAIN QUERY PLAN SELECT payload FROM step_runs WHERE case_id=? AND step=? AND attempt=? "
        "AND input_hash=? AND status='completed'", (cid, "S3_extract", 0, "a" * 64)))
    assert "USING INDEX" in plan
