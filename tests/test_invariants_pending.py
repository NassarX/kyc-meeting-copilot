"""Traceability: every spec invariant (docs/spec.md) appears in the test run. The ones owned by later milestones are skipped,
so they stay visible until implemented. Implemented: I1, I2, I4, I9, I11, I12 (test_models, test_store, test_service) and
I6 (test_reconcile). Partly: I8 holds as flags, not a minimum band (test_bounce_reasons); I10 is measured by the grader
(privacy leaks), not yet enforced by a filter (test_harness)."""
import pytest

PENDING = {
    "I3_score_only_from_rules_engine": "M2 rules",
    "I5_critical_fields_unconfirmed_widen_range": "M2 rules + M3 extraction",
    "I7_role_views_enforced_by_data_layer": "M5 review-ui (API views)",
    "I8_hard_triggers_set_minimum_band": "M2 scoring (today: flags only)",
    "I10_sensitive_topics_not_stored": "a sensitive-topic filter (today: measured, not enforced)",
}


@pytest.mark.parametrize("invariant", sorted(PENDING))
def test_invariant_pending(invariant):
    pytest.skip(f"owned by {PENDING[invariant]}")
