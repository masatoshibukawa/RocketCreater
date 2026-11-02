"use client";

import { useMemo } from "react";
import {
  ASPECT_LABEL,
  REVIEW_ASPECTS,
  SEVERITY_LABEL,
  isReviewAspect,
  reviewGateWarningsFromEvents,
  reviewsFromEvents,
  type ReviewAspect,
  type ReviewEntry,
  type ReviewSeverity,
  type ReviewVerdict,
} from "../lib/reviewTypes";
import type { AgentEvent } from "../lib/types";

interface ReviewPanelProps {
  events: AgentEvent[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

function chipClass(severity: ReviewSeverity): string {
  return `chip review-chip review-${severity}`;
}

function verdictFor(entry: ReviewEntry, aspect: ReviewAspect): ReviewVerdict | null {
  for (let i = 0; i < entry.verdicts.length; i += 1) {
    if (entry.verdicts[i].aspect === aspect) return entry.verdicts[i];
  }
  return null;
}

function AspectChips({ entry }: { entry: ReviewEntry }) {
  return (
    <div className="review-chips">
      {REVIEW_ASPECTS.map((aspect) => {
        const v = verdictFor(entry, aspect);
        if (!v) {
          return (
            <span key={aspect} className="chip chip-muted review-chip" title="レビュー結果なし">
              {ASPECT_LABEL[aspect]} <small>-</small>
            </span>
          );
        }
        return (
          <span key={aspect} className={chipClass(v.severity)} title={`${aspect}: ${v.severity}`}>
            {ASPECT_LABEL[aspect]} <small>{SEVERITY_LABEL[v.severity]}</small>
          </span>
        );
      })}
    </div>
  );
}

function VerdictDetail({ verdict }: { verdict: ReviewVerdict }) {
  if (verdict.findings.length === 0 && verdict.suggested_changes.length === 0) return null;
  return (
    <div className="review-verdict">
      <div className="review-verdict-title">
        <span className={chipClass(verdict.severity)}>
          {ASPECT_LABEL[verdict.aspect]} <small>{SEVERITY_LABEL[verdict.severity]}</small>
        </span>
      </div>
      {verdict.findings.length > 0 && (
        <ul className="review-list">
          {verdict.findings.map((f, i) => (
            <li key={`f-${i}`}>{f}</li>
          ))}
        </ul>
      )}
      {verdict.suggested_changes.length > 0 && (
        <div className="review-suggest">
          <span className="muted">提案: </span>
          <ul className="review-list">
            {verdict.suggested_changes.map((s, i) => (
              <li key={`s-${i}`}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ReviewCard({
  entry,
  selected,
  onSelect,
}: {
  entry: ReviewEntry;
  selected: boolean;
  onSelect?: (id: string) => void;
}) {
  const droppedAspects = Object.keys(entry.dropped);
  const select = onSelect;
  const className = `review-card${selected ? " review-card-selected" : ""}${
    select ? " row-clickable" : ""
  }`;
  const handleClick = select ? () => select(entry.source_id) : undefined;
  return (
    <div className={className} onClick={handleClick} role={select ? "button" : undefined}>
      <div className="review-card-header">
        <span className="mono">{entry.source_id}</span>
        <span className="muted">試行 {entry.attempt}</span>
        {entry.blocked && <span className="chip review-chip review-blocker">レビューで除外</span>}
      </div>
      <AspectChips entry={entry} />
      {entry.verdicts.map((v) => (
        <VerdictDetail key={v.aspect} verdict={v} />
      ))}
      {droppedAspects.length > 0 && (
        <div className="review-dropped muted">
          出典のない数値を含むため削除された指摘:{" "}
          {droppedAspects
            .map((a) => `${isReviewAspect(a) ? ASPECT_LABEL[a] : a} ${entry.dropped[a].length} 件`)
            .join(", ")}
        </div>
      )}
    </div>
  );
}

/**
 * Per-candidate reviewer verdicts (stability / recovery / cost / safety) folded from `review`
 * events, plus `warning` events of kind `review_gate` (designs removed from the final list).
 */
export default function ReviewPanel({ events, selectedId, onSelect }: ReviewPanelProps) {
  const reviews = useMemo(() => reviewsFromEvents(events), [events]);
  const gates = useMemo(() => reviewGateWarningsFromEvents(events), [events]);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">レビュー</h2>
        <span className="muted">{reviews.length} 件</span>
      </div>
      {gates.map((g, i) => (
        <div key={`gate-${i}`} className="warn-box review-gate">
          レビューで除外された設計案: <span className="mono">{g.rejected_ids.join(", ") || "-"}</span>
          {g.detail && <div className="muted">{g.detail}</div>}
        </div>
      ))}
      {reviews.length === 0 ? (
        <div className="empty">合格した設計案ごとのレビュー（安定性 / 回収 / 費用 / 安全）がここに並びます</div>
      ) : (
        <div className="review-cards">
          {reviews.map((entry) => (
            <ReviewCard
              key={entry.source_id}
              entry={entry}
              selected={selectedId === entry.source_id}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
