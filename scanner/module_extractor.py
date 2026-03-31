"""Extract module mappings from file paths."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List


class ModuleExtractor:
    """Group files by top-level module folder."""

    def extract(self, files: List[str], root_directory: str) -> Dict[str, List[str]]:
        """Return {module_name: [file_paths]} mapping."""
        root_path = Path(root_directory).resolve()
        modules: dict[str, list[str]] = defaultdict(list)

        for file_path in files:
            absolute_file = Path(file_path).resolve()
            try:
                relative_path = absolute_file.relative_to(root_path)
            except ValueError:
                relative_path = absolute_file

            parts = relative_path.parts
            module_name = parts[0] if len(parts) > 1 else "root"
            modules[module_name].append(str(absolute_file))

        return dict(modules)
