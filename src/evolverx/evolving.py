from __future__ import annotations
import ast
import inspect
import textwrap
import pathlib
import traceback
import re
from typing import Callable, Any

from .types import EvolverxConfig
from .llm import LLMClient
from .persist import load_from_cache, write_cache
from .sandbox import exec_in_sandbox
from .telemetry import record_failure, reset_failures, get_failures


def evolving(config: EvolverxConfig | None = None):
    cfg = config or EvolverxConfig()
    llm = LLMClient()

    def outer(func: Callable):
        # Resolve default cache directory to the CONSUMER project's root (not inside this package):
        # <project-root>/.evolverx/cache
        cache_base = (
            pathlib.Path(cfg.cache_dir)
            if cfg.cache_dir
            else _default_cache_base_for(func)
        )
        load_from_cache(func, cache_base)

        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except NotImplementedError as e:
                return _evolve(
                    func,
                    args,
                    kwargs,
                    cfg,
                    llm,
                    cache_base,
                    reason="NotImplementedError",
                    err=e,
                )
            except Exception as e:
                if not cfg.auto_resynthesize_on_any_error:
                    raise
                return _evolve(
                    func,
                    args,
                    kwargs,
                    cfg,
                    llm,
                    cache_base,
                    reason=type(e).__name__,
                    err=e,
                )

        return wrapper

    return outer


def _evolve(
    func: Callable,
    args: tuple,
    kwargs: dict,
    cfg: EvolverxConfig,
    llm: LLMClient,
    cache_base: pathlib.Path,
    *,
    reason: str,
    err: Exception,
):
    attempts = record_failure(func.__module__, func.__name__)
    if attempts > cfg.max_attempts:
        raise err

    doc = (func.__doc__ or "").strip()
    src = _get_source(func)
    tb = "".join(traceback.format_exception_only(type(err), err)).strip()

    # Strengthen prompt after first failure to emphasize argument sanitization
    extra_hint = ""
    if attempts > 1:
        extra_hint = (
            "\nAdditionally, sanitize and normalize incoming arguments before use; "
            "for URL strings, strip whitespace, remove embedded newlines, collapse spaces, "
            "and ensure the path is valid.\n"
        )
    prompt = _build_prompt(
        func.__name__,
        str(inspect.signature(func)),
        doc,
        src,
        args,
        kwargs,
        tb + extra_hint,
        cfg,
    )
    body = llm.generate_function_body(prompt)
    body = _normalize_body(body)
    body = _ensure_imports(body, cfg.allow_imports)

    # First attempt: as-is
    fn_src = _wrap_as_function(func, body)
    try:
        ast.parse(fn_src)
    except (IndentationError, SyntaxError):
        # Second attempt: repair indentation once
        repaired = _repair_indentation(body)
        fn_src = _wrap_as_function(func, repaired)
        try:
            ast.parse(fn_src)
        except (IndentationError, SyntaxError) as e:
            # Give LLM another chance
            return _evolve(
                func, args, kwargs, cfg, llm, cache_base, reason=type(e).__name__, err=e
            )

    # Only validate imports after syntax is known to be correct
    _validate_imports(fn_src, cfg.allow_imports)

    try:
        result = exec_in_sandbox(
            fn_src,
            func.__name__,
            args,
            kwargs,
            allow_imports=cfg.allow_imports,
            timeout=cfg.timeout_seconds,
        )
    except Exception as e:
        # If sandboxed execution fails (e.g., HTTPError), give LLM another chance up to max_attempts
        if get_failures(func.__module__, func.__name__) >= cfg.max_attempts:
            raise
        return _evolve(
            func, args, kwargs, cfg, llm, cache_base, reason=type(e).__name__, err=e
        )

    # Persist candidate and diff artifacts
    write_cache(func.__module__, func.__name__, fn_src, cache_base, original_src=src)
    ns: dict[str, Any] = {}
    exec(compile(fn_src, "<evolverx>", "exec"), ns, ns)
    candidate = ns[func.__name__]
    func.__code__ = candidate.__code__

    reset_failures(func.__module__, func.__name__)
    return result


def _default_cache_base_for(func: Callable) -> pathlib.Path:
    """Determine a safe default cache directory in the consumer's project.
    Heuristic: start from the file containing `func`, walk up until we find a
    project marker (pyproject.toml, setup.cfg, setup.py, or .git), else fall back
    to the function's directory. Place cache under ".evolverx/cache".
    """
    # Best-effort resolution of the source file for the function.
    try:
        src_file = pathlib.Path(inspect.getsourcefile(func) or inspect.getfile(func))
    except Exception:
        # Fallback to current working directory if introspection fails
        return pathlib.Path.cwd() / ".evolverx" / "cache"

    if not src_file.exists():
        return pathlib.Path.cwd() / ".evolverx" / "cache"

    start = src_file.parent
    root = _find_project_root(start)
    return root / ".evolverx" / "cache"


def _find_project_root(start: pathlib.Path) -> pathlib.Path:
    markers = {"pyproject.toml", "setup.cfg", "setup.py", ".git"}
    cur = start
    while True:
        if any((cur / m).exists() for m in markers):
            return cur
        if cur.parent == cur:
            # Reached filesystem root
            return start
        cur = cur.parent


def _normalize_body(body: str) -> str:
    # Preserve internal indentation; only strip code fences and common leading/trailing blank lines.
    b = body.strip()
    if b.startswith("```") and b.endswith("```"):
        b = b.strip("`\n")
        if b.startswith("python\n"):
            b = b[len("python\n") :]
    # Normalize newlines
    b = b.replace("\r\n", "\n").replace("\r", "\n")

    b = textwrap.dedent(b)

    # Trim leading/trailing empty lines without touching indentation of non-empty lines
    lines = b.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _ensure_imports(body: str, allow: tuple[str, ...]) -> str:
    """If body references allowed modules (e.g., 'requests.') but forgot to import them,
    prepend 'import <module>' at the top of the function body."
    """
    lines = body.split("\n")
    src_no_str = body  # simple heuristic; we won't strip strings for brevity
    existing_imports = set()
    import_re = re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+)")
    from_re = re.compile(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\s+")
    for ln in lines:
        m = import_re.match(ln)
        if m:
            existing_imports.add(m.group(1).split(".")[0])
        m = from_re.match(ln)
        if m:
            existing_imports.add(m.group(1).split(".")[0])

    to_add = []
    for mod in allow:
        root = mod.split(".")[0]
        if root in existing_imports:
            continue
        token = root + "."
        if token in src_no_str:
            to_add.append(f"import {root}")

    if to_add:
        return "\n".join(to_add) + "\n" + body
    return body


def _repair_indentation(body: str) -> str:
    """Attempt a conservative indentation repair on a function body produced by an LLM.
    Strategy:
    - Strip leading/trailing blank lines
    - If the first non-empty line starts with indentation, remove its leading spaces from all lines
    - Ensure any block-introducing lines ending with ':' are followed by an indented line
    This is best-effort; we avoid altering relative indentation where possible.
    """
    # Normalize newlines
    b = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in b.split("\n")]
    # Trim surrounding empties
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""

    # Remove common leading indent if first non-empty line is indented
    first = lines[0]
    lead = len(first) - len(first.lstrip(" "))
    if lead > 0:
        lines = [
            ln[lead:] if ln.startswith(" " * lead) else ln.lstrip("\t") for ln in lines
        ]

    # Flatten unexpected indents: if a line increases indent without a preceding block opener
    def count_paren_delta(s: str) -> int:
        # crude but workable; ignores strings
        return (
            s.count("(")
            + s.count("[")
            + s.count("{")
            - s.count(")")
            - s.count("]")
            - s.count("}")
        )

    out: list[str] = []
    prev_sig: str | None = None
    bracket_depth = 0
    for ln in lines:
        stripped = ln.lstrip(" ")
        if not stripped:
            out.append(ln)
            continue
        indent = len(ln) - len(stripped)
        allow_indent = bracket_depth > 0 or (
            prev_sig is not None and prev_sig.rstrip().endswith(":")
        )
        if indent > 0 and not allow_indent:
            # flatten to baseline
            ln = stripped
        out.append(ln)
        bracket_depth += count_paren_delta(stripped)
        if stripped:
            prev_sig = stripped

    # If a block opener has no indented successor, indent the immediate next non-empty line
    fixed: list[str] = []
    i = 0
    while i < len(out):
        fixed.append(out[i])
        if out[i].rstrip().endswith(":"):
            # find next non-empty line
            j = i + 1
            while j < len(out) and not out[j].strip():
                j += 1
            if j < len(out):
                nxt = out[j]
                if len(nxt) == len(nxt.lstrip(" ")):
                    out[j] = " " * 4 + nxt
        i += 1
    return "\n".join(out)


def _build_prompt(
    name: str,
    signature: str,
    doc: str,
    src: str,
    args: tuple,
    kwargs: dict,
    tb: str,
    cfg: EvolverxConfig,
) -> str:
    return f"""
You are upgrading a Python function in-place.

Function: {name}{signature}
Docstring: {doc}

Original source:
{src}

Last error:
{tb}

Inputs:
args={args!r}, kwargs={kwargs!r}

Write ONLY the function BODY (no def line). Prefer stdlib. If you use third-party modules present in allowlist, you MUST import them explicitly at top of the body.
Allowed imports: {", ".join(cfg.allow_imports)}.
The implementation must be deterministic and side-effect minimal.
The error can be caused by the function body or by incorrect arguments.
If the error is in the function body, please fix it.
If the error is due to invalid data in the function's arguments, add code to the function body to correct the arguments. For example, if a URL contains extraneous characters, the code should clean up the URL string before using it.
""".strip()


def _wrap_as_function(func: Callable, body: str) -> str:
    try:
        sig = inspect.signature(func)
        params_txt = ", ".join([str(p) for p in sig.parameters.values()])
    except Exception:
        params_txt = "*args, **kwargs"
    return f"def {func.__name__}({params_txt}):\n" + _indent(body)


def _validate_imports(fn_src: str, allow: tuple[str, ...]):
    tree = ast.parse(fn_src)
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module.split(".")[0])
            mods.extend([alias.name.split(".")[0] for alias in node.names])
        elif isinstance(node, ast.Import):
            mods.extend([alias.name.split(".")[0] for alias in node.names])
        else:
            continue
        for m in mods:
            if m not in allow:
                raise RuntimeError(f"Disallowed import: {m}")


def _get_source(func) -> str:
    try:
        import inspect as _ins

        return _ins.getsource(func)
    except Exception:
        return f"def {func.__name__}(...):\n    raise NotImplementedError\n"


def _indent(s: str, n: int = 4) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else line for line in s.splitlines())
