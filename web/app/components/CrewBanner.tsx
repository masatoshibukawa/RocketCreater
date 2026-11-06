"use client";

import { fmt } from "../lib/format";

interface CrewBannerProps {
  attemptCount: number;
  /** Apogee of the latest simulated attempt, straight from the tool result. */
  latestApogeeM: number | undefined;
}

/** The crew at work while the agent designs. The picture is decoration; the text is the run's. */
export default function CrewBanner({ attemptCount, latestApogeeM }: CrewBannerProps) {
  return (
    <div className="crew-banner" role="status">
      <img src="/workshop/crew.webp" alt="" />
      <p>
        {attemptCount > 0 ? `試行 ${attemptCount} 回目` : "要求を読み取っています"}
        {latestApogeeM === undefined ? "" : ` · 最新の到達高度 ${fmt(latestApogeeM, 2)} m`}
      </p>
      <span className="crew-banner-bar" aria-hidden="true" />
    </div>
  );
}
