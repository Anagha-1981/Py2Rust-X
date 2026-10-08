# Py2SafeRust-X 🚀

**An Academic Python-to-Rust Transpilation Framework with Adaptive Repair, Semantic Verification, Explainable Compilation, and Confidence Assessment.**

> MCA Mini-Project — Department of Computer Applications, Government Engineering College (GEC) Thrissur.

---

## 📖 Architecture Overview

Py2SafeRust-X translates arbitrary Python code into memory-safe, idiomatic, and compilable Rust code without requiring manual debugging. It organizes compilation into a strict 5-stage pipeline:

```text
Python Source Code
   │
   ▼
[Stage 1] Transpilation Module (AST -> Typed IR -> Ownership Analysis -> Rust Codegen)
   │
   ▼
[Stage 2] Adaptive Repair Module (rustc JSON diagnostics -> Knowledge Base -> LLM Fallback -> Recompile loop)
   │
   ▼
[Stage 3] Semantic Verification Module (Python vs Rust dual execution & stdout/diff comparator)
   │   └─ [Feedback Loop: on semantic mismatch, feeds back to Adaptive Repair]
   ▼
[Stage 4] Explainable Compilation Module (Plain-English borrow-checker & mutation rationale)
   │
   ▼
[Stage 5] Confidence Assessment Module (Transparent 0-100 score with itemized deductions)
   │
   ▼
Output: Safe Rust Code + Equivalence Evidence + Human-Readable Report + Confidence Score
```

---

## 🛠️ Prerequisites & Setup

### 1. Requirements
- **Python**: 3.10+ (tested on Python 3.11)
- **Rust Toolchain**: `rustc` and `cargo` installed and accessible on PATH (e.g., via `rustup`)
- **LLM Backend** (Optional for standard repairs; required for LLM fallback):
  - **Google Gemini** (Recommended): Set `GEMINI_API_KEY` in `.env`
  - **OpenAI-compatible API** (Optional fallback): Set `OPENAI_API_KEY` in `.env`

### 2. Installation
```powershell
git clone <repo-url>
cd py2saferust-x

# Install Python dependencies
py -m pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Key configuration settings:
- `LLM_BACKEND`: `gemini` (default), `groq`, or `openai`
- `GEMINI_API_KEY`: Your Google Gemini API key
- `GEMINI_MODEL`: Default `gemini-3.5-flash`
- `GROQ_API_KEY`: Your Groq API key for ultra-fast (sub-second) repairs and resilient fallback
- `GROQ_MODEL`: Default `openai/gpt-oss-120b` (or `qwen/qwen3.8-27b`)
- `OPENAI_API_KEY`: Optional fallback API key
- `EXECUTION_TIMEOUT_SECS`: Subprocess timeout for Python & Rust (default `5`)
- `LLM_TIMEOUT_SECS`: Network timeout for LLM repair queries (default `30`)

---

## 🚀 Running the REST API

Py2SafeRust-X provides a production-structured FastAPI server with Swagger documentation and asynchronous job execution.

Start the dev server:
```powershell
py -m uvicorn api.main:app --reload --port 8000
```

- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: `GET http://localhost:8000/api/v1/health`

### Synchronous Endpoint Example
```bash
curl -X POST "http://localhost:8000/api/v1/transpile" \
     -H "Content-Type: application/json" \
     -d '{"python_code": "x = [1, 2, 3]\ny = x\nprint(x)"}'
```

### Asynchronous Job Workflow
1. Submit job: `POST /api/v1/jobs` -> Returns `{"job_id": "<uuid>"}`
2. Poll status: `GET /api/v1/jobs/{job_id}` -> Returns `"pending"`, `"running"`, `"done"`, or `"failed"`
3. Fetch results: `GET /api/v1/jobs/{job_id}/result`

---

## 💻 Running the CLI

Run transpilation directly from the command line:

```powershell
# Basic usage
py -m cli.main input.py --out output.rs --report report.md

# Inspect full JSON pipeline payload
py -m cli.main input.py --json
```

---

## 🧪 Running the Test Suite

Run the full pytest automated test suite across all 5 modules:

```powershell
py -m pytest tests/ -v
```

### Test Coverage Highlights:
- **`tests/test_transpiler.py`**: AST parsing, type inference, mutability analysis, vector aliasing clone injection.
- **`tests/test_repair.py`**: rustc JSON diagnostic parsing, rule matching, self-learning rule persistence, LLM timeout handling.
- **`tests/test_verifier.py`**: Isolated subprocess execution of Python and compiled Rust binaries with stdout diffing.
- **`tests/test_explain.py`**: Human-readable Markdown and structured explanation generation.
- **`tests/test_confidence.py`**: Itemized deduction breakdown and clamped scoring verification.
- **`tests/test_api.py`**: FastAPI endpoints, async job state machine, failure recovery.
- **`tests/test_e2e.py`**: Slide benchmark (`x = [1, 2, 3]; y = x; print(x)` -> compiles with `x.clone()`, verifies output, achieves 100% confidence).

---

## 🧠 Key Design Features

### 1. Ownership & Borrowing Analysis (`transpiler/ownership.py`)
Python defaults to reference semantics for non-primitive types, whereas Rust enforces affine types and move semantics.
When transpiling `y = x` on a non-Copy collection (`Vec`, `HashMap`, `String`):
- The analyzer tracks future reads of `x` within the scope.
- If `x` is read after assignment to `y`, the assignment is rewritten as `y = x.clone()`.
- If `x` is reassigned or mutated (e.g. `.append()`), the variable is automatically declared `let mut x`.

### 2. Self-Learning Knowledge Base (`repair/knowledge_base.py`)
- Pre-seeded with deterministic rules for:
  - `E0382` (Borrow of moved value -> insert `.clone()`)
  - `E0384` (Cannot assign twice to immutable variable -> promote `let` to `let mut`)
  - `E0502`/`E0499` (Borrow conflicts -> scope restructure or clone)
  - `unused_mut` (Strip redundant `mut`)
  - `E0308` (Type mismatch / literal numeric casting)
- **Self-Learning**: When `llm_repair.py` synthesizes a valid fix that compiles successfully, the pattern and transformation are automatically extracted and persisted into `rules.json`. Future runs bypass the LLM and match the rule directly.
- Provenance is explicitly logged in `RepairLog` as `"pre_seeded"`, `"learned"`, or `"llm"`.

### 3. Confidence Assessment Scoring
The confidence score is computed as a transparent, explainable metric:
$$\text{Score} = \text{clamp}(100 - \Delta_{\text{iter}} - \Delta_{\text{KB}} - \Delta_{\text{LLM}} - \Delta_{\text{verif}} - \Delta_{\text{types}}, 0, 100)$$
- **Compilation Failure**: Score = 0
- **Extra Repair Iterations**: $-10$ per iteration beyond the first
- **KB Repairs**: $-5$ each (deterministic)
- **LLM Repairs**: $-15$ each (heuristic)
- **Semantic Mismatch**: $-30 \times (1 - \text{pass\_rate})$
- **Unknown Type Inference**: $-20$ if unresolved type placeholders remain

---

## 🎓 Academic Presentation / Viva Defense Notes

### What is Fully Built & Functional:
1. **5-Stage Pipeline**: Complete, end-to-end working pipeline from Python AST to compiled Rust with dual verification.
2. **Borrow Analysis**: Real dataflow analysis that automatically detects moves and mutability.
3. **Compiler Integration**: Direct subprocess orchestration with `rustc --error-format=json`.
4. **Self-Learning KB**: Data-driven rule repository that learns from successful LLM repairs.
5. **REST API & CLI**: Complete FastAPI service with background job worker and command-line tool.

### Prototype Simplifications vs. Production-Grade (Mention as "Future Work"):
1. **Parser Frontend**: v1 uses Python's standard `ast` module. Future work should integrate `tree-sitter-python` for language-agnostic AST parsing, incremental re-parsing, and fault-tolerant parsing of incomplete syntax.
2. **Execution Sandbox**: v1 executes Python and Rust binaries in subprocesses with strict 5-second timeouts. Production deployments should use container-based sandboxes (e.g. Docker, Firejail, gVisor) with seccomp filters and CPU/memory cgroups.
3. **Type Inference**: v1 implements flow-sensitive forward type propagation for primitives, lists, dictionaries, and tuples. Future work can incorporate a Hindley-Milner or constraint-based type solver.
4. **Intermediate Representation**: Future iterations could emit MLIR (Multi-Level Intermediate Representation) or Rust HIR/MIR directly for compiler-level optimization passes.
