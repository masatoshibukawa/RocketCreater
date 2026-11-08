import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./production.css";
import "./workshop-crew.css";
import "./workshop-scene.css";
import "./workshop-shell.css";

export const metadata: Metadata = {
  title: "RocketCreator",
  description: "Bottle-rocket design, simulated and verified before anything is shown.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
