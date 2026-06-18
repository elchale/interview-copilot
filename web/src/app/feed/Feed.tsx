"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type FeedEvent = { id: number; kind: string; payload: any };
type Line = { text: string; source: string };
type Answer = { id: string; text: string; status: string; latencyMs?: number | null };
type Status = { recording?: boolean; analyzing?: boolean; listening?: boolean; call_active?: boolean };

export default function Feed() {
  const [lines, setLines] = useState<Line[]>([]);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [status, setStatus] = useState<Status>({});
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const lastBeat = useRef(0); // last time we saw a "recording" heartbeat
  const callActive = useRef(false);
  const cursor = useRef(0);
  const answersRef = useRef<HTMLDivElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const apply = useCallback((evts: FeedEvent[]) => {
    for (const e of evts) {
      const p = e.payload || {};
      switch (e.kind) {
        case "status":
          setStatus((s) => ({ ...s, ...p }));
          callActive.current = !!p.call_active;
          if (p.call_active) lastBeat.current = Date.now();
          break;
        case "transcript":
          setLines((l) => [...l, { text: p.text ?? "", source: p.source ?? "system" }]);
          break;
        case "answer.start":
          setAnswers((a) => [...a, { id: p.answerId, text: "", status: "STREAMING" }]);
          break;
        case "answer.delta":
          setAnswers((a) => a.map((x) => (x.id === p.answerId ? { ...x, text: x.text + (p.text ?? "") } : x)));
          break;
        case "answer.done":
          setAnswers((a) => a.map((x) => (x.id === p.answerId ? { ...x, status: "DONE", latencyMs: p.latencyMs } : x)));
          break;
        case "answer.error":
          setAnswers((a) => a.map((x) => (x.id === p.answerId ? { ...x, status: "ERROR" } : x)));
          break;
      }
    }
  }, []);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      try {
        const res = await fetch(`/api/events?since=${cursor.current}`, { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          cursor.current = data.cursor ?? cursor.current;
          if (data.events?.length) apply(data.events);
          setConnected(true);
        } else if (res.status === 401) {
          window.location.href = "/api/auth/signin?callbackUrl=/feed";
          return;
        }
      } catch {
        setConnected(false);
      }
      // Poll faster while an answer is actively streaming, slower when idle.
      const streaming = status.analyzing || answers.some((a) => a.status === "STREAMING");
      if (!stop) timer = setTimeout(tick, streaming ? 400 : 1000);
    }

    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apply, status.analyzing, answers.length]);

  // Recording is "live heartbeat within the last 12s" — auto-reverts if the agent dies.
  useEffect(() => {
    const t = setInterval(() => {
      setRecording(callActive.current && Date.now() - lastBeat.current < 12000);
    }, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [lines]);
  useEffect(() => {
    if (answersRef.current) answersRef.current.scrollTop = answersRef.current.scrollHeight;
  }, [answers]);

  return (
    <>
      <div className="feed-header">
        <a className="brand" href="/">Interview Copilot</a>
        <div className="status-bar">
          <span><span className={`dot ${connected ? "on" : ""}`} /> {connected ? "connected" : "connecting"}</span>
          <span style={{ fontWeight: 700, color: recording ? "#ef5350" : "#888" }}>
            <span className="dot" style={{ background: recording ? "#ef5350" : "#555" }} />
            {recording ? "RECORDING" : "Not recording"}
          </span>
          <a href="/api/auth/signout">Log out</a>
        </div>
      </div>
      <div className="split">
        <div className="col">
          <h3>Transcript</h3>
          <div className="scroll" ref={transcriptRef}>
            {lines.length === 0 && <div className="empty">Waiting for audio… start a call in the app.</div>}
            {lines.map((l, i) => (
              <div key={i} className={`line ${l.source === "mic" ? "mic" : ""}`}>
                <div className="src">{l.source === "mic" ? "You" : "Interviewer"}</div>
                {l.text}
              </div>
            ))}
          </div>
        </div>
        <div className="col">
          <h3>Answers</h3>
          <div className="scroll" ref={answersRef}>
            {answers.length === 0 && <div className="empty">Suggestions appear here during a call.</div>}
            {answers.map((a) => (
              <div key={a.id} className="answer">
                {a.text}
                {a.status === "DONE" && a.latencyMs != null && (
                  <div className="meta">First token in {a.latencyMs} ms</div>
                )}
                {a.status === "ERROR" && <div className="meta" style={{ color: "var(--red)" }}>Error generating answer</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
