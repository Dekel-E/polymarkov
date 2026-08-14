import pytest

from backend import config
from backend.agent import pricing as pricing_mod
from backend.agent.types import MarketState, PricingResult
from backend.data import polymarket, supabase_client
from backend.llm.client import RunContext
from backend.sim import paper_broker


def make_market(**overrides) -> MarketState:
    defaults = dict(
        question="Test market?",
        slug="test-market",
        category="politics",
        yes_token_id="tok-yes",
        mid=0.50,
        best_bid=0.49,
        best_ask=0.51,
        spread=0.02,
        depth_at_ask_usd=10_000.0,
        volume24h=1_000_000.0,
    )
    defaults.update(overrides)
    return MarketState(**defaults)


def make_pricing(verdict="BUY_YES", size_pct=0.8, fair=0.60) -> PricingResult:
    return PricingResult(
        prior=0.5,
        fair=fair,
        fair_adj=fair,
        gross_edge_pts=fair - 0.5,
        half_spread=0.01,
        taker_fee=0.01,
        net_edge_pts=0.05,
        verdict=verdict,
        suggested_size_pct_bankroll=size_pct,
        resolution_risk="low",
    )


@pytest.fixture
def captured_positions(monkeypatch):
    rows: list[dict] = []

    def fake_insert(position: dict):
        rows.append(position)
        return "pos-123"

    monkeypatch.setattr(supabase_client, "insert_position", fake_insert)
    return rows


def mock_book(monkeypatch, bids=None, asks=None):
    async def fake_book(token_id):
        return {"bids": bids or [], "asks": asks or []}

    monkeypatch.setattr(polymarket, "get_order_book", fake_book)


# ---------------------------------------------------------------------------
# BUY_YES fill matches hand-computed VWAP / fee / slippage
# ---------------------------------------------------------------------------


async def test_buy_yes_fill_hand_computed(monkeypatch, captured_positions):
    # bankroll $10,000 * 0.8% = $80 against asks (0.50 x 100sh = $50, then 0.55)
    mock_book(monkeypatch, asks=[(0.50, 100.0), (0.55, 200.0)])
    ctx = RunContext()
    market = make_market()
    report = await paper_broker.execute_paper_trade(ctx, market, make_pricing(size_pct=0.8))

    assert report is not None
    expected_shares = 100.0 + 30.0 / 0.55
    expected_vwap = 80.0 / expected_shares
    expected_fee = config.FEE_RATE["politics"] * expected_vwap * (1 - expected_vwap) * expected_shares
    expected_slip_bps = (expected_vwap - 0.50) / 0.50 * 10_000

    assert report.size_usd == pytest.approx(80.0)
    assert report.vwap == pytest.approx(expected_vwap, abs=1e-6)
    assert report.fee_paid == pytest.approx(expected_fee, abs=1e-3)
    assert report.slippage_bps == pytest.approx(expected_slip_bps, abs=0.5)
    assert report.levels_consumed == 2
    assert report.position_id == "pos-123"

    # position row written with matching numbers
    assert len(captured_positions) == 1
    row = captured_positions[0]
    assert row["market_id"] == "test-market"
    assert row["side"] == "BUY_YES"
    assert row["entry_price"] == pytest.approx(expected_vwap, abs=1e-6)
    assert row["size_usd"] == pytest.approx(80.0)

    # PaperBroker appears as a tool step
    assert ctx.steps[-1].module == "PaperBroker"
    assert ctx.steps[-1].prompt.system_prompt.startswith("N/A")


# ---------------------------------------------------------------------------
# BUY_NO synthesizes the NO book from YES bids
# ---------------------------------------------------------------------------


async def test_buy_no_uses_inverted_bids(monkeypatch, captured_positions):
    # YES bids best-first: 0.45 then 0.40 -> NO asks: 0.55 then 0.60
    mock_book(monkeypatch, bids=[(0.45, 100.0), (0.40, 50.0)])
    ctx = RunContext()
    market = make_market()
    report = await paper_broker.execute_paper_trade(
        ctx, market, make_pricing(verdict="BUY_NO", size_pct=0.4, fair=0.40)
    )

    assert report is not None
    # $40 fills entirely at NO price 0.55 ($55 notional available)
    assert report.side == "BUY_NO"
    assert report.vwap == pytest.approx(0.55, abs=1e-6)
    assert report.levels_consumed == 1
    # slippage vs NO mid (1 - 0.50 = 0.50): (0.55-0.50)/0.50 = +1000 bps
    assert report.slippage_bps == pytest.approx(1000.0, abs=1.0)
    assert captured_positions[0]["side"] == "BUY_NO"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_pass_or_zero_size_returns_none(monkeypatch, captured_positions):
    mock_book(monkeypatch, asks=[(0.5, 100.0)])
    ctx = RunContext()
    assert await paper_broker.execute_paper_trade(ctx, make_market(), make_pricing(verdict="PASS")) is None
    assert await paper_broker.execute_paper_trade(ctx, make_market(), make_pricing(size_pct=0.0)) is None
    assert captured_positions == []
    assert ctx.steps == []


async def test_empty_book_reports_no_fill(monkeypatch, captured_positions):
    mock_book(monkeypatch)  # no levels at all
    ctx = RunContext()
    report = await paper_broker.execute_paper_trade(ctx, make_market(), make_pricing())
    assert report is None
    assert captured_positions == []
    assert ctx.steps[-1].module == "PaperBroker"
    assert ctx.steps[-1].response["filled"] is False


async def test_thin_book_partial_fill_flagged(monkeypatch, captured_positions):
    mock_book(monkeypatch, asks=[(0.50, 20.0)])  # only $10 resting; we want $80
    ctx = RunContext()
    report = await paper_broker.execute_paper_trade(ctx, make_market(), make_pricing(size_pct=0.8))
    assert report is not None
    assert report.size_usd == pytest.approx(10.0)  # filled what existed
    assert ctx.steps[-1].response["exhausted"] is True


def test_split_position_proportional():
    from backend.sim.paper_broker import split_position

    position = {"market_id": "m", "side": "BUY_YES", "entry_price": 0.4, "size_usd": 100.0, "fee_paid": 2.0}
    closed, remaining = split_position(position, 0.25)
    assert closed["size_usd"] == 25.0
    assert closed["fee_paid"] == 0.5
    assert closed["entry_price"] == 0.4
    assert remaining == {"size_usd": 75.0, "fee_paid": 1.5}
    # bounds are clamped
    closed_all, rem_all = split_position(position, 5.0)
    assert closed_all["size_usd"] == 100.0 and rem_all["size_usd"] == 0.0


def test_per_position_levels_override_percent_rules():
    from backend.sim.risk import evaluate_position

    risk = {"stop_loss_pct": 50, "take_profit_pct": 100}
    base = {"entry_price": 0.50, "size_usd": 100.0}
    # explicit SL level triggers even when % rule would not
    assert evaluate_position({**base, "sl_price": 0.45}, 0.44, risk) == "stop_loss"
    # explicit TP level
    assert evaluate_position({**base, "tp_price": 0.60}, 0.61, risk) == "take_profit"
    # explicit levels REPLACE the % rules: -52% but SL set lower -> hold
    assert evaluate_position({**base, "sl_price": 0.10}, 0.24, risk) is None
    # no explicit levels -> % rules still apply
    assert evaluate_position(base, 0.24, risk) == "stop_loss"


async def test_local_position_id_when_supabase_off(monkeypatch):
    mock_book(monkeypatch, asks=[(0.50, 1000.0)])
    monkeypatch.setattr(supabase_client, "insert_position", lambda p: None)
    ctx = RunContext()
    report = await paper_broker.execute_paper_trade(ctx, make_market(), make_pricing())
    assert report is not None
    assert report.position_id.startswith("local-")


async def test_paper_broker_trace_uses_configured_bankroll(monkeypatch, captured_positions):
    import copy

    settings = copy.deepcopy(config.DEFAULT_AGENT_SETTINGS)
    settings["funds"]["bankroll_usd"] = 12_345
    monkeypatch.setattr(supabase_client, "get_agent_settings", lambda: settings)
    mock_book(monkeypatch, asks=[(0.50, 1_000.0)])
    ctx = RunContext()

    report = await paper_broker.execute_paper_trade(
        ctx, make_market(), make_pricing(), size_usd=10.0
    )

    assert report is not None
    assert "bankroll $12,345.00" in ctx.steps[-1].prompt.user_prompt


# ---------------------------------------------------------------------------
# max_position_usd cap: autonomous directional fills only
# ---------------------------------------------------------------------------


@pytest.fixture
def small_cap(monkeypatch):
    """Agent settings with a tight max_position_usd."""
    import copy

    settings = copy.deepcopy(config.DEFAULT_AGENT_SETTINGS)
    settings["risk"]["max_position_usd"] = 40
    monkeypatch.setattr(supabase_client, "get_agent_settings", lambda: settings)
    return settings


async def test_cap_applies_to_autonomous_fill(monkeypatch, captured_positions, small_cap):
    mock_book(monkeypatch, asks=[(0.50, 1_000.0)])
    report = await paper_broker.execute_paper_trade(
        RunContext(), make_market(), make_pricing(size_pct=0.8), strategy="ai_signal"
    )  # Kelly wants $80; the desk cap is $40
    assert report is not None
    assert report.size_usd == pytest.approx(40.0)


async def test_cap_skips_manual_and_arbitrage(monkeypatch, captured_positions, small_cap):
    mock_book(monkeypatch, asks=[(0.50, 1_000.0)])
    manual = await paper_broker.execute_paper_trade(
        RunContext(), make_market(), make_pricing(), size_usd=80.0, strategy="manual"
    )
    arb = await paper_broker.execute_paper_trade(
        RunContext(), make_market(), make_pricing(), size_usd=80.0, strategy="arbitrage"
    )  # clamping one arb leg would break the hedge
    assert manual is not None and manual.size_usd == pytest.approx(80.0)
    assert arb is not None and arb.size_usd == pytest.approx(80.0)
