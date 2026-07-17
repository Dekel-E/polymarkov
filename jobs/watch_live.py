"""Live watcher — the agent's real-time sense (persistent WebSocket daemon).

Subscribes to Polymarket's CLOB market channel for tracked + trending
markets and reacts in seconds instead of the hourly sentinel cadence:
- price jump >= LIVE_MOVE_PTS since we started watching -> agenda item
  (the hourly worker investigates; run `python -m jobs.work_agenda`
  locally for immediate action)
- best YES+NO asks violate $1 -> top-priority arbitrage agenda item
- mid drifts >= MM_REQUOTE_DRIFT from resting MM quotes -> immediate
  settle-and-requote cycle (only when market_making is enabled)

Runs until Ctrl+C; reconnects on drops; refreshes its watch set every
LIVE_REFRESH_MIN minutes. This process needs somewhere persistent to live
(your PC or a small VPS) — GitHub Actions can't hold a socket open.

Usage:
    python -m jobs.watch_live [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from backend import config
from backend.agent.pricing import taker_fee
from backend.data import polymarket, supabase_client

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class WatchState:
    """Everything the tick handlers need, testable without a socket."""

    def __init__(self) -> None:
        self.market_by_yes_token: dict[str, dict] = {}
        self.no_token_of: dict[str, str] = {}  # yes token -> no token
        self.baseline_price: dict[str, float] = {}  # asset -> price when watching began
        self.best_ask: dict[str, float] = {}  # asset -> best ask (both YES and NO tokens)
        self.mm_quoted: dict[str, float] = {}  # slug -> mid_at_placement
        self.last_mm_cycle = 0.0
        self.filed: dict[str, float] = {}  # slug -> ts of last agenda filing (cooldown)


def _price_of(payload: dict) -> Optional[float]:
    """Extract a current YES price from a ws event (pure)."""
    if payload.get("event_type") == "last_trade_price":
        try:
            return float(payload.get("price"))
        except (TypeError, ValueError):
            return None
    if payload.get("event_type") == "book":
        asks = payload.get("asks") or []
        bids = payload.get("bids") or []
        try:
            best_ask = min(float(a["price"]) for a in asks) if asks else None
            best_bid = max(float(b["price"]) for b in bids) if bids else None
        except (TypeError, ValueError, KeyError):
            return None
        if best_ask is not None and best_bid is not None:
            return (best_ask + best_bid) / 2
    return None


def _best_ask_of(payload: dict) -> Optional[float]:
    if payload.get("event_type") != "book":
        return None
    asks = payload.get("asks") or []
    try:
        return min(float(a["price"]) for a in asks) if asks else None
    except (TypeError, ValueError, KeyError):
        return None


def price_jump_item(market: dict, baseline: float, price: float) -> Optional[dict]:
    """Agenda item when the live price broke away from our baseline (pure)."""
    move = price - baseline
    if abs(move) < config.LIVE_MOVE_PTS:
        return None
    return {
        "market_id": market["slug"],
        "reason": f"LIVE: moved {move * 100:+.1f} pts in minutes (from {baseline:.2f})",
        "priority": round(70 + abs(move) * 100, 2),
    }


def spread_violation_item(market: dict, yes_ask: float, no_ask: float) -> Optional[dict]:
    """Agenda item when YES+NO asks price under $1 after fees (pure)."""
    cost = yes_ask + no_ask
    fees = taker_fee(market["category"], yes_ask) + taker_fee(market["category"], no_ask)
    profit = 1.0 - cost - fees
    if profit < config.ARB_MIN_EDGE:
        return None
    return {
        "market_id": market["slug"],
        "reason": f"LIVE: spread violation — YES {yes_ask} + NO {no_ask} = {cost:.3f}, {profit:.3f}/share free",
        "priority": round(90 + profit * 100, 2),
    }


async def build_watch_set(state: WatchState) -> list[str]:
    """Pick assets to watch: agent holdings + watchlist + top trending.
    Held/watched markets OUTSIDE the trending list are fetched explicitly —
    a position must never fall off the radar just because volume moved on."""
    markets = await polymarket.get_trending_markets(60)
    held = {p["market_id"] for p in supabase_client.get_open_positions()}
    watched = set(supabase_client.distinct_watched_market_ids())

    picked: list[dict] = []
    for m in markets:
        if not m["yes_token_id"] or not m["no_token_id"]:
            continue
        if m["slug"] in held or m["slug"] in watched or len(picked) < 40:
            picked.append(m)

    trending_slugs = {m["slug"] for m in picked}
    missing = (held | watched) - trending_slugs
    for slug in sorted(missing)[:20]:  # bounded: one Gamma call per market
        try:
            m = await polymarket.get_market(slug)
        except Exception:
            continue
        if m and m.get("active") and m.get("yes_token_id") and m.get("no_token_id"):
            picked.append(m)

    assets: list[str] = []
    for m in picked:
        state.market_by_yes_token[m["yes_token_id"]] = m
        state.no_token_of[m["yes_token_id"]] = m["no_token_id"]
        assets += [m["yes_token_id"], m["no_token_id"]]

    # remember which markets have resting MM quotes (for drift requotes)
    state.mm_quoted.clear()
    if supabase_client.is_configured():
        try:
            for q in (
                supabase_client.get_client()
                .table("mm_quotes")
                .select("market_id,mid_at_placement")
                .eq("status", "pending")
                .execute()
                .data
                or []
            ):
                if q.get("mid_at_placement") is not None:
                    state.mm_quoted[q["market_id"]] = float(q["mid_at_placement"])
        except Exception:
            pass
    return assets


def file_item(state: WatchState, item: dict, dry_run: bool) -> None:
    now = time.time()
    if now - state.filed.get(item["market_id"], 0) < 600:
        return  # 10-min cooldown per market
    state.filed[item["market_id"]] = now
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {item['reason']}  ({item['market_id'][:45]})")
    if not dry_run:
        supabase_client.add_agenda_items([item])


async def handle_event(state: WatchState, payload: dict, dry_run: bool) -> None:
    asset = payload.get("asset_id", "")

    ask = _best_ask_of(payload)
    if ask is not None:
        state.best_ask[asset] = ask

    market = state.market_by_yes_token.get(asset)
    if market is None:
        return  # NO-token events only update best_ask above

    price = _price_of(payload)
    if price is not None:
        baseline = state.baseline_price.setdefault(asset, price)
        item = price_jump_item(market, baseline, price)
        if item:
            file_item(state, item, dry_run)
            state.baseline_price[asset] = price  # re-arm from the new level

        # MM drift requote (rate-limited to one cycle per 5 min)
        quoted_mid = state.mm_quoted.get(market["slug"])
        from backend.sim.market_maker import needs_requote

        if quoted_mid is not None and needs_requote(price, quoted_mid) and time.time() - state.last_mm_cycle > 300:
            state.last_mm_cycle = time.time()
            print(f"  mid drifted on quoted {market['slug'][:40]} — requoting")
            if not dry_run:
                from jobs.market_maker import cycle

                await cycle(dry_run=False)

    yes_ask = state.best_ask.get(asset)
    no_ask = state.best_ask.get(state.no_token_of.get(asset, ""))
    if yes_ask is not None and no_ask is not None:
        item = spread_violation_item(market, yes_ask, no_ask)
        if item:
            file_item(state, item, dry_run)


async def run(dry_run: bool, seconds: Optional[int] = None) -> None:
    import websockets

    stop_at = time.time() + seconds if seconds else None
    while True:
        if stop_at and time.time() >= stop_at:
            print("bounded run complete")
            return
        state = WatchState()
        try:
            assets = await build_watch_set(state)
            print(f"watching {len(assets) // 2} markets ({len(assets)} tokens) — Ctrl+C to stop")
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                await ws.send(json.dumps({"assets_ids": assets, "type": "market"}))
                deadline = time.time() + config.LIVE_REFRESH_MIN * 60
                if stop_at:
                    deadline = min(deadline, stop_at)
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        continue  # quiet market — keep listening
                    data = json.loads(raw)
                    for payload in data if isinstance(data, list) else [data]:
                        await handle_event(state, payload, dry_run)
            print("refreshing watch set…")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"connection dropped ({exc}) — reconnecting in 10s")
            await asyncio.sleep(10)


def main() -> None:
    # daemons get piped/redirected — line-buffer so output is visible live
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print findings, file nothing")
    parser.add_argument("--seconds", type=int, default=None, help="bounded run (smoke tests)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.dry_run, args.seconds))
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
