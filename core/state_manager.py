"""State manager for discovery engine pipeline state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DiscoveryState:
    """In-memory state for one discovery run."""

    files: List[str] = field(default_factory=list)
    classified_files: List[Dict[str, str]] = field(default_factory=list)
    modules: Dict[str, List[str]] = field(default_factory=dict)
    summaries: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable state dictionary."""
        return {
            "files": self.files,
            "classified_files": self.classified_files,
            "modules": self.modules,
            "summaries": self.summaries,
        }
