"use client";

import { useState } from "react";
import type { Step, StepMetric } from "@/lib/types";

function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
}

function StepItem({ step, index, metric }: { step: Step; index: number; metric?: StepMetric }) {
  const [open, setOpen] = useState(false);
  const isTool = step.prompt.system_prompt.startsWith("N/A");
  const tokens = metric ? metric.tokens_in + metric.tokens_out : 0;
  return (
    <div className="rounded-xl border border-desk-line bg-desk-panel/70">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex min-w-0 items-center gap-2 font-mono text-sm font-semibold text-instrument">
          {index + 1}. {step.module}
          <span className="rounded bg-desk-line px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-desk-dim">
            {isTool ? "tool" : "llm"}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          {metric && (
            <span className="font-mono text-[11px] tabular-nums text-desk-faint">
              {metric.latency_ms != null && <span>{metric.latency_ms} ms</span>}
              {!isTool && tokens > 0 && (
                <span className="ml-2 text-desk-dim">{fmtTokens(tokens)} tok</span>
              )}
            </span>
          )}
          <span className="text-desk-dim">{open ? "▾" : "▸"}</span>
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-desk-line px-4 py-3 text-xs">
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-desk-dim">
              System prompt
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-desk-deep p-3 font-mono text-desk-soft">
              {step.prompt.system_prompt}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-desk-dim">
              User prompt
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-desk-deep p-3 font-mono text-desk-soft">
              {step.prompt.user_prompt}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-desk-dim">
              Response
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-desk-deep p-3 font-mono text-desk-soft">
              {JSON.stringify(step.response, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default function StepsTrace({
  steps,
  metrics,
}: {
  steps: Step[];
  metrics?: StepMetric[];
}) {
  if (steps.length === 0) return null;
  const totalTokens = (metrics ?? []).reduce((s, m) => s + m.tokens_in + m.tokens_out, 0);
  return (
    <section>
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
        Run log
        <span className="ml-2 font-mono text-[11px] font-normal normal-case tracking-normal text-desk-faint">
          {steps.length} steps · every model call, verbatim
          {totalTokens > 0 && <> · {fmtTokens(totalTokens)} tokens total</>}
        </span>
      </h2>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <StepItem key={i} step={step} index={i} metric={metrics?.[i]} />
        ))}
      </div>
    </section>
  );
}
