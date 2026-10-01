"""Terminal output helpers: ANSI color, key/value lines, tables."""
from __future__ import annotations

import os
import sys


def _enable_vt():
    if sys.platform == "win32":
        os.system("")  # enables ANSI VT processing in Windows terminals


_enable_vt()
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(text: str, *codes: str) -> str:
    if not _USE_COLOR:
        return text
    return "\033[" + ";".join(codes) + "m" + text + "\033[0m"


GREEN, RED, YELLOW, DIM, BOLD, CYAN = "32", "31", "33", "2", "1", "36"


def ok(msg: str) -> str:
    return c("[ok] ", GREEN) + msg


def warn(msg: str) -> str:
    return c("[!!] ", YELLOW) + msg


def err(msg: str) -> str:
    return c("[xx] ", RED) + msg


def info(msg: str) -> str:
    return c("[..] ", DIM) + msg


def step(n: int, msg: str) -> str:
    return c(f"[{n}] ", CYAN) + msg


def head(msg: str) -> str:
    return c(msg, BOLD)


def kv(key: str, value, width: int = 24) -> str:
    return "  " + c(key.ljust(width), DIM) + str(value)


def hr(char: str = "-", width: int = 64) -> str:
    return c(char * width, DIM)


def table(rows, headers=(), indent: str = "  ") -> str:
    rows = [[str(x) for x in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    out = []
    if headers:
        out.append(indent + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
        out.append(indent + c("  ".join("-" * w for w in widths), DIM))
    for r in rows:
        out.append(indent + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)))
    return "\n".join(out)
