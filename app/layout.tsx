import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import CommandBar from "@/components/CommandBar";
import CommandPalette from "@/components/CommandPalette";
import "./globals.css";

// Space Grotesk display, Inter body, JetBrains Mono for data/labels.
const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
});

const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "Polymarkov — Market Intelligence",
  description:
    "AI pre-trade intelligence dossiers for Polymarket — news, sentiment, AI council, deterministic verdict, paper trading.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${sans.variable} ${mono.variable} ${display.variable} min-h-screen bg-desk-deep font-sans text-desk-ink antialiased`}
      >
        <CommandBar />
        <CommandPalette />
        <main className="min-w-0">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 py-8 md:px-8">
          <div className="border-t border-desk-line/60 pt-4 font-mono text-[11px] text-desk-faint">
            Polymarkov · educational tool · paper trading only — not financial advice
          </div>
        </footer>
      </body>
    </html>
  );
}
