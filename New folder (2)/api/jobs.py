"""Background Job Manager for Py2SafeRust-X.

Provides thread-safe asynchronous job scheduling and status tracking.
Ensures jobs transition to 'failed' with the captured exception message
if pipeline execution encounters any error, preventing hanging jobs.
"""
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pipeline import run_pipeline, PipelineResult


@dataclass
class JobRecord:
    job_id: str
    status: str  # "pending", "running", "done", "failed"
    result: Optional[PipelineResult] = None
    error: Optional[str] = None


class JobManager:
    def __init__(self):
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = JobRecord(job_id=job_id, status="pending")
        return job_id

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def process_job(
        self,
        job_id: str,
        python_source: str,
        test_inputs: Optional[List[Any]] = None
    ) -> None:
        """Executes pipeline asynchronously with guaranteed exception handling."""
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].status = "running"

        try:
            result = run_pipeline(python_source, test_inputs=test_inputs)
            with self._lock:
                self._jobs[job_id].result = result
                self._jobs[job_id].status = "done"
        except Exception as e:
            # Guarantee job transitions to 'failed' with captured error
            with self._lock:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = f"Pipeline execution error: {type(e).__name__}: {str(e)}"


# Global job manager singleton
job_manager = JobManager()
