"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchAgentStats } from "@/lib/api";
import type { AgentStats } from "@/lib/types";

interface AgentInfo {
  name: string;
  description: string;
  purpose: string;
  prompt_template: { template: string; example?: string };
  prompt_examples: { prompt: string }[];
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
  const primaryCal = cal?.latest_per_market;

  return (
    <section>
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide">
        Report card
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Analyses" value={stats.total_runs} />
        <Tile
          label="Verdicts"
          value={`${buys} buy / ${stats.verdicts["PASS"] ?? 0} pass`}
          sub="PASS means the safeguards found no trade"
        />
        <Tile
          label="Average runtime"
          value={stats.avg_latency_s !== null ? `${stats.avg_latency_s}s` : "—"}
        />
        <Tile
          label="Calibration"
          value={primaryCal ? primaryCal.agent_brier.toFixed(3) : "pending"}
          sub={
            primaryCal
              ? `Brier vs market ${primaryCal.market_brier.toFixed(3)} across ${primaryCal.markets} resolved markets`
              : "available after analyzed markets resolve"
          }
        />
      </div>

      {cal && primaryCal && (
        <div className="mt-4 rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-desk-ink">Calibration diagnostics</h3>
              <p className="mt-0.5 text-xs text-desk-dim">
                Latest forecast per resolved market; lower Brier, log loss, and calibration error are better.
              </p>
            </div>
            <span className="rounded-full border border-desk-edge px-2 py-1 font-mono text-[10px] uppercase text-desk-dim">
              {cal.sample_status} sample
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile
              label="Skill vs market"
              value={
                primaryCal.brier_skill_vs_market === null
                  ? "n/a"
                  : `${primaryCal.brier_skill_vs_market >= 0 ? "+" : ""}${(
                      primaryCal.brier_skill_vs_market * 100
                    ).toFixed(1)}%`
              }
              sub="positive means a lower Brier score"
            />
            <Tile label="Log loss" value={primaryCal.agent_log_loss.toFixed(3)} sub={`market ${primaryCal.market_log_loss.toFixed(3)}`} />
            <Tile label="Calibration error" value={primaryCal.expected_calibration_error.toFixed(3)} sub="weighted forecast/outcome gap" />
            <Tile label="Resolution coverage" value={`${cal.resolution_coverage_pct.toFixed(1)}%`} sub={`${cal.scored_runs} of ${cal.forecast_runs} forecasts scored`} />
          </div>

          {cal.sample_warning && (
            <p className="mt-3 rounded-lg border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-300">
              {cal.sample_warning}
            </p>
          )}

          {primaryCal.buckets.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-xs">
                <thead className="font-mono uppercase tracking-wide text-desk-faint">
                  <tr>
                    <th className="pb-2 font-normal">Forecast band</th>
                    <th className="pb-2 font-normal">Forecasts</th>
                    <th className="pb-2 font-normal">Mean forecast</th>
                    <th className="pb-2 font-normal">Observed YES</th>
                    <th className="pb-2 font-normal">Gap</th>
                  </tr>
                </thead>
                <tbody className="font-mono tabular-nums text-desk-dim">
                  {primaryCal.buckets.map((bucket) => (
                    <tr key={bucket.range} className="border-t border-desk-line/60">
                      <td className="py-2">{bucket.range}</td>
                      <td className="py-2">{bucket.count}</td>
                      <td className="py-2">{(bucket.mean_forecast * 100).toFixed(1)}%</td>
                      <td className="py-2">{(bucket.outcome_rate * 100).toFixed(1)}%</td>
                      <td className="py-2">{(bucket.absolute_gap * 100).toFixed(1)} pts</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

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
    <div className="desk-rise mx-auto max-w-4xl space-y-8 px-4 py-8 md:px-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
          The <span className="text-instrument">Agent</span>
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-desk-dim">
          What Polymarkov does, how the pipeline works, and the prompts behind each LLM module.
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
              Purpose and limits
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-desk-soft">{info.description}</p>
            <h2 className="mt-5 text-sm font-bold uppercase tracking-wider text-desk-dim">
              How to ask
            </h2>
            <pre className="mt-2 overflow-x-auto rounded-xl bg-desk-deep p-4 font-mono text-xs leading-relaxed text-instrument">
              {info.prompt_template.template}
            </pre>
            {info.prompt_template.example && (
              <pre className="mt-2 overflow-x-auto rounded-xl bg-desk-deep/60 p-4 font-mono text-xs leading-relaxed text-desk-dim">
                {info.prompt_template.example}
              </pre>
            )}
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
