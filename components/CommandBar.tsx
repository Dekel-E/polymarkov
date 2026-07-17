"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Markets" },
  { href: "/strategies", label: "Strategy" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/league", label: "League" },
  { href: "/agent", label: "Agent" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || pathname.startsWith("/market");
  return pathname.startsWith(href);
}

export default function CommandBar() {
  const pathname = usePathname();
  const openPalette = () => window.dispatchEvent(new Event("open-command-palette"));

  return (
    <header className="sticky top-0 z-[20] border-b border-desk-line/80 bg-desk-deep/70 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 md:px-8">
        {/* brand */}
        <Link href="/" className="group flex items-center gap-2.5">
          <span className="relative flex h-7 w-7 items-center justify-center">
            <span
              aria-hidden
              className="absolute inset-0 rounded-full animate-[spin_3.5s_linear_infinite]"
              style={{
                background:
                  "conic-gradient(from 0deg, transparent 0deg 250deg, rgb(34 225 230 / 0.6) 345deg, transparent 360deg)",
              }}
            />
            <span aria-hidden className="absolute inset-[2.5px] rounded-full bg-desk-deep" />
            <span aria-hidden className="absolute inset-0 rounded-full border border-instrument/30" />
            <span className="relative h-1.5 w-1.5 rounded-full bg-instrument shadow-glow desk-breathe" />
          </span>
          <span className="hidden font-display text-[15px] font-bold tracking-tight text-desk-ink sm:block">
            Poly<span className="text-instrument text-glow">markov</span>
          </span>
        </Link>

        {/* nav */}
        <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {NAV.map(({ href, label }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className={`relative whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors duration-200 ${
                  active ? "text-instrument" : "text-desk-dim hover:text-desk-ink"
                }`}
              >
                {label}
                {active && (
                  <span className="absolute inset-x-2.5 -bottom-[7px] hidden h-[2px] rounded-full bg-instrument shadow-glow md:block" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* command trigger */}
        <button
          onClick={openPalette}
          aria-label="Open command palette"
          className="group flex shrink-0 items-center gap-2 rounded-xl border border-desk-line bg-desk-panel/70 px-3 py-1.5 text-sm text-desk-dim transition-colors hover:border-instrument/40 hover:text-desk-ink"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="hidden md:inline">Search…</span>
          <kbd className="hidden rounded border border-desk-edge px-1.5 py-0.5 font-mono text-[10px] text-desk-faint transition-colors group-hover:border-instrument/40 group-hover:text-instrument md:inline">
            ⌘K
          </kbd>
        </button>
      </div>
    </header>
  );
}
