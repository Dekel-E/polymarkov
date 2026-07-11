"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchAgentStats } from "@/lib/api";
import type { AgentStats } from "@/lib/types";

interface AgentInfo {
  name: string;
  description: string;
  purpose: string;
  prompt_template: string;
  modules: string[];
  prompts: Record<string, string>;
}

function Tile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">{label}</div>
      <div className="mt-1 text-xl font-bold tabular-nums text-desk-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-desk-dim">{sub}</div>}
    </div>
  );
}

function ReportCard() {
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchAgentStats()
      .then(setStats)
      .catch(() => setError(true));
  }, []);

  if (error || !stats) return null;
  const buys = (stats.verdicts["BUY_YES"] ?? 0) + (stats.verdicts["BUY_NO"] ?? 0);
  const cal = stats.calibration;

  return (
    <section>
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide">
        Report card
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="analyses run" value={stats.total_runs} />
        <Tile
          label="verdicts"
          value={`${buys} buy / ${stats.verdicts["PASS"] ?? 0} pass`}
          sub="pass is a first-class outcome"
        />
        <Tile
          label="avg run time"
          value={stats.avg_latency_s !== null ? `${stats.avg_latency_s}s` : "—"}
        />
        <Tile
          label="calibration"
          value={cal ? `${cal.agent_brier} vs ${cal.market_brier}` : "pending"}
          sub={
            cal
              ? `Brier score over ${cal.scored_runs} resolved runs (lower is better)`
              : "scores appear once analyzed markets resolve"
          }
        />
      </div>

      {stats.recent.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
          <div className="border-b border-desk-line px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-desk-faint">
            recent runs
          </div>
          {stats.recent.map((r, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center gap-3 border-b border-desk-line/60 px-4 py-2.5 text-xs last:border-0"
            >
              {r.market_id ? (
                <Link
                  href={`/market/${r.market_id}`}
                  className="min-w-0 flex-1 truncate font-mono text-desk-soft transition hover:text-instrument"
                >
                  {r.market_id}
                </Link>
              ) : (
                <span className="min-w-0 flex-1 truncate font-mono text-desk-faint">—</span>
              )}
              <span
                className={`font-mono font-bold ${
                  r.verdict === "BUY_YES"
                    ? "text-emerald-400"
                    : r.verdict === "BUY_NO"
                      ? "text-red-400"
                      : "text-desk-dim"
                }`}
              >
                {(r.verdict ?? "—").replace("_", " ")}
              </span>
              {r.fair_prob != null && r.mid_at_run != null && (
                <span className="font-mono tabular-nums text-desk-dim">
                  fair {(r.fair_prob * 100).toFixed(1)}% vs {(r.mid_at_run * 100).toFixed(1)}%
                </span>
              )}
              <span className="font-mono text-desk-faint">
                {new Date(r.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default function AgentPage() {
  const [info, setInfo] = useState<AgentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/agent_info")
      .then((r) => {
        if (!r.ok) throw new Error(`API returned HTTP ${r.status}`);
        return r.json();
      })
      .then(setInfo)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 md:px-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
          The <span className="text-instrument">Agent</span>
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-desk-dim">
          What Polymarkov is, how it thinks, and the exact prompts each module runs on.
        </p>
      </header>

      {error && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load agent info: {error}
        </div>
      )}

      {!info && !error && <div className="h-40 animate-pulse rounded-2xl bg-desk-panel" />}

      <ReportCard />

      {info && (
        <>
          <section className="rounded-2xl border border-desk-line bg-desk-panel/60 p-5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-desk-dim">
              What it does
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-desk-soft">{info.description}</p>
            <h2 className="mt-5 text-sm font-bold uppercase tracking-wider text-desk-dim">
              How to ask
            </h2>
            <pre className="mt-2 overflow-x-auto rounded-xl bg-desk-deep p-4 font-mono text-xs leading-relaxed text-instrument">
              {info.prompt_template}
            </pre>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-bold tracking-tight">Pipeline modules</h2>
            <div className="flex flex-wrap gap-2">
              {info.modules.map((m) => (
                <span
                  key={m}
                  className="rounded-lg border border-desk-edge bg-desk-panel px-3 py-1.5 font-mono text-xs text-desk-soft"
                >
                  {m}
                </span>
              ))}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-bold tracking-tight">Architecture</h2>
            <div className="overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60 p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/api/model_architecture"
                alt="Polymarkov architecture diagram"
                className="w-full rounded-xl"
              />
            </div>
          </section>

          {Object.keys(info.prompts).length > 0 && (
            <section>
              <h2 className="mb-3 text-lg font-bold tracking-tight">Module prompts</h2>
              <div className="space-y-2">
                {Object.entries(info.prompts).map(([name, text]) => (
                  <details key={name} className="rounded-xl border border-desk-line bg-desk-panel/60">
                    <summary className="cursor-pointer select-none px-4 py-3 font-mono text-sm font-semibold text-desk-soft transition hover:text-desk-ink">
                      {name}
                    </summary>
                    <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-desk-line px-4 py-3 font-mono text-xs leading-relaxed text-desk-dim">
                      {text}
                    </pre>
                  </details>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
