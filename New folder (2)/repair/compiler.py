"""Rust Compiler Interface for Py2SafeRust-X.

Wraps rustc/cargo to compile generated Rust source and extracts
structured compiler diagnostics from `--error-format=json`.
Fully compatible with Windows paths and file locking behaviors.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

""" pinpoints the exact file, line number, and column where an error or warning occurs."""
@dataclass
class DiagnosticSpan:
    file_name: str
    line_start: int
    line_end: int
    column_start: int
    column_end: int
    text: str = ""
    suggested_replacement: Optional[str] = None


@dataclass
class RustDiagnostic:
    code: Optional[str]  # e.g., "E0382", "E0384", or None for generic errors
    message: str
    level: str  # "error", "warning", "note", "help"
    spans: List[DiagnosticSpan] = field(default_factory=list)
    suggestion: Optional[str] = None
    rendered: Optional[str] = None


@dataclass
class CompilationResult:
    success: bool
    returncode: int
    errors: List[RustDiagnostic] = field(default_factory=list)
    warnings: List[RustDiagnostic] = field(default_factory=list)
    binary_path: Optional[str] = None
    raw_output: str = ""


def find_rustc() -> str:
    """Locate rustc executable on Windows or POSIX."""
    rustc = shutil.which("rustc") or shutil.which("rustc.exe")
    if rustc:
        return rustc

    # Fallback check for default cargo bin on Windows
    cargo_bin = Path.home() / ".cargo" / "bin" / "rustc.exe"
    if cargo_bin.exists():
        return str(cargo_bin)

    raise FileNotFoundError("rustc executable not found on system PATH or ~/.cargo/bin")


def find_cargo() -> str:
    """Locate cargo executable on Windows or POSIX."""
    cargo = shutil.which("cargo") or shutil.which("cargo.exe")
    if cargo:
        return cargo

    cargo_bin = Path.home() / ".cargo" / "bin" / "cargo.exe"
    if cargo_bin.exists():
        return str(cargo_bin)

    raise FileNotFoundError("cargo executable not found on system PATH or ~/.cargo/bin")


def parse_rustc_json(stderr_text: str) -> List[RustDiagnostic]:
    """Parses JSON-formatted diagnostic lines output by rustc."""
    diagnostics: List[RustDiagnostic] = []
    for line in stderr_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if "message" not in data or "level" not in data:
            continue

        code = None
        if data.get("code") and isinstance(data["code"], dict):
            code = data["code"].get("code")

        spans: List[DiagnosticSpan] = []
        suggestion = None

        for sp in data.get("spans", []):
            span_obj = DiagnosticSpan(
                file_name=sp.get("file_name", ""),
                line_start=sp.get("line_start", 0),
                line_end=sp.get("line_end", 0),
                column_start=sp.get("column_start", 0),
                column_end=sp.get("column_end", 0),
                suggested_replacement=sp.get("suggested_replacement"),
            )
            if span_obj.suggested_replacement:
                suggestion = span_obj.suggested_replacement
            spans.append(span_obj)

        diag = RustDiagnostic(
            code=code,
            message=data.get("message", ""),
            level=data.get("level", "error"),
            spans=spans,
            suggestion=suggestion,
            rendered=data.get("rendered")
        )
        diagnostics.append(diag)

    return diagnostics


_CACHED_SIGNTOOL: Optional[str] = None


def _find_signtool() -> Optional[str]:
    """Find signtool.exe from Windows SDK / Kits or system PATH."""
    global _CACHED_SIGNTOOL
    if _CACHED_SIGNTOOL is not None:
        return _CACHED_SIGNTOOL if _CACHED_SIGNTOOL else None

    # Check PATH first
    s = shutil.which("signtool.exe") or shutil.which("signtool")
    if s:
        _CACHED_SIGNTOOL = s
        return s

    # Check standard Windows Kits directories
    kit_candidates = [
        Path(r"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe"),
        Path(r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"),
        Path(r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"),
        Path(r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe"),
    ]
    for cand in kit_candidates:
        if cand.exists():
            _CACHED_SIGNTOOL = str(cand)
            return str(cand)

    # Glob in Windows Kits
    wk = Path(r"C:\Program Files (x86)\Windows Kits")
    if wk.exists():
        try:
            for match in wk.glob("**/signtool.exe"):
                _CACHED_SIGNTOOL = str(match)
                return str(match)
        except Exception:
            pass

    _CACHED_SIGNTOOL = ""
    return None


def _sign_binary_if_windows(bin_path: str) -> bool:
    """Signs a compiled Windows PE binary using Authenticode to satisfy Windows SAC policy."""
    if os.name != "nt":
        return True
    if not os.path.exists(bin_path):
        return False

    # Attempt 1: Ultra-fast signtool.exe (completes in ~40ms)
    signtool = _find_signtool()
    if signtool:
        for attempt in range(3):
            try:
                p = subprocess.run(
                    [signtool, "sign", "/q", "/fd", "SHA256", "/s", "MY", "/n", "RustLocalDev", bin_path],
                    capture_output=True,
                    timeout=5
                )
                if p.returncode == 0:
                    return True
                time.sleep(0.1 * (attempt + 1))
            except Exception:
                time.sleep(0.1 * (attempt + 1))

    # Attempt 2: PowerShell Set-AuthenticodeSignature fallback
    for attempt in range(3):
        try:
            ps_script = (
                f"Unblock-File -Path '{bin_path}' -ErrorAction SilentlyContinue; "
                f"$c = Get-Item 'Cert:\\CurrentUser\\My\\0DC93D5AC9D405D6459BF5A61B77A36874710C5E' -ErrorAction SilentlyContinue; "
                f"if (-not $c) {{ $c = (Get-ChildItem Cert:\\CurrentUser\\My | Where-Object Subject -like '*RustLocalDev*')[0] }} "
                f"if ($c) {{ "
                f"    Set-AuthenticodeSignature -FilePath '{bin_path}' -Certificate $c -HashAlgorithm SHA256 | Out-Null; "
                f"    $ver = Get-AuthenticodeSignature -FilePath '{bin_path}'; "
                f"    if ($ver.SignerCertificate) {{ exit 0 }} else {{ exit 1 }} "
                f"}} else {{ exit 2 }}"
            )
            p = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )
            if p.returncode == 0:
                return True
            time.sleep(0.2 * (attempt + 1))
        except Exception:
            time.sleep(0.2 * (attempt + 1))
    return False


def compile_rust_string(
    rust_source: str,
    output_bin_dir: Optional[str] = None,
    timeout: int = 30
) -> CompilationResult:
    """Compiles a Rust source string to an executable binary using rustc."""
    try:
        rustc = find_rustc()

        workspace_cache = Path(__file__).resolve().parent.parent / ".build_tmp"
        workspace_cache.mkdir(parents=True, exist_ok=True)
        
        if output_bin_dir:
            temp_dir = output_bin_dir
            cleanup_temp = False
        else:
            temp_dir = tempfile.mkdtemp(prefix="py2saferust_comp_", dir=str(workspace_cache))
            cleanup_temp = True

        src_file = Path(temp_dir) / "main.rs"
        bin_file = Path(temp_dir) / ("main.exe" if os.name == "nt" else "main")

        # Write Rust source and ensure file is completely closed
        with open(src_file, "w", encoding="utf-8") as f:
            f.write(rust_source)

        cmd = [
            rustc,
            "--error-format=json",
            str(src_file),
            "-o",
            str(bin_file)
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        all_diagnostics = parse_rustc_json(proc.stderr)
        errors = [d for d in all_diagnostics if d.level == "error"]
        warnings = [d for d in all_diagnostics if d.level == "warning"]

        success = proc.returncode == 0 and bin_file.exists()
        persisted_bin_path = str(bin_file) if success else None
        if success and persisted_bin_path:
            _sign_binary_if_windows(persisted_bin_path)

        return CompilationResult(
            success=success,
            returncode=proc.returncode,
            errors=errors,
            warnings=warnings,
            binary_path=persisted_bin_path,
            raw_output=proc.stderr + "\n" + proc.stdout
        )

    except subprocess.TimeoutExpired:
        return CompilationResult(
            success=False,
            returncode=-1,
            errors=[RustDiagnostic(code="TIMEOUT", message="rustc compilation timed out", level="error")],
            raw_output="rustc compilation timed out"
        )
    except Exception as e:
        return CompilationResult(
            success=False,
            returncode=-1,
            errors=[RustDiagnostic(code="EXCEPTION", message=str(e), level="error")],
            raw_output=str(e)
        )
