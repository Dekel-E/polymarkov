"use client";

import { useState } from "react";
import type { Step } from "@/lib/types";

function StepItem({ step, index }: { step: Step; index: number }) {
  const [open, setOpen] = useState(false);
  const isTool = step.prompt.system_prompt.startsWith("N/A");
  return (
    <div className="rounded-xl border border-desk-line bg-desk-panel/70">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 font-mono text-sm font-semibold text-instrument">
          {index + 1}. {step.module}
          <span className="rounded bg-desk-line px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-desk-dim">
            {isTool ? "tool" : "llm"}
          </span>
        </span>
        <span className="text-desk-dim">{open ? "▾" : "▸"}</span>
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

export default function StepsTrace({ steps }: { steps: Step[] }) {
  if (steps.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
        Run log
        <span className="ml-2 font-mono text-[11px] font-normal normal-case tracking-normal text-desk-faint">
          {steps.length} steps · every model call, verbatim
        </span>
      </h2>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <StepItem key={i} step={step} index={i} />
        ))}
      </div>
    </section>
  );
}
