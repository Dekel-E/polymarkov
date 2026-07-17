"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { searchMarkets } from "@/lib/api";
import type { MarketSummary } from "@/lib/types";

const NAV = [
  { label: "Markets", href: "/", hint: "browse & analyze" },
  { label: "Strategy Desk", href: "/strategies", hint: "autonomous trading" },
  { label: "Watchlist", href: "/watchlist", hint: "tracked markets" },
  { label: "Portfolio", href: "/portfolio", hint: "paper positions" },
  { label: "Smart Money League", href: "/league", hint: "top wallets" },
  { label: "The Agent", href: "/agent", hint: "how it works" },
];

type Item =
  | { kind: "nav"; label: string; href: string; hint: string }
  | { kind: "market"; label: string; href: string; hint: string };

/** ⌘K / Ctrl-K command palette: jump to any page or live market. */
export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MarketSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
    setActive(0);
  }, []);

  // global open: ⌘K / Ctrl-K, or a custom event from the command bar button
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    }
    function onOpen() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("open-command-palette", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("open-command-palette", onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // debounced live market search
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const id = setTimeout(() => {
      searchMarkets(q)
        .then((r) => setResults(r.slice(0, 6)))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 220);
    return () => clearTimeout(id);
  }, [query]);

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase();
    const nav: Item[] = NAV.filter((n) => !q || n.label.toLowerCase().includes(q)).map((n) => ({ kind: "nav", ...n }));
    const markets: Item[] = results.map((m) => ({
      kind: "market",
      label: m.question,
      href: `/market/${m.slug}`,
      hint: `${(m.mid * 100).toFixed(0)}% · ${m.category}`,
    }));
    return [...nav, ...markets];
  }, [query, results]);

  useEffect(() => setActive(0), [items.length]);

  const go = useCallback(
    (item: Item) => {
      close();
      router.push(item.href);
    },
    [router, close],
  );

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && items[active]) {
      e.preventDefault();
      go(items[active]);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[40] flex items-start justify-center bg-desk-deep/70 px-4 pt-[12vh] backdrop-blur-sm"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="desk-rise w-full max-w-xl overflow-hidden rounded-2xl border border-desk-edge bg-desk-panel shadow-glow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-desk-line px-4">
          <span className="font-mono text-sm text-instrument text-glow">›</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search markets or jump to a page…"
            className="w-full bg-transparent py-3.5 text-sm text-desk-ink placeholder-desk-faint focus:outline-none"
          />
          {searching && <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-desk-line border-t-instrument" />}
          <kbd className="shrink-0 rounded border border-desk-edge px-1.5 py-0.5 font-mono text-[10px] text-desk-faint">esc</kbd>
        </div>

        <ul className="max-h-[52vh] overflow-y-auto p-2">
          {items.length === 0 && (
            <li className="px-3 py-6 text-center text-sm text-desk-dim">
              {query.trim() ? "No matches." : "Type to search live markets…"}
            </li>
          )}
          {items.map((item, i) => (
            <li key={`${item.kind}-${item.href}-${i}`}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => go(item)}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                  i === active ? "bg-instrument/10" : "hover:bg-desk-raised"
                }`}
              >
                <span
                  className={`shrink-0 rounded-md border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${
                    item.kind === "market"
                      ? "border-instrument/40 text-instrument"
                      : "border-desk-edge text-desk-dim"
                  }`}
                >
                  {item.kind === "market" ? "market" : "go"}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm text-desk-ink">{item.label}</span>
                <span className="shrink-0 font-mono text-[10px] text-desk-faint">{item.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
