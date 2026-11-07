"""Document facts derived from the checklist. Shared by the service and the eval harness,
so the facts a case is scored on are exactly the facts the service would store."""
from __future__ import annotations

from .enums import Purpose, SourceType
from .models import ChecklistItem, ExactDate, Fact, Flag, Provenance, Text

CHECKLIST_LOADER = "checklist-loader-v1"


def document_facts(case_id: str, item: ChecklistItem, created_by: str) -> list[Fact]:
    prov = (Provenance(source_type=SourceType.DOCUMENT, source_ref=item.item_id, extractor_version=CHECKLIST_LOADER),)
    values = [("document.type", Text(value=item.document_type)), ("document.present", Flag(value=item.present))]
    if item.issue_date:
        values.append(("document.issue_date", ExactDate(value=item.issue_date)))
    if item.expiry_date:
        values.append(("document.expiry_date", ExactDate(value=item.expiry_date)))
    return [Fact(case_id=case_id, field=f, subject_ref=f"document/{item.item_id}", value=v, confidence=1.0,
                 purpose=(Purpose.AML,), provenance=prov, created_by=created_by) for f, v in values]
