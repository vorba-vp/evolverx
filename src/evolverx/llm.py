from __future__ import annotations
import os
import openai  # type: ignore
from openai import OpenAI  # type: ignore


class LLMClient:
    """OpenAI-backed generator that returns ONLY the function body text."""

    def __init__(self, *, model: str | None = None, temperature: float = 0.0):
        self.model = model or os.getenv("EVOLVERX_OPENAI_MODEL", "gpt-5")
        self.temperature = float(os.getenv("EVOLVERX_TEMPERATURE", str(temperature)))
        self._client = OpenAI()

    def generate_function_body(self, prompt: str) -> str:
        print(f"LLM involved. The prompt is:\n{prompt}\n---")
        system = (
            "You write minimal, deterministic Python function BODIES only. "
            "Return raw code text without fences, without leading 'def'. "
        )

        request_args = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }

        # Try with temperature first; if the model rejects it, retry without.
        use_temperature = True
        resp = None
        try:
            resp = self._client.responses.create(
                **(
                    {**request_args, "temperature": self.temperature}
                    if use_temperature
                    else request_args
                )
            )
        except Exception as e:
            # Some models don't support 'temperature' on the /responses API.
            # Detect OpenAI BadRequestError and retry without temperature.
            if isinstance(
                e, openai.BadRequestError
            ) or "Unsupported parameter: 'temperature'" in str(e):
                resp = self._client.responses.create(**request_args)
            else:
                raise

        try:
            out = resp.output[0].content[0].text  # type: ignore[attr-defined]
        except Exception:
            try:
                out = resp.output_text  # type: ignore[attr-defined]
            except Exception:
                out = str(resp)

        out = out.strip()
        if out.startswith("```"):
            out = out.strip("`\n")
            if out.startswith("python\n"):
                out = out[len("python\n") :]
        result = out.strip() + ("\n" if not out.endswith("\n") else "")
        print(f"LLM produced function body:\n{result}")
        return result
