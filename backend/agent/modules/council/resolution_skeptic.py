from backend.agent.modules.council.base import run_persona
from backend.llm.client import RunContext

NAME = "ResolutionSkeptic"
PROMPT_FILE = "council_resolution_skeptic"


async def run(ctx: RunContext, shared_context: str):
    return await run_persona(ctx, NAME, PROMPT_FILE, shared_context)
