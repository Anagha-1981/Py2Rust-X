"""Pydantic Models for Py2SafeRust-X REST API."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TranspileRequest(BaseModel):
    python_code: str = Field(..., description="Python source code to transpile")
    test_inputs: Optional[List[Any]] = Field(default=None, description="Optional explicit test cases")


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "pending", "running", "done", "failed"
    error: Optional[str] = None


class PipelineResponse(BaseModel):
    rust_code: str
    compiled: bool
    semantic_match: bool
    confidence_score: int
    confidence_breakdown: List[Dict[str, Any]]
    explanation_report_markdown: str
    explanation_report_dict: Dict[str, Any]
    repair_log: List[Dict[str, Any]]
    warnings: List[str]
    verification_details: Dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    rustc_available: bool
    rustc_path: Optional[str] = None
    python_version: str
    llm_backend: str
