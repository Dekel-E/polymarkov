"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { executeTrade, fetchSettings } from "@/lib/api";
import type { DossierUi, FillReport } from "@/lib/types";

export default function TradePanel({ slug, ui }: { slug: string; ui: DossierUi }) {
  const verdict = ui.verdict;
  const recommended = verdict && verdict.verdict !== "PASS" ? verdict.verdict : null;
  const [side, setSide] = useState<"BUY_YES" | "BUY_NO">(recommended ?? "BUY_YES");
  const [amount, setAmount] = useState<number>(50);
  const [bankroll, setBankroll] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [fill, setFill] = useState<FillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchSettings()
      .then(({ settings }) => {
        if (!active) return;
        const currentBankroll = settings.funds.bankroll_usd;
        setBankroll(currentBankroll);
        if (recommended && verdict) {
          setAmount(
            Math.max(
              1,
              Math.round(currentBankroll * verdict.suggested_size_pct_bankroll / 100),
            ),
          );
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [recommended, verdict]);

  if (ui.fill || !verdict) return null; // agent already traded, or no verdict

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setFill(await executeTrade(slug, side, amount));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (fill) {
    return (
      <section className="rounded-2xl border border-emerald-800/60 bg-emerald-950/30 p-5">
        <h2 className="text-sm font-bold uppercase tracking-wider text-emerald-400">
          Paper trade executed
        </h2>
        <p className="mt-2 text-sm text-desk-ink">
          {fill.side.replace("_", " ")} ${fill.size_usd.toFixed(2)} at VWAP{" "}
          {(fill.vwap * 100).toFixed(1)}% — fee ${fill.fee_paid.toFixed(2)}, slippage{" "}
          {fill.slippage_bps.toFixed(1)} bps.
        </p>
        <Link
          href="/portfolio"
          className="mt-3 inline-block rounded-xl border border-emerald-500/60 px-4 py-1.5 text-xs font-bold text-emerald-300 transition hover:bg-emerald-500/10"
        >
          View in portfolio →
        </Link>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-desk-line bg-desk-panel/60 p-5">
      <h2 className="text-sm font-bold uppercase tracking-wider text-desk-dim">
        {recommended ? "Place the suggested paper trade" : "Manual paper trade"}
      </h2>
      <p className="mt-1 text-xs text-desk-dim">
        {recommended
          ? `The verdict is ${recommended.replace("_", " ")}. Suggested size: ${verdict.suggested_size_pct_bankroll.toFixed(1)}% of the paper bankroll${bankroll !== null ? ` ($${Math.max(1, Math.round(bankroll * verdict.suggested_size_pct_bankroll / 100)).toLocaleString()})` : ""}.`
          : "The agent returned PASS. A manual trade overrides its evidence, liquidity, and risk safeguards."}{" "}
        Any fill appears in the paper portfolio.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="flex rounded-xl border border-desk-line bg-desk-deep p-1">
          {(["BUY_YES", "BUY_NO"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={`rounded-lg px-4 py-1.5 text-xs font-bold transition ${
                side === s
                  ? s === "BUY_YES"
                    ? "bg-emerald-500 text-desk-deep"
                    : "bg-red-500 text-desk-deep"
                  : "text-desk-dim hover:text-desk-ink"
              }`}
            >
              {s.replace("_", " ")}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-desk-dim">
          $
          <input
            type="number"
            min={1}
            max={1000}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="w-24 rounded-xl border border-desk-line bg-desk-deep px-3 py-1.5 text-sm text-desk-ink focus:border-instrument/60 focus:outline-none"
          />
        </label>
        <button onClick={submit} disabled={busy || amount <= 0} className="btn-primary">
          {busy ? "Filling…" : "Execute paper trade"}
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
    </section>
  );
}
