"use client";

import { useEffect, useState } from "react";
import {
  fetchAutomationStatus,
  type AutomationJobStatus,
  type AutomationStatus as AutomationStatusData,
} from "@/lib/api";

const STATUS_STYLE: Record<AutomationJobStatus["status"], string> = {
  never_run: "border-desk-edge text-desk-faint",
  running: "border-instrument/60 bg-instrument/10 text-instrument",
  stale: "border-amber-700/60 bg-amber-950/20 text-amber-300",
  success: "border-emerald-700/60 bg-emerald-950/20 text-emerald-400",
  failure: "border-red-700/60 bg-red-950/30 text-red-300",
  cancelled: "border-amber-700/60 bg-amber-950/20 text-amber-300",
  skipped: "border-desk-edge text-desk-dim",
};

function when(value?: string | null) {
  if (!value) return "never observed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function AutomationStatus() {
  const [data, setData] = useState<AutomationStatusData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const next = await fetchAutomationStatus();
        if (active) {
          setData(next);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    const timer = setInterval(load, 30_000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <section className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm font-bold uppercase tracking-wider text-desk-ink">
            Automation status
          </h2>
          <p className="mt-1 text-xs text-desk-dim">
            Checked-in schedules plus live heartbeats from GitHub Actions.
          </p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider ${
          data?.schedules_enabled
            ? "border-emerald-700/60 text-emerald-400"
            : "border-amber-700/60 text-amber-300"
        }`}>
          {data?.schedules_enabled ? "cron enabled" : "manual only"}
        </span>
      </div>

      {error && <div className="mt-3 text-xs text-red-300">{error}</div>}
      {!data && !error && <div className="mt-3 h-20 animate-pulse rounded-xl bg-desk-deep/70" />}
      {data && (
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {data.jobs.map((job) => (
            <div key={`${job.workflow}/${job.job}`} className="rounded-xl border border-desk-line bg-desk-deep/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-semibold text-desk-ink">{job.label}</span>
                <span className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase ${STATUS_STYLE[job.status]}`}>
                  {job.status.replace("_", " ")}
                </span>
              </div>
              <div className="mt-1 font-mono text-[10px] text-desk-faint">
                {job.workflow}/{job.job} · {job.schedule_enabled ? job.cadence : "manual trigger"}
              </div>
              <div className="mt-1 text-[11px] text-desk-dim">
                {when(job.finished_at ?? job.updated_at)}
                {job.event && ` · ${job.event}`}
              </div>
              {job.run_url && (
                <a href={job.run_url} target="_blank" rel="noreferrer" className="mt-1 block font-mono text-[10px] text-instrument hover:underline">
                  open GitHub run ↗
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
