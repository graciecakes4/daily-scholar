"""
Configuration Management for Daily Scholar

This module handles loading and validating configuration from:
1. Environment variables (.env file)
2. YAML configuration files (interests.yaml, courses.yaml)

LEARNING NOTES:
- Pydantic Settings automatically loads from environment variables
- We use YAML for complex, nested configurations (interests, courses)
- Type hints ensure we catch configuration errors early
"""

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# ENVIRONMENT SETTINGS
# =============================================================================

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Pydantic automatically:
    - Loads values from .env file
    - Converts types (e.g., "8000" -> 8000 for port)
    - Validates required fields
    """
    
    # API Keys
    anthropic_api_key: str = Field(description="Anthropic API key for Claude")
    semantic_scholar_api_key: Optional[str] = Field(default=None)
    core_api_key: Optional[str] = Field(default=None)
    
    # Database
    database_url: str = Field(default="sqlite:///./data/daily_scholar.db")
    
    # Application
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    frontend_url: str = Field(default="http://localhost:3000")
    
    # Content Generation — Anthropic (default provider)
    claude_model: str = Field(default="claude-sonnet-4-5")
    max_tokens: int = Field(default=4096)

    # Content Generation — Google Gemini (optional; required if any task routes to gemini or antigravity)
    gemini_api_key: Optional[str] = Field(default=None)
    gemini_model: str = Field(default="gemini-2.5-flash")

    # Content Generation — Google Antigravity (uses GEMINI_API_KEY under the hood)
    # Leave model empty to use the Antigravity SDK's default.
    antigravity_model: Optional[str] = Field(default=None)

    # Per-task LLM routing overrides — format "provider:model".
    # Supported providers: anthropic, gemini, antigravity.
    # Examples:
    #   LLM_TASK_SUMMARY=gemini:gemini-2.5-flash
    #   LLM_TASK_QUIZ=antigravity:gemini-2.5-pro
    # Empty / None = use DEFAULT_TASK_ROUTING in backend/services/llm/factory.py.
    llm_task_summary: Optional[str] = Field(default=None)
    llm_task_review: Optional[str] = Field(default=None)
    llm_task_quiz: Optional[str] = Field(default=None)
    llm_task_evaluate: Optional[str] = Field(default=None)
    llm_task_default: Optional[str] = Field(default=None)
    
    # Scheduling
    daily_generation_time: str = Field(default="06:00")
    timezone: str = Field(default="America/New_York")
    
    # File Storage
    upload_dir: str = Field(default="./uploads")
    max_upload_size: int = Field(default=52428800)  # 50MB

    # Storage backend for blob writes (PDFs, future uploads):
    #   "local" — filesystem under local_storage_root (default for solo / beta)
    #   "b2"    — Backblaze B2 via S3-compatible API (default for cloud)
    storage_backend: str = Field(default="local")
    local_storage_root: str = Field(default="./data")

    # Backblaze B2 — required only if storage_backend == "b2"
    # Endpoint format: https://s3.<region>.backblazeb2.com
    b2_endpoint_url: Optional[str] = Field(default=None)
    b2_key_id: Optional[str] = Field(default=None)
    b2_application_key: Optional[str] = Field(default=None)
    b2_bucket_name: Optional[str] = Field(default=None)
    b2_region: str = Field(default="us-west-002")

    # Web Push (VAPID) — populate via `python scripts/generate_vapid_keys.py`.
    # All three left empty by default; push endpoints return 503 until set.
    vapid_public_key: Optional[str] = Field(default=None)
    vapid_private_key: Optional[str] = Field(default=None)
    vapid_subject: Optional[str] = Field(default=None)

    # Cloudflare Access — multi-user identity (optional).
    # The app always reads Cf-Access-Authenticated-User-Email as the identity
    # source when present. When CF_ACCESS_VERIFY_JWT is on, the app also
    # requires + cryptographically validates the Cf-Access-Jwt-Assertion
    # header against the team JWKS. Both TEAM_DOMAIN and AUD_TAG are required
    # at flag-on time; with the flag off they're unused.
    cf_access_verify_jwt: bool = Field(default=False)
    cf_access_team_domain: Optional[str] = Field(default=None)
    cf_access_aud_tag: Optional[str] = Field(default=None)

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Environment variables are case-insensitive
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Using @lru_cache means we only load settings once,
    then reuse the same instance. This is more efficient
    and ensures consistency across the application.
    """
    return Settings()


# =============================================================================
# YAML CONFIGURATION LOADERS
# =============================================================================

def get_config_path() -> Path:
    """Get the path to the config directory."""
    # This file is in backend/, config is in ../config/
    return Path(__file__).parent.parent / "config"


def load_interests_config() -> dict:
    """
    Load research interests configuration from YAML.
    
    Returns:
        Dictionary containing interests configuration
        
    Raises:
        FileNotFoundError: If interests.yaml doesn't exist
        yaml.YAMLError: If YAML is malformed
    """
    config_path = get_config_path() / "interests.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(
            f"Interests configuration not found at {config_path}. "
            "Please create it from the template."
        )
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_courses_config() -> dict:
    """
    Load courses configuration from YAML.
    
    Returns:
        Dictionary containing courses configuration
        
    Raises:
        FileNotFoundError: If courses.yaml doesn't exist
        yaml.YAMLError: If YAML is malformed
    """
    config_path = get_config_path() / "courses.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(
            f"Courses configuration not found at {config_path}. "
            "Please create it from the template."
        )
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

def validate_configuration() -> dict:
    """
    Validate all configuration files and return a status report.
    
    This is useful for debugging configuration issues.
    
    Returns:
        Dictionary with validation status for each config source
    """
    status = {
        "environment": {"valid": False, "errors": []},
        "interests": {"valid": False, "errors": []},
        "courses": {"valid": False, "errors": []},
    }
    
    # Validate environment settings
    try:
        settings = get_settings()
        if not settings.anthropic_api_key or settings.anthropic_api_key == "your_anthropic_api_key_here":
            status["environment"]["errors"].append("ANTHROPIC_API_KEY not set")
        else:
            status["environment"]["valid"] = True
    except Exception as e:
        status["environment"]["errors"].append(str(e))
    
    # Validate interests config
    try:
        interests = load_interests_config()
        if not interests.get("interests"):
            status["interests"]["errors"].append("No interests defined")
        else:
            status["interests"]["valid"] = True
    except Exception as e:
        status["interests"]["errors"].append(str(e))
    
    # Validate courses config
    try:
        courses = load_courses_config()
        if not courses.get("courses"):
            status["courses"]["errors"].append("No courses defined")
        else:
            status["courses"]["valid"] = True
    except Exception as e:
        status["courses"]["errors"].append(str(e))
    
    return status


# =============================================================================
# QUICK ACCESS HELPERS
# =============================================================================

def get_interest_keywords() -> list[str]:
    """Get a flat list of all interest keywords for searching."""
    config = load_interests_config()
    keywords = []
    
    for category in ["primary", "secondary", "exploratory"]:
        for interest in config.get("interests", {}).get(category, []):
            keywords.extend(interest.get("keywords", []))
    
    return list(set(keywords))  # Remove duplicates


def get_arxiv_categories() -> list[str]:
    """Get a flat list of all arXiv categories to search."""
    config = load_interests_config()
    categories = []
    
    for category in ["primary", "secondary", "exploratory"]:
        for interest in config.get("interests", {}).get(category, []):
            categories.extend(interest.get("arxiv_categories", []))
    
    return list(set(categories))


def get_course_topics(course_id: str) -> list[dict]:
    """Get all topics for a specific course."""
    config = load_courses_config()
    
    for course in config.get("courses", []):
        if course.get("id") == course_id:
            return course.get("topics", [])
    
    return []


def get_all_topics() -> list[dict]:
    """Get all topics from all courses."""
    config = load_courses_config()
    topics = []
    
    for course in config.get("courses", []):
        for topic in course.get("topics", []):
            # Add course info to each topic
            topic_with_course = topic.copy()
            topic_with_course["course_id"] = course["id"]
            topic_with_course["course_name"] = course["name"]
            topics.append(topic_with_course)
    
    return topics
