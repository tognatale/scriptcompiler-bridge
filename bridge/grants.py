import os

_readable = set()
_writable = set()


def _key(path):
    return os.path.normcase(os.path.realpath(path))


def allow_read(*paths):
    _readable.update(_key(path) for path in paths)


def allow_write(*paths):
    _writable.update(_key(path) for path in paths)


def can_read(path):
    return _key(path) in _readable


def can_write(path):
    return _key(path) in _writable
