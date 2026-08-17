"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ActivityFeed from "@/components/ActivityFeed";
import AutomationStatus from "@/components/AutomationStatus";
import DeskBriefing from "@/components/DeskBriefing";
import DeskChat from "@/components/DeskChat";
import { executeArbitrage, fetchArbitrage, fetchSettings, updateSettings } from "@/lib/api";
import type { AgentSettings, ArbOpportunity } from "@/lib/types";

const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

const STRATEGY_CARDS: {
  key: keyof AgentSettings["strategies"];
  name: string;
  how: string;
  risk: string;
  available: boolean;
}[] = [
  {
    key: "arbitrage",
    name: "Arbitrage",
    how: "Looks for complete YES/NO or mutually exclusive outcome baskets priced below their $1 payout. Before recording a paper trade, it refreshes every book and requires the full basket to remain fillable.",
    risk: "Execution risk remains: stale or incomplete baskets are aborted with no positions recorded.",
    available: true,
  },
  {
    key: "ai_signal",
    name: "AI signal",
    how: "Runs the full research pipeline, then applies deterministic pricing rules. It trades only when estimated edge survives spread, modeled fees, and the safety margin.",
    risk: "Directional model risk; sizing uses quarter-Kelly and hard risk gates.",
    available: true,
  },
  {
    key: "copy_trading",
    name: "Copy trading",
    how: "Mirrors newly observed positions from followed wallets, scaled to our paper bankroll and capped at $100. Each source position is copied once; exits follow our risk rules.",
    risk: "Late-entry and source-selection risk; a copied wallet may already have changed its view.",
    available: true,
  },
  {
    key: "market_making",
    name: "Market making",
    how: "Simulates two-sided quotes on up to two eligible markets. Quotes fill only after a trade-through; inventory is capped and quoting stops within 72 hours of resolution.",
    risk: "Inventory and adverse-selection risk; one side can fill without the other.",
    available: true,
  },
  {
    key: "correlation",
    name: "Correlation graph",
    how: "An LLM proposes strict implication or exclusion links between similar markets. The scanner checks high-confidence links for pricing inconsistencies.",
    risk: "Not risk-free: projected profit depends on the inferred logical relationship being correct.",
    available: true,
  },
];

const RISK_FIELDS: { key: keyof AgentSettings["risk"]; label: string; hint: string }[] = [
  { key: "stop_loss_pct", label: "Stop-loss %", hint: "close a position losing this % of its stake" },
  { key: "take_profit_pct", label: "Take-profit %", hint: "close a position gaining this %" },
  { key: "max_position_usd", label: "Max position $", hint: "hard cap per trade" },
  { key: "max_open_positions", label: "Max open positions", hint: "AI signal stops opening past this" },
  { key: "daily_loss_halt_usd", label: "Daily loss halt $", hint: "circuit breaker: halt all strategies" },
];

function Toggle({ label, on, onChange, disabled }: { label: string; on: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${
        disabled ? "cursor-not-allowed bg-desk-line/50" : on ? "bg-instrument" : "bg-desk-line"
      }`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-desk-deep transition-all ${
          on && !disabled ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

export default function StrategiesPage() {
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [realizedToday, setRealizedToday] = useState(0);
  const [riskDraft, setRiskDraft] = useState<AgentSettings["risk"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [opps, setOpps] = useState<ArbOpportunity[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [executing, setExecuting] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchSettings()
      .then(({ settings: s, realized_today }) => {
        setSettings(s);
        setRiskDraft(s.risk);
        setRealizedToday(realized_today);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleStrategy(key: keyof AgentSettings["strategies"]) {
    if (!settings) return;
    const next = { ...settings.strategies, [key]: !settings.strategies[key] };
    setSettings({ ...settings, strategies: next });
    try {
      await updateSettings({ strategies: { [key]: next[key] } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      load();
    }
  }

  async function saveRisk() {
    if (!riskDraft) return;
    setSaving(true);
    setNote(null);
    try {
      const saved = await updateSettings({ risk: riskDraft });
      setSettings(saved);
      setRiskDraft(saved.risk);
      setNote("Risk rules saved. Manual and scheduled strategy runs now use them.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function resume() {
    try {
      const saved = await updateSettings({ halt: { active: false } });
      setSettings(saved);
      setNote("Trading resumed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function scan(fresh: boolean) {
    setScanning(true);
    setNote(null);
    try {
      const { opportunities } = await fetchArbitrage(fresh);
      setOpps(opportunities);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setScanning(false);
    }
  }

  async function execute(opp: ArbOpportunity) {
    setExecuting(opp.question);
    setNote(null);
    try {
      const reports = await executeArbitrage(opp);
      const filled = reports.filter((r) => r.filled).length;
      const failure = reports.find((r) => !r.filled)?.error;
      setNote(
        reports.length > 0 && filled === reports.length
          ? `Paper basket recorded: all ${filled} legs filled at refreshed prices.`
          : `Not executed: ${failure ?? "the complete basket could not be verified"}. No legs were recorded.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExecuting(null);
    }
  }

  return (
    <div className="desk-rise mx-auto max-w-5xl space-y-8 px-4 py-8 md:px-8">
      <header>
        <h1 className="font-display text-2xl font-bold uppercase tracking-wide md:text-3xl">
          Strategy <span className="text-instrument">Desk</span>
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-desk-dim">
          Configure paper-trading strategies, set their risk limits, and run scans by hand.
          Autonomous runs require the local autopilot or an enabled workflow schedule.
        </p>
      </header>

      <AutomationStatus />

      {settings?.halt.active && (
        <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-red-800 bg-red-950/40 p-4">
          <div className="flex-1">
            <div className="font-display text-sm font-bold uppercase tracking-wider text-red-300">
              Circuit breaker tripped
            </div>
            <div className="mt-0.5 text-xs text-red-300/80">
              {settings.halt.reason || "daily loss limit breached"} — no new trades until
              tomorrow or manual resume. Risk checks keep running.
            </div>
          </div>
          <button
            onClick={resume}
            className="rounded-xl border border-red-400/60 px-4 py-2 text-xs font-bold text-red-300 transition hover:bg-red-500/10"
          >
            Resume trading
          </button>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          {error}
          <button onClick={() => { setError(null); load(); }} className="ml-2 text-instrument hover:underline">
            Retry
          </button>
        </div>
      )}
      {note && (
        <div className="rounded-xl border border-desk-edge bg-desk-panel p-3 text-sm text-desk-ink">
          {note}
        </div>
      )}

      <DeskChat
        onApplied={(s) => {
          setSettings(s);
          setRiskDraft(s.risk);
          setNote("Settings updated by the agent on your instruction.");
        }}
      />

      <DeskBriefing />

      {/* strategies */}
      <section>
        <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide">Strategies</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {STRATEGY_CARDS.map((card) => {
            const enabled =
              card.available && settings
                ? settings.strategies[card.key as keyof AgentSettings["strategies"]]
                : false;
            return (
              <div
                key={card.key}
                className={`rounded-2xl border p-4 ${
                  card.available ? "border-desk-line bg-desk-panel/60" : "border-desk-line/50 bg-desk-panel/30"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className={`font-display text-base font-bold uppercase tracking-wide ${card.available ? "text-desk-ink" : "text-desk-faint"}`}>
                    {card.name}
                  </span>
                  {card.available ? (
                    <Toggle
                      label={`${enabled ? "Disable" : "Enable"} ${card.name}`}
                      on={enabled}
                      onChange={() => toggleStrategy(card.key as keyof AgentSettings["strategies"])}
                      disabled={!settings}
                    />
                  ) : (
                    <span className="rounded border border-desk-edge px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-desk-faint">
                      in development
                    </span>
                  )}
                </div>
                <p className={`mt-2 text-xs leading-relaxed ${card.available ? "text-desk-soft" : "text-desk-faint"}`}>
                  {card.how}
                </p>
                <p className="mt-1.5 font-mono text-[11px] text-desk-dim">{card.risk}</p>
              </div>
            );
          })}
        </div>
        <p className="mt-2 font-mono text-[11px] text-desk-faint">
          These switches configure strategies; they do not start a schedule. Autonomous runs require the local autopilot or an enabled GitHub workflow;
          copy trading mirrors wallets followed in the{" "}
          <Link href="/league" className="text-instrument hover:underline">Smart Money League</Link>.
        </p>
      </section>

      {/* risk console */}
      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-display text-lg font-bold uppercase tracking-wide">Risk console</h2>
          <span className="font-mono text-xs text-desk-dim">
            realized today:{" "}
            <span className={realizedToday < 0 ? "text-red-400" : "text-emerald-400"}>
              {realizedToday >= 0 ? "+" : ""}
              {usd(realizedToday)}
            </span>
          </span>
        </div>
        <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {RISK_FIELDS.map((f) => (
              <label key={f.key} className="block">
                <span className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">
                  {f.label}
                </span>
                <input
                  type="number"
                  value={riskDraft ? riskDraft[f.key] : ""}
                  onChange={(e) =>
                    riskDraft && setRiskDraft({ ...riskDraft, [f.key]: Number(e.target.value) })
                  }
                  className="mt-1 w-full rounded-xl border border-desk-line bg-desk-deep px-3 py-2 font-mono text-sm text-desk-ink focus:border-instrument/60 focus:outline-none"
                />
                <span className="mt-1 block text-[10px] leading-tight text-desk-faint">{f.hint}</span>
              </label>
            ))}
          </div>
          <button onClick={saveRisk} disabled={saving || !riskDraft} className="btn-primary mt-4">
            {saving ? "Saving…" : "Save risk rules"}
          </button>
        </div>
      </section>

      <ActivityFeed />

      {/* arbitrage scanner */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold uppercase tracking-wide">Arbitrage scanner</h2>
          <button
            onClick={() => scan(true)}
            disabled={scanning}
            className="rounded-xl border border-instrument/50 px-4 py-1.5 text-xs font-bold text-instrument transition hover:bg-instrument/10 disabled:opacity-40"
          >
            {scanning ? "Scanning books…" : "Scan now"}
          </button>
        </div>

        {opps === null && !scanning && (
          <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-5 text-sm text-desk-dim">
            Checks top markets for complete YES/NO baskets, mutually exclusive outcome baskets,
            and high-confidence logical-relation mismatches. Empty results are normal; a scan
            reports only baskets that clear the configured edge and liquidity checks.
          </div>
        )}
        {scanning && <div className="h-24 animate-pulse rounded-2xl bg-desk-panel" />}

        {opps !== null && !scanning && opps.length === 0 && (
          <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-5 text-sm text-desk-dim">
            No qualifying pricing violations were found at the current books.
          </div>
        )}

        {opps !== null && opps.length > 0 && (
          <div className="space-y-3">
            {opps.map((opp, i) => (
              <div key={i} className="rounded-2xl border border-emerald-800/50 bg-emerald-950/20 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="rounded bg-desk-deep px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-instrument">
                    {opp.type === "spread" ? "YES / NO basket" : opp.type === "dutch_book" ? "outcome basket" : "relation hedge"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold text-desk-ink">
                    {opp.question}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-desk-soft">
                  <span>cost {opp.cost_per_share}/share</span>
                  <span>fees {opp.fees_per_share}</span>
                  <span className="text-emerald-400">
                    profit {opp.profit_per_share}/share ({opp.roi_pct}%)
                  </span>
                  <span>
                    {opp.type === "correlation"
                      ? `projected ${usd(opp.guaranteed_profit_usd)} if the relation holds`
                      : `${usd(opp.guaranteed_profit_usd)} locked if fully filled`}
                  </span>
                  <span>{opp.legs.length} legs</span>
                </div>
                <button
                  onClick={() => execute(opp)}
                  disabled={executing !== null}
                  className="mt-3 rounded-xl bg-emerald-500 px-4 py-1.5 text-xs font-bold text-desk-deep transition hover:bg-emerald-400 disabled:opacity-40"
                >
                  {executing === opp.question ? "Rechecking every leg…" : "Record complete paper basket"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
