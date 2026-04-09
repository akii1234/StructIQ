"""Pydantic response models for all API endpoints."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, field_validator


class HealthResponse(BaseModel):
    status: str


class AnalyzeResponse(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    progress: dict | None = None
    repo_path: str = ""
    created_at: str = ""
    updated_at: str = ""


class ExplainResponse(BaseModel):
    run_id: str
    question: str
    answer: str


class CompareMetricResult(BaseModel):
    run_a: float
    run_b: float
    delta: float
    direction: Literal["improved", "regressed", "unchanged"]


class OverrideRequest(BaseModel):
    """Request body for adding a finding override."""

    ap_type: str
    file: str | None = None
    reason: str  # "intentional" | "false_positive" | "deferred"
    note: str = ""

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        allowed = {"intentional", "false_positive", "deferred"}
        if v not in allowed:
            raise ValueError(f"reason must be one of {allowed}")
        return v

    @field_validator("ap_type")
    @classmethod
    def validate_ap_type(cls, v: str) -> str:
        if not v or len(v) > 64:
            raise ValueError("ap_type must be a non-empty string ≤ 64 chars")
        return v


class CompareResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    health_score: CompareMetricResult
    cycles: CompareMetricResult
    god_files: CompareMetricResult
    weak_boundaries: CompareMetricResult
    high_coupling_files: CompareMetricResult
