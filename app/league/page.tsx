"use client";

const SAMPLE_ROWS = [
  { rank: 1, wallet: "0x7a3f…e921", pnl30d: "+$184,220", winRate: "71%", positions: 34 },
  { rank: 2, wallet: "0xb1c4…0d77", pnl30d: "+$96,410", winRate: "64%", positions: 51 },
  { rank: 3, wallet: "0x33d9…4ac2", pnl30d: "+$71,835", winRate: "59%", positions: 27 },
  { rank: 4, wallet: "0xe802…19bb", pnl30d: "+$44,102", winRate: "62%", positions: 19 },
  { rank: 5, wallet: "0x51f6…c3d8", pnl30d: "+$38,577", winRate: "55%", positions: 42 },
];

export default function LeaguePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 md:px-8">
      <header>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            Smart Money <span className="text-instrument">League</span>
          </h1>
          <span className="rounded-full border border-instrument/50 bg-instrument/10 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider text-instrument">
            Coming soon
          </span>
        </div>
        <p className="mt-2 max-w-2xl text-sm text-desk-dim">
          A leaderboard of Polymarket&apos;s sharpest wallets — tracked by realized PnL, win
          rate, and category edge. Follow what smart money is buying before you run the
          agent on a market.
        </p>
      </header>

      <div className="relative overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-desk-line text-[11px] uppercase tracking-wider text-desk-dim">
              <th className="px-5 py-3 font-semibold">#</th>
              <th className="px-5 py-3 font-semibold">Wallet</th>
              <th className="px-5 py-3 font-semibold">30d PnL</th>
              <th className="px-5 py-3 font-semibold">Win rate</th>
              <th className="px-5 py-3 font-semibold">Open positions</th>
            </tr>
          </thead>
          <tbody className="select-none blur-[5px]">
            {SAMPLE_ROWS.map((r) => (
              <tr key={r.rank} className="border-b border-desk-line/60 last:border-0">
                <td className="px-5 py-3.5 font-bold text-desk-dim">{r.rank}</td>
                <td className="px-5 py-3.5 font-mono text-desk-soft">{r.wallet}</td>
                <td className="px-5 py-3.5 font-semibold text-emerald-400">{r.pnl30d}</td>
                <td className="px-5 py-3.5 text-desk-soft">{r.winRate}</td>
                <td className="px-5 py-3.5 text-desk-soft">{r.positions}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="absolute inset-0 flex items-center justify-center bg-desk-deep/40">
          <div className="rounded-xl border border-desk-edge bg-desk-panel px-5 py-3 text-center shadow-2xl">
            <div className="text-sm font-bold text-desk-ink">Wallet tracking is on the roadmap</div>
            <div className="mt-1 text-xs text-desk-dim">
              Sample data shown — on-chain tracking lands in a future update.
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          ["Track", "Follow specific wallets and get their entries surfaced on market pages."],
          ["Rank", "Realized PnL and win-rate leaderboards, by category and overall."],
          ["Compare", "See where the agent's verdict agrees — or disagrees — with smart money."],
        ].map(([title, body]) => (
          <div key={title} className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
            <div className="text-sm font-bold text-instrument">{title}</div>
            <p className="mt-1 text-xs leading-relaxed text-desk-dim">{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
