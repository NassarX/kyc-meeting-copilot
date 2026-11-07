"""SQLite store. Every table is append-only, enforced by triggers in the database, not by convention (I2)."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kyc_copilot.domain.enums import CaseState
from kyc_copilot.domain.models import (AuditEvent, Case, ChecklistItem, Contradiction, Fact, Finding, GateEvent,
                                   Resolution, StepRun)
from .base import GateConflict

TABLES = ("cases", "case_transitions", "facts", "audit_events", "gate_events",
          "checklist_items", "step_runs", "contradictions", "resolutions", "findings")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS case_transitions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(case_id),
    from_state TEXT, to_state TEXT NOT NULL, trigger TEXT NOT NULL, resume_state TEXT,
    event_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
    supersedes_fact_id TEXT REFERENCES facts(fact_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
    case_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gate_events (
    gate_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checklist_items (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(case_id),
    item_id TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE (case_id, item_id));
CREATE TABLE IF NOT EXISTS step_runs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, case_id TEXT NOT NULL REFERENCES cases(case_id),
    step TEXT NOT NULL, attempt INTEGER NOT NULL, input_hash TEXT NOT NULL, status TEXT NOT NULL,
    payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contradictions (
    contradiction_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resolutions (
    resolution_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
    contradiction_id TEXT NOT NULL REFERENCES contradictions(contradiction_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, finding_id TEXT UNIQUE NOT NULL,
    case_id TEXT NOT NULL REFERENCES cases(case_id), attempt INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS facts_supersedes ON facts(supersedes_fact_id);
CREATE INDEX IF NOT EXISTS step_runs_reuse ON step_runs(case_id, step, attempt, input_hash);
"""


def _append_only_triggers() -> str:
    out = []
    for t in TABLES:
        for op in ("UPDATE", "DELETE"):
            out.append(
                f"CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t} "
                f"BEGIN SELECT RAISE(ABORT, 'append-only table: {op} on {t} refused'); END;"
            )
    return "\n".join(out)


class SQLiteStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        # Autocommit outside transaction(); inside it, BEGIN/SAVEPOINT are issued by hand (D11).
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA + _append_only_triggers())
        self._depth = 0

    # unit of work
    @contextmanager
    def transaction(self) -> Iterator[None]:
        """All writes inside commit together or not at all. Re-entrant: the outermost call owns BEGIN/COMMIT,
        inner calls use SAVEPOINTs, so an inner failure that is caught rolls back only the inner part, and one
        that escapes rolls back everything."""
        name = f"sp{self._depth}"
        self.conn.execute("BEGIN IMMEDIATE" if self._depth == 0 else f"SAVEPOINT {name}")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("ROLLBACK")
            else:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
                self.conn.execute(f"RELEASE SAVEPOINT {name}")
            raise
        self._depth -= 1
        self.conn.execute("COMMIT" if self._depth == 0 else f"RELEASE SAVEPOINT {name}")

    # cases
    def create_case(self, case: Case) -> None:
        self.conn.execute("INSERT INTO cases VALUES (?, ?)", (case.case_id, case.model_dump_json()))

    def get_case(self, case_id: str) -> Case | None:
        row = self.conn.execute("SELECT payload FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        return Case.model_validate_json(row[0]) if row else None

    # transitions
    def append_transition(self, case_id, from_state, to_state, trigger, resume_state, event_id) -> None:
        self.conn.execute(
            "INSERT INTO case_transitions (case_id, from_state, to_state, trigger, resume_state, event_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (case_id, from_state and str(from_state), str(to_state), trigger,
             resume_state and str(resume_state), event_id),
        )

    def count_transitions(self, case_id: str, trigger: str) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM case_transitions WHERE case_id = ? AND trigger = ?",
                                (case_id, trigger)).fetchone()
        return int(row[0])

    def current_state(self, case_id: str) -> tuple[CaseState, CaseState | None]:
        row = self.conn.execute(
            "SELECT to_state, resume_state FROM case_transitions WHERE case_id = ? ORDER BY seq DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no such case {case_id}")
        return CaseState(row[0]), CaseState(row[1]) if row[1] else None

    # facts
    def append_fact(self, fact: Fact) -> None:
        self.conn.execute(
            "INSERT INTO facts VALUES (?, ?, ?, ?)",
            (fact.fact_id, fact.case_id, fact.supersedes_fact_id, fact.model_dump_json()),
        )

    def get_fact(self, fact_id: str) -> Fact | None:
        row = self.conn.execute("SELECT payload FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
        return Fact.model_validate_json(row[0]) if row else None

    def facts(self, case_id: str, current_only: bool = True) -> list[Fact]:
        sql = "SELECT payload FROM facts f WHERE case_id = ?"
        if current_only:
            sql += " AND NOT EXISTS (SELECT 1 FROM facts s WHERE s.supersedes_fact_id = f.fact_id)"
        sql += " ORDER BY rowid"
        return [Fact.model_validate_json(r[0]) for r in self.conn.execute(sql, (case_id,))]

    # audit
    def append_audit(self, event: AuditEvent) -> None:
        self.conn.execute(
            "INSERT INTO audit_events (event_id, case_id, payload) VALUES (?, ?, ?)",
            (event.event_id, event.case_id, event.model_dump_json()),
        )

    def audit(self, case_id: str) -> list[AuditEvent]:
        rows = self.conn.execute("SELECT payload FROM audit_events WHERE case_id = ? ORDER BY seq", (case_id,))
        return [AuditEvent.model_validate_json(r[0]) for r in rows]

    # gates
    def append_gate_event(self, event: GateEvent) -> bool:
        payload = event.model_dump_json()
        row = self.conn.execute("SELECT payload FROM gate_events WHERE gate_id = ?", (event.gate_id,)).fetchone()
        if row is not None:
            if row[0] == payload:
                return False
            raise GateConflict(f"gate {event.gate_id} already recorded with different content")
        self.conn.execute("INSERT INTO gate_events VALUES (?, ?, ?)", (event.gate_id, event.case_id, payload))
        return True

    def get_gate_event(self, gate_id: str) -> GateEvent | None:
        row = self.conn.execute("SELECT payload FROM gate_events WHERE gate_id = ?", (gate_id,)).fetchone()
        return GateEvent.model_validate_json(row[0]) if row else None

    def gate_events(self, case_id: str) -> list[GateEvent]:
        rows = self.conn.execute("SELECT payload FROM gate_events WHERE case_id = ? ORDER BY rowid", (case_id,))
        return [GateEvent.model_validate_json(r[0]) for r in rows]

    # checklist (D16: the single source of document facts)
    def append_checklist_item(self, case_id: str, item: ChecklistItem) -> None:
        self.conn.execute("INSERT INTO checklist_items (case_id, item_id, payload) VALUES (?, ?, ?)",
                          (case_id, item.item_id, item.model_dump_json()))

    def checklist(self, case_id: str) -> list[ChecklistItem]:
        rows = self.conn.execute("SELECT payload FROM checklist_items WHERE case_id = ? ORDER BY seq", (case_id,))
        return [ChecklistItem.model_validate_json(r[0]) for r in rows]

    # step runs (a status change is a new row)
    def append_step_run(self, run: StepRun) -> None:
        self.conn.execute(
            "INSERT INTO step_runs (run_id, case_id, step, attempt, input_hash, status, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run.run_id, run.case_id, run.step, run.attempt, run.input_hash, run.status, run.model_dump_json()))

    def step_runs(self, case_id: str) -> list[StepRun]:
        rows = self.conn.execute("SELECT payload FROM step_runs WHERE case_id = ? ORDER BY seq", (case_id,))
        return [StepRun.model_validate_json(r[0]) for r in rows]

    def completed_run(self, case_id: str, step: str, attempt: int, input_hash: str) -> StepRun | None:
        """Crash recovery only: a completed run with the same step, attempt and inputs can be reused."""
        row = self.conn.execute(
            "SELECT payload FROM step_runs WHERE case_id = ? AND step = ? AND attempt = ? AND input_hash = ? "
            "AND status = 'completed' ORDER BY seq DESC LIMIT 1", (case_id, step, attempt, input_hash)).fetchone()
        return StepRun.model_validate_json(row[0]) if row else None

    # contradictions and resolutions (D4, D19)
    def append_contradiction(self, c: Contradiction) -> None:
        self.conn.execute("INSERT INTO contradictions VALUES (?, ?, ?)",
                          (c.contradiction_id, c.case_id, c.model_dump_json()))

    def get_contradiction(self, contradiction_id: str) -> Contradiction | None:
        row = self.conn.execute("SELECT payload FROM contradictions WHERE contradiction_id = ?",
                                (contradiction_id,)).fetchone()
        return Contradiction.model_validate_json(row[0]) if row else None

    def contradictions(self, case_id: str) -> list[Contradiction]:
        rows = self.conn.execute("SELECT payload FROM contradictions WHERE case_id = ? ORDER BY rowid", (case_id,))
        return [Contradiction.model_validate_json(r[0]) for r in rows]

    def append_resolution(self, r: Resolution) -> None:
        self.conn.execute("INSERT INTO resolutions VALUES (?, ?, ?, ?)",
                          (r.resolution_id, r.case_id, r.contradiction_id, r.model_dump_json()))

    def resolutions(self, case_id: str) -> list[Resolution]:
        rows = self.conn.execute("SELECT payload FROM resolutions WHERE case_id = ? ORDER BY rowid", (case_id,))
        return [Resolution.model_validate_json(r[0]) for r in rows]

    # findings (D17)
    def append_finding(self, f: Finding) -> None:
        self.conn.execute("INSERT INTO findings (finding_id, case_id, attempt, payload) VALUES (?, ?, ?, ?)",
                          (f.finding_id, f.case_id, f.attempt, f.model_dump_json()))

    def findings(self, case_id: str, attempt: int | None = None) -> list[Finding]:
        sql, args = "SELECT payload FROM findings WHERE case_id = ?", [case_id]
        if attempt is not None:
            sql, args = sql + " AND attempt = ?", args + [attempt]
        rows = self.conn.execute(sql + " ORDER BY seq", args)
        return [Finding.model_validate_json(r[0]) for r in rows]
