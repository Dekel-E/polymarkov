"use client";

import type { DossierUi, PersonaOpinion } from "@/lib/types";

const PERSONAS: { key: keyof NonNullable<DossierUi["council"]>; name: string; accent: string }[] = [
  { key: "bull", name: "BullAnalyst", accent: "text-emerald-400" },
  { key: "bear", name: "BearAnalyst", accent: "text-red-400" },
  { key: "quant", name: "QuantAnalyst", accent: "text-blue-400" },
  { key: "skeptic", name: "ResolutionSkeptic", accent: "text-amber-400" },
];

function Card({ name, accent, opinion }: { name: string; accent: string; opinion: PersonaOpinion }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-center justify-between">
        <span className={`font-mono text-sm font-semibold ${accent}`}>{name}</span>
        <span className="text-sm font-bold text-zinc-100">
          {(opinion.estimated_probability * 100).toFixed(0)}%
          <span className="ml-1 text-xs font-normal text-zinc-500">({opinion.confidence})</span>
        </span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-zinc-300">{opinion.thesis}</p>
      {opinion.red_flags?.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-amber-400/80">
          {opinion.red_flags.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function CouncilCards({ council }: { council: NonNullable<DossierUi["council"]> }) {
  const present = PERSONAS.filter((p) => council[p.key]);
  if (!present.length) return null;
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-zinc-200">AI council</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {present.map((p) => (
          <Card key={p.key} name={p.name} accent={p.accent} opinion={council[p.key]!} />
        ))}
      </div>
    </section>
  );
}
