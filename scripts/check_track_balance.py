#!/usr/bin/env python3
"""
Show what each research track actually searches for, and what it gets back.

This is the verification tool for per-track paper discovery. It answers the
question the old single-pool discovery made impossible to ask: is every track
in scope actually being queried, or is one topic quietly supplying all the
search terms?

Run it after changing topic weights or keywords, and after running
scripts/assign_topic_tracks.py.

Two modes:

  --dry (default)  Print the per-track keyword and category budgets only.
                   No network. Shows the BEFORE/AFTER comparison so you can
                   see which topics the old global truncation excluded.

  --live           Additionally run a real discovery pass and print the
                   papers each track selected. Needs outbound access to
                   arXiv / Semantic Scholar / CORE.

Usage:
    python scripts/check_track_balance.py
    python scripts/check_track_balance.py --live --quota 2
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.database import DEFAULT_USER_ID  # noqa: E402
from backend.services.paper_discovery import PaperDiscoveryService  # noqa: E402


def report_budgets(svc: PaperDiscoveryService) -> None:
    """Print the old global aggregation next to the new per-track one."""
    scope = svc._topics_in_scope()
    if not scope:
        print("no topics in scope — nothing to report")
        return
    eligible = svc._quota_eligible(scope)

    # reconstruct which topic each globally-selected term came from, so the
    # starvation is visible rather than merely asserted
    owners = {}
    for topic in sorted(scope, key=lambda t: t.weight or 0.0, reverse=True):
        for kw in topic.keywords or []:
            owners.setdefault(kw.lower(), topic)

    old_keywords = svc._aggregate_keywords(scope, limit=5)
    print("BEFORE — a single global aggregation across the whole scope:")
    for kw in old_keywords:
        topic = owners.get(kw.lower())
        if topic is not None:
            print(f"  {kw!r:<40} <- {topic.id} (track={topic.track}, weight={topic.weight})")
    reached = {owners[k.lower()].track for k in old_keywords if k.lower() in owners}
    contributing = {owners[k.lower()].id for k in old_keywords if k.lower() in owners}
    print(f"  tracks reached: {reached or '{}'}")
    print(f"  topics contributing any search term: {len(contributing)} of {len(scope)}")

    print("\nAFTER — one aggregation per track:")
    grouped = svc._group_by_track(eligible)
    for track, topics in grouped.items():
        print(f"  {track or '(untracked)'}: {[t.id for t in topics]}")
        print(f"    keywords:   {svc._aggregate_keywords(topics, limit=5)}")
        print(f"    categories: {svc._aggregate_categories(topics, limit=3)}")
        print(f"    threshold:  {svc._scope_min_relevance(topics):.2f}")
        print(f"    recency:    {svc._scope_max_recency(topics)}d")

    skipped = [t.id for t in scope if getattr(t, "prerequisite_only", False)]
    if skipped:
        print(f"\n  prerequisite-only (never consume a paper slot): {skipped}")
    if len([t for t in grouped if t]) < 2:
        print(
            "\nWARNING: fewer than two named tracks in scope. Discovery will "
            "behave like the old single-pool version."
        )


async def report_live(svc: PaperDiscoveryService, quota: int) -> None:
    print(f"\nLIVE — selecting up to {quota} paper(s) per track:\n")
    selected = await svc.select_daily_papers(quota_per_track=quota)
    for track, papers in selected.items():
        print(f"--- {track or '(untracked)'}: {len(papers)} selected ---")
        for paper in papers:
            print(f"  [{paper.relevance_score:.3f}] {paper.title[:88]}")
            print(f"      best-fit topic: {paper.primary_category}")
        if not papers:
            print("  (nothing cleared this track's threshold today)")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--live", action="store_true", help="also run a real discovery pass")
    parser.add_argument("--quota", type=int, default=2, help="papers per track in --live mode")
    parser.add_argument("--user", default=DEFAULT_USER_ID, help="user whose scope to inspect")
    args = parser.parse_args()

    svc = PaperDiscoveryService(user_id=args.user)
    try:
        report_budgets(svc)
        if args.live:
            await report_live(svc, args.quota)
    finally:
        await svc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
