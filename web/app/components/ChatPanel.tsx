"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Status } from "../lib/designState";
import type { ChatMessage } from "../lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  status: Status;
  /** A clarifying question from the agent waiting for an answer (reply box shown under it). */
  pendingQuestion: string | null;
  onStart: (text: string, seed: number | null) => void;
  onAnswer: (text: string) => void;
  onStop: () => void;
  onReset: () => void;
}

const EXAMPLES: readonly string[] = [
  "卵を割らずに 30 m まで上げて回収したい",
  "1 kg の荷物を 2 km まで上げてパラシュートで回収したい。予算 5 万円",
  "200 g の荷物を 500 m まで上げて回収したい。予算 2 万円。資格なしで飛ばしたい",
  "150 kg の小型衛星を高度 400 km の軌道に投入したい。予算 20 億円",
];

const ROLE_LABEL: Record<ChatMessage["role"], string> = {
  user: "あなた",
  agent: "設計エージェント",
  thinking: "考え中",
  question: "質問",
  error: "エラー",
  system: "",
};

export default function ChatPanel({
  messages,
  status,
  pendingQuestion,
  onStart,
  onAnswer,
  onStop,
  onReset,
}: ChatPanelProps) {
  const [text, setText] = useState<string>("");
  const [seed, setSeed] = useState<string>("42");
  const [reply, setReply] = useState<string>("");
  const logRef = useRef<HTMLDivElement | null>(null);
  const streaming = status === "streaming";
  const awaitingAnswer = pendingQuestion !== null && !streaming;

  // Keep the newest message in view.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, awaitingAnswer]);

  const submit = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    if (streaming || text.trim() === "") return;
    const seedValue = seed.trim() === "" ? null : Number(seed);
    onStart(text, seedValue !== null && Number.isFinite(seedValue) ? seedValue : null);
  };

  const submitReply = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    if (!awaitingAnswer || reply.trim() === "") return;
    onAnswer(reply);
    setReply("");
  };

  return (
    <div className="panel chat">
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <p>どこまで飛ばすか・何を載せるか・回収するか・予算を、ふつうの文章で書いてください。</p>
            <p className="muted">
              段階（ペットボトル／アマチュア／企業級／重工級）を判定し、物理シミュレーションで検証した設計案だけを返します。
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.key} className={`msg msg-${m.role}`}>
              {ROLE_LABEL[m.role] !== "" && <span className="msg-role">{ROLE_LABEL[m.role]}</span>}
              <span className="msg-text">{m.text}</span>
            </div>
          ))
        )}
        {awaitingAnswer && (
          <form className="msg msg-reply" onSubmit={submitReply}>
            <span className="msg-role">回答</span>
            <textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="質問への答えを書いて送信すると、元の要求に追記して設計をやり直します"
              rows={2}
            />
            <div className="chat-actions">
              <button type="submit" className="btn btn-primary btn-small" disabled={reply.trim() === ""}>
                回答して続ける
              </button>
            </div>
          </form>
        )}
      </div>
      <form className="chat-form" onSubmit={submit}>
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="chip chip-example"
              disabled={streaming}
              onClick={() => setText(ex)}
              title="クリックで入力欄にコピー"
            >
              {ex}
            </button>
          ))}
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="例: 1 kg の荷物を 2 km まで上げてパラシュートで回収したい。予算 5 万円"
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
          <label className="seed-field" title="乱数シード（同じ要求と seed なら同じ結果）">
            seed
            <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} disabled={streaming} />
          </label>
        </div>
      </form>
    </div>
  );
}
