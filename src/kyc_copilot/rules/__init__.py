"""Bounce reasons: why a KYC file comes back, as data, plus the deterministic checks that test a case against them.

Eng review D7 (loader checks field and document-type references, a source per reason) and D18 (four worked
checks: missing fact, expired document vs as_of_date, cross-field mismatch, threshold trigger).
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

import yaml

from kyc_copilot.domain.enums import FactStatus
from kyc_copilot.domain.models import Fact
from kyc_copilot.taxonomy import Taxonomy

DEFAULT_PATH = Path(__file__).with_name("bounce_reasons.yaml")

SOURCE_TYPES = frozenset({"public", "interview"})  # public texts or interviews; nothing else
EFFECTS = frozenset({"bounce", "flag"})
CATEGORIES = frozenset({"fact", "document", "consistency", "risk"})
CHECK_KINDS = frozenset({"missing_fact", "document_missing", "document_expired", "field_mismatch", "threshold",
                         "any_fact", "country_in_list", "value_in", "uncorroborated_amount"})


class BounceReasonError(ValueError):
    pass


class Outcome(StrEnum):
    FIRE = "fire"        # the reason applies: the file would bounce, or the flag shows
    PASS = "pass"        # the case satisfies the check
    UNKNOWN = "unknown"  # not enough facts to decide; never read as a pass


@dataclass(frozen=True)
class Source:
    type: str
    ref: str
    checked: bool


@dataclass(frozen=True)
class Reason:
    id: str
    title: str
    category: str
    effect: str
    source: Source
    check: dict


@dataclass(frozen=True)
class NamedList:
    """A reference list a check can use, e.g. high-risk jurisdictions. Same source rules as a reason."""
    name: str
    members: frozenset[str]
    source: Source
    as_of: str


@dataclass(frozen=True)
class BounceReasons:
    version: str
    reasons: tuple[Reason, ...]
    lists: dict[str, NamedList] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    reason_id: str
    outcome: Outcome
    effect: str
    fact_refs: tuple[str, ...]
    detail: str


# ---------- loading ----------

def load_bounce_reasons(taxonomy: Taxonomy, path: Path = DEFAULT_PATH) -> BounceReasons:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    lists = {name: _named_list(name, body) for name, body in (raw.get("lists") or {}).items()}
    seen: set[str] = set()
    reasons = []
    for row in raw.get("reasons") or ():
        rid = row.get("id")
        if not rid:
            raise BounceReasonError(f"{path.name}: a reason has no id")
        if rid in seen:
            raise BounceReasonError(f"{rid}: duplicate id")
        seen.add(rid)
        reasons.append(_reason(rid, row, taxonomy, lists))
    if not reasons:
        raise BounceReasonError(f"{path.name}: no reasons")
    return BounceReasons(version=str(raw["version"]), reasons=tuple(reasons), lists=lists)


def _source(owner: str, src: object) -> Source:
    if not isinstance(src, dict) or not src.get("ref"):
        raise BounceReasonError(f"{owner}: every reason needs a source with a ref")
    if src.get("type") not in SOURCE_TYPES:
        raise BounceReasonError(f"{owner}: source type must be one of {sorted(SOURCE_TYPES)}, got {src.get('type')!r}")
    return Source(type=src["type"], ref=str(src["ref"]), checked=bool(src.get("checked", False)))


def _named_list(name: str, body: dict) -> NamedList:
    members = frozenset(str(m) for m in (body.get("members") or ()))
    if not members:
        raise BounceReasonError(f"list {name}: no members")
    return NamedList(name=name, members=members, source=_source(f"list {name}", body.get("source")),
                     as_of=str(body.get("as_of") or ""))


def _reason(rid: str, row: dict, taxonomy: Taxonomy, lists: dict[str, NamedList]) -> Reason:
    source = _source(rid, row.get("source"))
    if row.get("effect") not in EFFECTS:
        raise BounceReasonError(f"{rid}: effect must be one of {sorted(EFFECTS)}")
    if row.get("category") not in CATEGORIES:
        raise BounceReasonError(f"{rid}: category must be one of {sorted(CATEGORIES)}")
    check = dict(row.get("check") or {})
    _validate_check(rid, check, taxonomy, lists)
    return Reason(id=rid, title=str(row.get("title") or rid), category=row["category"], effect=row["effect"],
                  source=source, check=check)


def _field(rid: str, taxonomy: Taxonomy, key: object, want_type: str | None = None) -> None:
    spec = taxonomy.fields.get(key) if isinstance(key, str) else None
    if spec is None:
        raise BounceReasonError(f"{rid}: unknown field {key!r} in taxonomy {taxonomy.version}")
    if want_type and spec.type != want_type:
        raise BounceReasonError(f"{rid}: {key} is {spec.type}, this check needs {want_type}")


def _validate_check(rid: str, check: dict, taxonomy: Taxonomy, lists: dict[str, NamedList]) -> None:
    kind = check.get("kind")
    if kind not in CHECK_KINDS:
        raise BounceReasonError(f"{rid}: unknown check kind {kind!r}")
    if kind == "missing_fact":
        _field(rid, taxonomy, check.get("field"))
    elif kind in ("document_missing", "document_expired"):
        if check.get("document_type") not in taxonomy.document_types:
            raise BounceReasonError(f"{rid}: unknown document type {check.get('document_type')!r}")
    elif kind == "field_mismatch":
        fields = check.get("fields")
        if not isinstance(fields, list) or len(fields) != 2:
            raise BounceReasonError(f"{rid}: field_mismatch needs exactly two fields")
        for f in fields:
            _field(rid, taxonomy, f)
        if taxonomy.fields[fields[0]].type != taxonomy.fields[fields[1]].type:
            raise BounceReasonError(f"{rid}: field_mismatch compares fields of different types")
    elif kind == "threshold":
        _field(rid, taxonomy, check.get("field"), want_type="money")
        try:
            Decimal(str(check.get("at_least")))
        except InvalidOperation:
            raise BounceReasonError(f"{rid}: threshold at_least must be a number") from None
        if not isinstance(check.get("currency"), str) or len(check["currency"]) != 3:
            raise BounceReasonError(f"{rid}: threshold needs a 3-letter currency")
    elif kind == "any_fact":
        for f in check.get("fields") or []:
            _field(rid, taxonomy, f)
        if not check.get("fields"):
            raise BounceReasonError(f"{rid}: any_fact needs fields")
        if check.get("cleared_by") is not None:
            _field(rid, taxonomy, check["cleared_by"], want_type="bool")
    elif kind == "country_in_list":
        for f in check.get("fields") or []:
            _field(rid, taxonomy, f, want_type="country")
        if not check.get("fields"):
            raise BounceReasonError(f"{rid}: country_in_list needs fields")
        if check.get("list") not in lists:
            raise BounceReasonError(f"{rid}: unknown list {check.get('list')!r}")
    elif kind == "value_in":
        _field(rid, taxonomy, check.get("field"), want_type="enum")
        bad = set(check.get("values") or []) - taxonomy.fields[check["field"]].values
        if bad or not check.get("values"):
            raise BounceReasonError(f"{rid}: values {sorted(bad)} not in {check['field']}")
    elif kind == "uncorroborated_amount":
        _field(rid, taxonomy, check.get("field"), want_type="money")
        _field(rid, taxonomy, check.get("type_field"), want_type="enum")
        Decimal(str(check.get("at_least")))
        by = check.get("corroborated_by")
        if not isinstance(by, dict) or not by:
            raise BounceReasonError(f"{rid}: uncorroborated_amount needs corroborated_by")
        bad_types = set(by) - taxonomy.fields[check["type_field"]].values
        bad_docs = {d for docs in by.values() for d in docs} - taxonomy.document_types
        if bad_types or bad_docs:
            raise BounceReasonError(f"{rid}: unknown event types {sorted(bad_types)} or document types {sorted(bad_docs)}")


# ---------- evaluation ----------

def current_facts(facts: Iterable[Fact]) -> list[Fact]:
    """Drop facts that something else in the list supersedes, and facts marked superseded."""
    facts = list(facts)
    replaced = {f.supersedes_fact_id for f in facts if f.supersedes_fact_id}
    return [f for f in facts if f.fact_id not in replaced and f.status is not FactStatus.SUPERSEDED]


def evaluate(reasons: BounceReasons, facts: Sequence[Fact], as_of: date) -> tuple[CheckResult, ...]:
    """Test every reason against the case's facts. Pure: same inputs, same results, in file order."""
    live = current_facts(facts)
    out = []
    for r in reasons.reasons:
        if r.check["kind"] == "country_in_list":
            out.append(_country_in_list(r, live, reasons.lists[r.check["list"]]))
        else:
            out.append(_CHECKS[r.check["kind"]](r, live, as_of))
    return tuple(out)


def _result(r: Reason, outcome: Outcome, refs: Iterable[Fact], detail: str) -> CheckResult:
    return CheckResult(reason_id=r.id, outcome=outcome, effect=r.effect,
                       fact_refs=tuple(f.fact_id for f in refs), detail=detail)


def _by_field(facts: Sequence[Fact], field: str) -> list[Fact]:
    return [f for f in facts if f.field == field]


def _missing_fact(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    found = _by_field(facts, r.check["field"])
    if found:
        return _result(r, Outcome.PASS, found, f"{r.check['field']} is present")
    return _result(r, Outcome.FIRE, (), f"{r.check['field']} is missing")


def _documents(facts: Sequence[Fact], doc_type: str) -> dict[str, dict[str, Fact]]:
    """Group document facts by subject_ref, keeping only documents of the given type."""
    groups: dict[str, dict[str, Fact]] = {}
    for f in facts:
        if f.field.startswith("document.") and f.subject_ref:
            groups.setdefault(f.subject_ref, {})[f.field] = f
    return {ref: g for ref, g in groups.items()
            if "document.type" in g and g["document.type"].value.value == doc_type}  # type: ignore[union-attr]


def _all_documents(facts: Sequence[Fact]) -> dict[str, dict[str, Fact]]:
    groups: dict[str, dict[str, Fact]] = {}
    for f in facts:
        if f.field.startswith("document.") and f.subject_ref:
            groups.setdefault(f.subject_ref, {})[f.field] = f
    return {ref: g for ref, g in groups.items() if "document.type" in g}


def _present(group: dict[str, Fact]) -> bool:
    flag = group.get("document.present")
    return flag is not None and flag.value.value is True  # type: ignore[union-attr]


def _document_missing(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    t = r.check["document_type"]
    present = [g for g in _documents(facts, t).values() if _present(g)]
    if present:
        return _result(r, Outcome.PASS, [g["document.present"] for g in present], f"{t} on file")
    return _result(r, Outcome.FIRE, (), f"no {t} on file")


def _document_expired(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    t = r.check["document_type"]
    expiries = [g["document.expiry_date"] for g in _documents(facts, t).values()
                if _present(g) and "document.expiry_date" in g]
    valid = [e for e in expiries if e.value.value >= as_of]  # type: ignore[union-attr]
    if valid:
        return _result(r, Outcome.PASS, valid, f"{t} valid on {as_of.isoformat()}")
    if expiries:
        return _result(r, Outcome.FIRE, expiries, f"{t} expired before {as_of.isoformat()}")
    return _result(r, Outcome.UNKNOWN, (), f"no expiry date for a {t} on file")


def _field_mismatch(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    a, b = r.check["fields"]
    fa, fb = _by_field(facts, a), _by_field(facts, b)
    if not fa or not fb:
        return _result(r, Outcome.UNKNOWN, fa + fb, f"need both {a} and {b}")
    if {f.value for f in fa} == {f.value for f in fb}:
        return _result(r, Outcome.PASS, fa + fb, f"{a} matches {b}")
    return _result(r, Outcome.FIRE, fa + fb, f"{a} differs from {b}")


def _threshold(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    field, cur = r.check["field"], r.check["currency"]
    line = Decimal(str(r.check["at_least"]))
    found = _by_field(facts, field)
    same = [f for f in found if f.value.currency == cur]  # type: ignore[union-attr]
    over = [f for f in same if f.value.amount >= line]  # type: ignore[union-attr]
    if over:
        return _result(r, Outcome.FIRE, over, f"{field} at or above {line} {cur}")
    if not found or len(same) < len(found):
        # No amount, or an amount in another currency: no FX in the PoC, so do not guess.
        return _result(r, Outcome.UNKNOWN, found, f"cannot compare {field} with {line} {cur}")
    return _result(r, Outcome.PASS, same, f"{field} below {line} {cur}")


def _any_fact(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    hits = [f for f in facts if f.field in r.check["fields"]]
    if hits:  # an indicator wins over a declaration of none (e.g. a PEP brother mentioned in passing)
        return _result(r, Outcome.FIRE, hits, f"indicator present: {', '.join(sorted({f.field for f in hits}))}")
    cleared = [f for f in _by_field(facts, r.check.get("cleared_by") or "") if f.value.value is True]  # type: ignore[union-attr]
    if cleared:
        return _result(r, Outcome.PASS, cleared, "declared none, no indicator found")
    return _result(r, Outcome.UNKNOWN, (), "no indicator and no declaration")


def _country_in_list(r: Reason, facts: Sequence[Fact], named: NamedList) -> CheckResult:
    found = [f for f in facts if f.field in r.check["fields"]]
    listed = [f for f in found if f.value.iso2 in named.members]  # type: ignore[union-attr]
    if listed:
        codes = ", ".join(sorted({f.value.iso2 for f in listed}))  # type: ignore[union-attr]
        return _result(r, Outcome.FIRE, listed, f"{codes} on {named.name} (as of {named.as_of})")
    if found:
        return _result(r, Outcome.PASS, found, f"no country on {named.name} (as of {named.as_of})")
    return _result(r, Outcome.UNKNOWN, (), "no country facts to check")


def _value_in(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    found = _by_field(facts, r.check["field"])
    hits = [f for f in found if f.value.value in r.check["values"]]  # type: ignore[union-attr]
    if hits:
        return _result(r, Outcome.FIRE, hits, f"{r.check['field']} is {', '.join(sorted({f.value.value for f in hits}))}")  # type: ignore[union-attr]
    # Not a required field: no matching fact means none was declared, which passes.
    return _result(r, Outcome.PASS, found, f"no {r.check['field']} in {sorted(r.check['values'])}")


def _uncorroborated_amount(r: Reason, facts: Sequence[Fact], as_of: date) -> CheckResult:
    c = r.check
    line, cur = Decimal(str(c["at_least"])), c["currency"]
    present_docs = {g["document.type"].value.value for g in _all_documents(facts).values() if _present(g)}  # type: ignore[union-attr]
    fired, unknown = [], []
    for f in _by_field(facts, c["field"]):
        if f.value.currency != cur:  # type: ignore[union-attr]
            unknown.append(f)
            continue
        if f.value.amount < line:  # type: ignore[union-attr]
            continue
        kinds = [t.value.value for t in _by_field(facts, c["type_field"]) if t.subject_ref == f.subject_ref]  # type: ignore[union-attr]
        if not kinds:
            unknown.append(f)
            continue
        if not any(set(c["corroborated_by"].get(k, ())) & present_docs for k in kinds):
            fired.append(f)
    if fired:
        return _result(r, Outcome.FIRE, fired, f"{c['field']} at or above {line} {cur} with no corroborating document")
    if unknown:
        return _result(r, Outcome.UNKNOWN, unknown, f"cannot judge {c['field']} (currency or event type)")
    return _result(r, Outcome.PASS, (), f"no uncorroborated {c['field']} at or above {line} {cur}")


_CHECKS = {
    "missing_fact": _missing_fact,
    "document_missing": _document_missing,
    "document_expired": _document_expired,
    "field_mismatch": _field_mismatch,
    "threshold": _threshold,
    "any_fact": _any_fact,
    "value_in": _value_in,
    "uncorroborated_amount": _uncorroborated_amount,
}
