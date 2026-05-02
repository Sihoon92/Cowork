"""Subprocess-based execution of LLM-generated slide code."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


class CodeExecutionError(RuntimeError):
    def __init__(self, message: str, *, stderr: str = "", returncode: int = -1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def run_slide_code(
    code: str,
    slide_data: dict,
    output_path: Path,
    *,
    timeout: int = 30,
) -> Path:
    """Execute slide-generation code in a subprocess; return output_path on success."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        try:
            result = subprocess.run(
                [sys.executable, script_path, str(output_path)],
                input=json.dumps(slide_data).encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise CodeExecutionError(
                f"slide code timeout after {timeout}s",
                stderr=(e.stderr or b"").decode("utf-8", errors="replace"),
            )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if result.returncode != 0:
        raise CodeExecutionError(
            f"slide code exited with {result.returncode}",
            stderr=result.stderr.decode("utf-8", errors="replace"),
            returncode=result.returncode,
        )

    if not output_path.exists():
        raise CodeExecutionError(
            "slide code completed but output_path was not created",
            stderr=result.stderr.decode("utf-8", errors="replace"),
        )

    return output_path
