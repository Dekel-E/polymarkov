"""Render the architecture diagram PNG.

    python -m scripts.gen_architecture_png
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# desk palette
BG = "#0B1017"
PANEL = "#121A26"
LINE = "#33436b"
INK = "#E7EDF4"
DIM = "#8A98AB"
AMBER = "#F0B441"   # LLM modules
STEEL = "#7A9CC6"   # deterministic tools
TEAL = "#3EB48E"    # storage
GRAY = "#5A6880"    # externals

W, H = 15.5, 11.5
fig, ax = plt.subplots(figsize=(W, H), dpi=110)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")


def box(x, y, w, h, title, kind="tool", sub=None, dashed=False, title_size=11.5):
    color = {"llm": AMBER, "tool": STEEL, "store": TEAL, "ext": GRAY, "io": INK}[kind]
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.35,rounding_size=0.9",
        facecolor=PANEL, edgecolor=color,
        linewidth=1.8, linestyle=(0, (4, 2)) if dashed else "solid",
    )
    ax.add_patch(patch)
    cy = y + h / 2 + (0.9 if sub else 0)
    ax.text(x + w / 2, cy, title, ha="center", va="center",
            fontsize=title_size, fontweight="bold", color=INK, family="DejaVu Sans")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 1.6, sub, ha="center", va="center",
                fontsize=8, color=DIM, family="DejaVu Sans")
    return (x, y, w, h)


def arrow(a, b, color=DIM, style="-|>", lw=1.4, connection="arc3,rad=0.0", dashed=False):
    p = FancyArrowPatch(
        a, b, arrowstyle=style, color=color, linewidth=lw,
        connectionstyle=connection, mutation_scale=13,
        linestyle=(0, (4, 3)) if dashed else "solid",
    )
    ax.add_patch(p)


def bottom(b):  # noqa: E741
    x, y, w, h = b
    return (x + w / 2, y - 0.4)


def top(b):
    x, y, w, h = b
    return (x + w / 2, y + h + 0.4)


def left(b):
    x, y, w, h = b
    return (x - 0.4, y + h / 2)


def right(b):
    x, y, w, h = b
    return (x + w + 0.4, y + h / 2)


# title
ax.text(2, 97.5, "POLYMARKOV", fontsize=17, fontweight="bold", color=AMBER)
ax.text(2, 95.2, "pre-trade intelligence agent for Polymarket — one /api/execute run "
        "+ DeskChat (/api/chat) · MarketChat (/api/market/chat) · StrategyChat (/api/strategy/chat)",
        fontsize=9.5, color=DIM)
# legend
for i, (label, color) in enumerate([("LLM call", AMBER), ("deterministic tool", STEEL),
                                    ("storage", TEAL), ("external API", GRAY)]):
    x0 = 55 + i * 11.5
    ax.add_patch(FancyBboxPatch((x0, 96.2), 1.6, 1.6, boxstyle="round,pad=0.1",
                                facecolor=PANEL, edgecolor=color, linewidth=1.6))
    ax.text(x0 + 2.3, 97, label, fontsize=8, color=DIM, va="center")

# main pipeline (center column)
gui = box(28, 88, 20, 5, "Web GUI", kind="io", sub="POST /api/execute  {prompt, history}")
dc = box(3, 88, 22, 5, "DeskChat", kind="llm",
         sub="global chat · POST /api/chat\nroutes → MarketChat / portfolio / meta")
sc2 = box(3, 79.5, 22, 5, "StrategyChat", kind="llm",
          sub="desk control · POST /api/strategy/chat\ninstructions → settings patch (clamped by code)")
qp = box(28, 79.5, 20, 5, "QueryPlanner", kind="llm", sub="LLM #1 · intent, market query, entities")
mr = box(28, 71, 20, 5, "MarketResolver", kind="tool", sub="URL / text search / vector match")

er = box(14, 61, 20, 6, "EvidenceRetriever", kind="tool",
         sub="news search + web fallback,\ndedup · cluster ≤8 · read pages")
ss = box(36.5, 61, 17, 6, "SocialScanner", kind="tool", sub="comments + mention\nvelocity")
cvs = box(56, 61, 13.5, 6, "CrossVenueScanner", kind="tool", sub="same event on Kalshi", title_size=8.5)

sc = box(28, 52.5, 20, 5, "SentimentScorer", kind="llm", sub="LLM #2 · ONE batched call")

# council container
ax.add_patch(FancyBboxPatch((12, 39), 52, 10, boxstyle="round,pad=0.4,rounding_size=1.2",
                            facecolor="none", edgecolor=LINE, linewidth=1.2,
                            linestyle=(0, (5, 3))))
ax.text(38, 50.1, "COUNCIL — concurrent, identical context", fontsize=8.5, color=DIM, ha="center")
bull = box(13.5, 40.5, 11.5, 5.5, "BullAnalyst", kind="llm", sub="LLM #3", title_size=10)
bear = box(26.5, 40.5, 11.5, 5.5, "BearAnalyst", kind="llm", sub="LLM #4", title_size=10)
quant = box(39.5, 40.5, 11.5, 5.5, "QuantAnalyst", kind="llm", sub="LLM #5", title_size=10)
skep = box(52.5, 40.5, 11.0, 5.5, "ResolutionSkeptic", kind="llm", sub="LLM #6", title_size=9.5)

judge = box(28, 28.5, 20, 6.5, "Judge", kind="llm",
            sub="LLM #7 · deterministic pricing engine\ncomputes verdict/edge/size (code)")

out = box(15, 17.5, 22, 6, "Response + Steps", kind="io",
          sub="dossier markdown + full trace\n(every LLM call logged in order)")
pb = box(42, 17.5, 20, 6, "PaperBroker", kind="tool",
         sub="fills Kelly size on the live book\n(only when Trade: yes & not PASS)")

# pipeline arrows
arrow(bottom(gui), top(qp))
arrow(right(dc), left(gui), color=DIM, dashed=True, style="-")
arrow(bottom(qp), top(mr))
arrow(bottom(mr), (24, 67.4), connection="arc3,rad=0.2")
arrow(bottom(mr), (45, 67.4), connection="arc3,rad=-0.1")
arrow(bottom(mr), (62.5, 67.4), connection="arc3,rad=-0.3")
arrow((24, 61 - 0.4), top(sc), connection="arc3,rad=0.2")
arrow((45, 61 - 0.4), top(sc), connection="arc3,rad=-0.1")
arrow((62.5, 61 - 0.4), top(sc), connection="arc3,rad=-0.3")
arrow(bottom(sc), (38, 49.6))
arrow((38, 39 - 0.5), top(judge))
arrow(bottom(judge), top(out), connection="arc3,rad=0.12")
arrow(bottom(judge), top(pb), connection="arc3,rad=-0.12")

# externals (right column)
gamma = box(72, 79, 24, 6, "Polymarket Gamma + CLOB", kind="ext", dashed=True,
            sub="markets · order books · price history")
news = box(72, 69.5, 24, 6, "GDELT · Google News · RSS · Wiki · Web", kind="ext", dashed=True,
           sub="live headlines + page crawling", title_size=9)
soc = box(72, 60, 24, 6, "Comments · Bluesky · Reddit", kind="ext", dashed=True,
          sub="social posts")
llmod = box(72, 44, 24, 6, "LLMod.ai", kind="ext", dashed=True,
            sub="gpt-5.4-mini · text-embedding-3-small")
kalshi = box(72, 34.5, 24, 6, "Kalshi", kind="ext", dashed=True,
             sub="cross-venue odds (keyless search)")

# MarketChat sits on the externals spine (endpoint in sub text)
chat = box(72, 51.5, 24, 7, "MarketChat", kind="llm",
           sub="grounded Q&A · POST /api/market/chat\nplans → searches news + socials →\nindexes finds → answers with citations")

arrow(right(mr), left(gamma), color=GRAY, connection="arc3,rad=-0.15", dashed=True)
arrow((34.4, 65.5), (72 - 0.4, 72.5), color=GRAY, connection="arc3,rad=-0.1", dashed=True)
arrow(right(ss), left(soc), color=GRAY, connection="arc3,rad=-0.1", dashed=True)
arrow((64, 43.2), (72 - 0.4, 46.2), color=GRAY, dashed=True)
arrow((66.5, 60.6), (72 - 0.4, 38.5), color=GRAY, connection="arc3,rad=-0.15", dashed=True)
arrow(right(pb), (84, 17.5 + 3), color=GRAY, connection="arc3,rad=0.0", dashed=True)
# externals spine, split around the Kalshi + MarketChat boxes
arrow((84, 20.5), (84, 34.5 - 0.5), color=GRAY, dashed=True, style="-")
arrow((84, 40.5 + 0.5), (84, 51.5 - 0.5), color=GRAY, dashed=True, style="-")
arrow((84, 58.5 + 0.5), (84, 79 - 0.5), color=GRAY, dashed=True, style="-")

# storage + background jobs (bottom left)
store = box(4, 2.5, 38, 7, "Supabase + Pinecone", kind="store",
            sub="markets · articles · precedents · positions · runs\nvector namespaces: markets / news / precedents")
jobs = box(50, 2.5, 46, 7, "MarketIndexer · NewsIndexer · RedditIndexer", kind="store",
           sub="cron (Actions or local autopilot): markets + news + Reddit posts\nevery 2h, resolve positions daily → precedents")

arrow(right(jobs[0:1][0] and jobs), left(store) if False else (42.4, 6), color=TEAL, style="-|>")
arrow((23, 9.9), (18, 61 - 0.4), color=TEAL, connection="arc3,rad=0.25", dashed=True)
arrow((23, 9.9), (30, 28.1), color=TEAL, connection="arc3,rad=0.15", dashed=True, style="-")
ax.text(10, 11.2, "warm cache reads", fontsize=7.5, color=TEAL)
# StrategyChat writes agent_settings (read by every autonomous job)
arrow((8, 79.5 - 0.4), (8, 9.9), color=TEAL, dashed=True)
ax.text(8.7, 44, "agent_settings", fontsize=7.5, color=TEAL, rotation=90, va="center")

plt.tight_layout(pad=0.6)
OUT = r"c:\Users\admin1\Desktop\Coding\polymarkov\backend\assets\architecture.png"
plt.savefig(OUT, facecolor=BG, bbox_inches="tight")
print("wrote", OUT)
