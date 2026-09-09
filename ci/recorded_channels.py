# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded pipes for test results and execution markers."""

from contextlib import contextmanager
import os

from recorded_failures import RecordedFailure
def add_bytes(used, size, limit):
    if used < 0 or size < 0 or size > limit - used:
        raise RecordedFailure("staging_limit_exceeded")


class Channel:
    def __init__(self, limit):
        self.reader, self.writer = os.pipe()
        os.set_blocking(self.reader, False)
        self.limit, self.data, self.eof = limit, bytearray(), False

    def read(self):
        while not self.eof:
            try:
                data = os.read(self.reader, 65536)
            except BlockingIOError:
                break
            if not data:
                self.eof = True
                break
            add_bytes(len(self.data), len(data), self.limit)
            self.data.extend(data)

    def close_writer(self):
        if self.writer is not None:
            os.close(self.writer)
            self.writer = None

    def finish(self):
        self.close_writer()
        self.read()
        if not self.eof or not self.data:
            raise RecordedFailure("trace_invalid")
        return bytes(self.data)

    def close(self):
        self.close_writer()
        os.close(self.reader)


@contextmanager
def channels():
    receipt = Channel(1024 ** 2)
    try:
        markers = Channel(1024 ** 2)
        try:
            yield receipt, markers
        finally:
            markers.close()
    finally:
        receipt.close()
