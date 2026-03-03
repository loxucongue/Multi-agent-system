"""Structured JSON logging utilities with trace id support."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone


trace_id_context: ContextVar[str] = ContextVar("trace_id", default="-")


def set_trace_id(trace_id: str) -> None:
    """Store trace id in context for current execution flow."""

    trace_id_context.set(trace_id or "-")


def get_trace_id() -> str:
    """Read trace id from context."""

    return trace_id_context.get()


class JsonFormatter(logging.Formatter):
    """Format log records as JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record into JSON."""

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", get_trace_id()),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger to output JSON logs."""

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Return logger instance by name."""

    return logging.getLogger(name)
