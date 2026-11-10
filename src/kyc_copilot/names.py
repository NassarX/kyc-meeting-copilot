"""Name variants (hardening, item 4): is a contradiction between two names really two people, or one name heard or
written differently? Flag only, never merge: reconcile still records the contradiction; this explains it to the RM.

Kinds, strongest first: same (equal after removing case, accents, punctuation), honorific (a title added or dropped),
reordered ("Vandenberg, Pieter"), initial ("M. Egger"), typo (one edit: insert, delete, substitute or swap two
letters, Damerau distance 1, on names of 3+ letters), variant (same surname, a given name spelt slightly differently:
Isabelle / Isabel), surname (one side is the other's surname alone).

Adapted from gbrain (src/core/entities/name-variants.ts and near-name.ts), MIT License, Copyright (c) 2026
Garry Tan. https://github.com/garrytan/gbrain
"""
from __future__ import annotations

import re
import unicodedata

HONORIFICS = frozenset("mr mrs ms miss dr prof sir dame herr frau mme mlle sr sra don dona".split())
NAME_FIELDS = frozenset({"identity.full_name", "relationship.person_present", "structure.name",
                         "wealth_event.counterparty", "structure.beneficial_owner"})


def _tokens(name: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return [t for t in re.split(r"[^a-z0-9]+", plain) if t]


def _damerau1(a: str, b: str) -> bool:
    """True when a and b differ by exactly one insert, delete, substitution or adjacent swap."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


_NOTE = re.compile(r"\s*[(\[][^()\[\]]*[)\]]\s*$")


def clean_name(text: str) -> str:
    """Drop trailing notes in brackets ("Orla Brennan-Silva (beneficiaries)"): a role is not part of a name, and it
    would make the name fail to match the bank's file. If nothing would be left, keep the text as given."""
    out = text
    while _NOTE.search(out):
        out = _NOTE.sub("", out)
    return out.strip() or text


def name_relation(a: str, b: str) -> str | None:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return None
    if ta == tb:
        return "same"
    ca, cb = [t for t in ta if t not in HONORIFICS], [t for t in tb if t not in HONORIFICS]
    if ca == cb and ca:
        return "honorific"
    if sorted(ca) == sorted(cb) and len(ca) > 1:
        return "reordered"
    if len(ca) == len(cb) and len(ca) > 1 and ca[-1] == cb[-1] and all(
            x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y)) for x, y in zip(ca, cb)):
        return "initial"
    ja, jb = "".join(ca), "".join(cb)
    if len(ca) == len(cb) and min(len(ja), len(jb)) >= 3 and _damerau1(ja, jb):
        return "typo"
    if len(ca) == len(cb) and len(ca) > 1 and ca[-1] == cb[-1] and all(
            x == y or _damerau1(x, y) or ((x.startswith(y) or y.startswith(x)) and abs(len(x) - len(y)) <= 2
                                          and min(len(x), len(y)) >= 4) for x, y in zip(ca[:-1], cb[:-1])):
        return "variant"  # same surname, a given name spelt slightly differently (Isabelle / Isabel)
    if (len(cb) < len(ca) and ca[-len(cb):] == cb) or (len(ca) < len(cb) and cb[-len(ca):] == ca):
        return "surname"
    return None


_EXPLAIN = {
    "same": "probably the same name, written differently",
    "honorific": "probably the same name, with a title added or dropped",
    "reordered": "probably the same name, in a different order",
    "initial": "likely the same name, with an initial",
    "typo": "likely the same name: they differ by one letter, a common transcription slip",
    "variant": "likely the same person: same surname, the first name spelt differently",
    "surname": "likely the same person: one is the surname alone",
}


def explain_conflict(field: str, values: list[str]) -> str | None:
    """A plain-language note for a name contradiction, or None when the names look like different people."""
    if field not in NAME_FIELDS or len(values) < 2:
        return None
    kinds = {name_relation(values[0], v) for v in values[1:]}
    if None in kinds or not kinds:
        return None
    order = list(_EXPLAIN)
    text = _EXPLAIN[max(kinds, key=order.index)]
    return text[0].upper() + text[1:] + ". Confirm the spelling with the client."
