"""Fact taxonomy: which fields exist, their value types, and which are critical or required."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from kyc_copilot.domain.models import Fact

_KINDS_FOR_TYPE: dict[str, frozenset[str]] = {
    "text": frozenset({"text"}),
    "enum": frozenset({"text"}),
    "date": frozenset({"date", "relative_date"}),
    "money": frozenset({"money"}),
    "percent": frozenset({"percent"}),
    "country": frozenset({"country"}),
    "bool": frozenset({"bool"}),
}

DEFAULT_PATH = Path(__file__).with_name("tax-v0.2.yaml")
_LISTS = ("document_types",)  # named top-level lists an enum may take its values from (values_from)


class TaxonomyError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    key: str
    type: str
    critical: bool
    required: bool
    grouped: bool
    values: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Taxonomy:
    version: str
    fields: dict[str, FieldSpec]
    document_types: frozenset[str] = frozenset()

    @property
    def critical_fields(self) -> frozenset[str]:
        return frozenset(k for k, f in self.fields.items() if f.critical)

    @property
    def required_fields(self) -> frozenset[str]:
        return frozenset(k for k, f in self.fields.items() if f.required)

    def validate_fact(self, fact: Fact) -> None:
        spec = self.fields.get(fact.field)
        if spec is None:
            raise TaxonomyError(f"unknown field {fact.field!r} for taxonomy {self.version}")
        if fact.value.kind not in _KINDS_FOR_TYPE[spec.type]:
            raise TaxonomyError(f"{fact.field} expects {spec.type}, got {fact.value.kind}")
        if spec.type == "enum" and fact.value.value not in spec.values:  # type: ignore[union-attr]
            raise TaxonomyError(f"{fact.field} value must be one of {sorted(spec.values)}")
        if spec.grouped and not fact.subject_ref:
            raise TaxonomyError(f"{fact.field} is grouped and needs a subject_ref")


def load_taxonomy(path: Path = DEFAULT_PATH) -> Taxonomy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    lists = {name: frozenset(raw.get(name) or ()) for name in _LISTS}
    fields: dict[str, FieldSpec] = {}
    for key, f in raw["fields"].items():
        if f["type"] not in _KINDS_FOR_TYPE:
            raise TaxonomyError(f"{key}: unknown type {f['type']!r}")
        values = frozenset(f.get("values", ()))
        source = f.get("values_from")
        if source is not None:
            if values:
                raise TaxonomyError(f"{key}: give either values or values_from, not both")
            if source not in lists or not lists[source]:
                raise TaxonomyError(f"{key}: values_from {source!r} names no non-empty list in {path.name}")
            values = lists[source]
        if f["type"] == "enum" and not values:
            raise TaxonomyError(f"{key}: enum needs values")
        fields[key] = FieldSpec(
            key=key, type=f["type"], critical=bool(f["critical"]), required=bool(f["required"]),
            grouped=bool(f.get("grouped", False)), values=values,
        )
    return Taxonomy(version=raw["version"], fields=fields, document_types=lists["document_types"])
