"""Lightweight progress logger for the pipeline. Always writes to stderr."""
from __future__ import annotations

import os
import sys
import time

_START = time.time()
_INDENT = 0

# Disable colors on Windows cp949 unless caller forces them.
_USE_COLOR = os.environ.get("COWORK_LOG_COLOR", "0") == "1"

_RESET = "\033[0m" if _USE_COLOR else ""
_DIM = "\033[2m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_GREEN = "\033[32m" if _USE_COLOR else ""
_YELLOW = "\033[33m" if _USE_COLOR else ""
_BLUE = "\033[34m" if _USE_COLOR else ""


def _elapsed() -> str:
    return f"{time.time() - _START:6.1f}s"


def _emit(prefix: str, msg: str) -> None:
    pad = "  " * _INDENT
    print(f"[{_elapsed()}] {pad}{prefix} {msg}", file=sys.stderr, flush=True)


def stage(name: str) -> None:
    """Top-level stage divider — resets indent to 1."""
    global _INDENT
    print(f"\n[{_elapsed()}] {_BOLD}{_BLUE}=== {name} ==={_RESET}", file=sys.stderr, flush=True)
    _INDENT = 1


def step(msg: str) -> None:
    _emit(f"{_BLUE}>{_RESET}", msg)


def info(msg: str) -> None:
    _emit(f"{_DIM}.{_RESET}", msg)


def ok(msg: str) -> None:
    _emit(f"{_GREEN}+{_RESET}", msg)


def warn(msg: str) -> None:
    _emit(f"{_YELLOW}!{_RESET}", msg)


def detail(text: str, *, max_lines: int = 10, max_chars: int = 600) -> None:
    """Print a code/critique snippet, truncated and dimmed."""
    lines = text.splitlines()
    truncated = lines[:max_lines]
    body = "\n".join(truncated)
    if len(body) > max_chars:
        body = body[:max_chars] + "..."
    if len(lines) > max_lines:
        body += f"\n... ({len(lines) - max_lines} more lines)"
    pad = "  " * (_INDENT + 1)
    for line in body.splitlines():
        print(f"{pad}{_DIM}{line}{_RESET}", file=sys.stderr, flush=True)
