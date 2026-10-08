"""LLM-Based Repair Module for Py2SafeRust-X.

Provides fallback repair capabilities using Google Gemini when rule-based
Knowledge Base matching does not resolve a compiler or semantic verification error.
Supports configurable 30s timeout and graceful fallback error handling.
"""
import os
import re
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv
import requests

load_dotenv(override=True)
from .compiler import RustDiagnostic


@dataclass
class LLMRepairResult:
    success: bool
    repaired_code: Optional[str] = None
    error_message: Optional[str] = None
    model_name: Optional[str] = None


class LLMRepairClient:
    def __init__(
        self,
        backend: Optional[str] = None,
        timeout: int = 30,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        groq_base_url: Optional[str] = None,
        groq_model: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
        openai_model: Optional[str] = None,
    ):
        self.backend = backend or os.getenv("LLM_BACKEND", "gemini").lower()
        self.timeout = timeout
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.groq_base_url = groq_base_url or os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
        self.groq_model = groq_model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.openai_base_url = openai_base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        self.openai_model = openai_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def repair(
        self,
        python_source: str,
        current_rust_code: str,
        diagnostics: List[RustDiagnostic],
        semantic_mismatch: Optional[str] = None
    ) -> LLMRepairResult:
        """Requests a repair with multi-tier provider cascade: Primary -> Groq -> OpenAI."""
        prompt = self._build_prompt(python_source, current_rust_code, diagnostics, semantic_mismatch)

        backend = (self.backend or os.getenv("LLM_BACKEND", "gemini")).lower()
        gemini_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        openai_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")

        # Determine caller execution sequence based on backend preference
        call_sequence = []
        if backend == "groq":
            if groq_key:
                call_sequence.append(("groq", self._call_groq))
            if gemini_key:
                call_sequence.append(("gemini", self._call_gemini))
            if openai_key:
                call_sequence.append(("openai", self._call_openai))
        elif backend == "openai":
            if openai_key:
                call_sequence.append(("openai", self._call_openai))
            if groq_key:
                call_sequence.append(("groq", self._call_groq))
            if gemini_key:
                call_sequence.append(("gemini", self._call_gemini))
        else: # default "gemini"
            if gemini_key:
                call_sequence.append(("gemini", self._call_gemini))
            if groq_key:
                call_sequence.append(("groq", self._call_groq))
            if openai_key:
                call_sequence.append(("openai", self._call_openai))

        if not call_sequence:
            if groq_key:
                return self._call_groq(prompt)
            return self._call_gemini(prompt)

        errors = []
        for provider_name, call_fn in call_sequence:
            res = call_fn(prompt)
            if res.success:
                return res
            errors.append(f"{provider_name}: {res.error_message}")

        return LLMRepairResult(
            success=False,
            error_message="; ".join(errors),
            model_name=self.gemini_model if backend == "gemini" else (self.groq_model if backend == "groq" else self.openai_model)
        )

    def _build_prompt(
        self,
        python_source: str,
        current_rust_code: str,
        diagnostics: List[RustDiagnostic],
        semantic_mismatch: Optional[str]
    ) -> str:
        diag_summary = []
        for d in diagnostics:
            diag_summary.append(f"[{d.level.upper()} {d.code or ''}]: {d.message}")
            if d.suggestion:
                diag_summary.append(f"  Suggestion: {d.suggestion}")

        if diag_summary:
            diag_text = "\n".join(diag_summary)
        elif semantic_mismatch:
            diag_text = "None (Code compiles cleanly, but exhibits semantic logic/output mismatch across test cases)."
        else:
            diag_text = "Unknown compilation or runtime failure."

        semantic_text = f"\nSemantic Test Mismatch Details:\n{semantic_mismatch}" if semantic_mismatch else ""

        return f"""You are an expert Rust systems programmer repairing automatically transpiled Python-to-Rust code.

Original Python source:
```python
{python_source}
```

Current Rust code that failed:
```rust
{current_rust_code}
```

Rust Compiler Diagnostics:
{diag_text}
{semantic_text}

TASK:
Fix the Rust code so that it compiles cleanly without borrow checker or type errors, and EXACTLY matches the semantic behavior of the Python code across all test cases.
Pay close attention to loop bounds (e.g. 0..n vs 0..=n), base cases, integer vs float division, vector/slice indexing, and output formatting.
Return ONLY the complete, corrected Rust code inside a single ```rust ... ``` markdown code block. Do NOT include conversational explanations.
"""

    def _extract_rust_code(self, response_text: str) -> Optional[str]:
        """Extracts Rust code from markdown fences and unescapes any HTML entities."""
        match = re.search(r"```(?:rust)?\s*([\s\S]*?)\s*```", response_text, re.IGNORECASE)
        code = None
        if match:
            code = match.group(1).strip()
        elif "fn main" in response_text or "fn " in response_text:
            code = response_text.strip()

        if code:
            import html
            return html.unescape(code)
        return None

    def _call_gemini(self, prompt: str) -> LLMRepairResult:
        api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return LLMRepairResult(
                success=False,
                error_message="GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable not configured",
                model_name=self.gemini_model
            )

        # Build candidate list: primary model first, then resilient fallbacks
        candidate_models = [self.gemini_model]
        for fallback in ["gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        last_error = ""
        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        last_error = f"{model}: empty response candidates"
                        continue

                    parts = candidates[0].get("content", {}).get("parts", [])
                    content = parts[0].get("text", "") if parts else ""
                    code = self._extract_rust_code(content)
                    if not code:
                        last_error = f"{model}: failed to extract valid Rust code from response"
                        continue

                    return LLMRepairResult(success=True, repaired_code=code, model_name=model)
                else:
                    last_error = f"{model} returned HTTP {resp.status_code}: {resp.text[:150]}"
                    # If model is 503 (high demand) or 429, continue to next candidate model
                    continue

            except requests.exceptions.Timeout:
                last_error = f"{model} request timed out after {self.timeout}s"
                continue
            except Exception as e:
                last_error = f"{model} repair error: {str(e)}"
                continue

        return LLMRepairResult(
            success=False,
            error_message=last_error or "All Gemini models failed",
            model_name=self.gemini_model
        )

    def _call_groq(self, prompt: str) -> LLMRepairResult:
        api_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            return LLMRepairResult(
                success=False,
                error_message="GROQ_API_KEY environment variable not configured",
                model_name=self.groq_model
            )

        candidate_models = [self.groq_model]
        for fallback in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        last_error = ""
        for model in candidate_models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an expert Rust repair compiler engine. Return only the repaired Rust code inside a ```rust ... ``` block."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }

            try:
                resp = requests.post(self.groq_base_url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        last_error = f"{model}: empty response choices"
                        continue
                    content = choices[0].get("message", {}).get("content", "")
                    code = self._extract_rust_code(content)
                    if not code:
                        last_error = f"{model}: could not extract valid Rust code from output"
                        continue
                    return LLMRepairResult(success=True, repaired_code=code, model_name=f"groq/{model}")
                else:
                    last_error = f"{model} returned HTTP {resp.status_code}: {resp.text[:150]}"
                    continue
            except requests.exceptions.Timeout:
                last_error = f"{model} timed out after {self.timeout}s"
                continue
            except Exception as e:
                last_error = f"{model} error: {str(e)}"
                continue

        return LLMRepairResult(
            success=False,
            error_message=f"Groq failure across models: {last_error}",
            model_name=f"groq/{self.groq_model}"
        )

    def _call_openai(self, prompt: str) -> LLMRepairResult:
        if not self.openai_api_key:
            return LLMRepairResult(
                success=False,
                error_message="OPENAI_API_KEY environment variable not configured",
                model_name=self.openai_model
            )

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": "You are a Rust repair compiler engine."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }

        try:
            resp = requests.post(self.openai_base_url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                return LLMRepairResult(
                    success=False,
                    error_message=f"OpenAI API returned HTTP {resp.status_code}: {resp.text[:200]}",
                    model_name=self.openai_model
                )

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            code = self._extract_rust_code(content)
            if not code:
                return LLMRepairResult(
                    success=False,
                    error_message="Failed to extract valid Rust code from OpenAI response",
                    model_name=self.openai_model
                )

            return LLMRepairResult(success=True, repaired_code=code, model_name=self.openai_model)

        except requests.exceptions.Timeout:
            return LLMRepairResult(
                success=False,
                error_message=f"OpenAI API request timed out after {self.timeout}s",
                model_name=self.openai_model
            )
        except Exception as e:
            return LLMRepairResult(
                success=False,
                error_message=f"OpenAI repair error: {str(e)}",
                model_name=self.openai_model
            )
