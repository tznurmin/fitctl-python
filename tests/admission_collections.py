# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Collection and combined-budget inputs for the recorded admission case."""

from admission_vectors import (AT, BUDGET, CYCLE, TYPE, Case, Handle, Items,
                               Object, Q, Sentinel, asset, nested, pack)


def collection_cases():
    for count in (15, 16, 17):
        yield Case(f"packs/items/{count}", "derive", {"at": AT, "extension_packs": [{}] * count},
                   BUDGET if count > 16 else None)
    yield Case("packs/items-before-element", "derive",
               {"at": AT, "extension_packs": [{}] * 16 + [Sentinel()]}, BUDGET)
    for size in (Q - 1, Q, Q + 1):
        for field in ("extension_packs", "invocation_context"):
            value = [pack(size)] if field == "extension_packs" else pack(size)
            yield Case(f"document/{field}/{size}", "derive", {"at": AT, field: value},
                       BUDGET if size > Q else None)
    for label, value in (("tuple", ()), ("subclass", Items([{}])), ("none-item", [None]),
                         ("callback", [Sentinel()]), ("dict-subclass", [Object()])):
        yield Case(f"packs/type/{label}", "derive", {"at": AT, "extension_packs": value}, TYPE)
    for label, value in (("list", []), ("subclass", Object())):
        yield Case(f"context/type/{label}", "derive", {"at": AT, "invocation_context": value}, TYPE)
    one = {}; one["k"] = one
    first = {}; second = [first]; first["k"] = second
    try:
        for label, value in (("self", one), ("pair", first)):
            yield Case(f"context/cycle/{label}", "derive", {"at": AT, "invocation_context": value}, CYCLE)
        for label, kwargs, error in (
            ("type-first", {"at": "a" * 65, "notes": False}, TYPE),
            ("at-first", {"at": "a" * 65, "extension_packs": [pack(Q + 1)]}, BUDGET),
            ("pack-first", {"at": AT, "extension_packs": [pack(Q + 1)], "invocation_context": one}, BUDGET),
            ("individual-first", {"at": AT, "extension_packs": [pack(Q)] * 7 + [pack(Q + 1)]}, BUDGET),
        ):
            yield Case(f"order/{label}", "derive", kwargs, error)
    finally:
        one.clear(); first.clear(); second.clear()
    shared = pack(Q)
    for delta in (-1, 0, 1):
        for context in (False, True):
            kwargs = {"at": AT, "extension_packs": [shared] * (6 if context else 7)
                      + [pack(Q - (4116 if context else 20) + delta)]}
            if context:
                kwargs.update(invocation_context=shared, notes="a" * 4096)
            yield Case(f"combined/bytes/{context}/{delta}", "derive", kwargs, BUDGET if delta > 0 else None)
    for count in (99992, 99993, 99994):
        yield Case(f"combined/nodes/{count}", "derive",
                   {"at": AT, "extension_packs": [{"k": [None] * count}], "invocation_context": {"k": []}},
                   BUDGET if count > 99993 else None)
    for depth in (62, 63, 64):
        for field in ("extension_packs", "invocation_context"):
            value = [nested(depth)] if field == "extension_packs" else nested(depth)
            yield Case(f"depth/{field}/{depth}", "derive", {"at": AT, field: value}, BUDGET if depth > 63 else None)
    yield from thermal_cases()
    for label, empty in (("none", None), ("list", [])):
        for notes in (None, ""):
            yield Case(f"empty/packs/{label}/{notes is None}", "derive",
                       {"at": AT, "extension_packs": empty, "notes": notes, "invocation_context": None})
            yield Case(f"empty/thermal/{label}/{notes is None}", "validate",
                       {"at": AT, "thermal_evidence": empty, "notes": notes, "max_state_age_seconds": None})
    yield Case("context/without-packs", "derive",
               {"at": AT, "extension_packs": [], "invocation_context": asset("invocation_contexts")})
    left, right = {"k": "left"}, {"k": "right"}
    for label, packs in (("forward", [left, right, left]), ("reverse", [right, left])):
        yield Case(f"order/packs/{label}", "derive", {"at": AT, "extension_packs": packs})


def thermal_cases():
    thermal = Handle("thermal")
    for count in (127, 128, 129):
        yield Case(f"thermal/items/{count}", "validate", {"at": AT, "thermal_evidence": [thermal] * count},
                   BUDGET if count > 128 else None)
    yield Case("thermal/items-before-element", "validate",
               {"at": AT, "thermal_evidence": [thermal] * 128 + [Sentinel()]}, BUDGET)
    for label, value, error in (
        ("tuple", (), TYPE), ("subclass", Items([thermal]), TYPE), ("none-item", [None], TYPE),
        ("integer", [0], TYPE), ("survey", [Handle("survey")], (ValueError, "incompatible artifact kind")),
    ):
        yield Case(f"thermal/type/{label}", "validate", {"at": AT, "thermal_evidence": value}, error)
    for label, items in (("forward", [thermal, Handle("thermal-copy"), thermal]),
                         ("reverse", [Handle("thermal-copy"), thermal])):
        yield Case(f"order/thermal/{label}", "validate", {"at": AT, "thermal_evidence": items})
