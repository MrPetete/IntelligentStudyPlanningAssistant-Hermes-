"""
TraceLearn — document ingestion pipeline (Member C, Phase 2 / C2 + C3).

C2: turn a saved file into plain text.
C3: wire that text into the real extract_concepts call, with the
    goal-topic fallback (D4) for empty/failed extraction or a model error.

Scope fence (hard limit, D14 / handoff §4): clean text-based PDF or TXT
only. No OCR, no scanned images, no PPT, no DOCX, no multiple documents.
"""
from __future__ import annotations

from typing import Any

from agent import llm_client

# Below this many characters, extracted text is treated as failed/unusable
# (this is what a scanned/image PDF produces) and routed to the goal-topic
# fallback instead of being sent to the model.
_MIN_USABLE_CHARS = 40


class UnsupportedDocumentError(Exception):
    """Raised for any file type outside the V1 scope fence (PDF/TXT only)."""


# ---------------------------------------------------------------------------
# C2 — text extraction
# ---------------------------------------------------------------------------
def extract_text(path: str) -> str:
    """
    Extract plain text from a saved .txt or .pdf file.

    - .txt: read directly (utf-8, falling back to latin-1 on decode error).
    - .pdf: pdfplumber, page text joined with a blank line.
    - anything else: UnsupportedDocumentError (A's caller turns this into
      documents.status='failed').

    A scanned/image PDF is expected to yield empty or near-empty text here
    — that's not this function's error to raise; it's handled by the
    caller (build_concept_map) via the goal-topic fallback.
    """
    lower = path.lower()
    if lower.endswith(".txt"):
        return _read_txt(path)
    if lower.endswith(".pdf"):
        return _read_pdf(path)
    raise UnsupportedDocumentError(
        f"unsupported document type: {path!r} "
        "(V1 supports .pdf and .txt only — no OCR, DOCX, PPT, or scanned images)"
    )


def _read_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


def _read_pdf(path: str) -> str:
    import pdfplumber  # imported lazily so .txt-only setups don't need it

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()


def is_usable_material(material_text: str) -> bool:
    """True if extracted text is substantial enough to attempt concept
    extraction on. False for empty/garbage extraction (e.g. a scanned PDF)."""
    return bool(material_text) and len(material_text.strip()) >= _MIN_USABLE_CHARS


# ---------------------------------------------------------------------------
# C3 — wire extraction -> real concept map
# ---------------------------------------------------------------------------
def build_concept_map(
    material_text: str,
    explanation_language: str,
    *,
    goal_text: str | None = None,
) -> list[dict[str, Any]]:
    """
    Call the real extract_concepts with the extracted document text.
    With MOCK_LLM=false this hits the real model via A's llm_client.

    The prompt builder already map-reduces above _MAP_REDUCE_CHAR_THRESHOLD
    (llm_client._split_into_sections) — pass the full text, don't
    re-chunk here.

    Fallback (D4): if material_text is empty/too short, or the model call
    itself errors, and a goal_text is supplied, fall back to
    build_goal_topic_map. If no goal_text is given, the failure is raised
    so the caller (A's async runner) can mark the document 'failed' and
    decide the fallback itself.
    """
    if not is_usable_material(material_text):
        if goal_text:
            return build_goal_topic_map(goal_text, explanation_language)
        raise ValueError(
            "material_text is empty/too short (failed extraction) and no "
            "goal_text was given for the fallback"
        )

    try:
        return llm_client.extract_concepts(
            material_text=material_text, explanation_language=explanation_language
        )
    except Exception:
        if goal_text:
            return build_goal_topic_map(goal_text, explanation_language)
        raise


def build_goal_topic_map(goal_text: str, explanation_language: str) -> list[dict[str, Any]]:
    """
    Fallback (D4): generate a concept map from the goal text alone — no
    usable document — using the model's own topic knowledge. Same output
    shape as build_concept_map, but every concept is tagged
    `source='goal_topic'` instead of `'material'`.
    """
    concepts = llm_client.extract_concepts(
        material_text=(
            "No usable document was provided for this goal. Using only your "
            "own knowledge of the subject, produce a concept map appropriate "
            f"for a learner whose goal is: {goal_text}"
        ),
        explanation_language=explanation_language,
    )
    for c in concepts:
        c["source"] = "goal_topic"
    return concepts
