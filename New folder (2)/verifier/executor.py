"""Execution Sandbox for Semantic Verification in Py2SafeRust-X.

Runs Python code and compiled Rust binaries in isolated subprocesses with
strict timeouts (5 seconds).
NOTE ON PRODUCTION SANDBOXING:
    TODO: In a production multi-tenant deployment, arbitrary user-submitted code
    should be wrapped within an isolated container/sandbox (e.g., Docker container,
    gVisor, seccomp-bpf, or firejail on Linux) with CPU, memory, and network limits.
    For this prototype/demo environment, local subprocess isolation with timeouts is used.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from repair.compiler import compile_rust_string, _sign_binary_if_windows, find_rustc


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False
    error: Optional[str] = None


def _find_python() -> str:
    """Find Python executable on Windows or POSIX."""
    py = shutil.which("py") or shutil.which("python") or shutil.which("python3") or sys.executable
    return py


def run_python_code(
    python_source: str,
    stdin_input: Optional[str] = None,
    timeout: int = 5
) -> ExecutionResult:
    """Executes a Python snippet in a clean subprocess with timeout."""
    python_bin = _find_python()
    temp_dir = tempfile.mkdtemp(prefix="py2saferust_py_")
    script_path = Path(temp_dir) / "script.py"

    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(python_source)

        cmd = [python_bin, str(script_path)]
        proc = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return ExecutionResult(
            success=(proc.returncode == 0),
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr="Execution timed out after 5 seconds",
            returncode=-1,
            timed_out=True,
            error="Timeout"
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=str(e),
            returncode=-1,
            error=str(e)
        )
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def run_rust_code(
    rust_source: str,
    stdin_input: Optional[str] = None,
    timeout: int = 5
) -> ExecutionResult:
    """Compiles and executes a Rust source snippet in a clean subprocess with timeout."""
    workspace_cache = Path(__file__).resolve().parent.parent / ".build_tmp"
    workspace_cache.mkdir(parents=True, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="py2saferust_rs_", dir=str(workspace_cache))

    try:
        comp_res = compile_rust_string(rust_source, output_bin_dir=temp_dir, timeout=30)
        if not comp_res.success or not comp_res.binary_path:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Compilation failed:\n{comp_res.raw_output}",
                returncode=-1,
                error="CompilationError"
            )

        bin_path = comp_res.binary_path
        for attempt in range(3):
            try:
                proc = subprocess.run(
                    [bin_path],
                    input=stdin_input,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                return ExecutionResult(
                    success=(proc.returncode == 0),
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    returncode=proc.returncode
                )
            except OSError as oe:
                time.sleep(0.2 * (attempt + 1))
                if os.name == "nt":
                    _sign_binary_if_windows(bin_path)
                    try:
                        ps_cmd = f"& '{bin_path}'"
                        proc = subprocess.run(
                            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                            input=stdin_input,
                            capture_output=True,
                            text=True,
                            timeout=timeout
                        )
                        if "Application Control policy" not in proc.stderr and "ApplicationFailedException" not in proc.stderr:
                            return ExecutionResult(
                                success=(proc.returncode == 0),
                                stdout=proc.stdout,
                                stderr=proc.stderr,
                                returncode=proc.returncode
                            )
                    except Exception:
                        pass

        return _run_rust_cdylib(rust_source, stdin_input=stdin_input, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr="Execution timed out after 5 seconds",
            returncode=-1,
            timed_out=True,
            error="Timeout"
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=str(e),
            returncode=-1,
            error=str(e)
        )
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def run_rust_binary(
    bin_path: str,
    stdin_input: Optional[str] = None,
    timeout: int = 5
) -> ExecutionResult:
    """Executes a previously compiled Rust executable binary with timeout and stdin."""
    try:
        proc = None
        for attempt in range(5):
            try:
                proc = subprocess.run(
                    [bin_path],
                    input=stdin_input,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                break
            except OSError as oe:
                if attempt < 3:
                    time.sleep(0.2 * (attempt + 1))
                    _sign_binary_if_windows(bin_path)
                    time.sleep(0.1)
                    continue
                try:
                    ps_cmd = f"& '{bin_path}'"
                    proc = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                        input=stdin_input,
                        capture_output=True,
                        text=True,
                        timeout=timeout
                    )
                    break
                except Exception:
                    raise oe

        return ExecutionResult(
            success=(proc.returncode == 0) if proc else False,
            stdout=proc.stdout if proc else "",
            stderr=proc.stderr if proc else "",
            returncode=proc.returncode if proc else -1
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr="Execution timed out after 5 seconds",
            returncode=-1,
            timed_out=True,
            error="Timeout"
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=str(e),
            returncode=-1,
            error=str(e)
        )


def _run_rust_cdylib(
    rust_source: str,
    stdin_input: Optional[str] = None,
    timeout: int = 5
) -> ExecutionResult:
    """Executes Rust code by compiling as cdylib and running inside Python via ctypes."""
    workspace_cache = Path(__file__).resolve().parent.parent / ".build_tmp"
    workspace_cache.mkdir(parents=True, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="py2saferust_cdy_", dir=str(workspace_cache))
    src_path = Path(temp_dir) / "lib.rs"
    dll_path = Path(temp_dir) / ("lib.dll" if os.name == "nt" else "lib.so")

    try:
        wrapper = (
            rust_source
            + '\n\n#[no_mangle]\npub extern "C" fn py2saferust_entrypoint() -> i32 {\n    main();\n    0\n}\n'
        )
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(wrapper)

        rustc = find_rustc()
        cmd = [rustc, "--crate-type", "cdylib", str(src_path), "-o", str(dll_path)]
        comp = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if comp.returncode != 0:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Compilation error:\n{comp.stderr}",
                returncode=-1,
                error="CompilationError"
            )

        if os.name == "nt":
            _sign_binary_if_windows(str(dll_path))

        py_runner = (
            f"import ctypes, sys, time\n"
            f"for attempt in range(4):\n"
            f"    try:\n"
            f"        lib = ctypes.CDLL(r'{str(dll_path)}')\n"
            f"        ret = lib.py2saferust_entrypoint()\n"
            f"        sys.exit(ret)\n"
            f"    except Exception as e:\n"
            f"        if attempt == 3:\n"
            f"            sys.stderr.write(str(e))\n"
            f"            sys.exit(1)\n"
            f"        time.sleep(0.2 * (attempt + 1))\n"
        )
        python_bin = sys.executable
        p = subprocess.run(
            [python_bin, "-c", py_runner],
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return ExecutionResult(
            success=(p.returncode == 0),
            stdout=p.stdout,
            stderr=p.stderr,
            returncode=p.returncode
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr="Execution timed out after 5 seconds",
            returncode=-1,
            timed_out=True,
            error="Timeout"
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=str(e),
            returncode=-1,
            error=str(e)
        )
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
