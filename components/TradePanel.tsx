"use client";

import Link from "next/link";
import { useState } from "react";
import { executeTrade } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DossierUi, FillReport } from "@/lib/types";

export default function TradePanel({ slug, ui }: { slug: string; ui: DossierUi }) {
  const { user, token } = useAuth();
  const verdict = ui.verdict;
  const recommended = verdict && verdict.verdict !== "PASS" ? verdict.verdict : null;
  const suggestedUsd = verdict
    ? Math.max(10, Math.round(verdict.suggested_size_pct_bankroll * 100))
    : 50;

  const [side, setSide] = useState<"BUY_YES" | "BUY_NO">(recommended ?? "BUY_YES");
  const [amount, setAmount] = useState<number>(recommended ? suggestedUsd : 50);
  const [busy, setBusy] = useState(false);
  const [fill, setFill] = useState<FillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (ui.fill || !verdict) return null; // agent already traded, or no verdict

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setFill(await executeTrade(slug, side, amount, token));
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
        <p className="mt-2 text-sm text-zinc-200">
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
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
      <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
        {recommended ? "Execute the agent's trade" : "Override: trade anyway"}
      </h2>
      <p className="mt-1 text-xs text-zinc-500">
        {recommended
          ? `The verdict is ${recommended.replace("_", " ")} with a suggested ${verdict.suggested_size_pct_bankroll.toFixed(1)}% of the $10k paper bankroll.`
          : "The agent says PASS — you can still direct a paper trade at your own discretion."}
        {!user && " Trades made while logged out land in the agent's shared book."}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="flex rounded-xl border border-zinc-800 bg-zinc-950 p-1">
          {(["BUY_YES", "BUY_NO"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={`rounded-lg px-4 py-1.5 text-xs font-bold transition ${
                side === s
                  ? s === "BUY_YES"
                    ? "bg-emerald-500 text-zinc-950"
                    : "bg-red-500 text-zinc-950"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {s.replace("_", " ")}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-400">
          $
          <input
            type="number"
            min={1}
            max={1000}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="w-24 rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 focus:border-emerald-500/60 focus:outline-none"
          />
        </label>
        <button
          onClick={submit}
          disabled={busy || amount <= 0}
          className="rounded-xl bg-amber-500 px-5 py-2 text-sm font-bold text-zinc-950 transition hover:bg-amber-400 disabled:opacity-40"
        >
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
