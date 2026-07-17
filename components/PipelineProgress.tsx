"use client";

/**
 * Staged wait indicator for the ~1 min agent run. Stages advance on elapsed
 * time against typical timings — orientation, not fake telemetry (the last
 * stage stays live however long the run takes).
 */
const STAGES: { label: string; doneAt: number }[] = [
  { label: "planning the query", doneAt: 7 },
  { label: "resolving the market", doneAt: 12 },
  { label: "reading news & socials", doneAt: 24 },
  { label: "scoring sentiment", doneAt: 32 },
  { label: "council deliberating", doneAt: 50 },
  { label: "judge writing the dossier", doneAt: Infinity },
];

export default function PipelineProgress({ elapsed }: { elapsed: number }) {
  // orientation-only progress: eases toward ~95% over the typical minute, then
  // holds while the final stage finishes (never a fake 100%)
  const pct = Math.min(95, Math.round((1 - Math.exp(-elapsed / 22)) * 100));
  return (
    <div className="desk-rise rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="mb-2.5 flex items-center justify-between font-mono text-[11px] uppercase tracking-wider text-desk-dim">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-instrument desk-breathe" />
          compiling dossier
        </span>
        <span className="tabular-nums">{elapsed}s · typical ~1 min</span>
      </div>
      <div className="mb-3.5 h-1 overflow-hidden rounded-full bg-desk-line">
        <div
          className="h-full rounded-full bg-instrument transition-[width] duration-1000 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <ol className="space-y-1.5">
        {STAGES.map((stage, i) => {
          const done = elapsed >= stage.doneAt;
          const active = !done && (i === 0 || elapsed >= STAGES[i - 1].doneAt);
          return (
            <li
              key={stage.label}
              className={`flex items-center gap-2.5 font-mono text-xs ${
                done ? "text-desk-faint" : active ? "text-desk-ink" : "text-desk-faint/60"
              }`}
            >
              {done ? (
                <span className="flex h-3.5 w-3.5 items-center justify-center text-emerald-400">✓</span>
              ) : active ? (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-desk-line border-t-instrument [box-shadow:0_0_8px_rgb(34_225_230_/_0.45)]" />
              ) : (
                <span className="ml-1 h-1 w-1 rounded-full bg-desk-line" />
              )}
              {stage.label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
