"""Enumerations shared across the domain. Values are stable identifiers stored in the audit trail."""
from enum import StrEnum


class FactStatus(StrEnum):
    STATED = "stated"
    RM_CONFIRMED = "rm_confirmed"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class SourceType(StrEnum):
    TRANSCRIPT = "transcript"
    DOSSIER = "dossier"
    DOCUMENT = "document"
    RM_ENTRY = "rm_entry"


class Purpose(StrEnum):
    """Processing purpose of a fact (invariant I9; AMLR Art. 76(4))."""
    AML = "aml"
    ADVICE = "advice"


class Role(StrEnum):
    RM = "rm"
    COMPLIANCE = "compliance"
    RULE_OWNER = "rule_owner"
    OPERATOR = "operator"
    MODEL_RISK_OWNER = "model_risk_owner"


class GateKind(StrEnum):
    RM = "rm"
    COMPLIANCE = "compliance"


class CaseState(StrEnum):
    CREATED = "created"
    DOSSIER_READY = "dossier_ready"
    TRANSCRIPT_INGESTED = "transcript_ingested"
    FACTS_EXTRACTED = "facts_extracted"
    PRESUBMIT_CHECKED = "presubmit_checked"  # beta 0: check done; RM fixes or moves on to the gate
    AWAITING_RM_CONFIRMATION = "awaiting_rm_confirmation"
    FACTS_CONFIRMED = "facts_confirmed"
    ANALYSING = "analysing"
    ANALYSED = "analysed"
    CHECKED = "checked"
    AWAITING_COMPLIANCE_REVIEW = "awaiting_compliance_review"
    APPROVED = "approved"
    RETURNED_TO_RM = "returned_to_rm"
    ESCALATED = "escalated"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    FAILED_NEEDS_HUMAN = "failed_needs_human"
