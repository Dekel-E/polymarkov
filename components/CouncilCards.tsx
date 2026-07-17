"use client";

import { useEffect, useState, type ReactNode } from "react";
import CountUp from "@/components/CountUp";
import type { DossierUi, PersonaOpinion } from "@/lib/types";

// persona emblems: line-art, 24-grid, currentColor

function BullEmblem() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d="M6 9C3.4 8 2.9 5 4.6 3.4" />
      <path d="M18 9c2.6-1 3.1-4 1.4-5.6" />
      <path d="M6 9c0 4.7 2.6 8 6 8s6-3.3 6-8" />
      <path d="M9.6 13.4c1 1.4 3.8 1.4 4.8 0" />
      <path d="M9.5 21 12 18l2.5 3" />
      <circle cx="9.6" cy="9.4" r=".55" fill="currentColor" stroke="none" />
      <circle cx="14.4" cy="9.4" r=".55" fill="currentColor" stroke="none" />
    </svg>
  );
}

function BearEmblem() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <circle cx="6.5" cy="6.5" r="2.4" />
      <circle cx="17.5" cy="6.5" r="2.4" />
      <path d="M5 12.5C5 8.9 8.1 6.5 12 6.5s7 2.4 7 6c0 4-3.1 6.5-7 6.5s-7-2.5-7-6.5Z" />
      <circle cx="12" cy="14.5" r="2.2" />
      <path d="M12 16.7v1.6" />
      <circle cx="9.4" cy="11.5" r=".55" fill="currentColor" stroke="none" />
      <circle cx="14.6" cy="11.5" r=".55" fill="currentColor" stroke="none" />
    </svg>
  );
}

function QuantEmblem() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d="M4 20V5" />
      <path d="M4 19.5h16" />
      <path d="M4.5 18C9 18 9.2 7.5 12 7.5S15 18 19.5 18" />
      <path d="M12 7.5v10.5" strokeDasharray="2 2" />
    </svg>
  );
}

function SkepticEmblem() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d="M4 5.5h11" />
      <path d="M4 9.5h8" />
      <path d="M4 13.5h5" />
      <circle cx="15.5" cy="14.5" r="3.8" />
      <path d="m18.4 17.4 2.6 2.6" />
    </svg>
  );
}

type Persona = {
  key: keyof NonNullable<DossierUi["council"]>;
  name: string;
  archetype: string;
  ring: string; // emblem badge classes
  text: string; // accent text
  marker: string; // dial marker fill
  Emblem: () => ReactNode;
};

const PERSONAS: Persona[] = [
  { key: "bull", name: "BullAnalyst", archetype: "The Optimist · strongest YES case",
    ring: "border-emerald-400/40 bg-emerald-400/10 text-emerald-400", text: "text-emerald-400", marker: "bg-emerald-400", Emblem: BullEmblem },
  { key: "bear", name: "BearAnalyst", archetype: "The Contrarian · strongest NO case",
    ring: "border-red-400/40 bg-red-400/10 text-red-400", text: "text-red-400", marker: "bg-red-400", Emblem: BearEmblem },
  { key: "quant", name: "QuantAnalyst", archetype: "The Modeler · base rates & microstructure",
    ring: "border-sky-400/40 bg-sky-400/10 text-sky-400", text: "text-sky-400", marker: "bg-sky-400", Emblem: QuantEmblem },
  { key: "skeptic", name: "ResolutionSkeptic", archetype: "The Auditor · attacks the fine print",
    ring: "border-instrument/40 bg-instrument/10 text-instrument", text: "text-instrument", marker: "bg-instrument", Emblem: SkepticEmblem },
];

const CONF_DOTS = { low: 1, medium: 2, high: 3 } as const;

function Confidence({ level, text }: { level: PersonaOpinion["confidence"]; text: string }) {
  const filled = CONF_DOTS[level] ?? 2;
  return (
    <span className="inline-flex items-center gap-1" title={`${level} confidence`}>
      {[0, 1, 2].map((i) => (
        <span key={i} className={`h-1.5 w-1.5 rounded-full ${i < filled ? text.replace("text-", "bg-") : "bg-desk-line"}`} />
      ))}
    </span>
  );
}

function Card({ persona, opinion, index }: { persona: Persona; opinion: PersonaOpinion; index: number }) {
  const target = Math.min(97, Math.max(3, opinion.estimated_probability * 100));
  // dial marker slides from the 50% axis to the estimate on mount; neutralized under prefers-reduced-motion
  const [pos, setPos] = useState(50);
  useEffect(() => {
    const id = requestAnimationFrame(() => setPos(target));
    return () => cancelAnimationFrame(id);
  }, [target]);

  return (
    <div
      className="desk-rise group relative overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/70 p-4 transition-colors hover:border-desk-edge"
      style={{ "--i": index } as React.CSSProperties}
    >
      {/* accent spine */}
      <span className={`absolute inset-y-0 left-0 w-[3px] ${persona.marker} opacity-70`} aria-hidden />

      <div className="flex items-center gap-3 pl-1">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${persona.ring} transition-transform duration-300 group-hover:scale-105`}>
          <persona.Emblem />
        </span>
        <div className="min-w-0 flex-1">
          <div className={`font-mono text-sm font-semibold ${persona.text}`}>{persona.name}</div>
          <div className="truncate text-[11px] text-desk-dim">{persona.archetype}</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-lg font-bold tabular-nums text-desk-ink">
            <CountUp value={opinion.estimated_probability * 100} decimals={0} />
            <span className="text-xs font-normal text-desk-dim">%</span>
          </div>
          <div className="mt-0.5 flex items-center justify-end gap-1.5">
            <span className="font-mono text-[9px] uppercase tracking-wider text-desk-faint">P(YES)</span>
            <Confidence level={opinion.confidence} text={persona.text} />
          </div>
        </div>
      </div>

      {/* the analyst's dial on the same 0-100 axis as the page gauge */}
      <div className="relative mt-3.5 ml-1 h-1.5 rounded-full bg-desk-line">
        <div className="absolute top-0 h-full w-px bg-desk-edge" style={{ left: "50%" }} aria-hidden />
        <div
          className="absolute -top-1 h-3.5 w-1 -translate-x-1/2 rounded-full transition-[left] duration-700 ease-out motion-reduce:transition-none"
          style={{ left: `${pos}%` }}
        >
          <span className={`absolute inset-0 rounded-full ${persona.marker}`} />
          <span className={`absolute inset-0 rounded-full ${persona.marker} blur-[3px] opacity-60`} />
        </div>
      </div>

      <p className="mt-3.5 pl-1 text-xs leading-relaxed text-desk-soft">{opinion.thesis}</p>

      {opinion.red_flags?.length > 0 && (
        <ul className="mt-2.5 space-y-1 pl-1">
          {opinion.red_flags.map((f, i) => (
            <li key={i} className="flex gap-1.5 text-[11px] leading-snug text-instrument/80">
              <span aria-hidden className="mt-px">⚑</span>
              <span className="min-w-0">{f}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function CouncilCards({ council }: { council: NonNullable<DossierUi["council"]> }) {
  const present = PERSONAS.filter((p) => council[p.key]);
  if (!present.length) return null;

  // spread of the four estimates = how much they disagree
  const probs = present.map((p) => council[p.key]!.estimated_probability * 100);
  const spread = Math.round(Math.max(...probs) - Math.min(...probs));

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
          The council
        </h2>
        <span className="font-mono text-[11px] text-desk-faint">
          four analysts · one context ·{" "}
          <span className={spread > 25 ? "text-instrument" : "text-desk-dim"}>
            {spread} pt spread
          </span>
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {present.map((p, i) => (
          <Card key={p.key} persona={p} opinion={council[p.key]!} index={i} />
        ))}
      </div>
    </section>
  );
}
