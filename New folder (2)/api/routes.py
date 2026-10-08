"""FastAPI Route Definitions for Py2SafeRust-X API."""
import os
import sys
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from pipeline import run_pipeline
from repair.compiler import find_rustc
from .models import (
    TranspileRequest,
    JobSubmitResponse,
    JobStatusResponse,
    PipelineResponse,
    HealthResponse,
)
from .jobs import job_manager

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """System liveness check and runtime environment capabilities."""
    rustc_found = False
    rustc_path = None
    try:
        rustc_path = find_rustc()
        rustc_found = True
    except Exception:
        pass

    llm_backend = os.getenv("LLM_BACKEND", "gemini")
    return HealthResponse(
        status="healthy",
        rustc_available=rustc_found,
        rustc_path=rustc_path,
        python_version=sys.version.split()[0],
        llm_backend=llm_backend
    )


@router.post("/transpile", response_model=PipelineResponse, tags=["Transpilation"])
def transpile_synchronous(payload: TranspileRequest):
    """Synchronously executes the full 5-stage transpilation, repair, and verification pipeline."""
    try:
        result = run_pipeline(payload.python_code, test_inputs=payload.test_inputs)
        return PipelineResponse(**result.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transpilation failed: {str(e)}"
        )


@router.post("/transpile/file", response_model=PipelineResponse, tags=["Transpilation"])
async def transpile_file_upload(file: UploadFile = File(...)):
    """Accepts a Python (.py) file upload and executes the full transpilation pipeline."""
    if not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .py extension")

    content = await file.read()
    try:
        code_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Uploaded file must be valid UTF-8 text")

    try:
        result = run_pipeline(code_str)
        return PipelineResponse(**result.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transpilation failed: {str(e)}"
        )


@router.post("/jobs", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED, tags=["Async Jobs"])
def submit_job(payload: TranspileRequest, background_tasks: BackgroundTasks):
    """Submits a transpilation job for background asynchronous execution."""
    job_id = job_manager.create_job()
    background_tasks.add_task(
        job_manager.process_job,
        job_id=job_id,
        python_source=payload.python_code,
        test_inputs=payload.test_inputs
    )
    return JobSubmitResponse(
        job_id=job_id,
        status="pending",
        message="Job successfully submitted for async pipeline processing."
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["Async Jobs"])
def get_job_status(job_id: str):
    """Polls the execution status of a submitted background job."""
    record = job_manager.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        error=record.error
    )


@router.get("/jobs/{job_id}/result", response_model=PipelineResponse, tags=["Async Jobs"])
def get_job_result(job_id: str):
    """Retrieves the full transpilation, repair, and verification output of a completed job."""
    record = job_manager.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if record.status in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"Job is currently '{record.status}'. Please poll again shortly."
        )

    if record.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job execution failed: {record.error}"
        )

    if not record.result:
        raise HTTPException(status_code=500, detail="Result data missing for completed job")

    return PipelineResponse(**record.result.to_dict())
