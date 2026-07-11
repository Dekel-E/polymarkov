"use client";

import { useEffect, useState } from "react";

interface AgentInfo {
  name: string;
  description: string;
  purpose: string;
  prompt_template: string;
  modules: string[];
  prompts: Record<string, string>;
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
          The <span className="text-emerald-400">Agent</span>
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-400">
          What Polymarkov is, how it thinks, and the exact prompts each module runs on.
        </p>
      </header>

      {error && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load agent info: {error}
        </div>
      )}

      {!info && !error && <div className="h-40 animate-pulse rounded-2xl bg-zinc-900" />}

      {info && (
        <>
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-500">
              What it does
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-zinc-300">{info.description}</p>
            <h2 className="mt-5 text-sm font-bold uppercase tracking-wider text-zinc-500">
              How to ask
            </h2>
            <pre className="mt-2 overflow-x-auto rounded-xl bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-emerald-300">
              {info.prompt_template}
            </pre>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-bold tracking-tight">Pipeline modules</h2>
            <div className="flex flex-wrap gap-2">
              {info.modules.map((m) => (
                <span
                  key={m}
                  className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 font-mono text-xs text-zinc-300"
                >
                  {m}
                </span>
              ))}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-bold tracking-tight">Architecture</h2>
            <div className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/60 p-2">
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
                  <details key={name} className="rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <summary className="cursor-pointer select-none px-4 py-3 font-mono text-sm font-semibold text-zinc-300 transition hover:text-zinc-100">
                      {name}
                    </summary>
                    <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-zinc-800 px-4 py-3 font-mono text-xs leading-relaxed text-zinc-400">
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
