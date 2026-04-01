"""Configuration settings for service runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass

SUPPORTED_EXTENSIONS = [
    ext.strip().lower()
    for ext in os.getenv(
        "SUPPORTED_EXTENSIONS",
        ".py,.js,.ts,.java,.go",
    ).split(",")
    if ext.strip()
]

IGNORED_DIRECTORIES = [
    entry.strip().lower()
    for entry in os.getenv(
        "IGNORED_DIRECTORIES",
        "__pycache__,venv,.git,node_modules,dist,build,target",
    ).split(",")
    if entry.strip()
]

MODE = os.getenv("APP_MODE", "cli").lower()
if MODE not in ("cli", "api"):
    raise ValueError("APP_MODE must be 'cli' or 'api'")
IS_API_MODE = MODE == "api"


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Environment-backed runtime settings."""

    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))
    llm_max_chunks: int = int(os.getenv("LLM_MAX_CHUNKS", "20"))
    max_file_size: int = int(os.getenv("MAX_FILE_SIZE", "2000000"))
    cache_enabled: bool = _bool_env("CACHE_ENABLED", True)
    enable_llm: bool = _bool_env("ENABLE_LLM", False)
    llm_high_priority_only: bool = _bool_env("LLM_HIGH_PRIORITY_ONLY", True)
    llm_medium_priority: bool = _bool_env("LLM_MEDIUM_PRIORITY", False)
    batch_size: int = int(os.getenv("BATCH_SIZE", "5"))
    # ~8000 characters ≈ ~2000 tokens (assuming ~4 chars/token)
    # This balances context richness with LLM cost and context limits
    max_content_length: int = int(os.getenv("MAX_CONTENT_LENGTH", "8000"))


settings = Settings()
