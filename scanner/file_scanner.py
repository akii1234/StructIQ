"""Language-agnostic file scanner."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from StructIQ.config import IGNORED_DIRECTORIES, SUPPORTED_EXTENSIONS


class FileScanner:
    """Scan directories and return relevant source files."""

    def __init__(self, supported_extensions: set[str] | None = None) -> None:
        source = supported_extensions or set(SUPPORTED_EXTENSIONS)
        self.supported_extensions = {ext.strip().lower() for ext in source if ext.strip()}
        self._ignored_directories = {name.lower() for name in IGNORED_DIRECTORIES}

    def scan_directory(self, root_directory: str) -> List[str]:
        """Recursively scan for supported files."""
        root_path = Path(root_directory).resolve()
        if not root_path.exists():
            raise FileNotFoundError(f"Directory not found: {root_directory}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {root_directory}")

        collected_files: List[str] = []

        for current_root, dirs, files in os.walk(root_path):
            dirs[:] = [
                d
                for d in dirs
                if d.lower() not in self._ignored_directories and not d.startswith(".")
            ]

            for file_name in files:
                if file_name.startswith("."):
                    continue
                extension = Path(file_name).suffix.lower()
                if extension in self.supported_extensions:
                    full_path = Path(current_root) / file_name
                    if full_path.is_file() and not full_path.is_symlink():
                        collected_files.append(str(full_path))

        collected_files.sort()
        return collected_files
