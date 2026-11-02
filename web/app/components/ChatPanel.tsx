"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Status } from "../lib/designState";
import type { ChatMessage } from "../lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  status: Status;
  onStart: (text: string, seed: number | null) => void;
  onStop: () => void;
  onReset: () => void;
}

const EXAMPLES: { label: string; text: string }[] = [
  {
    label: "例: アマチュア",
    text: "1 kg の荷物を高度 2 km まで上げてパラシュートで回収したい。予算 5 万円。",
  },
  {
    label: "例: 企業級",
    text: "150 kg の小型衛星を高度 400 km の軌道に投入したい。予算 20 億円。",
  },
];

const STATUS_LABEL: Record<Status, string> = {
  idle: "待機中",
  streaming: "設計中…",
  done: "完了",
  error: "エラー",
};

const ROLE_PREFIX: Record<ChatMessage["role"], string> = {
  user: "",
  agent: "",
  thinking: "思考: ",
  question: "質問: ",
  error: "",
  system: "",
};

export default function ChatPanel({ messages, status, onStart, onStop, onReset }: ChatPanelProps) {
  const [text, setText] = useState<string>("");
  const [seed, setSeed] = useState<string>("42");
  const logRef = useRef<HTMLDivElement | null>(null);
  const streaming = status === "streaming";

  // Keep the newest message in view.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  const submit = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    if (streaming || text.trim() === "") return;
    const seedValue = seed.trim() === "" ? null : Number(seed);
    onStart(text, seedValue !== null && Number.isFinite(seedValue) ? seedValue : null);
  };

  return (
    <div className={`panel chat status-${status}`}>
      <div className="chat-brand">
        <h1>RocketWright</h1>
        <span className="muted">
          <span className="status-dot" />
          {STATUS_LABEL[status]}
        </span>
      </div>
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 ? (
          <div className="empty">
            要求を自然文で入力してください（どこまで飛ばすか・何を載せるか・回収するか・予算）。
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.key} className={`msg msg-${m.role}`}>
              {ROLE_PREFIX[m.role]}
              {m.text}
            </div>
          ))
        )}
      </div>
      <form className="chat-form" onSubmit={submit}>
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              className="btn btn-small"
              disabled={streaming}
              onClick={() => setText(ex.text)}
            >
              {ex.label}
            </button>
          ))}
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="例: 1 kg の荷物を高度 2 km まで上げてパラシュートで回収したい。予算 5 万円。"
          disabled={streaming}
        />
        <div className="chat-actions">
          <button type="submit" className="btn btn-primary" disabled={streaming || text.trim() === ""}>
            設計を開始
          </button>
          {streaming ? (
            <button type="button" className="btn" onClick={onStop}>
              中断
            </button>
          ) : (
            <button type="button" className="btn" onClick={onReset} disabled={status === "idle"}>
              リセット
            </button>
          )}
          <span className="spacer" />
          <label>
            seed
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              disabled={streaming}
            />
          </label>
        </div>
      </form>
    </div>
  );
}
