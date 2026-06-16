#!/usr/bin/env python3
"""
Dialect compatibility smoke test.

Exercises the data plane against whatever DATABASE_URL points to right now
(SQLite or Postgres) so we catch dialect-specific surprises before they
land in production:

  - JSON column round-trips (nested dicts + lists)
  - composite unique constraint on daily_content_cache (user_id, content_date)
  - UserStats unique-per-user constraint
  - alembic migrations apply cleanly from scratch (run separately via CI)

Usage:
    python scripts/check_dialect_compat.py

Exits non-zero on any failure so CI catches regressions.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import date, datetime
from typing import Callable

# project root on sys.path so `from backend...` works no matter where called from
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# require a key to satisfy Settings validation; never actually used for an LLM call here
os.environ.setdefault("ANTHROPIC_API_KEY", "compat-test-dummy")


def _section(name: str) -> Callable[[Callable[[], None]], Callable[[], bool]]:
    """Decorator that prints PASS/FAIL with a short reason."""
    def wrap(fn: Callable[[], None]) -> Callable[[], bool]:
        def runner() -> bool:
            try:
                fn()
                print(f"  PASS  {name}")
                return True
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL  {name}: {e}")
                traceback.print_exc()
                return False
        return runner
    return wrap


def main() -> int:
    from backend.database import (
        create_tables,
        get_session,
        get_engine,
        ArchivedQuiz,
        DailyContentCache,
        Topic,
        UserStats,
    )

    engine = get_engine()
    dialect = engine.dialect.name
    print(f"\n=== dialect compat: {dialect} ({engine.url.drivername}) ===")

    create_tables()  # idempotent — applies migrations if not yet at head

    suite: list[Callable[[], bool]] = []

    @_section("Topic JSON columns round-trip (keywords + arxiv_categories + lists)")
    def topic_json():
        s = get_session()
        try:
            t = Topic(
                id="compat-test-topic",
                name="Compat Test",
                stream="compat",
                active=True,
                weight=1.0,
                keywords=["alpha", "beta", "gamma"],
                arxiv_categories=["cs.LG", "astro-ph.IM"],
                recency_days=30,
                min_relevance=0.18,
                key_concepts=["k1", "k2"],
                learning_objectives=["o1"],
                resources=[],
                quiz_difficulty="medium",
                prerequisites=[],
                created_via="ui",
                source_yaml_present=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            s.merge(t)
            s.commit()
            got = s.get(Topic, "compat-test-topic")
            assert got is not None
            assert got.keywords == ["alpha", "beta", "gamma"], got.keywords
            assert got.arxiv_categories == ["cs.LG", "astro-ph.IM"]
            assert got.key_concepts == ["k1", "k2"]
            s.delete(got)
            s.commit()
        finally:
            s.close()
    suite.append(topic_json)

    @_section("DailyContentCache nested-JSON round-trip + composite unique works")
    def dcc_round_trip_and_unique():
        s = get_session()
        try:
            # one row per (user, date) is allowed
            row_a = DailyContentCache(
                user_id="compat-a",
                content_date=date.today(),
                paper_unique_id="arxiv:compat-a-1",
                paper_data={"title": "A paper", "authors": ["X", "Y"], "nested": {"k": 1}},
                paper_summary={"summary": "ok", "key_findings": ["one", "two"]},
                topic_reviews=[{"topic": {"id": "t"}, "review": {"x": "y"}}],
                quiz_questions={"display": [], "total_points": 0, "_full": []},
                resources=[],
                generated_at=datetime.utcnow(),
            )
            row_b = DailyContentCache(
                user_id="compat-b",
                content_date=date.today(),
                paper_data=None,
                quiz_questions={},
            )
            s.add_all([row_a, row_b])
            s.commit()

            # read back A's nested JSON intact
            got = (
                s.query(DailyContentCache)
                .filter_by(user_id="compat-a", content_date=date.today())
                .first()
            )
            assert got is not None and got.paper_data["nested"]["k"] == 1
            assert got.topic_reviews[0]["topic"]["id"] == "t"

            # cleanup
            s.query(DailyContentCache).filter(
                DailyContentCache.user_id.in_(["compat-a", "compat-b"])
            ).delete(synchronize_session=False)
            s.commit()
        finally:
            s.close()
    suite.append(dcc_round_trip_and_unique)

    @_section("DailyContentCache composite unique rejects same (user_id, content_date)")
    def dcc_unique_rejects():
        from sqlalchemy.exc import IntegrityError
        s = get_session()
        try:
            s.add(DailyContentCache(
                user_id="compat-dup",
                content_date=date.today(),
                paper_data={"t": "1"},
                quiz_questions={},
            ))
            s.commit()
            s.add(DailyContentCache(
                user_id="compat-dup",
                content_date=date.today(),
                paper_data={"t": "2"},
                quiz_questions={},
            ))
            try:
                s.commit()
                raise AssertionError("duplicate (user_id, content_date) accepted!")
            except IntegrityError:
                s.rollback()
        finally:
            s.query(DailyContentCache).filter_by(user_id="compat-dup").delete()
            s.commit()
            s.close()
    suite.append(dcc_unique_rejects)

    @_section("UserStats unique-per-user constraint")
    def user_stats_unique():
        from sqlalchemy.exc import IntegrityError
        s = get_session()
        try:
            existing = s.query(UserStats).filter_by(user_id="compat-stats").first()
            if existing:
                s.delete(existing); s.commit()
            s.add(UserStats(user_id="compat-stats")); s.commit()
            s.add(UserStats(user_id="compat-stats"))
            try:
                s.commit()
                raise AssertionError("duplicate UserStats(user_id) accepted!")
            except IntegrityError:
                s.rollback()
        finally:
            s.query(UserStats).filter_by(user_id="compat-stats").delete()
            s.commit()
            s.close()
    suite.append(user_stats_unique)

    @_section("ArchivedQuiz JSON list/dict round-trip")
    def quiz_json():
        s = get_session()
        try:
            q = ArchivedQuiz(
                user_id="compat-quiz",
                topics=["t1", "t2"],
                topic_ids=["id1", "id2"],
                total_questions=3,
                total_points=6,
                score_earned=5.0,
                percentage=0.83,
                questions=[
                    {"id": "q1", "options": ["a", "b"], "meta": {"x": 1}},
                ],
                taken_at=datetime.utcnow(),
            )
            s.add(q); s.commit(); s.refresh(q)
            got = s.get(ArchivedQuiz, q.id)
            assert got.questions[0]["options"] == ["a", "b"]
            assert got.questions[0]["meta"]["x"] == 1
            assert got.topics == ["t1", "t2"]
            s.delete(got); s.commit()
        finally:
            s.close()
    suite.append(quiz_json)

    results = [r() for r in suite]
    failed = results.count(False)
    print()
    if failed:
        print(f"❌ {failed}/{len(results)} checks failed on {dialect}")
        return 1
    print(f"✅ all {len(results)} checks passed on {dialect}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
