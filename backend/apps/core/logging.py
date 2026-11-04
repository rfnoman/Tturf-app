"""Structured logging (Phase 11 step 5).

A line like ``INFO Booking confirmed`` is unsearchable the moment there is more than one
of them. Every log call in this codebase already passes its facts through ``extra=``, so
all that was missing was a formatter that keeps them: JSON in production, where something
is going to index it, and the readable one-line format locally, where a person is reading
the terminal.

Nothing about the call sites changes. That is the point — ``logger.info("Booking
confirmed", extra={"booking": str(booking.id)})`` was already right.
"""

from __future__ import annotations

import json
import logging

#: Everything `LogRecord` sets for its own purposes. What is left after removing these
#: is what the call site actually passed, which is the part worth indexing.
_STANDARD = set(logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the call site's `extra` fields at the top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_"):
                continue
            # Anything that will not serialise is still worth having as a string; losing
            # a field because it held a model instance would defeat the purpose.
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError, ValueError:
                payload[key] = str(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)
