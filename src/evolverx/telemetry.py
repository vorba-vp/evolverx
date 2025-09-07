from __future__ import annotations
from collections import defaultdict

_failures: dict[tuple[str, str], int] = defaultdict(int)


def record_failure(module: str, func: str) -> int:
    key = (module, func)
    _failures[key] += 1
    return _failures[key]


def reset_failures(module: str, func: str) -> None:
    _failures[(module, func)] = 0


def get_failures(module: str, func: str) -> int:
    return _failures.get((module, func), 0)
