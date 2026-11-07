"""Domain records. All are frozen: a change is a new record, never an edit (invariant I2)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import FactStatus, GateKind, Purpose, Role, SourceType


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------- typed fact values ----------

class Money(Record):
    kind: Literal["money"] = "money"
    amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")  # ISO 4217
    period: Literal["one_off", "per_year", "per_month"] = "one_off"


class Percent(Record):
    kind: Literal["percent"] = "percent"
    value: Decimal = Field(ge=0, le=100)


class ExactDate(Record):
    kind: Literal["date"] = "date"
    value: date
    precision: Literal["day", "month", "year"] = "day"


class RelativeDate(Record):
    """A date spoken relatively ('three years ago in June'). The words are kept so the RM can check them."""
    kind: Literal["relative_date"] = "relative_date"
    words: str = Field(min_length=1)
    anchor: date
    resolved: date | None = None


class Text(Record):
    kind: Literal["text"] = "text"
    value: str = Field(min_length=1)


class Country(Record):
    kind: Literal["country"] = "country"
    iso2: str = Field(pattern=r"^[A-Z]{2}$")


class Flag(Record):
    kind: Literal["bool"] = "bool"
    value: bool


FactValue = Annotated[
    Union[Money, Percent, ExactDate, RelativeDate, Text, Country, Flag],
    Field(discriminator="kind"),
]


# ---------- spans and the document checklist (beta 0) ----------

class SpanOffset(Record):
    """Characters [start, end) of one utterance's raw text. `quote` is the text expected there, when known."""
    utt_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int
    quote: str | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> "SpanOffset":
        if self.end <= self.start:
            raise ValueError("span end must be after start")
        return self


class ChecklistItem(Record):
    """One document on the client's checklist. The single source of document facts (D16)."""
    item_id: str = Field(min_length=1)
    document_type: str = Field(min_length=1)  # checked against the taxonomy's document_types by the caller
    present: bool
    issue_date: date | None = None
    expiry_date: date | None = None

    @model_validator(mode="after")
    def expiry_after_issue(self) -> "ChecklistItem":
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValueError("expiry_date is before issue_date")
        return self


# ---------- facts ----------

class Provenance(Record):
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    span_offsets: tuple[SpanOffset, ...] = ()  # D6: replaces span_utt_ids
    extractor_version: str = Field(min_length=1)  # document facts: checklist-loader-<v>; RM facts: rm_entry
    run_id: str | None = None  # the StepRun that produced it; None for document and rm_entry facts

    @model_validator(mode="after")
    def spans_match_source(self) -> "Provenance":
        if self.source_type is SourceType.TRANSCRIPT and not self.span_offsets:
            raise ValueError("transcript provenance must cite at least one span")
        if self.source_type is not SourceType.TRANSCRIPT and self.span_offsets:
            raise ValueError(f"{self.source_type} provenance cannot carry transcript span offsets")
        return self

    @property
    def utt_ids(self) -> tuple[str, ...]:
        """Utterance IDs cited, in first-seen order (derived from the offsets)."""
        return tuple(dict.fromkeys(o.utt_id for o in self.span_offsets))


class Fact(Record):
    fact_id: str = Field(default_factory=lambda: new_id("f"))
    case_id: str
    field: str = Field(min_length=1)
    subject_ref: str | None = None  # groups facts, e.g. "wealth_event/1"
    value: FactValue
    status: FactStatus = FactStatus.STATED
    confidence: float = Field(ge=0.0, le=1.0)
    purpose: tuple[Purpose, ...] = Field(min_length=1)       # I9
    provenance: tuple[Provenance, ...] = Field(min_length=1)  # I1
    supersedes_fact_id: str | None = None
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utcnow)


# ---------- case, audit, gates ----------

class Case(Record):
    case_id: str = Field(default_factory=lambda: new_id("case"))
    lead_ref: str = Field(min_length=1)
    rm_id: str = Field(min_length=1)
    as_of_date: date  # D8: document validity and relative dates are judged against this, never "today"
    synthetic: Literal[True] = True  # I12: the PoC refuses non-synthetic cases
    created_at: datetime = Field(default_factory=utcnow)


# ---------- beta 0 workflow records ----------

class StepRun(Record):
    """One run of an LLM step. Append-only: a run is re-recorded with a new status, never edited."""
    run_id: str = Field(default_factory=lambda: new_id("run"))
    case_id: str
    step: str = Field(min_length=1)
    attempt: int = Field(ge=0)  # number of stored rm_fixed transitions when the run started (D14)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")  # SHA-256 of canonical JSON of inputs + versions
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    status: Literal["started", "completed", "abandoned"]
    output_ref: str | None = None
    at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def completed_has_output(self) -> "StepRun":
        if self.status == "completed" and not self.output_ref:
            raise ValueError("a completed step run needs an output_ref")
        return self


class Contradiction(Record):
    """Reconcile's decision that two or more facts disagree. Kept by original fact IDs (D4, D19)."""
    contradiction_id: str = Field(default_factory=lambda: new_id("k"))
    case_id: str
    field: str = Field(min_length=1)
    subject_ref: str | None = None
    fact_ids: tuple[str, ...] = Field(min_length=2)
    rule_version: str = Field(min_length=1)
    at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def distinct_facts(self) -> "Contradiction":
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise ValueError("a contradiction needs distinct fact ids")
        return self


class Resolution(Record):
    """How the RM settled a contradiction. 'open' = left for compliance; it still counts as resolved for G1."""
    resolution_id: str = Field(default_factory=lambda: new_id("res"))
    case_id: str
    contradiction_id: str = Field(min_length=1)
    outcome: Literal["stands", "unknown", "open"]
    standing_fact_id: str | None = None
    reason: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def standing_fact_iff_stands(self) -> "Resolution":
        if (self.outcome == "stands") != (self.standing_fact_id is not None):
            raise ValueError("standing_fact_id is required for 'stands' and not allowed otherwise")
        return self


class Finding(Record):
    """A stored result of a rule or checker run (D17). The summary and the I8 band read these, not live reruns."""
    finding_id: str = Field(default_factory=lambda: new_id("fd"))
    case_id: str
    attempt: int = Field(ge=0)
    source: Literal["rule", "checker"]
    source_id: str = Field(min_length=1)       # bounce reason id, or checker model id
    source_version: str = Field(min_length=1)  # rules file version, or checker prompt version
    outcome: Literal["fire", "pass", "unknown"]
    effect: Literal["bounce", "flag"]
    fact_refs: tuple[str, ...] = ()
    detail: str = ""
    at: datetime = Field(default_factory=utcnow)


class Actor(Record):
    kind: Literal["agent_step", "human", "system"]
    id: str = Field(min_length=1)
    role: Role | None = None

    @model_validator(mode="after")
    def human_needs_role(self) -> "Actor":
        if self.kind == "human" and self.role is None:
            raise ValueError("a human actor must act in a role")
        return self


class Versions(Record):
    model: str | None = None
    prompt: str | None = None
    rules: str | None = None
    taxonomy: str | None = None


class AuditEvent(Record):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    parent_id: str | None = None
    case_id: str
    actor: Actor
    action: str = Field(min_length=1)
    inputs_ref: tuple[str, ...] = ()
    outputs_ref: tuple[str, ...] = ()
    versions: Versions = Versions()
    decision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    at: datetime = Field(default_factory=utcnow)


GATE_DECISIONS: dict[GateKind, frozenset[str]] = {
    GateKind.RM: frozenset({"submit"}),
    GateKind.COMPLIANCE: frozenset({"approve", "amend", "return", "escalate"}),
}
GATE_ROLE: dict[GateKind, Role] = {GateKind.RM: Role.RM, GateKind.COMPLIANCE: Role.COMPLIANCE}


class GateEvent(Record):
    gate_id: str = Field(default_factory=lambda: new_id("g"))
    case_id: str
    gate: GateKind
    actor_id: str = Field(min_length=1)
    role: Role
    decision: str
    reason_text: str = ""
    reason_category: str | None = None
    rule_version: str = Field(min_length=1)
    fact_ids_relied_on: tuple[str, ...] = ()
    at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def check(self) -> "GateEvent":
        if self.decision not in GATE_DECISIONS[self.gate]:
            raise ValueError(f"decision {self.decision!r} not allowed at {self.gate} gate")
        if self.role is not GATE_ROLE[self.gate]:
            raise ValueError(f"{self.gate} gate must be decided in role {GATE_ROLE[self.gate]}")
        if self.gate is GateKind.COMPLIANCE and not self.reason_text.strip():
            raise ValueError("a compliance decision needs a reason in the decider's own words")
        return self
