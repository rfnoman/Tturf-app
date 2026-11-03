"""Guard against a logging footgun that only bites outside the test settings.

``logging.Logger.makeRecord`` raises ``KeyError: "Attempt to overwrite 'x' in LogRecord"``
when an ``extra`` dict uses one of the reserved attribute names — ``created`` and ``name``
are the easy ones to reach for. It never surfaces under the test settings (the root
logger has no handlers and sits at WARNING, so ``logger.info`` returns before the record
is built), but it crashes ``seed_demo`` and any real deployment at INFO.

So: scan every ``extra={...}`` literal in the codebase for reserved keys.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

APPS_DIR = Path(__file__).resolve().parents[2]

#: Everything ``LogRecord.__init__`` sets, plus the three that ``Formatter`` adds later.
RESERVED = set(logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def _extra_keys(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                continue
            for key in keyword.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append((key.value, keyword.value.lineno))
    return found


@pytest.mark.parametrize(
    "path",
    sorted(p for p in APPS_DIR.rglob("*.py") if "migrations" not in p.parts),
    ids=lambda p: str(p.relative_to(APPS_DIR)),
)
def test_logging_extra_avoids_reserved_logrecord_keys(path: Path):
    clashes = [(key, line) for key, line in _extra_keys(path) if key in RESERVED]
    assert not clashes, (
        f"{path.relative_to(APPS_DIR)} passes reserved LogRecord key(s) to extra=: "
        + ", ".join(f"{key!r} (line {line})" for key, line in clashes)
    )
