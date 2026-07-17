"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

function IconGrid() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </svg>
  );
}

function IconTrophy() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M8 21h8M12 17v4M7 4h10v6a5 5 0 0 1-10 0V4Z" />
      <path d="M7 6H4a1 1 0 0 0-1 1c0 2.2 1.8 4 4 4M17 6h3a1 1 0 0 1 1 1c0 2.2-1.8 4-4 4" />
    </svg>
  );
}

function IconCpu() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <rect x="10" y="10" width="4" height="4" rx="0.5" />
      <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M5 5l1.8 1.8M17.2 17.2 19 19M19 5l-1.8 1.8M6.8 17.2 5 19" />
    </svg>
  );
}

function IconWallet() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M3 7a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v2" />
      <path d="M3 7v11a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2H5a2 2 0 0 1-2-2Z" />
      <circle cx="16.5" cy="14.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function IconStar() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 3l2.7 5.7 6.3.8-4.6 4.3 1.2 6.2L12 17l-5.6 3 1.2-6.2L3 9.5l6.3-.8L12 3Z" />
    </svg>
  );
}

function IconBolt() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M13 2 4.5 13.5h6L11 22l8.5-11.5h-6L13 2Z" strokeLinejoin="round" />
    </svg>
  );
}

const NAV = [
  { href: "/", label: "Markets", icon: IconGrid },
  { href: "/strategies", label: "Strategy Desk", icon: IconBolt },
  { href: "/watchlist", label: "Watchlist", icon: IconStar },
  { href: "/portfolio", label: "Portfolio", icon: IconWallet },
  { href: "/league", label: "Smart Money League", icon: IconTrophy },
  { href: "/agent", label: "The Agent", icon: IconCpu },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex shrink-0 flex-row items-center gap-1 border-b border-desk-line/80 bg-desk-deep/80 px-3 py-2 backdrop-blur md:h-screen md:w-60 md:flex-col md:items-stretch md:gap-0 md:border-b-0 md:border-r md:px-4 md:py-6 md:sticky md:top-0">
      <Link href="/" className="flex items-center gap-2.5 md:mb-8 md:px-2">
        <span className="relative flex h-8 w-8 items-center justify-center rounded-full border border-instrument/40 bg-instrument/10 shadow-glow">
          <span className="h-2 w-2 rounded-full bg-instrument" />
          <span className="absolute inset-0 animate-ping rounded-full border border-instrument/30 [animation-duration:3s]" />
        </span>
        <span className="font-display text-base font-bold tracking-tight text-desk-ink">
          Poly<span className="text-instrument text-glow">markov</span>
        </span>
      </Link>

      <nav className="flex flex-1 flex-row gap-1 overflow-x-auto md:flex-col md:overflow-visible">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" || pathname.startsWith("/market") : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`relative flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors duration-200 ${
                active
                  ? "bg-instrument/10 font-semibold text-instrument"
                  : "text-desk-dim hover:bg-desk-raised hover:text-desk-ink"
              }`}
            >
              {active && (
                <span className="absolute left-0 top-1/2 hidden h-4 w-[3px] -translate-y-1/2 rounded-full bg-instrument shadow-glow md:block" />
              )}
              <Icon />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="hidden md:block">
        <div className="text-[11px] leading-relaxed text-desk-faint md:px-2">
          Educational tool.
          <br />
          Paper trading only — not financial advice.
        </div>
      </div>
    </aside>
  );
}
