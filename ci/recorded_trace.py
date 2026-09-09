# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Lossless syscall framing; partial or undecodable traces are rejected."""

import ast
from dataclasses import dataclass
from decimal import Decimal
import re
import sys

from recorded_failures import RecordedFailure

LINE = re.compile(r"^(\d+\.\d+) (.*)$")
CALL = re.compile(r"^([a-zA-Z0-9_]+)\((.*)\) += (.*)$")
RESUMED = re.compile(r"^<\.\.\. ([a-zA-Z0-9_]+) resumed>(.*)$")


@dataclass(frozen=True)
class Event:
    pid: int
    time: Decimal
    name: str
    arguments: str
    result: str


def invalid():
    error = RecordedFailure("trace_invalid")
    frame = sys._getframe(1)
    for _ in range(4):
        if frame is None:
            break
        event = frame.f_locals.get("event")
        detail = " syscall=" + event.name if isinstance(event, Event) else ""
        error.add_note("observer " + frame.f_code.co_name + ":" + str(frame.f_lineno) + detail)
        frame = frame.f_back
    raise error


def parse_trace(pid, text):
    if not text or not text.endswith("\n"):
        invalid()
    events, pending = [], None
    previous = Decimal(0)
    for line in text.splitlines():
        match = LINE.fullmatch(line)
        if match is None:
            invalid()
        instant, body = Decimal(match[1]), match[2]
        if instant < previous:
            invalid()
        previous = instant
        if body.startswith("--- ") and body.endswith(" ---"):
            events.append(Event(pid, instant, "signal", body, ""))
            continue
        if body.startswith("+++ exited with ") and body.endswith(" +++"):
            events.append(Event(pid, instant, "exited", "", body[16:-4]))
            continue
        if body == "+++ killed by SIGKILL +++":
            if pending is not None:
                invalid()
            events.append(Event(pid, instant, "killed", "SIGKILL", ""))
            continue
        if body.endswith("<unfinished ...>"):
            if pending is not None:
                invalid()
            pending = (instant, body.removesuffix("<unfinished ...>"))
            continue
        resumed = RESUMED.fullmatch(body)
        if resumed:
            if pending is None or not pending[1].startswith(resumed[1] + "("):
                invalid()
            instant, body = pending[0], pending[1] + resumed[2]
            pending = None
        call = CALL.fullmatch(body)
        if call is None:
            invalid()
        events.append(Event(pid, instant, call[1], call[2], call[3]))
    if pending is not None or not events:
        invalid()
    return events


def arguments(text):
    """Separate top-level syscall arguments without interpreting data buffers."""
    values, start, brackets, quote, escaped = [], 0, [], False, False
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
        elif char in "[{(<":
            brackets.append(char)
        elif char == ">" and text[max(0, index - 2):index + 2] == " => " and (not brackets or brackets[-1] != "<"):
            continue  # strace's decoded input => output annotation, not a delimiter.
        elif char in "]})>":
            if not brackets or brackets.pop() != {']': '[', '}': '{', ')': '(', '>': '<'}[char]:
                invalid()
        elif char == "," and not brackets:
            values.append(text[start:index].strip())
            start = index + 1
    if quote or brackets:
        invalid()
    values.append(text[start:].strip())
    return values


def quoted(text):
    if not text.startswith('"') or not text.endswith('"') or text.endswith('"...'):
        invalid()
    try:
        value = ast.literal_eval("b" + text).decode("utf-8", errors="strict")
    except (ValueError, SyntaxError, UnicodeError):
        invalid()
    if "\0" in value:
        invalid()
    return value


def descriptor(text):
    try:
        return int(text.split("<", 1)[0], 0)
    except ValueError:
        invalid()
