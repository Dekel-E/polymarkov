"""LLMod.ai chat wrapper with per-request step capture (course requirement).

Every LLM call goes through RunContext.call_llm, which:
- requests JSON (response_format json_object when supported, else instructed),
- retries once on invalid JSON with a "return only valid JSON" nudge,
- appends {module, prompt: {system_prompt, user_prompt}, response} to steps,
- accumulates token usage for the runs table.

Tool (non-LLM) modules log via RunContext.add_tool_step so the steps trace
stays 1:1 with the architecture diagram.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from backend import config
from backend.agent.types import Step, StepPrompt

TOOL_SYSTEM_PROMPT = "N/A (deterministic tool)"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def is_configured() -> bool:
    return bool(config.LLMOD_API_KEY and config.LLMOD_BASE_URL)


@lru_cache(maxsize=1)
def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=config.LLMOD_API_KEY,
        base_url=config.LLMOD_BASE_URL,
        timeout=config.LLM_TIMEOUT_S,
        max_retries=config.LLM_MAX_RETRIES,
    )


def parse_json_response(text: str) -> Any:
    """Parse model output as JSON, tolerating markdown code fences."""
    return json.loads(_FENCE_RE.sub("", text.strip()).strip())


class RunContext:
    """Per-/api/execute state: ordered steps + token accounting."""

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.tokens_in = 0
        self.tokens_out = 0

    # -- tool steps ---------------------------------------------------------

    def add_tool_step(self, module: str, inputs: str, outputs: Any) -> None:
        self.steps.append(
            Step(
                module=module,
                prompt=StepPrompt(system_prompt=TOOL_SYSTEM_PROMPT, user_prompt=inputs),
                response=outputs,
            )
        )

    # -- LLM steps ----------------------------------------------------------

    async def _completion(self, system_prompt: str, messages: list[dict]) -> str:
        kwargs: dict[str, Any] = dict(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": system_prompt}, *messages],
        )
        try:
            resp = await _client().chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception as exc:
            # some OpenAI-compatible gateways reject response_format
            if "response_format" not in str(exc):
                raise
            resp = await _client().chat.completions.create(**kwargs)
        if resp.usage:
            self.tokens_in += resp.usage.prompt_tokens or 0
            self.tokens_out += resp.usage.completion_tokens or 0
        return resp.choices[0].message.content or ""

    async def call_llm(self, module: str, system_prompt: str, user_prompt: str) -> Any:
        """One captured LLM call returning parsed JSON. Raises on failure."""
        if not is_configured():
            raise RuntimeError(
                "LLM is not configured — set LLMOD_API_KEY and LLMOD_BASE_URL in .env"
            )
        messages = [{"role": "user", "content": user_prompt}]
        try:
            text = await self._completion(system_prompt, messages)
            try:
                parsed = parse_json_response(text)
            except json.JSONDecodeError:
                # one retry with an explicit nudge (course efficiency: max 1 retry)
                messages += [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": "Your previous reply was not valid JSON. "
                        "Return ONLY the valid JSON object, no prose, no code fences.",
                    },
                ]
                text = await self._completion(system_prompt, messages)
                parsed = parse_json_response(text)  # let it raise this time
        except Exception as exc:
            # keep the trace honest: a failed call is still a call the agent
            # made — record it before the caller decides how to degrade
            self.steps.append(
                Step(
                    module=module,
                    prompt=StepPrompt(system_prompt=system_prompt, user_prompt=user_prompt),
                    response={"error": f"{type(exc).__name__}: {exc}"},
                )
            )
            raise

        self.steps.append(
            Step(
                module=module,
                prompt=StepPrompt(system_prompt=system_prompt, user_prompt=user_prompt),
                response=parsed,
            )
        )
        return parsed


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Read a prompt file (single source of truth, also served by agent_info).
    Cached: prompts only change on deploy."""
    return (config.PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
