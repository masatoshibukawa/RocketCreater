import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./production.css";
import "./workshop-crew.css";

export const metadata: Metadata = {
  title: "RocketWright",
  description: "Tiered rocket design, simulated and verified before anything is shown.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
