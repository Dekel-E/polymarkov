"use client";

import { useState } from "react";
import type { Step } from "@/lib/types";

function StepItem({ step, index }: { step: Step; index: number }) {
  const [open, setOpen] = useState(false);
  const isTool = step.prompt.system_prompt.startsWith("N/A");
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/70">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 font-mono text-sm font-semibold text-emerald-400">
          {index + 1}. {step.module}
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
            {isTool ? "tool" : "llm"}
          </span>
        </span>
        <span className="text-zinc-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-zinc-800 px-4 py-3 text-xs">
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-zinc-400">
              System prompt
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 font-mono text-zinc-300">
              {step.prompt.system_prompt}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-zinc-400">
              User prompt
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 font-mono text-zinc-300">
              {step.prompt.user_prompt}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold uppercase tracking-wide text-zinc-400">
              Response
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 font-mono text-emerald-300">
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
      <h2 className="mb-3 text-lg font-semibold text-zinc-200">
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
