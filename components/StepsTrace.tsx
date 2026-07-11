"use client";

import { useState } from "react";
import type { Step } from "@/lib/types";

function StepItem({ step, index }: { step: Step; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="font-mono text-sm font-semibold text-sky-400">
          {index + 1}. {step.module}
        </span>
        <span className="text-slate-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-800 px-4 py-3 text-xs">
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">
              System prompt
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-3 font-mono text-slate-300">
              {step.prompt.system_prompt}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">
              User prompt
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-3 font-mono text-slate-300">
              {step.prompt.user_prompt}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">
              Response
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-3 font-mono text-emerald-300">
              {JSON.stringify(step.response, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default function StepsTrace({ steps }: { steps: Step[] }) {
  if (steps.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-200">
        Steps trace ({steps.length})
      </h2>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <StepItem key={i} step={step} index={i} />
        ))}
      </div>
    </section>
  );
}
