"use client";

import { fmt } from "../lib/format";
import { useWorkshop } from "../lib/WorkshopContext";

interface CrewBannerProps {
  attemptCount: number;
  /** Apogee of the latest simulated attempt, straight from the tool result. */
  latestApogeeM: number | undefined;
}

/** The crew at work while the agent designs. The picture is decoration; the text is the run's. */
export default function CrewBanner({ attemptCount, latestApogeeM }: CrewBannerProps) {
  const { visible, motionEnabled, task } = useWorkshop();
  if (!visible) return null;
  return (
    <div className="crew-banner" role="status">
      <img src="/workshop/crew.webp" alt="" />
      <p>
        {attemptCount > 0 ? `試行 ${attemptCount} 回目` : "要求を読み取っています"}
        {latestApogeeM === undefined ? "" : ` · 最新の到達高度 ${fmt(latestApogeeM, 2)} m`}
      </p>
      {motionEnabled && task.status === "working" ? <span className="crew-banner-bar" aria-hidden="true" /> : null}
    </div>
  );
}
