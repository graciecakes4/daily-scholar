"""
Onboarding wizard: LLM-driven topic draft generation.

A first-login user types a few sentences about what they want to learn;
we feed that to the LLM and ask for a structured topic config
(keywords, arXiv categories, key concepts) the user can review + edit
before saving. The save itself goes through the regular POST /topics
path — the wizard just primes the form fields.

The LLM call is defensive about format: we strip markdown fences,
clamp list lengths, lowercase keywords, and fall back to a usable
scaffold if the model errors or returns garbage. The user can always
edit the draft, so "okay-ish" beats "nothing."
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from .llm.factory import get_llm_client

logger = logging.getLogger(__name__)


# soft clamps so we never hand the UI an unbounded list. The numbers are
# wider than the typical LLM output (5-10 items per list) so a verbose
# response still survives the trim instead of getting silently truncated.
MAX_KEYWORDS = 30
MAX_ARXIV_CATEGORIES = 10
MAX_KEY_CONCEPTS = 30
MAX_NAME_CHARS = 200

# minimum signal we'll accept from the user — a one-word interest is
# probably too thin to extract anything useful from
MIN_INTERESTS_CHARS = 4
MAX_INTERESTS_CHARS = 2000


@dataclass
class TopicDraft:
    """Shape the wizard hands to the frontend (and the user-edited form to POST /topics)."""

    name: str
    keywords: list[str]
    arxiv_categories: list[str]
    key_concepts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


_SYSTEM = (
    "You help learners set up study topics in Daily Scholar, a personalized "
    "research-paper discovery system. Your output is parsed as JSON and used "
    "to seed a topic editor — be concise and structured."
)


def _build_prompt(interests: str) -> str:
    return f"""A learner has described what they want to study. Extract a structured topic configuration.

Return a single JSON object (no prose, no markdown) with these fields:
- "name" (string, max 60 chars): a short topic name that captures the focus
- "keywords" (array of 5-15 strings): search terms a paper-discovery engine could use to find relevant papers; prefer specific technical phrases over vague ones
- "arxiv_categories" (array of 1-5 strings): valid arXiv category codes (e.g., "cs.LG", "astro-ph.HE", "stat.ML") that this topic falls under. If the topic isn't a natural arXiv fit, return an empty array.
- "key_concepts" (array of 3-8 strings): foundational concepts a learner studying this topic should understand

Example output for "transformer attention mechanisms":
{{"name":"Transformer Attention","keywords":["self-attention","multi-head attention","positional encoding","scaled dot-product attention","transformer architecture","attention is all you need"],"arxiv_categories":["cs.LG","cs.CL"],"key_concepts":["query-key-value projections","scaled dot-product attention","multi-head decomposition","positional encodings","layer normalization"]}}

Learner's description:
\"\"\"
{interests.strip()}
\"\"\"

JSON only:"""


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _norm_str(v: Any, max_chars: int) -> str:
    if not isinstance(v, str):
        return ""
    return " ".join(v.strip().split())[:max_chars]


def _norm_list(v: Any, *, max_len: int, lowercase: bool = False) -> list[str]:
    """Coerce an LLM-returned list to clean strings. Drops empties + dups."""
    if not isinstance(v, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in v:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        if lowercase:
            s = s.lower()
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_len:
            break
    return out


def _scaffold_from_interests(interests: str) -> TopicDraft:
    """
    Fallback when the LLM errors or returns junk. Take the first words of
    the user's input as keywords, leave categories empty, name from the
    first chunk. The user will edit it anyway.
    """
    tokens = [t.strip(",.;:!?").lower() for t in interests.split() if t.strip()]
    keywords: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 3:        # drop "a", "of", etc.
            continue
        if t in seen:
            continue
        seen.add(t)
        keywords.append(t)
        if len(keywords) >= 6:
            break
    # take the first ~8 tokens as the name; fall back to a generic label
    name_tokens = [t for t in interests.split() if t.strip()][:8]
    name = " ".join(name_tokens).strip() or "My new topic"
    return TopicDraft(
        name=name[:MAX_NAME_CHARS],
        keywords=keywords,
        arxiv_categories=[],
        key_concepts=[],
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


class InterestsTooShort(ValueError):
    """Raised when the input is too thin to bother sending to the LLM."""


def generate_topic_draft(interests: str) -> TopicDraft:
    """
    Run an LLM extraction on the user's free-text interests. Always
    returns a `TopicDraft`; falls back to a token-scaffold on any LLM
    error or invalid response. The caller (endpoint) doesn't need to
    catch anything except `InterestsTooShort`.
    """
    text = (interests or "").strip()
    if len(text) < MIN_INTERESTS_CHARS:
        raise InterestsTooShort(
            f"interests must be at least {MIN_INTERESTS_CHARS} characters"
        )
    text = text[:MAX_INTERESTS_CHARS]

    # default route is fine here — onboarding isn't latency-critical and
    # the prompt is small. Reuses the same provider routing as everything
    # else, so cost / model overrides land through the existing env knobs.
    try:
        client = get_llm_client("default")
        raw = client.complete_json(
            _build_prompt(text),
            max_tokens=600,
            temperature=0.3,
            system=_SYSTEM,
        )
    except Exception as e:  # noqa: BLE001 — never let the wizard 500 on LLM hiccups
        logger.warning("onboarding: LLM call failed, falling back: %s", e)
        return _scaffold_from_interests(text)

    # LLMClient.complete_json returns {} or a {__llm_parse_error__: ...}
    # marker dict on JSON parse failure — treat both as fallback triggers
    if not isinstance(raw, dict) or "__llm_parse_error__" in raw or not raw:
        logger.warning(
            "onboarding: LLM returned unparseable output, falling back. raw=%r",
            raw,
        )
        return _scaffold_from_interests(text)

    name = _norm_str(raw.get("name"), MAX_NAME_CHARS)
    if not name:
        # use the scaffold's name rather than ship a blank one
        name = _scaffold_from_interests(text).name

    return TopicDraft(
        name=name,
        keywords=_norm_list(raw.get("keywords"), max_len=MAX_KEYWORDS, lowercase=True),
        arxiv_categories=_norm_list(
            raw.get("arxiv_categories"), max_len=MAX_ARXIV_CATEGORIES,
        ),
        key_concepts=_norm_list(raw.get("key_concepts"), max_len=MAX_KEY_CONCEPTS),
    )
