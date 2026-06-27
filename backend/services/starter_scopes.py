"""
Seed the system-owned public "starter" scopes.

A starter scope is a curated, system-owned (owner_user_id=NULL),
public scope that new users see in the onboarding picker. Each one
references the foundation-level topics for a single domain so a user
who picks a starter immediately has meaningful content driving their
discovery / review / quizzes.

Idempotence: a starter scope is identified by the pair
(owner_user_id IS NULL, name). Re-running the seed:
  - inserts any missing starter
  - leaves existing starters' user-editable fields (mode, topic_ids,
    description) alone, but does refresh the topic_ids list to keep
    pace with new starter topics being added under config/topics/starter/
  - logs the action taken per starter

Topics referenced by each starter must already exist in the `topics`
table. In normal app boot order this is fine — bootstrap_topics_from_yaml
runs first in `lifespan` and inserts every YAML under config/topics/.
If a referenced topic id is missing at seed time, the corresponding id
is silently dropped from scope_topic_ids and a warning is logged; the
starter is still created so it's available to the picker.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..database import (
    Scope,
    SCOPE_VISIBILITY_PUBLIC,
    Topic,
    get_session,
)


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StarterSpec:
    """One row in the starter-scope catalog."""
    name: str
    description: str
    topic_ids: tuple[str, ...]


# the catalog. add a new starter by appending here — the seeder picks
# it up on the next boot.
STARTER_SCOPES: tuple[StarterSpec, ...] = (
    StarterSpec(
        name="ML Starter",
        description=(
            "Foundations of machine learning — neural networks, training, "
            "classification, fine-tuning, and diffusion. A good first scope "
            "for anyone getting into ML research."
        ),
        topic_ids=(
            "ml-foundations",
            "generic-ml",
        ),
    ),
    StarterSpec(
        name="Physics Starter",
        description=(
            "Foundations of physics — classical mechanics, quantum mechanics, "
            "and statistical mechanics. A good first scope for anyone "
            "rebuilding their physics intuition or following physics research."
        ),
        topic_ids=(
            "classical-mechanics-foundations",
            "quantum-mechanics-foundations",
            "statistical-mechanics-foundations",
        ),
    ),
    StarterSpec(
        name="Biology & Life Sciences Starter",
        description=(
            "Foundations of biology — molecular biology, cell biology, and "
            "genetics & genomics. A good first scope for following modern "
            "life-sciences research."
        ),
        topic_ids=(
            "molecular-biology-foundations",
            "cell-biology-foundations",
            "genetics-and-genomics-foundations",
        ),
    ),
    StarterSpec(
        name="Economics & Finance Starter",
        description=(
            "Foundations of economics and finance — microeconomics, "
            "macroeconomics, and financial economics. A good first scope "
            "for following economics research and asset-pricing work."
        ),
        topic_ids=(
            "microeconomics-foundations",
            "macroeconomics-foundations",
            "financial-economics-foundations",
        ),
    ),
    StarterSpec(
        name="Climate & Earth Sciences Starter",
        description=(
            "Foundations of climate and Earth sciences — climate science, "
            "atmospheric physics, and oceanography. A good first scope for "
            "following climate research."
        ),
        topic_ids=(
            "climate-science-foundations",
            "atmospheric-physics-foundations",
            "oceanography-foundations",
        ),
    ),
)


def _existing_topic_ids(session: Session, candidates: tuple[str, ...]) -> list[str]:
    """Return the subset of `candidates` that exists in the topics table."""
    if not candidates:
        return []
    rows = (
        session.query(Topic.id)
        .filter(Topic.id.in_(candidates))
        .all()
    )
    present = {r[0] for r in rows}
    missing = [tid for tid in candidates if tid not in present]
    if missing:
        log.warning(
            "starter scopes: dropping missing topic ids %s from starter",
            missing,
        )
    return [tid for tid in candidates if tid in present]


def seed_starter_scopes(session: Session | None = None) -> dict[str, int]:
    """
    Insert any missing starter scopes; refresh topic_ids on existing ones.

    Returns a summary dict with counts: {"inserted": N, "refreshed": M,
    "unchanged": K}. Safe to call repeatedly.
    """
    owns_session = session is None
    if owns_session:
        session = get_session()

    inserted = 0
    refreshed = 0
    unchanged = 0

    try:
        for spec in STARTER_SCOPES:
            topic_ids = _existing_topic_ids(session, spec.topic_ids)

            row = (
                session.query(Scope)
                .filter(
                    Scope.owner_user_id.is_(None),
                    Scope.name == spec.name,
                )
                .first()
            )

            if row is None:
                row = Scope(
                    name=spec.name,
                    description=spec.description,
                    owner_user_id=None,
                    visibility=SCOPE_VISIBILITY_PUBLIC,
                    # "all" if we couldn't find any topics — degenerate
                    # but still usable; user can fork and edit later.
                    scope_mode="multi" if topic_ids else "all",
                    scope_topic_ids=list(topic_ids),
                    forked_from_scope_id=None,
                )
                session.add(row)
                inserted += 1
                log.info("starter scopes: inserted %r with %d topic(s)", spec.name, len(topic_ids))
                continue

            # refresh topic_ids if the YAML catalog has expanded under us
            current = list(row.scope_topic_ids or [])
            if current != topic_ids:
                row.scope_topic_ids = list(topic_ids)
                # keep the row honest about its mode if topic_ids went empty
                if not topic_ids and row.scope_mode == "multi":
                    row.scope_mode = "all"
                refreshed += 1
                log.info(
                    "starter scopes: refreshed %r topic_ids %s -> %s",
                    spec.name, current, topic_ids,
                )
            else:
                unchanged += 1

        if owns_session:
            session.commit()
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()

    return {"inserted": inserted, "refreshed": refreshed, "unchanged": unchanged}
