"use client";

import type { DossierUi, PersonaOpinion } from "@/lib/types";

const PERSONAS: { key: keyof NonNullable<DossierUi["council"]>; name: string; accent: string }[] = [
  { key: "bull", name: "BullAnalyst", accent: "text-emerald-400" },
  { key: "bear", name: "BearAnalyst", accent: "text-red-400" },
  { key: "quant", name: "QuantAnalyst", accent: "text-blue-400" },
  { key: "skeptic", name: "ResolutionSkeptic", accent: "text-amber-400" },
];

function Card({ name, accent, opinion }: { name: string; accent: string; opinion: PersonaOpinion }) {
  const prob = Math.min(99, Math.max(1, opinion.estimated_probability * 100));
  return (
    <div className="rounded-2xl border border-desk-line bg-desk-panel p-4">
      <div className="flex items-center justify-between">
        <span className={`font-mono text-sm font-semibold ${accent}`}>{name}</span>
        <span className="text-sm font-bold text-desk-ink">
          P(YES) {(opinion.estimated_probability * 100).toFixed(0)}%
          <span className="ml-1 text-xs font-normal text-desk-dim">({opinion.confidence})</span>
        </span>
      </div>
      {/* the analyst's own dial on the same 0-100 axis as the page gauge */}
      <div className="relative mt-2.5 h-1 rounded-full bg-desk-line">
        <div className="absolute top-0 h-full w-px bg-desk-edge" style={{ left: "50%" }} />
        <div
          className="absolute -top-[3px] h-2.5 w-[3px] rounded-sm bg-current text-desk-soft"
          style={{ left: `${prob}%` }}
        >
          <span className={`absolute inset-0 rounded-sm ${accent.replace("text-", "bg-")}`} />
        </div>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-desk-soft">{opinion.thesis}</p>
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
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
        The council
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {present.map((p) => (
          <Card key={p.key} name={p.name} accent={p.accent} opinion={council[p.key]!} />
        ))}
      </div>
    </section>
  );
}
