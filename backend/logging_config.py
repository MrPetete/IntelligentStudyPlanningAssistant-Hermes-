"""
TraceLearn — logging setup (local, privacy-safe, persistent).

Writes an operational log to console AND a rotating file on the tester's own
machine (LOG_DIR/tracelearn.log). Testers attach that file to a bug report so
we can see the exact sequence + timing of what happened behind the scenes.

Design decisions (agreed for the V1 test round):
  - LOCAL ONLY. Nothing is sent off the machine — no phone-home, no server.
    A centralized/opt-in shipping layer is a deliberate post-V1 feature.
  - PRIVACY-SAFE by default. We log the OPERATIONAL layer — timestamps, HTTP
    method/path/status/duration, which model was called, durations, retries,
    errors, and agent decision types (new_version / no_change). We do NOT log
    request bodies, goal text, uploaded document text, concept names, or the
    model's prompts/reasoning. So the file is safe to share.
  - PERSISTENT. Size-based rotation (RotatingFileHandler), never time-based —
    the log survives across open/use/close/reopen cycles and is NOT wiped on
    restart or after a day. Only the oldest chunk rolls off once the file grows
    past LOG_MAX_BYTES, keeping LOG_BACKUP_COUNT older chunks.

Never logs the API key: we log model *ids* and endpoints, never credentials.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

# The single app logger namespace. All modules do
# logging.getLogger("tracelearn.<area>") so everything lands in one file.
LOGGER_NAME = "tracelearn"

_configured = False


def setup_logging() -> logging.Logger:
    """Configure the 'tracelearn' logger once. Idempotent (safe to call again).

    Reads LOG_DIR / LOG_LEVEL / LOG_MAX_BYTES / LOG_BACKUP_COUNT from config
    (which are env-overridable). Returns the configured root app logger.
    """
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger

    # Imported here (not at module top) so importing this module never triggers
    # config side effects before the app decides to configure logging.
    from config import LOG_BACKUP_COUNT, LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES

    level = getattr(logging, str(LOG_LEVEL).upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False  # don't double-emit through the root logger

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # Console handler — the live view in the tester's terminal.
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    # Rotating file handler — the persistent artifact they attach to bug reports.
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "tracelearn.log"),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:
        # A read-only or unwritable dir must never crash the app — degrade to
        # console-only and say so once.
        logger.warning("file logging disabled (cannot write LOG_DIR=%s): %s", LOG_DIR, exc)

    _configured = True
    logger.info("logging initialized (level=%s, dir=%s)", logging.getLevelName(level), LOG_DIR)
    return logger


def get_logger(area: str) -> logging.Logger:
    """Return a child logger 'tracelearn.<area>' for a module to log through."""
    return logging.getLogger(f"{LOGGER_NAME}.{area}")
