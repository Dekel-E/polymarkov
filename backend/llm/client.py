"""LLMod.ai chat wrapper with per-request step capture.

Every LLM call goes through RunContext.call_llm: it requests JSON, retries once
on invalid JSON, records every generated response (including repair attempts)
as a separate step, and tallies token usage.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from functools import lru_cache
from typing import Any

from backend import config
from backend.agent.types import Step, StepPrompt
from backend.llm import budget

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
    """Parse strict JSON model output, tolerating markdown code fences."""

    def reject_constant(value: str) -> None:
        raise json.JSONDecodeError(f"non-finite JSON number: {value}", value, 0)

    return json.loads(
        _FENCE_RE.sub("", text.strip()).strip(),
        parse_constant=reject_constant,
    )


class RunContext:
    """Per-/api/execute state: ordered steps + token accounting."""

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.tokens_in = 0
        self.tokens_out = 0
        # Per-step {kind, latency_ms, tokens_in, tokens_out}, index-aligned with
        # `steps`. Kept OFF the graded Step object (which must stay exactly
        # {module, prompt, response}); surfaced only via the GUI `ui` payload.
        self.step_metrics: list[dict] = []

    def add_tool_step(self, module: str, inputs: str, outputs: Any) -> None:
        self.steps.append(
            Step(
                module=module,
                prompt=StepPrompt(system_prompt=TOOL_SYSTEM_PROMPT, user_prompt=inputs),
                response=outputs,
            )
        )
        self.step_metrics.append(
            {"kind": "tool", "latency_ms": None, "tokens_in": 0, "tokens_out": 0}
        )

    async def _completion(self, system_prompt: str, messages: list[dict]) -> str:
        kwargs: dict[str, Any] = dict(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": system_prompt}, *messages],
        )

        async def _provider_request(**request_kwargs):
            # Reserve immediately before each paid request. This deliberately
            # lives below the logical-call layer so JSON retries and gateway
            # response_format fallbacks consume their own global quota slot.
            await asyncio.to_thread(budget.reserve, "chat")
            try:
                response = await _client().chat.completions.create(**request_kwargs)
            except Exception:
                await asyncio.to_thread(budget.record_usage, "chat", failed=True)
                raise
            usage = response.usage
            tokens_in = (usage.prompt_tokens or 0) if usage else 0
            tokens_out = (usage.completion_tokens or 0) if usage else 0
            await asyncio.to_thread(
                budget.record_usage,
                "chat",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            return response

        try:
            resp = await _provider_request(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception as exc:
            # some OpenAI-compatible gateways reject response_format
            if "response_format" not in str(exc):
                raise
            resp = await _provider_request(**kwargs)
        if resp.usage:
            self.tokens_in += resp.usage.prompt_tokens or 0
            self.tokens_out += resp.usage.completion_tokens or 0
        return resp.choices[0].message.content or ""

    async def call_llm(self, module: str, system_prompt: str, user_prompt: str) -> Any:
        """Run one logical module call and trace every completion attempt."""
        if not is_configured():
            raise RuntimeError(
                "LLM is not configured — set LLMOD_API_KEY and LLMOD_BASE_URL in .env"
            )
        messages = [{"role": "user", "content": user_prompt}]

        async def _attempt(trace_user_prompt: str) -> tuple[str, dict]:
            t0 = time.monotonic()
            tin0, tout0 = self.tokens_in, self.tokens_out
            try:
                text = await self._completion(system_prompt, messages)
            except Exception as exc:
                metric = {
                    "kind": "llm",
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "tokens_in": self.tokens_in - tin0,
                    "tokens_out": self.tokens_out - tout0,
                }
                self.steps.append(
                    Step(
                        module=module,
                        prompt=StepPrompt(
                            system_prompt=system_prompt,
                            user_prompt=trace_user_prompt,
                        ),
                        response={"error": f"{type(exc).__name__}: {exc}"},
                    )
                )
                self.step_metrics.append(metric)
                raise
            metric = {
                "kind": "llm",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "tokens_in": self.tokens_in - tin0,
                "tokens_out": self.tokens_out - tout0,
            }
            return text, metric

        text, metric = await _attempt(user_prompt)
        try:
            parsed = parse_json_response(text)
        except json.JSONDecodeError as first_error:
            self.steps.append(
                Step(
                    module=module,
                    prompt=StepPrompt(system_prompt=system_prompt, user_prompt=user_prompt),
                    response={
                        "error": f"invalid JSON: {first_error.msg}",
                        "raw_response": text,
                    },
                )
            )
            self.step_metrics.append(metric)

            repair_instruction = (
                "Your previous reply was not valid JSON. Return ONLY the valid "
                "JSON object, no prose, no code fences."
            )
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": repair_instruction},
            ]
            retry_trace = (
                f"{user_prompt}\n\n--- PREVIOUS ASSISTANT RESPONSE (INVALID JSON) ---\n"
                f"{text}\n\n--- REPAIR INSTRUCTION ---\n{repair_instruction}"
            )
            retry_text, retry_metric = await _attempt(retry_trace)
            try:
                parsed = parse_json_response(retry_text)
            except json.JSONDecodeError as retry_error:
                self.steps.append(
                    Step(
                        module=module,
                        prompt=StepPrompt(
                            system_prompt=system_prompt,
                            user_prompt=retry_trace,
                        ),
                        response={
                            "error": f"invalid JSON: {retry_error.msg}",
                            "raw_response": retry_text,
                        },
                    )
                )
                self.step_metrics.append(retry_metric)
                raise

            self.steps.append(
                Step(
                    module=module,
                    prompt=StepPrompt(
                        system_prompt=system_prompt,
                        user_prompt=retry_trace,
                    ),
                    response=parsed,
                )
            )
            self.step_metrics.append(retry_metric)
            return parsed

        self.steps.append(
            Step(
                module=module,
                prompt=StepPrompt(system_prompt=system_prompt, user_prompt=user_prompt),
                response=parsed,
            )
        )
        self.step_metrics.append(metric)
        return parsed


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Read a prompt file. Cached; prompts only change on deploy."""
    return (config.PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
