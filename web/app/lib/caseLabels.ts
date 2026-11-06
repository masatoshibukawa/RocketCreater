/** Names of the designs on screen. Tool-call ids stay in the history; people read 案 n. */

import type { AttemptRow, Candidate } from "./types";

export const REFERENCE_CASE_LABEL = "参照の初期案";

export function caseLabels(candidates: Candidate[], attempts: AttemptRow[]): Map<string, string> {
  const labels = new Map<string, string>();
  attempts.forEach((a) => labels.set(a.id, a.seededFrom ? REFERENCE_CASE_LABEL : `試行 ${a.attempt}`));
  let own = 0;
  candidates.forEach((c) => labels.set(c.source_id, c.seededFrom ? REFERENCE_CASE_LABEL : `案 ${++own}`));
  return labels;
}
