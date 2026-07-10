"""
NotebookLM export — bundles a topic review's content into a zip for manual
hand-off to the user's own Google NotebookLM notebook.

Why manual, not an API call: Google has no public consumer API for
NotebookLM. The only official API is NotebookLM Enterprise, which requires a
GCP project plus a paid Gemini Enterprise/Education Premium license — too
heavy for a ~30-user beta app. NotebookLM already covers both target use
cases (audio overviews, chat/Q&A over sources) once it has sources loaded, so
this module's only job is assembling those sources into something the user
can drag into a new notebook. See FUTURE_FEATURES.md Phase 5 / fd0 for the
full scoping notes.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Optional

from sqlalchemy.orm import Session

from ..database import ArchivedTopicReview, get_papers_and_pdfs_for_topic_review
from .storage import get_storage, storage_key_from_legacy_path


def _safe_filename(name: Optional[str], fallback: str) -> str:
    """Collapse a title/name into a filesystem-safe stem, no extension."""
    name = (name or "").strip() or fallback
    name = re.sub(r"[^\w\s\-]", "", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name[:80] or fallback


def render_review_markdown(topic_review: ArchivedTopicReview) -> str:
    """Render a topic review's stored fields as a single markdown document."""
    lines: list[str] = [f"# {topic_review.topic_name}", ""]
    lines.append(f"**Course:** {topic_review.course_name}")
    if topic_review.week_covered:
        lines.append(f"**Week covered:** {topic_review.week_covered}")
    lines.append("")

    if topic_review.review_content:
        lines.append("## Review")
        lines.append(topic_review.review_content)
        lines.append("")

    def _bullet_section(title: str, items: Optional[list]) -> None:
        if not items:
            return
        lines.append(f"## {title}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    _bullet_section("Key Points", topic_review.key_points)
    _bullet_section("Connections", topic_review.connections)
    _bullet_section("Practice Suggestions", topic_review.practice_suggestions)
    _bullet_section("Key Concepts", topic_review.key_concepts)

    if topic_review.user_notes:
        lines.append("## Your Notes")
        lines.append(topic_review.user_notes)
        lines.append("")

    return "\n".join(lines)


def build_notebooklm_export_zip(
    topic_review: ArchivedTopicReview, session: Optional[Session] = None
) -> tuple[bytes, str]:
    """
    Build an in-memory zip containing the rendered review markdown plus every
    linked paper's downloaded PDF. Papers with no downloaded PDF (or a PDF
    missing from the storage backend) are silently skipped rather than
    erroring the whole export — the review markdown alone is still useful,
    and "download the PDF first" is a separate, existing action in the UI.

    Returns (zip_bytes, suggested_filename).
    """
    storage = get_storage()
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("review.md", render_review_markdown(topic_review))

        papers_and_pdfs = get_papers_and_pdfs_for_topic_review(topic_review, session=session)
        used_names: set[str] = set()
        for paper, pdf in papers_and_pdfs:
            if pdf is None:
                continue
            key = storage_key_from_legacy_path(pdf.file_path)
            try:
                if not storage.exists(key):
                    continue
                data = storage.get(key)
            except FileNotFoundError:
                continue

            base_name = _safe_filename(paper.title, f"paper_{paper.id}")
            arcname = f"papers/{base_name}.pdf"
            suffix = 2
            while arcname in used_names:
                arcname = f"papers/{base_name}_{suffix}.pdf"
                suffix += 1
            used_names.add(arcname)
            zf.writestr(arcname, data)

    zip_filename = f"{_safe_filename(topic_review.topic_name, 'topic')}_notebooklm.zip"
    return buf.getvalue(), zip_filename
