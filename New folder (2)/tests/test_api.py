"""Unit and Integration tests for Py2SafeRust-X FastAPI REST API."""
import time
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.jobs import job_manager

client = TestClient(app)


def test_api_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["rustc_available"] is True
    assert data["rustc_path"] is not None


def test_api_transpile_synchronous():
    py_code = """
x = 42
print(x)
"""
    response = client.post("/api/v1/transpile", json={"python_code": py_code})
    assert response.status_code == 200
    data = response.json()
    assert "let x = 42;" in data["rust_code"]
    assert data["compiled"] is True
    assert data["semantic_match"] is True
    assert data["confidence_score"] == 100
    assert "Py2SafeRust-X" in data["explanation_report_markdown"]


def test_api_async_job_flow():
    py_code = """
total = 0
for i in range(4):
    total = total + i
print(total)
"""
    # 1. Submit job
    submit_resp = client.post("/api/v1/jobs", json={"python_code": py_code})
    assert submit_resp.status_code == 202
    job_id = submit_resp.json()["job_id"]
    assert job_id is not None

    # 2. Wait for completion (max 10s)
    status = "pending"
    for _ in range(20):
        stat_resp = client.get(f"/api/v1/jobs/{job_id}")
        assert stat_resp.status_code == 200
        status = stat_resp.json()["status"]
        if status in ("done", "failed"):
            break
        time.sleep(0.5)

    assert status == "done"

    # 3. Retrieve result
    result_resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert result_resp.status_code == 200
    res_data = result_resp.json()
    assert res_data["compiled"] is True
    assert res_data["semantic_match"] is True
    assert res_data["confidence_score"] > 0


def test_api_job_failure_state_handling():
    # If a job raises an error, job manager must set status to 'failed' with error
    job_id = job_manager.create_job()

    # Intentionally trigger an unparseable syntax error or crash
    job_manager.process_job(job_id=job_id, python_source="def invalid syntax ::::()")

    stat_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert stat_resp.status_code == 200
    data = stat_resp.json()
    assert data["status"] == "failed"
    assert data["error"] is not None
    assert "Pipeline execution error" in data["error"]


def test_frontend_static_serving():
    # 1. Root redirect to /ui/
    resp_root = client.get("/", follow_redirects=False)
    assert resp_root.status_code in (307, 302)
    assert resp_root.headers["location"] == "/ui/"

    # 2. UI HTML serving
    resp_ui = client.get("/ui/")
    assert resp_ui.status_code == 200
    assert "Py2SafeRust-X" in resp_ui.text
    assert "id=\"python-code-input\"" in resp_ui.text

    # 3. CSS static serving
    resp_css = client.get("/ui/style.css")
    assert resp_css.status_code == 200
    assert "--font-mono" in resp_css.text

    # 4. JS static serving
    resp_js = client.get("/ui/app.js")
    assert resp_js.status_code == 200
    assert "DOMContentLoaded" in resp_js.text

