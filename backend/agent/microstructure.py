"""Order-book microstructure + price technicals, computed deterministically.

Code does all the arithmetic here; the QuantAnalyst persona only *interprets*
the numbers. Everything degrades to None/0 on thin or missing data — a market
with an empty book still produces a valid (mostly-empty) indicator set.
"""

from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Optional

from backend.agent.types import MarketState

BAND_TIGHT = 0.02  # depth within 2c of mid
BAND_WIDE = 0.05   # depth within 5c of mid
RSI_PERIOD = 14


def _notional(levels: list[tuple[float, float]]) -> float:
    return sum(p * s for p, s in levels)


def _band_notional(levels: list[tuple[float, float]], lo: float, hi: float) -> float:
    return sum(p * s for p, s in levels if lo <= p <= hi)


def book_indicators(market: MarketState) -> dict:
    """Order-book shape: imbalance, micro-price, banded depth."""
    bids, asks = market.bids, market.asks
    out: dict = {
        "imbalance": None, "micro_price": None, "micro_vs_mid_pts": None,
        "bid_depth_2c_usd": 0.0, "ask_depth_2c_usd": 0.0,
        "bid_depth_5c_usd": 0.0, "ask_depth_5c_usd": 0.0,
        "total_bid_usd": round(_notional(bids), 2), "total_ask_usd": round(_notional(asks), 2),
    }
    if not bids or not asks:
        return out
    mid = market.mid
    out["bid_depth_2c_usd"] = round(_band_notional(bids, mid - BAND_TIGHT, mid + BAND_TIGHT), 2)
    out["ask_depth_2c_usd"] = round(_band_notional(asks, mid - BAND_TIGHT, mid + BAND_TIGHT), 2)
    out["bid_depth_5c_usd"] = round(_band_notional(bids, mid - BAND_WIDE, mid + BAND_WIDE), 2)
    out["ask_depth_5c_usd"] = round(_band_notional(asks, mid - BAND_WIDE, mid + BAND_WIDE), 2)

    # imbalance within the wide band: +1 all bids, -1 all asks
    b, a = out["bid_depth_5c_usd"], out["ask_depth_5c_usd"]
    if b + a > 0:
        out["imbalance"] = round((b - a) / (b + a), 3)

    # micro-price: depth-weighted mid that leans toward the thinner side
    (bp, bs), (ap, asz) = bids[0], asks[0]
    if bs + asz > 0:
        micro = (bp * asz + ap * bs) / (bs + asz)
        out["micro_price"] = round(micro, 4)
        out["micro_vs_mid_pts"] = round((micro - mid) * 100, 2)
    return out


def _returns(prices: list[float]) -> list[float]:
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices)) if prices[i - 1] > 0]


def _rsi(prices: list[float], period: int = RSI_PERIOD) -> Optional[float]:
    diffs = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    if len(diffs) < period:
        return None
    window = diffs[-period:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def price_technicals(market: MarketState) -> dict:
    """Trend/momentum/volatility from the 7-day price history."""
    hist = market.price_history_7d
    out: dict = {
        "momentum_24h_pts": None, "momentum_7d_pts": None, "volatility_pts": None,
        "trend": "flat", "rsi": None, "dist_from_high_pts": None, "dist_from_low_pts": None,
    }
    if len(hist) < 2:
        return out
    prices = [p for _, p in hist]
    last = prices[-1]
    out["momentum_7d_pts"] = round((last - prices[0]) * 100, 2)

    last_ts = hist[-1][0]
    day_ago = [p for ts, p in hist if ts <= last_ts - 86400]
    if day_ago:
        out["momentum_24h_pts"] = round((last - day_ago[-1]) * 100, 2)

    rets = _returns(prices)
    if rets:
        out["volatility_pts"] = round(pstdev(rets) * 100 * sqrt(len(rets)), 2) if len(rets) > 1 else 0.0

    n = len(prices)
    short = mean(prices[-max(2, n // 4):])
    long = mean(prices[-max(3, n // 2):])
    if short > long * 1.005:
        out["trend"] = "up"
    elif short < long * 0.995:
        out["trend"] = "down"
    out["rsi"] = _rsi(prices)

    hi, lo = max(prices), min(prices)
    out["dist_from_high_pts"] = round((hi - last) * 100, 2)
    out["dist_from_low_pts"] = round((last - lo) * 100, 2)
    return out


def compute(market: MarketState) -> dict:
    """All microstructure + technical indicators for one market."""
    ind = {**book_indicators(market), **price_technicals(market)}
    ind["spread_pct"] = round(market.spread / market.mid * 100, 2) if market.spread and market.mid else None
    ind["volume24h_usd"] = round(market.volume24h, 2)
    return ind


def summarize(ind: dict) -> str:
    """One compact human/LLM-readable line for the council context."""
    def g(k: str) -> str:
        v = ind.get(k)
        return "n/a" if v is None else f"{v:+.2f}" if isinstance(v, float) else str(v)

    parts = [
        f"imbalance {g('imbalance')} (>0 = bid/buy pressure)",
        f"micro-price vs mid {g('micro_vs_mid_pts')}pts",
        f"depth±5c bid ${ind.get('bid_depth_5c_usd', 0):,.0f} / ask ${ind.get('ask_depth_5c_usd', 0):,.0f}",
        f"spread {g('spread_pct')}%",
        f"24h mom {g('momentum_24h_pts')}pts, 7d mom {g('momentum_7d_pts')}pts",
        f"vol {g('volatility_pts')}pts, trend {ind.get('trend', 'flat')}, RSI {g('rsi')}",
    ]
    return " | ".join(parts)
