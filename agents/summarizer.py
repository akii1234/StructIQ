"""File summarization agent using dynamic prompts."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAIError

from StructIQ.config import settings
from StructIQ.llm.client import OpenAIClient
from StructIQ.services.cache_manager import CacheManager
from StructIQ.utils.content_extractor import extract_relevant_content
from StructIQ.utils.content_utils import (
    chunk_text,
    extract_lightweight_config_keys,
    get_file_hash,
    is_relevant_file,
)
from StructIQ.utils.logger import get_logger
from StructIQ.utils.static_analyzer import analyze_file, get_file_importance


def _parse_batch_row_id(val: Any) -> Optional[int]:
    """Parse JSON id field as integer; reject bools and non-numeric values."""
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val == int(val):
        return int(val)
    return None


def _coerce_batch_response_rows(raw: Any) -> List[dict]:
    """Normalize LLM payload to a list of summary dicts (order-independent)."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        val = raw.get("summaries")
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    return []


class Summarizer:
    """Summarize files with file-type-specific prompts."""

    def __init__(
        self,
        llm_client: OpenAIClient,
        max_chars: int = 12000,
        cache_manager: CacheManager | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.max_chars = max_chars
        self.retry_attempts = int(os.getenv("LLM_RETRY_ATTEMPTS", "2"))
        self.chunk_threshold = int(os.getenv("LLM_CHUNK_THRESHOLD", "8000"))
        self.max_chunks = int(os.getenv("LLM_MAX_CHUNKS", "20"))
        self.config_lightweight_max_bytes = int(
            os.getenv("CONFIG_LIGHTWEIGHT_MAX_BYTES", "1200")
        )
        self.cache_manager = cache_manager or CacheManager()
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def _touch_cost(
        cost_tracker: Optional[Dict[str, Any]],
        key: str,
        delta: int = 1,
    ) -> None:
        if cost_tracker is None:
            return
        cost_tracker[key] = cost_tracker.get(key, 0) + delta

    def summarize_file(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """Return summary JSON for one file (CLI / single-file compatibility)."""
        cost_tracker: Dict[str, Any] = {
            "llm_calls": 0,
            "batch_calls": 0,
            "cache_hits": 0,
            "llm_skipped_low_priority": 0,
            "batch_file_count_sum": 0,
        }
        return self._summarize_single_routed(
            file_path,
            file_type,
            cost_tracker=cost_tracker,
        )

    def summarize_low_priority(
        self,
        file_path: str,
        file_type: str,
        static_meta: Dict[str, Any],
        cost_tracker: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Static-only summary for low-importance files."""
        self._touch_cost(cost_tracker, "llm_skipped_low_priority")
        key_elements = (
            static_meta.get("classes", [])[:15]
            + static_meta.get("functions", [])[:15]
        )
        return {
            "file": file_path,
            "summary": "Low-value file (config/helper); static outline only.",
            "key_elements": [str(x) for x in key_elements],
            "dependencies": static_meta.get("imports", [])[:20],
            "_status": "success",
            "_reason": "low_priority_static",
        }

    def summarize_medium_priority(
        self,
        file_path: str,
        file_type: str,
        content: str,
        static_meta: Dict[str, Any],
        cost_tracker: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Medium tier: optional LLM with partial content."""
        content_hash = get_file_hash(content)
        cached = self.cache_manager.get(file_path, content_hash)
        if cached:
            self._touch_cost(cost_tracker, "cache_hits")
            payload = dict(cached)
            payload["_status"] = "success"
            payload["_reason"] = "cache_hit"
            return payload

        if not settings.enable_llm or not settings.llm_medium_priority:
            return self._medium_static_summary(file_path, static_meta)

        excerpt = extract_relevant_content(content)
        prompt = self._build_prompt(file_type)
        summary = self._summarize_with_retry(file_path, prompt, excerpt)
        if summary.get("_status") == "success":
            self.cache_manager.set(file_path, content_hash, self._clean_meta(summary))
        if cost_tracker is not None and summary.get("_status") == "success":
            self._touch_cost(cost_tracker, "llm_calls")
        return summary

    def summarize_batch_high_priority(
        self,
        items: List[Dict[str, Any]],
        cost_tracker: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Batch LLM summarize for high-importance files. Each item: file_path, file_type, content."""
        results: Dict[str, Dict[str, Any]] = {}
        batch: List[Dict[str, Any]] = []

        for item in items:
            fp = item["file_path"]
            ft = item["file_type"]
            content = item["content"]
            static_meta = item.get("static_meta") or analyze_file(fp)
            content_hash = get_file_hash(content)
            cached = self.cache_manager.get(fp, content_hash)
            if cached:
                results[fp] = {
                    **dict(cached),
                    "_status": "success",
                    "_reason": "cache_hit",
                }
                self._touch_cost(cost_tracker, "cache_hits")
                continue
            if not settings.enable_llm:
                results[fp] = self.high_static_fallback(fp, static_meta)
                continue

            excerpt = extract_relevant_content(content)
            batch.append(
                {
                    "file_path": fp,
                    "file_type": ft,
                    "excerpt": excerpt,
                    "content": content,
                    "content_hash": content_hash,
                    "static_meta": static_meta,
                }
            )

        size = max(1, settings.batch_size)
        for i in range(0, len(batch), size):
            chunk = batch[i : i + size]
            if not chunk:
                continue
            merged = self._run_batch_llm_validated(chunk, cost_tracker)
            for row in chunk:
                fp = row["file_path"]
                summary = merged.get(fp)
                if summary and summary.get("_status") == "success":
                    self.cache_manager.set(fp, row["content_hash"], self._clean_meta(summary))
                else:
                    summary = self.high_static_fallback(fp, row["static_meta"])
                results[fp] = summary

        return results

    def _run_batch_llm_validated(
        self,
        chunk: List[Dict[str, Any]],
        cost_tracker: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Call batch LLM up to twice; ID-keyed validation; per-file only where required."""
        expected_paths: Set[str] = {row["file_path"] for row in chunk}
        id_to_path: Dict[int, str] = {
            i: chunk[i]["file_path"] for i in range(len(chunk))
        }
        expected_ids: Set[int] = set(id_to_path.keys())
        parsed: Dict[str, Dict[str, Any]] = {}
        last_needs_individual: Set[str] = set(expected_paths)

        for _ in range(2):
            self._touch_cost(cost_tracker, "batch_calls")
            self._touch_cost(cost_tracker, "batch_file_count_sum", len(chunk))
            try:
                raw = self._call_batch_llm_raw(chunk, id_to_path, expected_ids)
            except RuntimeError:
                raw = {}
            parsed, last_needs_individual = self._strict_batch_validate_and_parse(
                raw, id_to_path, expected_ids
            )
            if (
                not last_needs_individual
                and set(parsed.keys()) == expected_paths
                and all(
                    parsed[k].get("_status") == "success" for k in expected_paths
                )
            ):
                return parsed

        must_individual = last_needs_individual | {
            fp
            for fp in expected_paths
            if fp not in parsed or parsed.get(fp, {}).get("_status") != "success"
        }

        for row in chunk:
            fp = row["file_path"]
            if fp not in must_individual:
                continue
            summary = self._individual_llm_for_chunk_row(row, cost_tracker)
            if summary.get("_status") == "success":
                self.cache_manager.set(fp, row["content_hash"], self._clean_meta(summary))
            parsed[fp] = summary

        return parsed

    def _strict_batch_validate_and_parse(
        self,
        raw: Any,
        id_to_path: Dict[int, str],
        expected_ids: Set[int],
    ) -> Tuple[Dict[str, Dict[str, Any]], Set[str]]:
        """
        Integer ID batch parse: exact ID set match and duplicate detection.
        Returns (parsed summaries by file path, paths that must use per-file LLM).
        """
        rows = _coerce_batch_response_rows(raw)
        row_id_per_item: List[Optional[int]] = []
        all_numeric_ids: Set[int] = set()

        for item in rows:
            raw_id = _parse_batch_row_id(item.get("id"))
            if raw_id is None:
                self.logger.error(
                    "batch_response_validation: missing or invalid \"id\" in row (keys=%s)",
                    list(item.keys())[:10],
                )
                row_id_per_item.append(None)
                continue
            all_numeric_ids.add(raw_id)
            if raw_id not in expected_ids:
                self.logger.error(
                    "batch_response_validation: unexpected id=%s (not in batch)",
                    raw_id,
                )
                row_id_per_item.append(None)
                continue
            row_id_per_item.append(raw_id)

        mapped_ids = [i for i in row_id_per_item if i is not None]
        cnt = Counter(mapped_ids)
        duplicate_ids = {i for i, n in cnt.items() if n > 1}

        response_expected_ids = set(mapped_ids)
        missing_ids = expected_ids - response_expected_ids
        unexpected_ids = all_numeric_ids - expected_ids

        needs_individual: Set[str] = set()
        for mid in missing_ids:
            needs_individual.add(id_to_path[mid])
        for did in duplicate_ids:
            needs_individual.add(id_to_path[did])

        if duplicate_ids:
            self.logger.error(
                "batch_response_validation: duplicate id entries for: %s",
                sorted(duplicate_ids),
            )
        if missing_ids or unexpected_ids:
            self.logger.error(
                "batch_response_validation: id set mismatch — "
                "missing_ids=%s unexpected_ids=%s",
                sorted(missing_ids),
                sorted(unexpected_ids),
            )

        out: Dict[str, Dict[str, Any]] = {}
        for item, rid in zip(rows, row_id_per_item):
            if rid is None or rid in duplicate_ids or rid not in expected_ids:
                continue
            file_path = id_to_path[rid]
            candidate = {
                "file": file_path,
                "summary": str(item.get("summary", "")).strip(),
                "key_elements": item.get("key_elements", []),
                "dependencies": item.get("dependencies", []),
            }
            if self._is_valid_summary(candidate):
                candidate["_status"] = "success"
                candidate["_reason"] = "batch_llm"
                out[file_path] = candidate
            else:
                self.logger.error(
                    "batch_response_validation: invalid summary payload for id=%s file=%s",
                    rid,
                    file_path,
                )
                needs_individual.add(file_path)

        for fp in id_to_path.values():
            if fp in needs_individual:
                continue
            if fp not in out or out[fp].get("_status") != "success":
                needs_individual.add(fp)

        return out, needs_individual

    def _call_batch_llm_raw(
        self,
        chunk: List[Dict[str, Any]],
        id_to_path: Dict[int, str],
        expected_ids: Set[int],
    ) -> Any:
        """Invoke LLM once for a batch; return parsed JSON."""
        body_blocks: List[str] = []
        for i, row in enumerate(chunk):
            body_blocks.append(
                f"ID: {i}\n"
                f"File: {row['file_path']}\n"
                f"Content:\n{row['excerpt']}"
            )
        body = "\n\n".join(body_blocks)
        id_list = ", ".join(str(x) for x in sorted(expected_ids))
        prompt = (
            "Summarize each file block below for codebase discovery "
            "(purpose, key symbols, dependencies).\n"
            "Each block starts with ID (integer), then File (for your reference only), then Content.\n"
            "Return a single JSON object with exactly one key \"summaries\" whose value is "
            "a JSON array.\n"
            "Every array element must be an object with exactly these keys: "
            "id (integer, must match the ID from the input block for that file), "
            "summary (string), key_elements (array of strings), "
            "dependencies (array of strings).\n"
            "Do not match files by path — use id only. Include exactly one element per input ID; "
            "array order does not matter.\n"
            "Required ids (each exactly once): "
            f"{id_list}\n"
        )
        last_exc: Exception | None = None
        for _ in range(self.retry_attempts + 1):
            try:
                return self.llm_client.generate_json(prompt, body)
            except (
                json.JSONDecodeError,
                OpenAIError,
                ValueError,
            ) as exc:
                self.logger.warning(
                    "batch_llm attempt failed (%s): %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                last_exc = exc
                continue
        if last_exc:
            raise RuntimeError(str(last_exc)) from last_exc
        raise RuntimeError("batch_llm_failed")

    def _individual_llm_for_chunk_row(
        self,
        row: Dict[str, Any],
        cost_tracker: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Fallback: one LLM call for a single file using structured excerpt."""
        excerpt = extract_relevant_content(row["content"])
        p = self._build_prompt(row["file_type"])
        summary = self._summarize_with_retry(row["file_path"], p, excerpt)
        self._touch_cost(cost_tracker, "llm_calls")
        return summary

    def _summarize_single_routed(
        self,
        file_path: str,
        file_type: str,
        cost_tracker: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return {
                "file": file_path,
                "summary": f"Failed to read file: {exc}",
                "key_elements": [],
                "dependencies": [],
                "_status": "failed",
                "_reason": f"read_error: {exc}",
            }

        relevant, reason = is_relevant_file(file_path, content)
        if not relevant:
            return {
                "file": file_path,
                "summary": f"Skipped file ({reason}).",
                "key_elements": [],
                "dependencies": [],
                "_status": "skipped",
                "_reason": reason,
            }

        if self._use_lightweight_config_summary(file_path, content):
            return self._lightweight_config_summary(file_path, content)

        static_meta = analyze_file(file_path)
        importance = get_file_importance(static_meta, file_path, file_type)

        if importance == "low":
            return self.summarize_low_priority(
                file_path, file_type, static_meta, cost_tracker=cost_tracker
            )

        if importance == "medium":
            return self.summarize_medium_priority(
                file_path, file_type, content, static_meta, cost_tracker
            )

        if settings.enable_llm and settings.llm_high_priority_only:
            batch_map = self.summarize_batch_high_priority(
                [
                    {
                        "file_path": file_path,
                        "file_type": file_type,
                        "content": content,
                        "static_meta": static_meta,
                    }
                ],
                cost_tracker=cost_tracker,
            )
            return batch_map.get(
                file_path,
                self.high_static_fallback(file_path, static_meta),
            )

        if not settings.enable_llm:
            return self.high_static_fallback(file_path, static_meta)

        content_hash = get_file_hash(content)
        cached = self.cache_manager.get(file_path, content_hash)
        if cached:
            self._touch_cost(cost_tracker, "cache_hits")
            payload = dict(cached)
            payload["_status"] = "success"
            payload["_reason"] = "cache_hit"
            return payload

        excerpt = extract_relevant_content(content)
        prompt = self._build_prompt(file_type)
        summary = self._summarize_with_retry(file_path, prompt, excerpt)
        if summary.get("_status") == "success":
            self.cache_manager.set(file_path, content_hash, self._clean_meta(summary))
        if cost_tracker is not None and summary.get("_status") == "success":
            self._touch_cost(cost_tracker, "llm_calls")
        return summary

    def _medium_static_summary(
        self,
        file_path: str,
        static_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "file": file_path,
            "summary": "Medium priority; static analysis only (LLM disabled for tier).",
            "key_elements": static_meta.get("functions", [])[:25]
            + static_meta.get("classes", [])[:25],
            "dependencies": static_meta.get("imports", [])[:30],
            "_status": "success",
            "_reason": "medium_static",
        }

    def high_static_fallback(
        self,
        file_path: str,
        static_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "file": file_path,
            "summary": "High priority fallback without LLM (batch/cache/offline).",
            "key_elements": static_meta.get("functions", [])[:30]
            + static_meta.get("classes", [])[:30],
            "dependencies": static_meta.get("imports", [])[:40],
            "_status": "success",
            "_reason": "high_static_fallback",
        }

    def persist_cache(self) -> None:
        """Write summary cache to disk."""
        self.cache_manager.persist()

    def _summarize_large_content(self, file_path: str, prompt: str, content: str) -> Dict[str, Any]:
        """Summarize large file by chunking and merging."""
        chunks = chunk_text(content)[: self.max_chunks]
        merged_parts: list[str] = []
        key_elements: set[str] = set()
        dependencies: set[str] = set()
        success_count = 0

        for chunk in chunks:
            chunk_excerpt = extract_relevant_content(chunk)
            chunk_result = self._summarize_with_retry(file_path, prompt, chunk_excerpt)
            if chunk_result.get("_status") == "success":
                success_count += 1
                summary_text = chunk_result.get("summary", "").strip()
                if summary_text:
                    merged_parts.append(summary_text)
                key_elements.update(
                    str(item).strip()
                    for item in chunk_result.get("key_elements", [])
                    if str(item).strip()
                )
                dependencies.update(
                    str(item).strip()
                    for item in chunk_result.get("dependencies", [])
                    if str(item).strip()
                )

        if success_count == 0:
            return self._fallback_summary(file_path, content, "chunk_summarization_failed")

        return {
            "file": file_path,
            "summary": " ".join(merged_parts).strip(),
            "key_elements": sorted(key_elements),
            "dependencies": sorted(dependencies),
            "_status": "success",
            "_reason": "chunked_partial" if success_count < len(chunks) else "chunked",
        }

    def _summarize_with_retry(self, file_path: str, prompt: str, content: str) -> Dict[str, Any]:
        """Call LLM with retries and response validation."""
        last_error = ""
        max_attempts = self.retry_attempts + 1

        for _ in range(max_attempts):
            try:
                response = self.llm_client.generate_json(prompt, content)
                payload = self._normalize_response(file_path, response)
                if self._is_valid_summary(payload):
                    payload["_status"] = "success"
                    payload["_reason"] = "llm_single"
                    return payload
                last_error = "invalid_response_schema"
            except (
                json.JSONDecodeError,
                OpenAIError,
                ValueError,
            ) as exc:
                self.logger.warning(
                    "summarize_with_retry failed for %s (%s): %s",
                    file_path,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                last_error = str(exc)

        return self._fallback_summary(file_path, content, f"llm_failed: {last_error}")

    def _normalize_response(self, file_path: str, response: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize LLM response into expected schema."""
        return {
            "file": file_path,
            "summary": str(response.get("summary", "")).strip(),
            "key_elements": response.get("key_elements", []),
            "dependencies": response.get("dependencies", []),
        }

    def _is_valid_summary(self, payload: Dict[str, Any]) -> bool:
        """Validate summary schema and data types."""
        required_keys = {"file", "summary", "key_elements", "dependencies"}
        if not required_keys.issubset(payload.keys()):
            return False
        if not isinstance(payload["summary"], str):
            return False
        if not isinstance(payload["key_elements"], list):
            return False
        if not isinstance(payload["dependencies"], list):
            return False
        return True

    def _fallback_summary(self, file_path: str, content: str, reason: str) -> Dict[str, Any]:
        """Return deterministic fallback summary."""
        return {
            "file": file_path,
            "summary": f"Basic summary generated without LLM. Content length: {len(content)} chars.",
            "key_elements": [],
            "dependencies": [],
            "_status": "failed",
            "_reason": reason,
        }

    def _use_lightweight_config_summary(self, file_path: str, content: str) -> bool:
        """Return whether config file should bypass LLM."""
        extension = Path(file_path).suffix.lower()
        if extension not in {".json", ".yaml", ".yml"}:
            return False
        size_in_bytes = len(content.encode("utf-8", errors="ignore"))
        return size_in_bytes <= self.config_lightweight_max_bytes

    def _lightweight_config_summary(self, file_path: str, content: str) -> Dict[str, Any]:
        """Generate lightweight config summary without LLM."""
        preview_keys = extract_lightweight_config_keys(file_path, content)
        return {
            "file": file_path,
            "summary": "Lightweight config summary generated locally.",
            "key_elements": preview_keys,
            "dependencies": [],
            "_status": "success",
            "_reason": "lightweight_config",
        }

    def _clean_meta(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Strip internal metadata keys before persistence."""
        return {
            "file": payload.get("file", ""),
            "summary": payload.get("summary", ""),
            "key_elements": payload.get("key_elements", []),
            "dependencies": payload.get("dependencies", []),
        }

    def _build_prompt(self, file_type: str) -> str:
        """Return a dynamic summarization prompt by file type."""
        if file_type == "backend":
            return (
                "Summarize this code:\n"
                "- purpose\n"
                "- key functions/classes\n"
                "- dependencies\n\n"
                "Return JSON with keys: summary, key_elements, dependencies."
            )
        if file_type == "frontend":
            return (
                "Summarize this frontend file:\n"
                "- UI purpose\n"
                "- components\n"
                "- APIs used\n\n"
                "Return JSON with keys: summary, key_elements, dependencies."
            )
        if file_type == "database":
            return (
                "Summarize this SQL:\n"
                "- tables involved\n"
                "- type of queries\n"
                "- purpose\n\n"
                "Return JSON with keys: summary, key_elements, dependencies."
            )
        if file_type == "config":
            return (
                "Explain this configuration:\n"
                "- purpose\n"
                "- key settings\n\n"
                "Return JSON with keys: summary, key_elements, dependencies."
            )
        return (
            "Summarize this file:\n"
            "- purpose\n"
            "- key elements\n"
            "- dependencies\n\n"
            "Return JSON with keys: summary, key_elements, dependencies."
        )
