from __future__ import annotations
import multiprocessing as mp
import builtins
import types
from typing import Any


class SandboxError(RuntimeError):
    pass


def _runner(
    fn_src: str, fn_name: str, args: tuple, kwargs: dict, allow_imports: tuple[str, ...]
):
    safe_builtins = {
        "len": len,
        "range": range,
        "min": min,
        "max": max,
        "sum": sum,
        "isinstance": isinstance,
        "print": print,
        "enumerate": enumerate,
        "zip": zip,
        "all": all,
        "any": any,
        "map": map,
        "filter": filter,
        "dict": dict,
        "list": list,
        "set": set,
        "tuple": tuple,
        "float": float,
        "int": int,
        "str": str,
        "__build_class__": builtins.__build_class__,
        "__name__": "__sandbox__",
    }

    real_import = __import__

    def guarded_import(name, globals=None, locals=None, from_list=(), level=0):
        root = name.split(".")[0]
        if root not in allow_imports:
            raise SandboxError(f"Disallowed import: {root}")
        return real_import(name, globals, locals, from_list, level)

    safe_builtins["__import__"] = guarded_import

    _globals: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "__name__": "__sandbox__",
    }
    _locals: dict[str, Any] = {}

    code = compile(fn_src, "<evolverx>", "exec")
    exec(code, _globals, _locals)
    fn = _locals.get(fn_name) or _globals.get(fn_name)
    if not isinstance(fn, types.FunctionType):
        raise SandboxError("Function not compiled")
    return fn(*args, **kwargs)


def _sandbox_target(
    q: mp.Queue,
    fn_src: str,
    fn_name: str,
    args: tuple,
    kwargs: dict,
    allow_imports: tuple[str, ...],
):
    try:
        res = _runner(fn_src, fn_name, args, kwargs, allow_imports)
        q.put(("ok", res))
    except Exception as e:
        q.put(("err", repr(e)))


def exec_in_sandbox(
    fn_src: str,
    fn_name: str,
    args: tuple,
    kwargs: dict,
    *,
    allow_imports: tuple[str, ...],
    timeout: float,
):
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    p = ctx.Process(
        target=_sandbox_target, args=(q, fn_src, fn_name, args, kwargs, allow_imports)
    )
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join(1.0)
        raise SandboxError("Timeout")
    if q.empty():
        raise SandboxError("Sandbox process exited without result")
    status, payload = q.get()
    if status == "ok":
        return payload
    raise SandboxError(payload)
