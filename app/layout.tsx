import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Sidebar from "@/components/Sidebar";
import "./globals.css";

// Luminous Terminal type: Space Grotesk display (character), Inter body
// (clean, modern), JetBrains Mono for all data/labels (terminal feel).
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
        <div className="flex min-h-screen flex-col md:flex-row">
          <Sidebar />
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
