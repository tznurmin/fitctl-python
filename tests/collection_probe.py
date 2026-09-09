# Copyright 2026 fitctl contributors
# SPDX-License-Identifier: Apache-2.0

"""Cheap declared-effect harness probe; no fitctl import or evidence claims."""

import fcntl
import os
from pathlib import Path
import resource
import shutil
import threading
import time


def marked(scope, function):
    tid = threading.get_native_id()
    os.write(4, f'FITCTL_{scope}_BEGIN {tid}\n'.encode())
    try:
        return function()
    finally:
        os.write(4, f'FITCTL_END {tid}\n'.encode())


def process(mode):
    read, write = os.pipe2(os.O_CLOEXEC)
    null = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)
    child = os.fork()
    if child == 0:
        os.dup2(null, 0); os.dup2(write, 1); os.dup2(write, 2)
        argv = (['/env/bin/ip', '-json', 'addr', 'show'] if mode == 'missing' else
                ['/env/bin/python', '-I', '-B', '/tests/collection_provider.py', mode])
        try:
            os.execv(argv[0], argv)
        except FileNotFoundError:
            os._exit(127)
    os.close(write); os.close(null)
    if mode == 'sleep2':
        time.sleep(0.05)
        os.kill(child, 9)
    waited, status = os.waitpid(child, 0)
    assert waited == child
    assert os.waitstatus_to_exitcode(status) == (-9 if mode == 'sleep2' else 127 if mode == 'missing' else 0)
    data = os.read(read, 4096)
    os.close(read)
    return data


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        return os.read(fd, 65536)
    finally:
        os.close(fd)


def path_files(root, destination, payload):
    source = root / 'source'
    fd = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC, 0o600)
    os.write(fd, payload); os.close(fd)
    os.link(source, destination / 'hardlink')
    os.symlink(source, destination / 'symlink')
    first = os.open(source, os.O_RDONLY | os.O_CLOEXEC)
    second = os.open(destination / 'copy', os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC, 0o600)
    os.sendfile(second, first, 0, len(payload)); os.close(second)
    second = os.open(destination / 'reflink', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        try:
            fcntl.ioctl(second, 0x40049409, first)
        except OSError:
            pass  # Support is core's concern; the observer must see the attempt.
    finally:
        os.close(first); os.close(second)


def paths():
    try:
        with os.scandir('/dev/disk'):
            raise AssertionError('unexpected device links in isolated root')
    except FileNotFoundError:
        pass
    for pair, payload in ((False, b'fitctl-link-probe\n'), (True, b'fitctl-link-pair-probe\n')):
        prefix = f'.fitctl-link-{"pair-" if pair else ""}probe-{os.getpid()}-1'
        root = Path('/work/paths/a') / (prefix + '-source' if pair else prefix)
        destination = Path('/work/paths/b') / (prefix + '-destination') if pair else root
        roots = [root, destination] if pair else [root]
        for path in roots:
            path.mkdir()
        try:
            path_files(root, destination, payload)
        finally:
            for path in reversed(roots):
                shutil.rmtree(path)
    denied = Path('/work/paths/denied/.fitctl-link-probe-2-1')
    try:
        denied.mkdir()
    except PermissionError:
        pass
    else:
        raise AssertionError('denied path fixture did not deny creation')


def live():
    read('/proc/meminfo')
    read('/proc/self/mountinfo')
    os.statvfs('/work/paths/a')


def survey():
    resource.getrlimit(resource.RLIMIT_STACK)
    with os.scandir('/dev') as entries:
        assert {entry.name for entry in entries} == {'null', 'zero', 'urandom'}
    try:
        with os.scandir('/dev/dri'):
            raise AssertionError('unexpected GPU device directory in isolated root')
    except FileNotFoundError:
        pass
    assert process('missing') == b''


def run():
    for path in ('/work/collection/state/complete', '/work/collection-configs', '/work/paths/a', '/work/paths/b', '/work/paths/denied'):
        Path(path).mkdir(parents=True, exist_ok=True)
    corpus = Path('/work/collection/state/complete/snapshot.json')
    corpus.write_text('{}\n')
    config = Path('/work/collection-configs/config.json')
    config.write_text('{}\n')
    Path('/work/paths/denied').chmod(0)
    try:
        marked('REPLAY', lambda: (corpus.resolve(strict=True), read(corpus)))
        marked('CONFIG', lambda: read(config))
        marked('STATE', live)
        marked('PATH', paths)
        marked('SURVEY', survey)
        assert marked('PROVIDER', lambda: process('good'))
        assert marked('PROVIDER', lambda: process('delay0.2'))
        assert marked('PROVIDER', lambda: process('sleep2')) == b''
    finally:
        Path('/work/paths/denied').chmod(0o700)
    assert list(Path('/work/paths/a').iterdir()) == []
    assert list(Path('/work/paths/b').iterdir()) == []
