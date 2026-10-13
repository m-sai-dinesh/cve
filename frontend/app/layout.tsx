import type { Metadata, Viewport } from "next";
import React from "react";
import { Header } from "@/components/Header";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "ModernRx - GxP-Aware Modernization Advisor",
  description:
    "Generic AI tools rewrite code. ModernRx tells a pharma company what to modernize, " +
    "in which order, and how to prove to FDA/EMA that nothing broke.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <Providers>
          <Header />
          <main className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
