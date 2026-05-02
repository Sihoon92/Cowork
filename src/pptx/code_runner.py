"""Subprocess-based execution of LLM-generated slide code."""
from __future__ import annotations

import ast
import builtins as _builtins
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from src.util import log

FixCallback = Callable[[str, str, dict], str]

# Names guaranteed available inside the executed script via the injected preamble,
# the standard main block, or standard builtins.
# `add_slide` is the contract function that the main block always calls — it may not
# be defined by every snippet (e.g. snippets that only raise for testing purposes),
# so we allow it here to avoid false positives on the caller side.
_PREAMBLE_NAMES = frozenset({
    "Presentation", "Inches", "Pt",
    "add_text", "add_rect", "add_line", "add_arrow", "add_image", "set_bg",
    "_json", "_sys",
    "add_slide",  # called by _STANDARD_MAIN_BLOCK; defined by user code
})

_BUILTIN_NAMES = frozenset(dir(_builtins))

_GUARANTEED_PREAMBLE = '''# --- guaranteed imports (injected) ---
from pptx import Presentation
from pptx.util import Inches, Pt
from src.pptx.primitives import (
    add_text, add_rect, add_line, add_arrow, add_image, set_bg,
)
import json as _json
import sys as _sys
# --- end injected ---
'''

_STANDARD_MAIN_BLOCK = '''

if __name__ == "__main__":
    data = _json.loads(_sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(_sys.argv[1])
'''


def ensure_main_block(code: str) -> str:
    """Ensure generated code has a complete __main__ entry block with prs.save.

    If the code already contains both ``if __name__`` and ``prs.save``, it is
    returned unchanged.  Otherwise any partial ``if __name__`` block is stripped
    and the standard entry block is appended.
    """
    if "if __name__" in code and "prs.save" in code:
        return code

    # Strip any existing (incomplete) if __name__ block before appending.
    lines = code.splitlines()
    trimmed: list[str] = []
    skip = False
    for line in lines:
        if line.strip().startswith("if __name__"):
            skip = True
        if skip:
            continue
        trimmed.append(line)
    base = "\n".join(trimmed)
    return base + _STANDARD_MAIN_BLOCK


def inject_preamble(code: str) -> str:
    """Prepend guaranteed imports so missing imports in LLM output don't crash.

    Python tolerates duplicate imports; this is cheaper than parsing the AST.
    """
    return _GUARANTEED_PREAMBLE + "\n" + code


def _collect_assign_targets(target: ast.AST, out: set[str]) -> None:
    """Recursively collect bound names from assignment targets."""
    if isinstance(target, ast.Name):
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_assign_targets(elt, out)
    elif isinstance(target, ast.Starred):
        _collect_assign_targets(target.value, out)
    # Attribute / Subscript targets bind nothing new at name level.


def _collect_defined_names(tree: ast.AST) -> set[str]:
    """Walk AST and collect every name that gets bound (def, assign, import, arg)."""
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                for arg in (
                    list(args.posonlyargs)
                    + list(args.args)
                    + list(args.kwonlyargs)
                ):
                    defined.add(arg.arg)
                if args.vararg:
                    defined.add(args.vararg.arg)
                if args.kwarg:
                    defined.add(args.kwarg.arg)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _collect_assign_targets(target, defined)
        elif isinstance(node, ast.AnnAssign) and node.target:
            _collect_assign_targets(node.target, defined)
        elif isinstance(node, ast.AugAssign):
            _collect_assign_targets(node.target, defined)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _collect_assign_targets(node.target, defined)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    _collect_assign_targets(item.optional_vars, defined)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                defined.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, ast.comprehension):
            _collect_assign_targets(node.target, defined)
        elif isinstance(node, ast.Lambda):
            args = node.args
            for arg in (
                list(args.posonlyargs)
                + list(args.args)
                + list(args.kwonlyargs)
            ):
                defined.add(arg.arg)
    return defined


def _validate_code(code: str) -> None:
    """Raise CodeExecutionError if *code* has a syntax error or obviously undefined names.

    This is a fast pre-flight check (microseconds) that avoids spawning a 30-second
    subprocess for clearly broken LLM output.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeExecutionError(
            f"SyntaxError: {exc.msg} at line {exc.lineno}",
            stderr=str(exc),
        )

    defined = _collect_defined_names(tree)
    allowed = defined | _PREAMBLE_NAMES | _BUILTIN_NAMES

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in allowed:
                raise CodeExecutionError(
                    f"undefined name likely: '{node.id}' at line {node.lineno}",
                    stderr=f"name '{node.id}' is not defined",
                )


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
    code = ensure_main_block(code)
    code = inject_preamble(code)
    _validate_code(code)  # short-circuit obviously broken code before spawning subprocess
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # required on Windows
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }

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


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.splitlines()[-lines:])


def render_slide_with_retry(
    code: str,
    slide_data: dict,
    output_path: Path,
    *,
    fix_callback: FixCallback,
    max_retries: int = 3,
    timeout: int = 30,
) -> Path:
    """Run slide code; on failure, ask fix_callback for a new full code and retry."""
    last_err: CodeExecutionError | None = None
    current_code = code
    attempts = 0
    while attempts <= max_retries:
        try:
            return run_slide_code(current_code, slide_data, output_path, timeout=timeout)
        except CodeExecutionError as e:
            last_err = e
            attempts += 1
            if attempts > max_retries:
                break
            log.warn(f"slide failed (attempt {attempts}), asking LLM to fix: {str(e)[:80]}")
            current_code = fix_callback(current_code, _tail(e.stderr or str(e)), slide_data)
    raise CodeExecutionError(
        f"slide rendering failed after {max_retries} retries",
        stderr=last_err.stderr if last_err else "",
    )
