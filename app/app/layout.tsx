import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Take the LEAP",
  description:
    "Daily verdicts from a rules-based AI LEAPS screener that treats zero trades as success. Not financial advice.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full bg-zinc-950 font-sans text-zinc-200">
        <nav className="border-b border-zinc-800/80">
          <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
            <Link href="/" className="font-bold text-zinc-100">
              Take the <span className="text-emerald-400">LEAP</span>
            </Link>
            <div className="flex gap-5 text-sm text-zinc-400">
              <Link href="/dashboard" className="hover:text-zinc-100">
                Dashboard
              </Link>
              <a
                href="https://github.com/shawnjohnsamuel/leaps-hunter"
                className="hover:text-zinc-100"
              >
                Methodology
              </a>
            </div>
          </div>
        </nav>
        {children}
        <footer className="mx-auto max-w-3xl px-6 pb-10 pt-4 text-xs leading-relaxed text-zinc-600">
          Not financial advice. Rules-based AI research output — do your own research.
          Options can lose 100% of premium. © {new Date().getFullYear()} Take the LEAP.
        </footer>
      </body>
    </html>
  );
}
