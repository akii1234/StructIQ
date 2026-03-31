"""Classify files by language and type."""

from __future__ import annotations

from pathlib import Path
from typing import Dict


LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".sql": "sql",
    ".json": "config",
    ".yaml": "config",
    ".yml": "config",
    ".sh": "shell",
}


class FileClassifier:
    """Classify code files into language and type."""

    def classify(self, file_path: str) -> Dict[str, str]:
        """Return classification metadata for a file."""
        path = Path(file_path)
        extension = path.suffix.lower()
        language = LANGUAGE_BY_EXTENSION.get(extension, "unknown")
        file_type = self._infer_type(path, language)

        return {
            "file": str(path),
            "language": language,
            "type": file_type,
        }

    def _infer_type(self, path: Path, language: str) -> str:
        """Infer logical file type from path and language."""
        if language == "sql":
            return "database"
        if language == "shell":
            return "script"
        if language == "config":
            return "config"

        parts = {part.lower() for part in path.parts}
        if {"infra", "infrastructure", "terraform", "k8s", "helm"} & parts:
            return "infrastructure"
        if language == "typescript" and path.suffix.lower() == ".tsx":
            return "frontend"
        if language == "javascript" and path.suffix.lower() == ".jsx":
            return "frontend"
        if {"frontend", "client", "web", "ui", "components"} & parts:
            return "frontend"
        if language in {"python", "javascript", "typescript", "java", "go"}:
            return "backend"
        return "unknown"
