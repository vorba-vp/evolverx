# evolverx

Self‑evolving Python functions. Wrap a function with the `@evolving` decorator and, on the first failure, evolverx captures the call context, asks an LLM to synthesize a deterministic function body, validates it in a sandbox, and persists the implementation so future calls run as plain Python. If the function fails again later, it can re‑synthesize.

Status: experimental research prototype. Use in non‑critical environments, review generated code, and prefer running in sandboxes first.

## Installation

- Python 3.10+
- Clone this repo and install from source:

```powershell
pip install -e .
```

Set your LLM credentials and optional model:

- OPENAI_API_KEY must be set in your environment.
- EVOLVERX_OPENAI_MODEL can override the default model name (defaults to "gpt-5" in code; set this to a model your account supports for the Responses API).

## Quick start

Basic self‑evolving function:

```python
from evolverx.evolving import evolving, EvolverxConfig

@evolving(EvolverxConfig())
def add(x: float, y: float) -> float:
    """Return sum of two numbers."""
    raise NotImplementedError

print(add(1, 2))  # First call triggers LLM synthesis; future calls use cached code
```

With imports and automatic re‑synthesis on any error (similar to `examples/example_usage.py`):

```python
from evolverx.evolving import evolving, EvolverxConfig

@evolving(
    EvolverxConfig(allow_imports=("json", "time", "requests", "re"), auto_resynthesize_on_any_error=True)
)
def fetch_weather(url: str, params: dict) -> dict:
    """Return weather JSON for given url+params."""
    raise NotImplementedError

print(fetch_weather("https://httpbin.org/get", {"city": "Haifa"}))
```

## How it works

- Decorator `@evolving(config)` loads a cached implementation if present, else runs your function.
- On failure (`NotImplementedError` or any error if enabled), it prompts the LLM with signature, docstring, source, args/kwargs, and the error.
- The returned function body is normalized, imports are validated against an allowlist, and it runs in a sandbox with a timeout.
- If execution succeeds, the full function source is written under `.evolverx/cache` in your project and hot‑swapped into the running process.

## Cache and version control

- Default cache folder: `<project-root>/.evolverx/cache/` (resolved from the file that defines your function).
- Recommended `.gitignore` entry:

```
.evolverx/
```

If you want to commit generated code, set a tracked path: `EvolverxConfig(cache_dir="./evolved_functions")`.

## CLI: view diffs and manage cache

The package ships a small CLI `evolverx` to inspect changes and clean cache.

Install (from repo root):

```powershell
pip install -e .
```

Default cache location: `<project-root>/.evolverx/cache` unless overridden in `EvolverxConfig`.

### Show diffs

Print a unified diff to the console, or get paths to Markdown/HTML reports.

```powershell
# Show unified diff in console
evolverx show <module> <func> --show diff --cache-dir ".\.evolverx\cache"

# Show path to Markdown diff
evolverx show <module> <func> --show md --cache-dir ".\.evolverx\cache"

# Show path to HTML side-by-side diff
evolverx show <module> <func> --show html --cache-dir ".\.evolverx\cache"
```

Notes:
- When a function evolves while running a script (e.g., `python examples/example_usage.py`), the module name is usually `__main__`.
- Reports visually preserve the original decorator block so it’s clear the decorator remains, though the cached function file is undecorated.
- You can regenerate the report files at any time:

```powershell
evolverx show <module> <func> --regen --show html --cache-dir ".\.evolverx\cache"
```

### Discover available diffs

List diff files to see available `<module>__<func>` pairs:

```powershell
Get-ChildItem .\.evolverx\cache\diffs -Filter *.diff | Select-Object -ExpandProperty Name
```

### Clean cache

Remove cached functions and reports (all, module, or function scope):

```powershell
# Clean entire cache directory
evolverx clean --cache-dir ".\.evolverx\cache"

# Clean a module
evolverx clean --module "__main__" --cache-dir ".\.evolverx\cache"

# Clean a single function in a module
evolverx clean --module "__main__" --func "add" --cache-dir ".\.evolverx\cache"
```

Exit code is 0; the command prints how many files were removed.

## Configuration surface

Key options in `EvolverxConfig` (see `src/evolverx/types.py`):

- allow_imports: tuple of module names allowed in generated code (e.g., "json", "re", "requests").
- auto_resynthesize_on_any_error: if true, any runtime error triggers a new synthesis attempt.
- timeout_seconds: sandbox execution timeout per attempt.
- max_attempts: maximum synthesis attempts per call site.
- cache_dir: override where evolved functions are written.

## Safety notes

- Generated code is executed in a restricted sandbox with an import allowlist and a timeout; still, review outputs before trusting them.
- Network/domain allowlisting is planned; today imports gate which clients can be used, but you control them via `allow_imports`.
- Keep functions deterministic and side‑effect light for best results.

## License

Licensed under the **Apache License, Version 2.0**. You may not use this project except in compliance with the License. A copy is included in the `LICENSE` file and is also available at:

```
http://www.apache.org/licenses/LICENSE-2.0
```

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

### Legal / Generated Code Disclaimer
This library synthesizes function bodies using an LLM. Generated code may be incorrect, insecure, or unsuitable for production without review. You are responsible for:
- Verifying correctness, safety, and compliance with your policies.
- Ensuring prompts and arguments do not leak sensitive data.
- Auditing any generated logic before deployment.

By contributing, you agree that your contributions are licensed under the Apache-2.0 License and include the patent grant defined therein.