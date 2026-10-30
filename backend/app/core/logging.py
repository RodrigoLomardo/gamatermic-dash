import logging
import sys

import structlog

SENSITIVE = {"password", "token", "authorization", "cookie", "secret", "refresh", "device_code", "set-cookie"}


def _redact(_, __, event_dict):
    for k in list(event_dict):
        if any(s in k.lower() for s in SENSITIVE):
            event_dict[k] = "***"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
