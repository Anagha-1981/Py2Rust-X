"""FastAPI Application Entrypoint for Py2SafeRust-X."""
from pathlib import Path
from dotenv import load_dotenv

# Load .env configuration
load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from .routes import router

app = FastAPI(
    title="Py2SafeRust-X REST API",
    description=(
        "Academic Python-to-Rust Transpilation Framework with Adaptive Repair, "
        "Semantic Verification, Explainable Compilation, and Confidence Assessment."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware allowing all origins for local development and demo testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Mount frontend directory as StaticFiles at /ui
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/", tags=["Root"])
def root():
    return RedirectResponse(url="/ui/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
