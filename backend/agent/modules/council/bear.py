from backend.agent.modules.council.base import run_persona
from backend.llm.client import RunContext

NAME = "BearAnalyst"
PROMPT_FILE = "council_bear"


async def run(ctx: RunContext, shared_context: str):
    return await run_persona(ctx, NAME, PROMPT_FILE, shared_context)
