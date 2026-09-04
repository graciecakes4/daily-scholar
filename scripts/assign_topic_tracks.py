#!/usr/bin/env python3
"""
Assign research tracks (and prerequisite-only flags) to existing topics.

Why this exists as a script rather than a YAML change: `config/topics/private/`
is gitignored, so the topics that actually matter here never travel with a
deployment. Their canonical state lives in the DB — the YAML bootstrap only
seeds topics it can see. Setting `track` in prod is therefore a data step, and
this is it.

The assignment itself is what makes per-track paper discovery work. Before
tracks existed, discovery aggregated the top 5 keywords across the whole scope
sorted by topic weight, which meant the two highest-weight topics supplied
every search term and the other track was never queried at all. Grouping
topics by track gives each one its own keyword budget.

`prerequisite_only` marks foundations topics that should inform review and quiz
generation but never consume a daily paper slot.

By default this is a DRY RUN — it prints what would change and exits. Pass
--apply to write. Safe to re-run; unchanged topics are skipped, and topic ids
that aren't present are reported rather than created.

Usage:
    # see what would change
    python scripts/assign_topic_tracks.py

    # actually do it
    python scripts/assign_topic_tracks.py --apply

    # point at a different database (e.g. a prod copy)
    DATABASE_URL=postgresql://... python scripts/assign_topic_tracks.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow running from repo root without installing as a package
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.database import Topic, get_session  # noqa: E402


# topic_id -> (track, weight or None to leave alone, prerequisite_only)
#
# praxis  = imputation layers: diffusion models and learnable tokens
# astro   = photometry, spectroscopy, imagery, transients, time-domain
#
# The two straddlers are demoted to 0.8 rather than deactivated: they're
# still genuinely relevant, they just shouldn't outrank the topics the
# tracks exist to follow.
ASSIGNMENTS: dict[str, tuple[str, float | None, bool]] = {
    "generative-cross-modal-imputation":      ("praxis", None, False),
    "missing-modality-learning":              ("praxis", None, False),
    "multimodal-foundation-models-astronomy": ("praxis", 0.8,  False),
    "ml-foundations":                         ("praxis", None, True),
    "transient-photometric-classification":   ("astro",  None, False),
    "astronomy-foundations":                  ("astro",  None, False),
    "sim-to-real-transfer-astronomy":         ("astro",  0.8,  False),
}


def assign(*, apply: bool) -> int:
    """Apply ASSIGNMENTS. Returns a process exit code."""
    session = get_session()
    changed = 0
    missing: list[str] = []
    try:
        for topic_id, (track, weight, prereq) in ASSIGNMENTS.items():
            topic = session.query(Topic).filter(Topic.id == topic_id).one_or_none()
            if topic is None:
                missing.append(topic_id)
                continue

            deltas: list[str] = []
            if topic.track != track:
                deltas.append(f"track {topic.track!r} -> {track!r}")
                topic.track = track
            if weight is not None and float(topic.weight or 0) != weight:
                deltas.append(f"weight {topic.weight} -> {weight}")
                topic.weight = weight
            if bool(topic.prerequisite_only) != prereq:
                deltas.append(f"prerequisite_only {bool(topic.prerequisite_only)} -> {prereq}")
                topic.prerequisite_only = prereq

            if deltas:
                changed += 1
                print(f"  {topic_id}: {', '.join(deltas)}")
            else:
                print(f"  {topic_id}: already correct")

        if missing:
            print("\nnot found in this database (skipped):")
            for topic_id in missing:
                print(f"  {topic_id}")

        if not apply:
            session.rollback()
            print(f"\nDRY RUN — {changed} topic(s) would change. Re-run with --apply to write.")
            return 0

        session.commit()
        print(f"\napplied — {changed} topic(s) updated.")

        # a scope with topics on only one side of the split still "works",
        # but silently defeats the point, so say so loudly.
        tracked = session.query(Topic).filter(Topic.active.is_(True)).all()
        by_track: dict[str | None, int] = {}
        for topic in tracked:
            if topic.prerequisite_only:
                continue
            by_track[topic.track] = by_track.get(topic.track, 0) + 1
        print("\nquota-eligible active topics per track:")
        for track, count in sorted(by_track.items(), key=lambda kv: (kv[0] is None, kv[0])):
            print(f"  {track or '(untracked)'}: {count}")
        if len([t for t in by_track if t]) < 2:
            print(
                "\nWARNING: fewer than two named tracks are populated. Per-track "
                "discovery will behave like the old single-pool version."
            )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI surface, report and fail
        session.rollback()
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the changes (default is a dry run)",
    )
    args = parser.parse_args()
    print("assigning topic tracks" + ("" if args.apply else " (dry run)") + ":")
    return assign(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
