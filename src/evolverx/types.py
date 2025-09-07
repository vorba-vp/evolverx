from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence


@dataclass
class EvolverxConfig:
    persist_mode: str = "cache"  # "cache" | "source" (source TODO)
    allow_imports: tuple[str, ...] = (
        "json",
        "re",
        "math",
        "datetime",
        "typing",
        "time",
        "requests",
    )
    max_body_lines: int = 200
    auto_resynthesize_on_any_error: bool = True
    cache_dir: str | None = None  # default resolved at runtime
    network_allowlist: Sequence[str] | None = None  # e.g., ["api.example.com"]
    timeout_seconds: float = 10.0  # sandbox exec timeout
    max_attempts: int = 3  # max evolution attempts per function
