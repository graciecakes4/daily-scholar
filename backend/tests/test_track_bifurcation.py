"""
Tests for per-track paper discovery.

The bug these guard against: discovery used to aggregate search keywords
across the ENTIRE topic scope, sorted by topic weight descending, then
truncate to the top 5. Any topic whose keywords didn't make that cut was
never actually searched for — so a couple of high-weight topics could
silently monopolize every query and starve another research track
completely. Weight tuning couldn't fix it, because the truncation happened
before weights were used for anything else.

These tests stub the network layer entirely; they're about which searches
get issued and how results are grouped, not about any external API.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.services.paper_discovery import Paper, PaperDiscoveryService


class FakeTopic:
    """Minimal stand-in for a Topic row; discovery only reads attributes."""

    def __init__(
        self,
        topic_id: str,
        *,
        weight: float,
        track: str | None,
        keywords: list[str],
        categories: list[str] | None = None,
        min_relevance: float = 0.1,
        recency_days: int = 30,
        prerequisite_only: bool = False,
    ):
        self.id = topic_id
        self.name = topic_id
        self.weight = weight
        self.track = track
        self.keywords = keywords
        self.arxiv_categories = categories or []
        self.min_relevance = min_relevance
        self.recency_days = recency_days
        self.prerequisite_only = prerequisite_only


def _lopsided_scope() -> list[FakeTopic]:
    """
    The exact shape that broke: two heavy topics on one track with more than
    five keywords between them, and a lighter track that used to get zero
    search terms as a result.
    """
    return [
        FakeTopic(
            "heavy-astro-a",
            weight=2.0,
            track="astro",
            keywords=["light curve", "transient", "supernova", "alert broker", "photometry"],
            categories=["astro-ph.IM"],
        ),
        FakeTopic(
            "heavy-astro-b",
            weight=2.0,
            track="astro",
            keywords=["spectroscopy", "time domain", "kilonova"],
            categories=["astro-ph.HE"],
        ),
        FakeTopic(
            "light-praxis",
            weight=1.8,
            track="praxis",
            keywords=["conditional diffusion", "learnable tokens", "missing modality"],
            categories=["cs.LG"],
        ),
        FakeTopic(
            "foundations",
            weight=1.5,
            track="praxis",
            keywords=["neural network", "backpropagation"],
            categories=["cs.LG"],
            prerequisite_only=True,
        ),
    ]


@pytest.fixture
def service(monkeypatch) -> PaperDiscoveryService:
    """A service whose scope is stubbed and whose network calls are recorded."""
    svc = PaperDiscoveryService(user_id="__test__")
    monkeypatch.setattr(svc, "_topics_in_scope", lambda: _lopsided_scope())
    return svc


def _record_searches(svc, monkeypatch) -> list[str]:
    """Capture every search term issued, returning one matching paper each."""
    issued: list[str] = []

    async def fake_arxiv(query, max_results=10, days_back=30):
        issued.append(query)
        return [
            Paper(
                title=f"Paper about {query}",
                authors=["A. Author"],
                abstract=f"An abstract mentioning {query} at length.",
                url=f"https://example.test/{query.replace(' ', '-')}",
                source="arxiv",
                arxiv_id=f"0000.{abs(hash(query)) % 10000:04d}",
                published_date=date.today(),
                categories=["astro-ph.IM", "cs.LG"],
            )
        ]

    async def fake_by_category(category, max_results=10, days_back=30):
        return []

    async def empty(*args, **kwargs):
        return []

    monkeypatch.setattr(svc, "search_arxiv", fake_arxiv)
    monkeypatch.setattr(svc, "search_arxiv_by_category", fake_by_category)
    monkeypatch.setattr(svc, "search_semantic_scholar", empty)
    monkeypatch.setattr(svc, "search_core", empty)
    return issued


def test_prerequisite_topics_are_excluded_from_quota(service):
    eligible = service._quota_eligible(service._topics_in_scope())
    ids = {t.id for t in eligible}
    assert "foundations" not in ids, "prerequisite-only topic must not consume a paper slot"
    assert "light-praxis" in ids


def test_group_by_track_buckets_and_orders_by_weight(service):
    grouped = service._group_by_track(service._quota_eligible(service._topics_in_scope()))
    assert set(grouped) == {"astro", "praxis"}
    assert [t.id for t in grouped["astro"]] == ["heavy-astro-a", "heavy-astro-b"]
    assert [t.id for t in grouped["praxis"]] == ["light-praxis"]


def test_untracked_scope_collapses_to_a_single_bucket(service):
    """A scope that never declared tracks must behave exactly as before."""
    plain = [
        FakeTopic("a", weight=2.0, track=None, keywords=["alpha"]),
        FakeTopic("b", weight=1.0, track=None, keywords=["beta"]),
    ]
    grouped = service._group_by_track(plain)
    assert list(grouped) == [None]
    assert len(grouped[None]) == 2


@pytest.mark.asyncio
async def test_every_track_actually_gets_searched(service, monkeypatch):
    """
    The core regression. Under the old global top-5 truncation, the five
    keywords all came from the two weight-2.0 astro topics and the praxis
    track contributed none — so praxis papers could not be found at all.
    """
    issued = _record_searches(service, monkeypatch)

    await service.discover_papers_by_track(max_results_per_track=10, sources=["arxiv"])

    praxis_terms = {"conditional diffusion", "learnable tokens", "missing modality"}
    assert praxis_terms & set(issued), (
        f"praxis track was never searched; issued terms were {issued}"
    )
    astro_terms = {"light curve", "transient", "supernova", "spectroscopy"}
    assert astro_terms & set(issued), "astro track was never searched"

    # prerequisite-only keywords must never become search terms
    assert "backpropagation" not in issued
    assert "neural network" not in issued


@pytest.mark.asyncio
async def test_results_are_grouped_by_track(service, monkeypatch):
    _record_searches(service, monkeypatch)

    by_track = await service.discover_papers_by_track(
        max_results_per_track=10, sources=["arxiv"]
    )

    assert set(by_track) == {"astro", "praxis"}
    assert by_track["praxis"], "praxis track returned nothing"
    assert by_track["astro"], "astro track returned nothing"
    for track, papers in by_track.items():
        for paper in papers:
            assert paper.track == track, "each paper must be stamped with its track"


@pytest.mark.asyncio
async def test_no_paper_appears_in_two_tracks(service, monkeypatch):
    _record_searches(service, monkeypatch)

    by_track = await service.discover_papers_by_track(
        max_results_per_track=10, sources=["arxiv"]
    )

    ids = [p.unique_id for papers in by_track.values() for p in papers]
    assert len(ids) == len(set(ids)), "a paper was counted toward more than one track"


@pytest.mark.asyncio
async def test_daily_selection_honours_per_track_quota(service, monkeypatch):
    _record_searches(service, monkeypatch)

    selected = await service.select_daily_papers(quota_per_track=2)

    assert set(selected) == {"astro", "praxis"}
    for track, papers in selected.items():
        assert len(papers) <= 2, f"{track} exceeded its quota"
    assert selected["praxis"], "praxis got no slot despite having its own quota"


@pytest.mark.asyncio
async def test_seen_papers_are_excluded(service, monkeypatch):
    _record_searches(service, monkeypatch)

    first = await service.select_daily_papers(quota_per_track=1)
    seen = [p.unique_id for papers in first.values() for p in papers]

    second = await service.select_daily_papers(quota_per_track=1, seen_ids=seen)
    repeats = [
        p.unique_id for papers in second.values() for p in papers if p.unique_id in seen
    ]
    assert not repeats, f"already-seen papers came back: {repeats}"


@pytest.mark.asyncio
async def test_single_paper_wrapper_still_works(service, monkeypatch):
    """Legacy callers expecting one paper must keep working."""
    _record_searches(service, monkeypatch)

    paper = await service.select_daily_paper()

    assert paper is not None
    assert paper.track in {"astro", "praxis"}


@pytest.mark.asyncio
async def test_track_threshold_is_its_own_not_the_loosest_in_scope(monkeypatch):
    """
    A permissive topic in one track must not lower the bar for the other.
    Here astro accepts almost anything (0.01) while praxis demands 0.99;
    praxis should end up empty rather than inheriting astro's threshold.
    """
    svc = PaperDiscoveryService(user_id="__test__")
    monkeypatch.setattr(svc, "_topics_in_scope", lambda: [
        FakeTopic("loose-astro", weight=2.0, track="astro",
                  keywords=["transient"], min_relevance=0.01),
        FakeTopic("strict-praxis", weight=1.8, track="praxis",
                  keywords=["conditional diffusion"], min_relevance=0.99),
    ])
    _record_searches(svc, monkeypatch)

    selected = await svc.select_daily_papers(quota_per_track=1)

    assert selected["astro"], "loose track should still return a paper"
    assert not selected["praxis"], (
        "strict track accepted a paper below its own min_relevance"
    )


# ---------------------------------------------------------------------------
# Keyword/category budget: every topic in a track must be represented.
#
# The original aggregation was depth-first — it exhausted the highest-weight
# topic's keyword list before moving to the next. On the real topic set that
# meant a 33-keyword topic consumed the entire 5-keyword budget by itself and
# every other topic in its track was never searched for at all, however high
# its weight. Per-track grouping alone didn't fix that; it just moved the
# truncation from scope level to track level.
# ---------------------------------------------------------------------------


def _lopsided_keyword_group() -> list[FakeTopic]:
    """One keyword-rich topic sorted first, two smaller ones behind it."""
    return [
        FakeTopic(
            "rich",
            weight=1.8,
            track="praxis",
            keywords=[f"rich-term-{i}" for i in range(33)],
        ),
        FakeTopic(
            "learnable-tokens",
            weight=1.8,
            track="praxis",
            keywords=["missing modality", "modality dropout", "learnable token"],
        ),
        FakeTopic(
            "third",
            weight=0.8,
            track="praxis",
            keywords=["multimodal foundation model", "cross-modal alignment"],
        ),
    ]


class TestKeywordBudgetIsSharedAcrossTopics:

    def test_every_topic_contributes_a_search_term(self, service):
        """
        The regression. Under depth-first ordering all five slots went to
        'rich' and the other two topics contributed nothing.
        """
        group = _lopsided_keyword_group()

        keywords = service._aggregate_keywords(group, limit=5)

        assert len(keywords) == 5
        for topic in group:
            contributed = [k for k in keywords if k in topic.keywords]
            assert contributed, (
                f"topic {topic.id!r} contributed no search term; got {keywords}"
            )

    def test_highest_weight_topic_still_picks_first(self, service):
        keywords = service._aggregate_keywords(_lopsided_keyword_group(), limit=5)
        assert keywords[0] == "rich-term-0"

    def test_budget_is_respected(self, service):
        assert len(service._aggregate_keywords(_lopsided_keyword_group(), limit=2)) == 2
        assert service._aggregate_keywords(_lopsided_keyword_group(), limit=None)

    def test_duplicate_keywords_are_deduped_case_insensitively(self, service):
        group = [
            FakeTopic("a", weight=2.0, track="t", keywords=["Light Curve", "alpha"]),
            FakeTopic("b", weight=1.0, track="t", keywords=["light curve", "beta"]),
        ]
        keywords = service._aggregate_keywords(group, limit=10)
        lowered = [k.lower() for k in keywords]
        assert lowered.count("light curve") == 1
        assert "beta" in keywords

    def test_categories_are_shared_across_topics_too(self, service):
        group = [
            FakeTopic("a", weight=2.0, track="t", keywords=["x"],
                      categories=["astro-ph.IM", "astro-ph.HE", "astro-ph.SR"]),
            FakeTopic("b", weight=1.0, track="t", keywords=["y"],
                      categories=["cs.LG"]),
        ]
        categories = service._aggregate_categories(group, limit=3)
        assert "cs.LG" in categories, (
            f"the second topic's category was crowded out entirely: {categories}"
        )

    def test_single_topic_group_is_unchanged(self, service):
        """Round-robin over one list must behave exactly like the old path."""
        group = [FakeTopic("solo", weight=1.0, track="t",
                           keywords=["a", "b", "c", "d", "e", "f"])]
        assert service._aggregate_keywords(group, limit=4) == ["a", "b", "c", "d"]

    def test_empty_keyword_lists_are_skipped(self, service):
        group = [
            FakeTopic("empty", weight=2.0, track="t", keywords=[]),
            FakeTopic("full", weight=1.0, track="t", keywords=["only", "these"]),
        ]
        assert service._aggregate_keywords(group, limit=5) == ["only", "these"]
