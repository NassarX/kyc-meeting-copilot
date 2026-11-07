"""The pre-submission check (beta 0 step 4): reconcile, then the rules, stored as findings, in one step."""
from datetime import date

import pytest

from kyc_copilot.domain.enums import CaseState as S, FactStatus, SourceType
from kyc_copilot.domain.models import ChecklistItem, Country, Provenance
from kyc_copilot.rules import load_bounce_reasons
from kyc_copilot.service import CaseService
from kyc_copilot.store.sqlite import SQLiteStore, TABLES
from kyc_copilot.workflow.state_machine import IllegalTransition
from conftest import AGENT, AS_OF, RM, ROLES, make_fact

DOSSIER = Provenance(source_type=SourceType.DOSSIER, source_ref="dossier", extractor_version="dossier-stub")
CHECK = AGENT.model_copy(update={"id": "S4_check"})


@pytest.fixture
def reasons(taxonomy):
    return load_bounce_reasons(taxonomy)


def extracted(service):
    """A case at facts_extracted: dossier says tax resident in LU, the client said France."""
    case = service.open_case("lead-1", "rm.alice", AS_OF)
    for trig in ("dossier_built", "transcript_ingested", "facts_extracted"):
        service.advance(case.case_id, trig, AGENT)
    service.add_fact(make_fact(case.case_id, field="identity.residence_country", subject_ref=None,
                               value=Country(iso2="LU"), provenance=(DOSSIER,)), AGENT)
    service.add_fact(make_fact(case.case_id, field="identity.tax_residence", subject_ref=None,
                               value=Country(iso2="LU"), provenance=(DOSSIER,)), AGENT)
    service.add_fact(make_fact(case.case_id, field="identity.tax_residence", subject_ref=None,
                               value=Country(iso2="FR")), AGENT)
    service.load_checklist(case.case_id, [ChecklistItem(item_id="chk-01", document_type="passport", present=True,
                                                        expiry_date=date(2026, 10, 1))], AGENT)
    return case


def outcomes(findings):
    return {f.source_id: f.outcome for f in findings}


def test_check_records_contradictions_and_findings_then_moves_on(service, reasons):
    case = extracted(service)
    report = service.run_presubmit_check(case.case_id, reasons, CHECK)
    (k,) = report.contradictions
    assert k.field == "identity.tax_residence" and k.rule_version.startswith("reconcile-")
    got = outcomes(report.findings)
    assert got["BR-DOC-ID-EXPIRED"] == "fire" and got["BR-ID-DOB"] == "fire"
    assert got["BR-TAX-RESIDENCE-DIFFERS"] == "unknown"  # a contradicted value feeds no rule until resolved
    assert all(f.attempt == 0 and f.source == "rule" and f.source_version == reasons.version for f in report.findings)
    assert service.store.findings(case.case_id) == list(report.findings)
    assert service.state(case.case_id) is S.PRESUBMIT_CHECKED


def test_recheck_does_not_raise_a_known_contradiction_again(service, reasons):
    case = extracted(service)
    service.run_presubmit_check(case.case_id, reasons, CHECK)
    service.advance(case.case_id, "rm_fixed", RM)
    report = service.run_presubmit_check(case.case_id, reasons, CHECK)
    assert report.contradictions == () and len(service.store.contradictions(case.case_id)) == 1
    assert {f.attempt for f in service.store.findings(case.case_id, attempt=1)} == {1}


def test_a_standing_value_feeds_the_rules_on_recheck(service, reasons):
    case = extracted(service)
    (k,) = service.run_presubmit_check(case.case_id, reasons, CHECK).contradictions
    fr = next(f for f in service.store.facts(case.case_id) if f.field == "identity.tax_residence"
              and f.value.iso2 == "FR")
    assert fr.status is FactStatus.CONTRADICTED
    service.resolve_contradiction(k.contradiction_id, "stands", fr.fact_id, "client's statement", RM)
    service.advance(case.case_id, "rm_fixed", RM)
    got = outcomes(service.run_presubmit_check(case.case_id, reasons, CHECK).findings)
    assert got["BR-TAX-RESIDENCE-DIFFERS"] == "fire"  # LU residence vs FR tax residence, now known


def test_open_for_compliance_counts_as_missing_for_the_rules(service, reasons):
    case = extracted(service)
    (k,) = service.run_presubmit_check(case.case_id, reasons, CHECK).contradictions
    service.resolve_contradiction(k.contradiction_id, "open", None, "ask compliance", RM)
    service.advance(case.case_id, "rm_fixed", RM)
    got = outcomes(service.run_presubmit_check(case.case_id, reasons, CHECK).findings)
    assert got["BR-TAX-RESIDENCE-DIFFERS"] == "unknown"


def test_check_outside_facts_extracted_writes_nothing(service, reasons):
    case = service.open_case("lead-1", "rm.alice", AS_OF)
    before = {t: service.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in TABLES if t != "audit_events"}
    with pytest.raises(IllegalTransition):
        service.run_presubmit_check(case.case_id, reasons, CHECK)
    after = {t: service.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in TABLES if t != "audit_events"}
    assert before == after  # only the refusal's audit is added
    assert service.store.audit(case.case_id)[-1].action == "transition_rejected"


def test_replay_gives_identical_findings(taxonomy, reasons):
    """H3: same inputs and rule version, same results."""
    runs = []
    for _ in range(2):
        svc = CaseService(SQLiteStore(), taxonomy, ROLES)
        case = extracted(svc)
        report = svc.run_presubmit_check(case.case_id, reasons, CHECK)
        runs.append([(f.source_id, f.outcome, f.effect, f.detail) for f in report.findings])
    assert runs[0] == runs[1]
