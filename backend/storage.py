"""
TraceLearn — file storage for uploaded documents (Member C, Phase 2 / C1).

Local disk only for V1 (single machine, single user). No S3/cloud storage —
see MEMBER_C_PHASE2_TASKLIST.md C1 limitation.

Note: `config.py` is Member A's file, so this reads UPLOAD_DIR from the
environment directly (same default as the task list's suggested config
value, `./uploads`) instead of editing config.py. If A later adds
`UPLOAD_DIR` to config.py, this can switch to importing it — same value,
no behavior change.
"""
from __future__ import annotations

import os
import re

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename(filename: str) -> str:
    """Strip path separators and other unsafe characters from a client-
    supplied filename so it can't escape the goal's upload directory
    (e.g. a filename of '../../etc/passwd')."""
    name = os.path.basename(filename or "upload")
    name = _UNSAFE_CHARS.sub("_", name)
    return name or "upload"


def save_upload(goal_id: int, filename: str, content_bytes: bytes) -> str:
    """
    Write an uploaded file's bytes to disk under
    {UPLOAD_DIR}/{goal_id}/{filename} and return the path.

    Creates the goal's directory as needed. A goal has at most one active
    document in V1, so a same-named re-upload overwrites in place.

    Accept (C1): calling this with a real PDF's bytes writes the file to
    disk and returns a path that exists.
    """
    safe_name = _safe_filename(filename)
    goal_dir = os.path.join(UPLOAD_DIR, str(goal_id))
    os.makedirs(goal_dir, exist_ok=True)
    path = os.path.join(goal_dir, safe_name)
    with open(path, "wb") as f:
        f.write(content_bytes)
    return path
