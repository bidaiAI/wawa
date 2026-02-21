"""
Service Sandbox — Two-layer validation for AI-generated service code.

Layer 1: AST static analysis
  - Reject forbidden imports (os, sys, subprocess, socket, ...)
  - Reject forbidden calls (eval, exec, open, ...)
  - Enforce allowlist imports (json, math, random, ...)
  - Verify required interface (async deliver + sync test_deliver)
  - Enforce code size limit

Layer 2: subprocess execution
  - Run test_deliver() in isolated child process
  - Restricted __builtins__ dict (no open/eval/exec in child namespace)
  - Linux: RLIMIT_AS (memory) + RLIMIT_CPU (CPU time)
  - Windows dev: asyncio timeout only (resource module unavailable)
  - Communication via stdin (code) / stdout (JSON result)

Used by: services/_registry.py during register_service()
"""

import ast
import sys
import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.constitution import IRON_LAWS

logger = logging.getLogger("mortal.services.sandbox")

# ── Forbidden import root names (Layer 1) ─────────────────────────────────────
FORBIDDEN_IMPORTS: frozenset = frozenset({
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "importlib", "ctypes", "mmap", "signal", "resource",
    "builtins",           # prevents __import__ via builtins
    "multiprocessing",    # process escape
    "threading",          # thread escape
    "_thread",            # low-level thread
    "pty", "tty", "termios",      # tty / Unix stream escape
    "fcntl", "pwd", "grp",        # Unix privilege escalation
    "pickle", "shelve",            # arbitrary code exec via deserialization
    "struct",             # binary memory manipulation
    "cffi", "cython",     # native code bridges
    "ast",                # prevents meta-programming attacks
})

# ── Forbidden call names (Layer 1 — bare names and attribute calls) ────────────
FORBIDDEN_CALLS: frozenset = frozenset({
    "eval", "exec", "compile",
    "__import__",     # dynamic import bypass
    "open",           # file system read or write
    "setattr", "delattr",
    "globals", "locals",    # live symbol table introspection
    "vars",
    # Note: getattr is NOT blocked — `obj.attr` style is safe.
    # Only bare `getattr(builtins, "open")` calls are a concern,
    # but builtins itself is blocked via FORBIDDEN_IMPORTS.
})

# ── Allowed standard library imports (explicit allowlist) ─────────────────────
ALLOWED_IMPORTS: frozenset = frozenset({
    "json", "math", "random", "datetime", "re", "hashlib",
    "base64", "collections", "itertools", "typing",
    "string", "textwrap", "functools", "dataclasses", "enum",
    "time",           # time.time(), time.sleep() — read-only time
    "logging",        # safe — goes to stdout/stderr
    "uuid",           # ID generation
    "urllib",         # urllib.parse only (URL parsing, not HTTP)
    "html",           # html.escape etc.
    "decimal",        # safe numeric type
    "fractions",      # safe
    "statistics",     # safe
    "copy",           # copy.copy / deepcopy — safe
    "pprint",         # safe formatting
    "abc",            # ABCMeta — safe
})


@dataclass
class SandboxResult:
    passed: bool
    error: Optional[str] = None
    output: str = ""
    failed_at_layer: int = 0   # 0 = not failed, 1 = AST, 2 = subprocess


def validate_service_code(code: str) -> tuple[bool, str]:
    """
    Layer 1: AST static analysis.

    Returns (is_valid, error_message).
    Fast, synchronous, zero external dependencies.
    """
    # ── Size check ─────────────────────────────────────────────────────────────
    if len(code.encode("utf-8")) > IRON_LAWS.SERVICE_CODE_MAX_BYTES:
        return False, (
            f"Code too large: {len(code.encode('utf-8'))} bytes "
            f"(max {IRON_LAWS.SERVICE_CODE_MAX_BYTES})"
        )

    # ── Syntax check ───────────────────────────────────────────────────────────
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"

    # ── Walk AST for forbidden patterns ────────────────────────────────────────
    for node in ast.walk(tree):

        # `import os`, `import os.path`
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    return False, f"Forbidden import: {alias.name}"
                if root not in ALLOWED_IMPORTS and not alias.name.startswith("services."):
                    return False, (
                        f"Import not in allowlist: {alias.name}. "
                        f"Allowed: {sorted(ALLOWED_IMPORTS)}"
                    )

        # `from os import path`, `from subprocess import run`
        if isinstance(node, ast.ImportFrom):
            module = (node.module or "")
            root = module.split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                return False, f"Forbidden import: from {module}"
            if root and root not in ALLOWED_IMPORTS and not module.startswith("services."):
                return False, (
                    f"Import not in allowlist: from {module}. "
                    f"Allowed: {sorted(ALLOWED_IMPORTS)}"
                )

        # Bare forbidden calls: eval(...), exec(...), open(...)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                return False, f"Forbidden call: {func.id}()"
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                return False, f"Forbidden attribute call: .{func.attr}()"

    # ── Required interface check ────────────────────────────────────────────────
    top_level: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:   # top-level only
                top_level[node.name] = node

    if "deliver" not in top_level:
        return False, "Missing required function: async def deliver(user_input, context)"

    if "test_deliver" not in top_level:
        return False, "Missing required function: def test_deliver()"

    deliver_node = top_level["deliver"]
    if not isinstance(deliver_node, ast.AsyncFunctionDef):
        return False, "deliver() must be async: async def deliver(user_input, context) -> str"

    test_node = top_level["test_deliver"]
    if isinstance(test_node, ast.AsyncFunctionDef):
        return False, "test_deliver() must be synchronous (not async def)"

    return True, ""


async def run_in_sandbox(code: str, service_id: str) -> SandboxResult:
    """
    Layer 2: Execute test_deliver() in an isolated child subprocess.

    The child script is passed via python -c (no temp files written).
    Service code is passed via stdin.
    Results are received as JSON via stdout.

    Timeout: IRON_LAWS.SERVICE_SANDBOX_TIMEOUT_SECONDS
    Memory limit (Linux only): IRON_LAWS.SERVICE_SANDBOX_MAX_MEMORY_MB
    """
    runner_script = _build_runner_script()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", runner_script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=code.encode("utf-8")),
                timeout=float(IRON_LAWS.SERVICE_SANDBOX_TIMEOUT_SECONDS),
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            await proc.wait()
            return SandboxResult(
                passed=False,
                error=f"Sandbox timeout after {IRON_LAWS.SERVICE_SANDBOX_TIMEOUT_SECONDS}s — "
                      f"possible infinite loop or blocking call in test_deliver()",
                failed_at_layer=2,
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0 and stdout_text:
            try:
                result = json.loads(stdout_text)
                if result.get("passed"):
                    return SandboxResult(
                        passed=True,
                        output=result.get("output", "test_deliver() passed"),
                    )
                else:
                    return SandboxResult(
                        passed=False,
                        error=result.get("error", "test_deliver() returned False"),
                        failed_at_layer=2,
                    )
            except json.JSONDecodeError:
                return SandboxResult(
                    passed=False,
                    error=f"Sandbox returned non-JSON stdout: {stdout_text[:300]}",
                    failed_at_layer=2,
                )
        else:
            # Non-zero exit or no stdout
            err_detail = stderr_text[:500] if stderr_text else f"Exit code {proc.returncode}, no output"
            return SandboxResult(
                passed=False,
                error=err_detail,
                failed_at_layer=2,
            )

    except FileNotFoundError:
        return SandboxResult(
            passed=False,
            error="Python interpreter not found for sandbox subprocess",
            failed_at_layer=2,
        )
    except Exception as e:
        logger.error(f"Sandbox execution error for service '{service_id}': {e}")
        return SandboxResult(
            passed=False,
            error=f"Sandbox internal error: {type(e).__name__}: {e}",
            failed_at_layer=2,
        )


def _build_runner_script() -> str:
    """
    Build the child process runner script as a string for python -c.

    Designed to:
    - Read service code from stdin (no disk artifacts)
    - Apply resource limits on Linux (silently skip on Windows)
    - Execute test_deliver() in a restricted namespace
    - Print JSON result to stdout

    The restricted __builtins__ dict removes open/eval/exec even as a
    second defense layer after AST scanning.
    """
    max_mb = IRON_LAWS.SERVICE_SANDBOX_MAX_MEMORY_MB
    timeout_s = IRON_LAWS.SERVICE_SANDBOX_TIMEOUT_SECONDS

    return f"""
import sys
import json

def _apply_limits():
    try:
        import resource
        mem_bytes = {max_mb} * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, ({timeout_s}, {timeout_s}))
    except Exception:
        pass  # Windows or unprivileged container — asyncio timeout is the backstop

_apply_limits()

code = sys.stdin.buffer.read().decode("utf-8", errors="replace")

_RESTRICTED_BUILTINS = {{
    "True": True, "False": False, "None": None,
    "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "frozenset": frozenset,
    "str": str, "int": int, "float": float, "bool": bool, "bytes": bytes,
    "abs": abs, "max": max, "min": min, "sum": sum, "round": round,
    "divmod": divmod, "pow": pow, "hash": hash, "id": id,
    "sorted": sorted, "reversed": reversed,
    "isinstance": isinstance, "issubclass": issubclass,
    "repr": repr, "print": print,
    "any": any, "all": all,
    "hasattr": hasattr, "callable": callable,
    "type": type, "object": object,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "AttributeError": AttributeError,
    "StopIteration": StopIteration, "RuntimeError": RuntimeError,
    "NotImplementedError": NotImplementedError, "AssertionError": AssertionError,
    "OverflowError": OverflowError, "ZeroDivisionError": ZeroDivisionError,
    "ImportError": ImportError, "NameError": NameError,
    "property": property, "staticmethod": staticmethod, "classmethod": classmethod,
    "super": super,
    "__name__": "__main__",
    "__build_class__": __build_class__,
    # Deliberately EXCLUDED: open, eval, exec, compile, __import__, getattr/setattr
}}

_ns = {{"__builtins__": _RESTRICTED_BUILTINS}}

try:
    exec(compile(code, "<service>", "exec"), _ns)
except Exception as e:
    print(json.dumps({{"passed": False, "error": f"Code exec failed: {{type(e).__name__}}: {{e}}"}}))
    sys.exit(1)

if "test_deliver" not in _ns:
    print(json.dumps({{"passed": False, "error": "test_deliver() not found after exec"}}))
    sys.exit(1)

try:
    result = _ns["test_deliver"]()
    if result is True or result is None:
        print(json.dumps({{"passed": True, "output": "test_deliver() passed"}}))
        sys.exit(0)
    else:
        print(json.dumps({{
            "passed": False,
            "error": f"test_deliver() returned {{result!r}} (expected True or None)"
        }}))
        sys.exit(1)
except Exception as e:
    print(json.dumps({{"passed": False, "error": f"test_deliver() raised {{type(e).__name__}}: {{e}}"}}))
    sys.exit(1)
"""
