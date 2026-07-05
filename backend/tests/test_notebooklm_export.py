"""
Tests for the NotebookLM export feature (FUTURE_FEATURES.md Phase 5 / fd0).

Covers three layers:
  * render_review_markdown — pure formatting, no DB
  * get_papers_and_pdfs_for_topic_review — the linked_paper_ids -> (paper, pdf)
    resolver in database.py, including the "no PDF downloaded yet" case
  * build_notebooklm_export_zip + the GET /archive/topics/{id}/export-notebooklm
    endpoint — zip contents, per-user isolation, and 404 handling

Storage is faked (a tiny in-memory stand-in for the Storage interface)
rather than touching the real local filesystem backend, since get_storage()
is process-cached and tests shouldn't depend on ./data being writable/clean.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.database import ArchivedPaper, ArchivedTopicReview, PaperPDF, get_session
from backend.services import notebooklm_export as nlm

from .conftest import as_user


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    """Trigger the FastAPI lifespan once so Alembic + bootstrap runs."""
    from backend.main import app
    with TestClient(app):
        pass


class _FakeStorage:
    """Minimal Storage stand-in: an in-memory key -> bytes map."""

    def __init__(self, files: dict[str, bytes]):
        self._files = files

    def exists(self, key: str) -> bool:
        return key in self._files

    def get(self, key: str) -> bytes:
        if key not in self._files:
            raise FileNotFoundError(key)
        return self._files[key]


class TestRenderReviewMarkdown:

    def test_includes_all_populated_sections(self):
        review = ArchivedTopicReview(
            user_id="alice@example.com",
            topic_id="diffusion-models",
            topic_name="Diffusion Models",
            course_id="ml101",
            course_name="Machine Learning 101",
            week_covered=4,
            review_content="Diffusion models learn to reverse a noising process.",
            key_points=["Forward process adds noise", "Reverse process denoises"],
            connections=["Related to score-based generative models"],
            practice_suggestions=["Implement a toy DDPM on MNIST"],
            key_concepts=["Score matching"],
            user_notes="Still fuzzy on the ELBO derivation.",
        )
        md = nlm.render_review_markdown(review)

        assert "# Diffusion Models" in md
        assert "**Course:** Machine Learning 101" in md
        assert "**Week covered:** 4" in md
        assert "Diffusion models learn to reverse a noising process." in md
        assert "## Key Points" in md and "- Forward process adds noise" in md
        assert "## Connections" in md and "score-based generative models" in md
        assert "## Practice Suggestions" in md and "toy DDPM" in md
        assert "## Key Concepts" in md and "Score matching" in md
        assert "## Your Notes" in md and "ELBO derivation" in md

    def test_omits_empty_sections(self):
        review = ArchivedTopicReview(
            user_id="alice@example.com",
            topic_id="bare-topic",
            topic_name="Bare Topic",
            course_id="c1",
            course_name="Course One",
        )
        md = nlm.render_review_markdown(review)

        assert "# Bare Topic" in md
        for heading in ("## Review", "## Key Points", "## Connections",
                        "## Practice Suggestions", "## Key Concepts", "## Your Notes"):
            assert heading not in md


class TestGetPapersAndPdfsForTopicReview:

    def test_returns_empty_list_when_no_papers_linked(self, user_a):
        from backend.database import get_papers_and_pdfs_for_topic_review

        review = ArchivedTopicReview(
            user_id=user_a, topic_id="t1", topic_name="T1", course_id="c", course_name="C",
        )
        assert get_papers_and_pdfs_for_topic_review(review) == []

    def test_resolves_linked_papers_with_and_without_pdfs(self, user_a):
        session = get_session()
        try:
            paper_with_pdf = ArchivedPaper(
                user_id=user_a, unique_id="arxiv:with-pdf", title="Has A PDF",
                authors="[]", source="arxiv", url="https://example.com",
            )
            paper_without_pdf = ArchivedPaper(
                user_id=user_a, unique_id="arxiv:without-pdf", title="No PDF Yet",
                authors="[]", source="arxiv", url="https://example.com",
            )
            other_users_paper = ArchivedPaper(
                user_id="bob@example.com", unique_id="arxiv:not-mine", title="Not Mine",
                authors="[]", source="arxiv", url="https://example.com",
            )
            session.add_all([paper_with_pdf, paper_without_pdf, other_users_paper])
            session.flush()

            pdf = PaperPDF(
                user_id=user_a,
                archived_paper_id=paper_with_pdf.id,
                original_filename="has-a-pdf.pdf",
                stored_filename="has-a-pdf.pdf",
                file_path=f"papers/{paper_with_pdf.id}.pdf",
            )
            session.add(pdf)

            review = ArchivedTopicReview(
                user_id=user_a, topic_id="t1", topic_name="T1", course_id="c", course_name="C",
                linked_paper_ids=[paper_with_pdf.id, paper_without_pdf.id, other_users_paper.id],
            )
            session.add(review)
            session.commit()

            from backend.database import get_papers_and_pdfs_for_topic_review
            results = get_papers_and_pdfs_for_topic_review(review, session=session)
        finally:
            session.close()

        by_title = {paper.title: pdf for paper, pdf in results}
        # other user's paper must never resolve, even though its id was listed
        assert "Not Mine" not in by_title
        assert by_title["Has A PDF"] is not None
        assert by_title["Has A PDF"].stored_filename == "has-a-pdf.pdf"
        assert by_title["No PDF Yet"] is None


class TestBuildNotebookLMExportZip:

    def test_zip_contains_review_and_available_pdfs_only(self, user_a, monkeypatch):
        session = get_session()
        try:
            has_pdf = ArchivedPaper(
                user_id=user_a, unique_id="arxiv:zip-1", title="Zippable Paper",
                authors="[]", source="arxiv", url="https://example.com",
            )
            missing_from_storage = ArchivedPaper(
                user_id=user_a, unique_id="arxiv:zip-2", title="Ghost PDF",
                authors="[]", source="arxiv", url="https://example.com",
            )
            session.add_all([has_pdf, missing_from_storage])
            session.flush()

            session.add(PaperPDF(
                user_id=user_a, archived_paper_id=has_pdf.id,
                original_filename="zippable.pdf", stored_filename="zippable.pdf",
                file_path="papers/zippable.pdf",
            ))
            session.add(PaperPDF(
                user_id=user_a, archived_paper_id=missing_from_storage.id,
                original_filename="ghost.pdf", stored_filename="ghost.pdf",
                file_path="papers/ghost.pdf",  # never actually stored — see fake below
            ))

            review = ArchivedTopicReview(
                user_id=user_a, topic_id="t1", topic_name="Export Me!", course_id="c", course_name="C",
                review_content="Some review text.",
                linked_paper_ids=[has_pdf.id, missing_from_storage.id],
            )
            session.add(review)
            session.commit()
            session.refresh(review)

            fake_storage = _FakeStorage({"papers/zippable.pdf": b"%PDF-1.4 fake bytes"})
            monkeypatch.setattr(nlm, "get_storage", lambda: fake_storage)

            zip_bytes, filename = nlm.build_notebooklm_export_zip(review, session=session)
        finally:
            session.close()

        assert filename == "Export_Me_notebooklm.zip"
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "review.md" in names
            assert "papers/Zippable_Paper.pdf" in names
            # the ghost PDF (missing from storage) must be silently skipped
            assert not any("Ghost_PDF" in n for n in names)
            assert zf.read("papers/Zippable_Paper.pdf") == b"%PDF-1.4 fake bytes"
            assert "Some review text." in zf.read("review.md").decode()


class TestExportEndpoint:

    def test_404_for_other_users_topic(self, client: TestClient, user_a: str, user_b: str):
        session = get_session()
        try:
            review = ArchivedTopicReview(
                user_id=user_b, topic_id="t1", topic_name="Bob's Topic", course_id="c", course_name="C",
            )
            session.add(review)
            session.commit()
            session.refresh(review)
            review_id = review.id
        finally:
            session.close()

        r = client.get(f"/archive/topics/{review_id}/export-notebooklm", headers=as_user(client, user_a))
        assert r.status_code == 404

    def test_happy_path_returns_zip(self, client: TestClient, user_a: str, monkeypatch):
        session = get_session()
        try:
            review = ArchivedTopicReview(
                user_id=user_a, topic_id="t1", topic_name="Endpoint Topic", course_id="c", course_name="C",
                review_content="Endpoint review body.",
                linked_paper_ids=[],
            )
            session.add(review)
            session.commit()
            session.refresh(review)
            review_id = review.id
        finally:
            session.close()

        r = client.get(f"/archive/topics/{review_id}/export-notebooklm", headers=as_user(client, user_a))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "attachment" in r.headers["content-disposition"]
        assert "Endpoint_Topic_notebooklm.zip" in r.headers["content-disposition"]

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            assert "review.md" in zf.namelist()
            assert "Endpoint review body." in zf.read("review.md").decode()
