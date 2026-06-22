"""
Topic configuration loader.

Three operations on config/topics/*.yaml ↔ topics table:

1. bootstrap_topics_from_yaml() — called at FastAPI startup. INSERTs any
   YAML topics that aren't yet in the DB. Existing DB rows are left untouched
   ("DB wins" per architectural decision). YAML files removed from disk
   mark the corresponding DB row as source_yaml_present=False (the row is
   preserved so UI-only edits aren't blown away).

2. import_topics_from_yaml() — explicit re-sync triggered by
   POST /topics/import-yaml. OVERWRITES every topic field with YAML values
   for topics present in YAML. Topics not in YAML are NOT deleted, only
   marked source_yaml_present=False. UI-created topics (created_via='ui')
   are never touched here.

3. export_topics_to_yaml() — write current DB state to config/topics/*.yaml.
   Triggered by POST /topics/export-yaml. One file per topic, named
   "{id}.yaml". On local-beta installs this updates the working tree so
   `git diff` shows the change; on Railway it produces files in the
   ephemeral container filesystem that the API zips for download.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..database import Topic, get_session

logger = logging.getLogger(__name__)

# fields written to / read from YAML for each topic (alongside 'id')
_YAML_FIELDS: tuple[str, ...] = (
    "name",
    "stream",
    "active",
    "weight",
    "keywords",
    "arxiv_categories",
    "recency_days",
    "min_relevance",
    "key_concepts",
    "learning_objectives",
    "resources",
    "quiz_difficulty",
    "prerequisites",
)


def _topics_dir() -> Path:
    """Resolve config/topics/ relative to the repo root."""
    return Path(__file__).resolve().parents[2] / "config" / "topics"


def _iter_topic_yaml_paths() -> list[Path]:
    """
    Return all *.yaml files under config/topics/.

    Scans the top-level directory plus any immediate child directory whose
    name does NOT start with '_'. This keeps `_archive/` (and any future
    `_disabled/`-style folders) excluded by convention while allowing
    `examples/` (tracked demo topics) and `private/` (gitignored user
    topics) to coexist. Nested subdirectories beyond one level are not
    scanned.
    """
    topics_dir = _topics_dir()
    if not topics_dir.exists():
        logger.info("config/topics/ does not exist; skipping topic loader")
        return []
    paths: list[Path] = list(topics_dir.glob("*.yaml"))
    for child in topics_dir.iterdir():
        if child.is_dir() and not child.name.startswith("_"):
            paths.extend(child.glob("*.yaml"))
    return sorted(p for p in paths if p.is_file())


def _load_topic_yaml(path: Path) -> dict[str, Any]:
    """Parse one topic YAML; raise on missing required fields."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping at top level")
    for required in ("id", "name", "stream"):
        if required not in data:
            raise ValueError(f"{path.name}: missing required field '{required}'")
    return data


def _coerce_str_list(items: Any, *, source: str, field: str) -> list[str]:
    """
    Normalize a YAML list field into list[str].

    A common foot-gun: a list item like `- foo: bar` is parsed by YAML as a
    single-key dict, not the string "foo: bar". This helper rejoins those
    into colon-separated strings and warns. The right long-term fix is to
    quote the YAML, but we should not crash the app over it.
    """
    out: list[str] = []
    for i, item in enumerate(items or []):
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and len(item) == 1:
            (k, v), = item.items()
            coerced = f"{k}: {v}" if v not in (None, "") else str(k)
            logger.warning(
                "%s :: %s[%d] parsed as dict; coercing to string %r "
                "(quote the YAML value to silence this warning)",
                source, field, i, coerced,
            )
            out.append(coerced)
        else:
            # last-resort cast
            logger.warning(
                "%s :: %s[%d] is not a string (%s); using str()",
                source, field, i, type(item).__name__,
            )
            out.append(str(item))
    return out


def _extract_fields(data: dict[str, Any], *, source: str = "<unknown>") -> dict[str, Any]:
    """Map a parsed YAML dict to Topic model kwargs, applying defaults."""
    return {
        "name": data["name"],
        "stream": data["stream"],
        "active": bool(data.get("active", True)),
        "weight": float(data.get("weight", 1.0)),
        "keywords": _coerce_str_list(data.get("keywords"), source=source, field="keywords"),
        "arxiv_categories": _coerce_str_list(
            data.get("arxiv_categories"), source=source, field="arxiv_categories"
        ),
        "recency_days": int(data.get("recency_days", 30)),
        "min_relevance": float(data.get("min_relevance", 0.18)),
        "key_concepts": _coerce_str_list(
            data.get("key_concepts"), source=source, field="key_concepts"
        ),
        "learning_objectives": _coerce_str_list(
            data.get("learning_objectives"), source=source, field="learning_objectives"
        ),
        "resources": _coerce_str_list(data.get("resources"), source=source, field="resources"),
        "quiz_difficulty": str(data.get("quiz_difficulty", "medium")),
        "prerequisites": _coerce_str_list(
            data.get("prerequisites"), source=source, field="prerequisites"
        ),
    }


def _collect_yaml_topics() -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Read every topic YAML; return (ids, id->data)."""
    yaml_ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for path in _iter_topic_yaml_paths():
        try:
            data = _load_topic_yaml(path)
        except Exception as exc:
            logger.error("failed to load %s: %s", path.name, exc)
            continue
        topic_id = data["id"]
        if topic_id in yaml_ids:
            logger.warning(
                "duplicate topic id %s (in %s); first one wins",
                topic_id,
                path.name,
            )
            continue
        yaml_ids.add(topic_id)
        by_id[topic_id] = data
    return yaml_ids, by_id


def bootstrap_topics_from_yaml() -> dict[str, int]:
    """
    Startup hook. Insert new YAML topics; never overwrite existing DB rows.

    Returns:
        {"inserted": int, "preserved": int, "marked_orphaned": int}
    """
    yaml_ids, by_id = _collect_yaml_topics()

    inserted = 0
    preserved = 0
    marked_orphaned = 0

    session = get_session()
    try:
        existing_ids = {t.id for t in session.query(Topic.id).all()}
        now = datetime.utcnow()

        # insert topics that exist in YAML but not in DB
        for topic_id in sorted(yaml_ids - existing_ids):
            row = Topic(
                id=topic_id,
                created_via="yaml",
                source_yaml_present=True,
                created_at=now,
                updated_at=now,
                **_extract_fields(by_id[topic_id], source=topic_id),
            )
            session.add(row)
            inserted += 1
            logger.info("bootstrap: inserted topic %s", topic_id)

        # YAML present + DB present -> leave alone, ensure flag is true
        for topic_id in yaml_ids & existing_ids:
            row = session.get(Topic, topic_id)
            if row is not None and not row.source_yaml_present:
                row.source_yaml_present = True
            preserved += 1

        # DB present, YAML missing -> mark orphaned (do not delete)
        for topic_id in existing_ids - yaml_ids:
            row = session.get(Topic, topic_id)
            if row is None:
                continue
            if row.created_via == "yaml" and row.source_yaml_present:
                row.source_yaml_present = False
                marked_orphaned += 1
                logger.info(
                    "bootstrap: %s YAML missing; marked source_yaml_present=False",
                    topic_id,
                )

        session.commit()
    finally:
        session.close()

    return {
        "inserted": inserted,
        "preserved": preserved,
        "marked_orphaned": marked_orphaned,
    }


def import_topics_from_yaml() -> dict[str, int]:
    """
    Explicit re-sync. Overwrite DB fields for every topic present in YAML.
    UI-only topics (created_via='ui') are untouched.

    Returns:
        {"upserted": int, "inserted": int, "updated": int, "marked_orphaned": int}
    """
    yaml_ids, by_id = _collect_yaml_topics()

    inserted = 0
    updated = 0
    marked_orphaned = 0

    session = get_session()
    try:
        existing_ids = {t.id for t in session.query(Topic.id).all()}
        now = datetime.utcnow()

        for topic_id, data in sorted(by_id.items()):
            fields = _extract_fields(data, source=topic_id)
            if topic_id in existing_ids:
                row = session.get(Topic, topic_id)
                if row is None:
                    continue
                for key, value in fields.items():
                    setattr(row, key, value)
                row.source_yaml_present = True
                row.updated_at = now
                updated += 1
            else:
                session.add(
                    Topic(
                        id=topic_id,
                        created_via="yaml",
                        source_yaml_present=True,
                        created_at=now,
                        updated_at=now,
                        **fields,
                    )
                )
                inserted += 1

        for topic_id in existing_ids - yaml_ids:
            row = session.get(Topic, topic_id)
            if row is None:
                continue
            if row.created_via == "yaml" and row.source_yaml_present:
                row.source_yaml_present = False
                marked_orphaned += 1

        session.commit()
    finally:
        session.close()

    return {
        "upserted": inserted + updated,
        "inserted": inserted,
        "updated": updated,
        "marked_orphaned": marked_orphaned,
    }


def export_topics_to_yaml() -> dict[str, Any]:
    """
    Write current DB state out to one YAML file per topic. Clears any prior
    orphan flag because the file is now back on disk.

    Returns:
        {"exported": int, "directory": str}
    """
    topics_dir = _topics_dir()
    topics_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    session = get_session()
    try:
        topics = session.query(Topic).order_by(Topic.id.asc()).all()
        for topic in topics:
            data = {"id": topic.id}
            for field in _YAML_FIELDS:
                data[field] = getattr(topic, field)
            path = topics_dir / f"{topic.id}.yaml"
            with path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(
                    data,
                    f,
                    sort_keys=False,
                    allow_unicode=True,
                    default_flow_style=False,
                )
            topic.source_yaml_present = True
            exported += 1
        session.commit()
    finally:
        session.close()

    return {"exported": exported, "directory": str(topics_dir)}
