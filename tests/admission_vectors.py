# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Concrete request vectors shared by installed assertions and core preparation."""

from dataclasses import dataclass

from support import AT, asset

Q = 1_048_576
TYPE = (TypeError, "invalid argument type")
BUDGET = (ValueError, "argument budget exceeded")
UNICODE = (ValueError, "invalid Unicode scalar")
CYCLE = (ValueError, "cyclic input")
KEY = (KeyError, "unknown builtin configuration")
MODE = (ValueError, "unsupported validation mode")


@dataclass(frozen=True)
class Handle:
    name: str


@dataclass(frozen=True)
class Case:
    name: str
    operation: str
    kwargs: dict
    error: tuple | None = None

    @property
    def reference(self):
        return self.error is None or self.error == KEY


class Sentinel:
    calls = 0

    def forbidden(self, *args):
        Sentinel.calls += 1
        raise AssertionError("coercion callback invoked")

    __str__ = __repr__ = __iter__ = __len__ = forbidden


class Text(str):
    __str__ = __repr__ = Sentinel.forbidden


class Items(list):
    __iter__ = __len__ = Sentinel.forbidden


class Object(dict):
    __iter__ = __len__ = Sentinel.forbidden


def pad(size, multibyte=False):
    return "é" * (size // 2) + "a" * (size % 2) if multibyte else "a" * size


def pack(size):
    return {"k": "a" * (size - 1)}


def nested(size):
    value = None
    for _ in range(size):
        value = [value]
    return {"k": value}


def defaults(operation):
    if operation == "builtin":
        return {"category": "policy", "config_id": "general_compute_default.v1.json"}
    return {"at": AT, **({"profile": "local"} if operation == "redact" else {})}


def scalar_cases():
    yield Case("builtin/selected", "builtin", defaults("builtin"))
    for multi in (False, True):
        for operation in ("derive", "validate", "redact"):
            for size in (63, 64, 65):
                yield Case(f"at/{operation}/{multi}/{size}", operation,
                           {**defaults(operation), "at": pad(size, multi)}, BUDGET if size > 64 else None)
        for operation in ("derive", "validate"):
            for size in (4095, 4096, 4097):
                yield Case(f"notes/{operation}/{multi}/{size}", operation,
                           {"at": AT, "notes": pad(size, multi)}, BUDGET if size > 4096 else None)
        for category in (63, 64, 65):
            for identity in (127, 128, 129):
                yield Case(f"builtin/{multi}/{category}/{identity}", "builtin",
                           {"category": pad(category, multi), "config_id": pad(identity, multi)},
                           BUDGET if category > 64 or identity > 128 else KEY)
        for size in (31, 32, 33):
            for operation, slot in (("redact", "profile"), ("validate", "mode")):
                error = BUDGET if size > 32 else MODE if slot == "mode" else None
                yield Case(f"enum/{operation}/{multi}/{size}", operation,
                           {"at": AT, slot: pad(size, multi)}, error)
    for operation, slot, values in (
        ("redact", "profile", ("", "local", "fleet", "auditor", "external")),
        ("validate", "mode", ("", "contract_only", "state_advisory", "state_required")),
    ):
        for value in values:
            yield Case(f"enum/{operation}/{value or 'empty'}", operation,
                       {"at": AT, slot: value}, MODE if slot == "mode" and not value else None)


def control_cases():
    slots = (("derive", "at"), ("validate", "at"), ("redact", "at"),
             ("derive", "notes"), ("validate", "notes"), ("builtin", "category"),
             ("builtin", "config_id"), ("redact", "profile"), ("validate", "mode"))
    for operation, slot in slots:
        values = (("int", 0, TYPE), ("bool", True, TYPE), ("subclass", Text("x"), TYPE),
                  ("high", "\ud800", UNICODE), ("low", "\udc00", UNICODE),
                  ("composed", "é", None), ("decomposed", "e\u0301", None),
                  ("none", None, None if slot == "notes" else TYPE))
        for label, value, error in values:
            if error is None and slot == "mode":
                error = MODE
            if error is None and operation == "builtin":
                error = KEY
            yield Case(f"control/{operation}/{slot}/{label}", operation,
                       {**defaults(operation), slot: value}, error)


def cases():
    from admission_collections import collection_cases
    yield from scalar_cases()
    yield from control_cases()
    yield from collection_cases()


def bind(case, module, handles):
    kwargs = dict(case.kwargs)
    if type(kwargs.get("thermal_evidence")) is list:
        kwargs["thermal_evidence"] = [handles[item.name] if isinstance(item, Handle) else item
                                      for item in kwargs["thermal_evidence"]]
    if case.operation == "derive":
        return module.derive_contract, (handles["survey"], handles["policy"]), kwargs
    if case.operation == "validate":
        return module.validate, (handles["contract"], handles["profile"]), kwargs
    if case.operation == "redact":
        return handles["survey"].redact, (), kwargs
    if case.operation == "builtin":
        return module.builtin_config, (), kwargs
    raise AssertionError("unknown admission operation")


def reference_input(case):
    assert case.reference
    kwargs = dict(case.kwargs)
    if type(kwargs.get("thermal_evidence")) is list:
        kwargs["thermal_evidence"] = [item.name for item in kwargs["thermal_evidence"]]
    return {"name": case.name, "operation": case.operation, "kwargs": kwargs}
