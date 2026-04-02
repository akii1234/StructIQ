"""Pydantic response models for all API endpoints."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class AnalyzeResponse(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    created_at: str | None = None
    repo_path: str | None = None


class ExplainResponse(BaseModel):
    run_id: str
    question: str
    answer: str


class CompareMetricResult(BaseModel):
    run_a: float
    run_b: float
    delta: float
    direction: str  # "improved" | "regressed" | "unchanged"


class CompareResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    health_score: CompareMetricResult
    cycles: CompareMetricResult
    god_files: CompareMetricResult
    weak_boundaries: CompareMetricResult
    high_coupling_files: CompareMetricResult
