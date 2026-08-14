"""Render the canonical Polymarkov architecture diagram.

Usage:
    python -m scripts.gen_architecture_png

The diagram is deliberately generated from code so module names remain
reviewable in git. ``DIAGRAM_MODULES`` is checked against the canonical agent
registry before the PNG is written.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

from backend import config
from backend.agent.registry import MODULES


# Canvas and palette ---------------------------------------------------------

WIDTH, HEIGHT = 180, 112
BG = "#070B11"
SECTION_BG = "#0B111A"
CARD = "#101925"
CARD_ALT = "#0D151F"
INK = "#EDF3F8"
SOFT = "#B1BECC"
DIM = "#75869A"
GRID = "#233143"
LLM = "#F2B84B"
TOOL = "#78A9D6"
JOB = "#B18AE6"
STORE = "#36C59A"
EXTERNAL = "#657790"
IO = "#D8E3EC"

fig, ax = plt.subplots(figsize=(18, 11.2), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, WIDTH)
ax.set_ylim(0, HEIGHT)
ax.axis("off")
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)


# Drawing helpers ------------------------------------------------------------

def section(x: float, y: float, w: float, h: float, title: str) -> None:
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.5,rounding_size=1.2",
        facecolor=SECTION_BG, edgecolor=GRID, linewidth=1.25, zorder=0,
    )
    ax.add_patch(patch)
    ax.text(
        x + 2, y + h - 2.5, title, color=SOFT, fontsize=8.2,
        fontweight="bold", va="center", family="DejaVu Sans", zorder=4,
    )


def nested_section(x: float, y: float, w: float, h: float, title: str) -> None:
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.35,rounding_size=0.8",
        facecolor=CARD_ALT, edgecolor=GRID, linewidth=1.0,
        linestyle=(0, (4, 3)), zorder=0.5,
    )
    ax.add_patch(patch)
    ax.text(
        x + 1.5, y + h - 2.2, title, color=DIM, fontsize=7.2,
        fontweight="bold", va="center", family="DejaVu Sans", zorder=4,
    )


def color_for(kind: str) -> str:
    return {
        "llm": LLM,
        "tool": TOOL,
        "job": JOB,
        "store": STORE,
        "external": EXTERNAL,
        "io": IO,
    }[kind]


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    *,
    kind: str,
    sub: str = "",
    badge: str | None = None,
    title_size: float = 9.0,
    sub_size: float = 6.5,
    dashed: bool = False,
) -> tuple[float, float, float, float]:
    color = color_for(kind)
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.35,rounding_size=0.8",
        facecolor=CARD, edgecolor=color, linewidth=1.65,
        linestyle=(0, (4, 2.5)) if dashed else "solid", zorder=3,
    )
    ax.add_patch(patch)
    title_y = y + h / 2 + (1.05 if sub else 0)
    ax.text(
        x + w / 2, title_y, title, ha="center", va="center", color=INK,
        fontsize=title_size, fontweight="bold", linespacing=1.0,
        family="DejaVu Sans", zorder=4,
    )
    if sub:
        ax.text(
            x + w / 2, y + h / 2 - 1.4, sub, ha="center", va="center",
            color=DIM, fontsize=sub_size, linespacing=1.12,
            family="DejaVu Sans", zorder=4,
        )
    if badge:
        circle = Circle(
            (x + 1.5, y + h - 1.45), 0.9, facecolor=color,
            edgecolor=color, linewidth=0, zorder=5,
        )
        ax.add_patch(circle)
        ax.text(
            x + 1.5, y + h - 1.48, badge, ha="center", va="center",
            color=BG, fontsize=6.2, fontweight="bold",
            family="DejaVu Sans", zorder=6,
        )
    return (x, y, w, h)


def left(node: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, _w, h = node
    return (x - 0.25, y + h / 2)


def right(node: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = node
    return (x + w + 0.25, y + h / 2)


def top(node: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = node
    return (x + w / 2, y + h + 0.25)


def bottom(node: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, _h = node
    return (x + w / 2, y - 0.25)


def arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = SOFT,
    dashed: bool = False,
    width: float = 1.25,
    connection: str = "arc3,rad=0",
) -> None:
    patch = FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=11, color=color,
        linewidth=width, linestyle=(0, (4, 3)) if dashed else "solid",
        connectionstyle=connection, shrinkA=0, shrinkB=0, zorder=1.5,
    )
    ax.add_patch(patch)


def route(
    points: list[tuple[float, float]],
    *,
    color: str = SOFT,
    dashed: bool = False,
    width: float = 1.15,
) -> None:
    style = (0, (4, 3)) if dashed else "solid"
    for start, end in zip(points[:-2], points[1:-1]):
        ax.plot(
            [start[0], end[0]], [start[1], end[1]], color=color,
            linewidth=width, linestyle=style, solid_capstyle="round", zorder=1.25,
        )
    arrow(points[-2], points[-1], color=color, dashed=dashed, width=width)


def label(x: float, y: float, text: str, *, color: str = DIM, size: float = 6.4) -> None:
    ax.text(
        x, y, text, color=color, fontsize=size, ha="center", va="center",
        family="DejaVu Sans", zorder=4,
    )


# Header ---------------------------------------------------------------------

ax.text(
    3, 109.3, "POLYMARKOV  |  SYSTEM ARCHITECTURE", color=LLM,
    fontsize=17, fontweight="bold", family="DejaVu Sans",
)
ax.text(
    3, 106.5,
    "Prediction-market research and paper trading  |  code owns every numeric decision  |  paper only",
    color=DIM, fontsize=8.5, family="DejaVu Sans",
)

legend = [
    ("LLM module", LLM),
    ("deterministic tool", TOOL),
    ("background job", JOB),
    ("storage", STORE),
    ("external service", EXTERNAL),
]
for index, (name, color) in enumerate(legend):
    x = 105 + index * 14.2
    ax.add_patch(
        FancyBboxPatch(
            (x, 106.5), 1.5, 1.5,
            boxstyle="round,pad=0.1,rounding_size=0.2",
            facecolor=CARD, edgecolor=color, linewidth=1.5, zorder=3,
        )
    )
    ax.text(x + 2.1, 107.25, name, color=DIM, fontsize=6.3, va="center")


# A. Graded /api/execute path ------------------------------------------------

section(
    3, 19, 126, 85,
    "A  GRADED REQUEST PATH  |  POST /api/execute  |  exact response: {status, error, response, steps}",
)

gui = box(8, 92, 22, 7, "Web GUI", kind="io", sub="prompt + optional history")
planner = box(
    40, 92, 22, 7, "QueryPlanner", kind="llm",
    sub="scope + intent + market target", badge="1",
)
resolver = box(
    72, 92, 22, 7, "MarketResolver", kind="tool",
    sub="URL | search | vector fallback",
)
arrow(right(gui), left(planner))
arrow(right(planner), left(resolver))

nested_section(8, 57.5, 116, 30.5, "PARALLEL CONTEXT GATHERING  |  resolved market is shared once")
query_gen = box(
    10, 72, 17, 9, "SearchQuery\nGenerator", kind="llm",
    sub="targeted news +\nweb queries", badge="2", title_size=7.5, sub_size=6.0,
)
evidence = box(
    29, 72, 20, 9, "EvidenceRetriever", kind="tool",
    sub="retrieve | dedup | cluster\nread pages | precedents",
    title_size=8.0, sub_size=5.9,
)
social = box(
    51, 72, 16, 9, "SocialScanner", kind="tool",
    sub="comments | Bluesky\nReddit | velocity", title_size=7.4, sub_size=5.8,
)
cross = box(
    69, 72, 17, 9, "CrossVenue\nScanner", kind="tool",
    sub="conservative\nKalshi match", title_size=7.0, sub_size=5.7,
)
micro = box(
    88, 72, 16, 9, "Microstructure\nScanner", kind="tool",
    sub="book + price\nindicators", title_size=6.8, sub_size=5.7,
)
smart = box(
    106, 72, 16, 9, "SmartMoney\nScanner", kind="tool",
    sub="wallet flow +\nlarge prints", title_size=6.8, sub_size=5.7,
)

# One arrow into the gathering lane communicates fan-out without a web of
# repeated edges. SearchQueryGenerator's output relationship is explicit.
arrow(bottom(resolver), (83, 88.25), color=TOOL)
label(83, 85.7, "fan out with one shared MarketState", color=TOOL)
arrow(right(query_gen), left(evidence), color=LLM)

sentiment = box(
    39, 60.5, 28, 7, "SentimentScorer", kind="llm",
    sub="one batch over evidence + posts", badge="3",
)
arrow(bottom(evidence), top(sentiment), color=TOOL, connection="arc3,rad=0.12")
arrow(bottom(social), top(sentiment), color=TOOL, connection="arc3,rad=-0.12")

# Context bus: scored evidence plus the three deterministic market signals.
bus_y = 58.8
ax.plot([52.8, 114], [bus_y, bus_y], color=GRID, linewidth=1.35, zorder=1.2)
for node in (cross, micro, smart):
    center_x = node[0] + node[2] / 2
    ax.plot([center_x, center_x], [node[1], bus_y], color=GRID, linewidth=1.15, zorder=1.2)
arrow(bottom(sentiment), (52.8, bus_y), color=SOFT)
label(84, 60.0, "shared scored evidence + market signals", color=SOFT)

nested_section(12, 39.5, 110, 16, "COUNCIL  |  four concurrent calls on identical context")
bull = box(14, 42.3, 25, 8, "BullAnalyst", kind="llm", sub="strongest YES case", badge="4")
bear = box(41, 42.3, 25, 8, "BearAnalyst", kind="llm", sub="strongest NO case", badge="5")
quant = box(68, 42.3, 25, 8, "QuantAnalyst", kind="llm", sub="base rates + signals", badge="6")
skeptic = box(
    95, 42.3, 25, 8, "ResolutionSkeptic", kind="llm",
    sub="criteria + oracle risk", badge="7", title_size=8.2,
)
arrow((84, bus_y), (67, 55.8), color=SOFT)

pricing = box(
    17, 28.5, 26, 8, "PricingEngine", kind="tool",
    sub="fair value | costs | PASS gates | Kelly", title_size=8.5,
)
judge = box(
    50, 28.5, 26, 8, "Judge", kind="llm",
    sub="explains immutable code output", badge="8",
)
response = box(
    83, 28.5, 33, 8, "Response + steps[]", kind="io",
    sub="dossier + complete ordered trace", title_size=8.7,
)
paper = box(
    91, 20.6, 30, 5.2, "PaperBroker  (optional)", kind="tool",
    sub="walk live book | simulated fill", title_size=7.5, sub_size=5.8,
)

route([(67, 39.2), (67, 37.7), (30, 37.7), top(pricing)], color=SOFT)
arrow(right(pricing), left(judge))
arrow(right(judge), left(response))
route([bottom(pricing), (30, 23.2), (90.7, 23.2)], color=TOOL)
label(60, 24.3, "only when Trade: yes and verdict is not PASS", color=TOOL)
arrow(top(paper), bottom(response), color=TOOL, connection="arc3,rad=-0.08")


# B. Conversational endpoints ------------------------------------------------

section(133, 64, 44, 40, "B  CONVERSATIONAL LAYER  |  outside the graded 8-call path")
desk_chat = box(
    137, 91, 36, 8, "DeskChat", kind="llm",
    sub="/api/chat | routes questions + actions",
)
market_chat = box(
    137, 72, 17, 11, "MarketChat", kind="llm",
    sub="grounded Q&A\nfresh sources\ncitations", title_size=7.5, sub_size=5.8,
)
strategy_chat = box(
    156, 72, 17, 11, "StrategyChat", kind="llm",
    sub="desk control\npropose patch\ncode clamps", title_size=7.2, sub_size=5.8,
)
arrow(bottom(desk_chat), top(market_chat), color=LLM, connection="arc3,rad=0.22")
arrow(bottom(desk_chat), top(strategy_chat), color=LLM, connection="arc3,rad=-0.22")
label(155, 87.3, "market Q&A  |  portfolio facts  |  watch/trade  |  settings", color=SOFT)
label(155, 68.0, "May delegate to deterministic tools and the main pipeline.", color=DIM)


# C. Autonomous desk ---------------------------------------------------------

section(133, 19, 44, 41, "C  AUTONOMOUS DESK  |  explicitly scheduled; paper only")
runner = box(
    137, 49, 36, 7, "Autopilot | GitHub Actions", kind="job",
    sub="settings + halt + workload gates", title_size=8.0,
)
indexers = box(
    137, 39.5, 36, 7, "MarketIndexer | NewsIndexer | RedditIndexer", kind="job",
    sub="warm Supabase + Pinecone", title_size=6.7,
)
perception = box(
    137, 29.5, 17, 7, "Sentinel -> WorkAgenda", kind="job",
    sub="detect -> investigate", title_size=6.6, sub_size=5.7,
)
strategies = box(
    156, 29.5, 17, 7, "AI | Arb | Copy | MM", kind="job",
    sub="strategy cycles", title_size=6.6, sub_size=5.7,
)
operations = box(
    137, 21.2, 36, 5.5, "ManageRisk | ResolvePositions | Relations | Briefing",
    kind="job", sub="protect -> settle -> learn -> report",
    title_size=6.2, sub_size=5.5,
)
label(155, 47.8, "launches each group independently by cadence", color=JOB, size=5.7)


# D. Services and stores -----------------------------------------------------

section(3, 2, 174, 14, "D  DATA + MODEL SERVICES  |  used by request, chat, and scheduled jobs")
box(
    7, 5, 25, 7, "Polymarket APIs", kind="external",
    sub="Gamma | CLOB | Data", dashed=True,
)
box(
    35, 5, 39, 7, "Open evidence sources", kind="external",
    sub="GDELT | News | RSS | Wiki | web | social | Kalshi",
    dashed=True, title_size=8.0,
)
box(
    77, 5, 22, 7, "LLMod.ai", kind="external",
    sub="text + embeddings", dashed=True,
)
box(
    102, 5, 32, 7, "Supabase", kind="store",
    sub="research | book | runs | atomic LLM quota", title_size=8.5,
)
box(
    137, 5, 36, 7, "Pinecone", kind="store",
    sub="markets | news | precedents | social", title_size=8.5,
)


# Registry consistency and output -------------------------------------------

DIAGRAM_MODULES = {
    "QueryPlanner",
    "MarketResolver",
    "SearchQueryGenerator",
    "EvidenceRetriever",
    "SocialScanner",
    "SentimentScorer",
    "BullAnalyst",
    "BearAnalyst",
    "QuantAnalyst",
    "ResolutionSkeptic",
    "PricingEngine",
    "Judge",
    "PaperBroker",
    "MarketChat",
    "DeskChat",
    "StrategyChat",
    "CrossVenueScanner",
    "MicrostructureScanner",
    "SmartMoneyScanner",
    "MarketIndexer",
    "NewsIndexer",
    "RedditIndexer",
}
canonical_modules = {module["name"] for module in MODULES}
if DIAGRAM_MODULES != canonical_modules:
    missing = sorted(canonical_modules - DIAGRAM_MODULES)
    extra = sorted(DIAGRAM_MODULES - canonical_modules)
    raise RuntimeError(f"architecture module drift: missing={missing}, extra={extra}")

plt.savefig(config.ARCHITECTURE_PNG, facecolor=BG, dpi=160, pad_inches=0)
plt.close(fig)
print(f"wrote {config.ARCHITECTURE_PNG} ({len(DIAGRAM_MODULES)} canonical modules)")
