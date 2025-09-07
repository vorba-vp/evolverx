from __future__ import annotations
import pathlib
import types
from typing import Callable, Optional
import difflib
import datetime as _dt
import json
import shutil


def cache_path(module: str, func: str, base: pathlib.Path) -> pathlib.Path:
    safe_module = module.replace(".", "_")
    return base / f"{safe_module}__{func}.py"


def _original_path(module: str, func: str, base: pathlib.Path) -> pathlib.Path:
    safe_module = module.replace(".", "_")
    return base / "originals" / f"{safe_module}__{func}.py"


def _diff_path(module: str, func: str, base: pathlib.Path) -> pathlib.Path:
    safe_module = module.replace(".", "_")
    return base / "diffs" / f"{safe_module}__{func}.diff"


def _diff_md_path(module: str, func: str, base: pathlib.Path) -> pathlib.Path:
    safe_module = module.replace(".", "_")
    return base / "diffs" / f"{safe_module}__{func}.md"


def _diff_html_path(module: str, func: str, base: pathlib.Path) -> pathlib.Path:
    safe_module = module.replace(".", "_")
    return base / "diffs" / f"{safe_module}__{func}.html"


def _meta_path(module: str, func: str, base: pathlib.Path) -> pathlib.Path:
    safe_module = module.replace(".", "_")
    return base / "diffs" / f"{safe_module}__{func}.meta.json"


def write_cache(
    module: str,
    func: str,
    fn_src: str,
    base: pathlib.Path,
    original_src: Optional[str] = None,
) -> pathlib.Path:
    """Persist the evolved function and optional diff artifacts.

    Always writes the candidate implementation to <base>/<module>__<func>.py.
    If original_src is provided, also writes:
    - <base>/originals/<module>__<func>.py (the "before" snapshot)
    - <base>/diffs/<module>__<func>.diff (unified diff)
    - <base>/diffs/<module>__<func>.md (markdown with diff fenced)
    - <base>/diffs/<module>__<func>.html (HTML side-by-side diff)
    """
    base.mkdir(parents=True, exist_ok=True)
    p = cache_path(module, func, base)
    p.write_text(fn_src, encoding="utf-8")

    if original_src is not None:
        # Originals folder
        op = _original_path(module, func, base)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(original_src, encoding="utf-8")

        # Diffs folder
        dif_dir = (_diff_path(module, func, base)).parent
        dif_dir.mkdir(parents=True, exist_ok=True)

        # Text unified diff
        before_lines = (
            original_src.replace("\r\n", "\n")
            .replace("\r", "\n")
            .splitlines(keepends=True)
        )

        # For visualization: keep original decorator lines (if any) so reports don't suggest
        # the decorator was removed. The cached file itself remains undecorated by design.
        def _extract_decorator_block(src: str) -> list[str]:
            ls = src.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
            # find the def line
            def_idx = next(
                (i for i, ln in enumerate(ls) if ln.lstrip().startswith("def ")), None
            )
            if def_idx is None:
                return []
            # collect contiguous @-lines directly above the def line
            j = def_idx - 1
            decs: list[str] = []
            while j >= 0:
                if ls[j].lstrip().startswith("@"):
                    decs.append(ls[j])
                    j -= 1
                else:
                    break
            decs.reverse()
            return decs

        decor = _extract_decorator_block(original_src)
        after_body_lines = (
            fn_src.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
        )
        after_lines = (decor + after_body_lines) if decor else after_body_lines

        ts = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        diff_lines = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"before:{module}.{func}",
            tofile=f"after:{module}.{func}",
            fromfiledate=ts,
            tofiledate=ts,
            n=3,
        )
        diff_txt = "".join(diff_lines)
        _diff_path(module, func, base).write_text(diff_txt, encoding="utf-8")

        # Markdown diff
        md = [
            f"# evolverx diff for `{module}.{func}`",
            "",
            f"_Generated: {ts}_",
            "",
            "```diff",
            diff_txt,
            "```",
            "",
        ]
        _diff_md_path(module, func, base).write_text("\n".join(md), encoding="utf-8")

        # HTML diff (side-by-side)
        try:
            html = difflib.HtmlDiff(tabsize=4, wrapcolumn=120).make_file(
                before_lines,
                after_lines,
                fromdesc=f"before: {module}.{func}",
                todesc=f"after: {module}.{func}",
                context=True,
                numlines=3,
            )
            _diff_html_path(module, func, base).write_text(html, encoding="utf-8")
        except Exception:
            # HtmlDiff can occasionally fail on exotic input; ignore silently.
            pass

        # Metadata
        meta = {
            "module": module,
            "func": func,
            "safe_module": module.replace(".", "_"),
            "paths": {
                "cached": str(p),
                "original": str(_original_path(module, func, base)),
                "diff": str(_diff_path(module, func, base)),
                "diff_md": str(_diff_md_path(module, func, base)),
                "diff_html": str(_diff_html_path(module, func, base)),
            },
            "generated_utc": ts,
        }
        _meta_path(module, func, base).write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

    return p


def load_from_cache(func: Callable, base: pathlib.Path) -> bool:
    p = cache_path(func.__module__, func.__name__, base)
    if not p.exists():
        return False
    ns: dict = {}
    code = compile(p.read_text(encoding="utf-8"), str(p), "exec")
    exec(code, ns, ns)
    candidate = ns.get(func.__name__)
    if isinstance(candidate, types.FunctionType):
        func.__code__ = candidate.__code__
        return True
    return False


def get_diff_paths(
    module: str, func: str, base: pathlib.Path
) -> dict[str, pathlib.Path]:
    """Return paths for cached file and diff artifacts (existence not guaranteed)."""
    return {
        "cached": cache_path(module, func, base),
        "original": _original_path(module, func, base),
        "diff": _diff_path(module, func, base),
        "diff_md": _diff_md_path(module, func, base),
        "diff_html": _diff_html_path(module, func, base),
    }


def get_diff_text(module: str, func: str, base: pathlib.Path) -> str | None:
    """Read the stored unified diff if present; if not, attempt to compute it from
    originals and cached files. Returns None if unavailable.
    """
    paths = get_diff_paths(module, func, base)
    dp = paths["diff"]
    if dp.exists():
        return dp.read_text(encoding="utf-8")

    # Attempt to compute on the fly (include decorator block for visualization)
    op = paths["original"]
    cp = paths["cached"]
    if not (op.exists() and cp.exists()):
        return None
    original_src = op.read_text(encoding="utf-8")
    cached_src = cp.read_text(encoding="utf-8")

    def _extract_decorator_block(src: str) -> list[str]:
        ls = src.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
        def_idx = next(
            (i for i, ln in enumerate(ls) if ln.lstrip().startswith("def ")), None
        )
        if def_idx is None:
            return []
        j = def_idx - 1
        decs: list[str] = []
        while j >= 0:
            if ls[j].lstrip().startswith("@"):
                decs.append(ls[j])
                j -= 1
            else:
                break
        decs.reverse()
        return decs

    before_lines = original_src.splitlines(keepends=True)
    decor = _extract_decorator_block(original_src)
    after_body_lines = cached_src.splitlines(keepends=True)
    after_lines = (decor + after_body_lines) if decor else after_body_lines
    diff_lines = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"before:{module}.{func}",
        tofile=f"after:{module}.{func}",
        n=3,
    )
    return "".join(diff_lines)


def regenerate_diff_artifacts(module: str, func: str, base: pathlib.Path) -> bool:
    """Regenerate diff, markdown, and HTML artifacts from the current cached and original files.
    Returns True if regenerated, False if required files are missing.
    """
    op = _original_path(module, func, base)
    cp = cache_path(module, func, base)
    if not (op.exists() and cp.exists()):
        return False

    original_src = op.read_text(encoding="utf-8")
    cached_src = cp.read_text(encoding="utf-8")

    # Decorator-preserving after lines
    def _extract_decorator_block(src: str) -> list[str]:
        ls = src.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
        def_idx = next(
            (i for i, ln in enumerate(ls) if ln.lstrip().startswith("def ")), None
        )
        if def_idx is None:
            return []
        j = def_idx - 1
        decs: list[str] = []
        while j >= 0:
            if ls[j].lstrip().startswith("@"):
                decs.append(ls[j])
                j -= 1
            else:
                break
        decs.reverse()
        return decs

    before_lines = (
        original_src.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    )
    decor = _extract_decorator_block(original_src)
    after_body_lines = (
        cached_src.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    )
    after_lines = (decor + after_body_lines) if decor else after_body_lines

    ts = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # Ensure dirs exist
    (_diff_path(module, func, base)).parent.mkdir(parents=True, exist_ok=True)

    diff_lines = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"before:{module}.{func}",
        tofile=f"after:{module}.{func}",
        fromfiledate=ts,
        tofiledate=ts,
        n=3,
    )
    diff_txt = "".join(diff_lines)
    _diff_path(module, func, base).write_text(diff_txt, encoding="utf-8")

    md = [
        f"# evolverx diff for `{module}.{func}`",
        "",
        f"_Generated: {ts}_",
        "",
        "```diff",
        diff_txt,
        "```",
        "",
    ]
    _diff_md_path(module, func, base).write_text("\n".join(md), encoding="utf-8")

    try:
        html = difflib.HtmlDiff(tabsize=4, wrapcolumn=120).make_file(
            before_lines,
            after_lines,
            fromdesc=f"before: {module}.{func}",
            todesc=f"after: {module}.{func}",
            context=True,
            numlines=3,
        )
        _diff_html_path(module, func, base).write_text(html, encoding="utf-8")
    except Exception:
        pass

    # Write meta
    meta = {
        "module": module,
        "func": func,
        "paths": {
            "cached": str(cp),
            "original": str(op),
            "diff": str(_diff_path(module, func, base)),
            "diff_md": str(_diff_md_path(module, func, base)),
            "diff_html": str(_diff_html_path(module, func, base)),
        },
        "generated_utc": ts,
    }
    _meta_path(module, func, base).write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return True


def clean_cache(
    base: pathlib.Path, module: str | None = None, func: str | None = None
) -> int:
    """Clean cache files and diff artifacts.

    - If module and func provided: remove artifacts for that function.
    - If only module provided: remove artifacts for all functions in that module.
    - If neither provided: remove entire cache directory.

    Returns the number of files removed.
    """
    removed = 0
    if not base.exists():
        return 0

    if module and func:
        # precise removal
        targets = [
            cache_path(module, func, base),
            _original_path(module, func, base),
            _diff_path(module, func, base),
            _diff_md_path(module, func, base),
            _diff_html_path(module, func, base),
            _meta_path(module, func, base),
        ]
        for p in targets:
            if p.exists():
                try:
                    p.unlink()
                    removed += 1
                except Exception:
                    pass
        # Optionally prune empty directories
        for d in [base / "diffs", base / "originals", base]:
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                except Exception:
                    pass
        return removed

    safe_module = module.replace(".", "_") if module else None

    if module and not func:
        # remove all functions for the module by globbing cached file names
        for p in base.glob(f"{safe_module}__*.py"):
            name = p.stem  # <safe_module>__<func>
            if "__" not in name:
                continue
            func_name = name.split("__", 1)[1]
            removed += clean_cache(base, module, func_name)
        return removed

    # neither module nor func: delete entire cache directory
    # Count files first
    try:
        for p in base.rglob("*"):
            if p.is_file():
                removed += 1
        shutil.rmtree(base, ignore_errors=True)
    except Exception:
        pass
    return removed


# TODO: source editing via libcst (future work)
