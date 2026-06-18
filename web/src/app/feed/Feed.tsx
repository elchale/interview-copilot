"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type FeedEvent = { id: number; kind: string; payload: any };
type Line = { id: number; text: string; source: string };
type Answer = { id: string; text: string; status: string; latencyMs?: number | null; question?: string };
type Ctx = { id: number; kind: string; text: string; url?: string; answerId?: string | null };
type Status = { recording?: boolean; analyzing?: boolean; listening?: boolean; call_active?: boolean };

type TabKey = "answers" | "transcript" | "context";
const TABS: { key: TabKey; label: string }[] = [
  { key: "answers", label: "Answers" },
  { key: "transcript", label: "Transcript" },
  { key: "context", label: "Context" },
];

export default function Feed() {
  const [lines, setLines] = useState<Line[]>([]);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [contexts, setContexts] = useState<Ctx[]>([]);
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);

  // Layout: which feed each pane shows, and whether the screen is split in two.
  const [split, setSplit] = useState(false);
  const [paneA, setPaneA] = useState<TabKey>("answers");
  const [paneB, setPaneB] = useState<TabKey>("transcript");

  const [clearing, setClearing] = useState(false);

  const lastBeat = useRef(0); // last time we saw a "recording" heartbeat
  const callActive = useRef(false);
  const cursor = useRef(0);
  const seen = useRef<Set<number>>(new Set()); // event ids already applied — kills duplicates
  const streaming = useRef(false); // poll faster while an answer streams

  const clearHistory = useCallback(async () => {
    if (!confirm("Clear all history (transcript, answers, context)? This can't be undone.")) return;
    setClearing(true);
    try {
      const res = await fetch("/api/clear", { method: "POST" });
      if (res.ok) {
        setLines([]);
        setAnswers([]);
        setContexts([]);
        seen.current.clear();
        cursor.current = 0;
      }
    } catch {
      /* leave history in place on failure */
    } finally {
      setClearing(false);
    }
  }, []);

  const apply = useCallback((evts: FeedEvent[]) => {
    for (const e of evts) {
      if (seen.current.has(e.id)) continue; // dedupe: never apply the same event twice
      seen.current.add(e.id);
      const p = e.payload || {};
      switch (e.kind) {
        case "status":
          callActive.current = !!p.call_active;
          if (p.call_active) lastBeat.current = Date.now();
          break;
        case "transcript":
          setLines((l) => [...l, { id: e.id, text: p.text ?? "", source: p.source ?? "system" }]);
          break;
        case "context":
          setContexts((c) => [
            ...c,
            { id: e.id, kind: p.kind ?? "source", text: p.text ?? "", url: p.url ?? "", answerId: p.answerId ?? null },
          ]);
          break;
        case "answer.start":
          streaming.current = true;
          setAnswers((a) => [...a, { id: p.answerId, text: "", status: "STREAMING", question: p.question ?? "" }]);
          break;
        case "answer.delta":
          setAnswers((a) => a.map((x) => (x.id === p.answerId ? { ...x, text: x.text + (p.text ?? "") } : x)));
          break;
        case "answer.done":
          streaming.current = false;
          setAnswers((a) => a.map((x) => (x.id === p.answerId ? { ...x, status: "DONE", latencyMs: p.latencyMs } : x)));
          break;
        case "answer.error":
          streaming.current = false;
          setAnswers((a) => a.map((x) => (x.id === p.answerId ? { ...x, status: "ERROR" } : x)));
          break;
      }
    }
  }, []);

  // Single, stable polling loop — never re-created, so concurrent fetches can't
  // double-apply the same window of events (the old duplication bug).
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      try {
        const res = await fetch(`/api/events?since=${cursor.current}`, { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (data.events?.length) apply(data.events);
          cursor.current = data.cursor ?? cursor.current;
          setConnected(true);
        } else if (res.status === 401) {
          window.location.href = "/api/auth/signin?callbackUrl=/feed";
          return;
        }
      } catch {
        setConnected(false);
      }
      if (!stop) timer = setTimeout(tick, streaming.current ? 400 : 1000);
    }

    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [apply]);

  // Recording is "live heartbeat within the last 12s" — auto-reverts if the agent dies.
  useEffect(() => {
    const t = setInterval(() => {
      setRecording(callActive.current && Date.now() - lastBeat.current < 12000);
    }, 1000);
    return () => clearInterval(t);
  }, []);

  const renderPane = (tab: TabKey, setTab: (t: TabKey) => void) => (
    <section className="pane">
      <div className="pane-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`chip ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="pane-body">
        {tab === "answers" && <AnswersView answers={answers} />}
        {tab === "transcript" && <TranscriptView lines={lines} />}
        {tab === "context" && <ContextView contexts={contexts} />}
      </div>
    </section>
  );

  return (
    <>
      <div className="feed-header">
        <a className="brand" href="/">Interview Copilot</a>
        <div className="status-bar">
          <span><span className={`dot ${connected ? "on" : ""}`} /> {connected ? "connected" : "connecting"}</span>
          <span style={{ fontWeight: 700, color: recording ? "var(--red)" : "var(--muted)" }}>
            <span className="dot" style={{ background: recording ? "var(--red)" : "#555" }} />
            {recording ? "RECORDING" : "Not recording"}
          </span>
          <button className="splitbtn" onClick={() => setSplit((s) => !s)}>
            {split ? "Single view" : "Split view"}
          </button>
          <button className="splitbtn danger" onClick={clearHistory} disabled={clearing}>
            {clearing ? "Clearing…" : "Clear history"}
          </button>
          <a href="/settings">Settings</a>
          <a href="/api/auth/signout">Log out</a>
        </div>
      </div>

      <div className={`panes ${split ? "is-split" : ""}`}>
        {renderPane(paneA, setPaneA)}
        {split && renderPane(paneB, setPaneB)}
      </div>
    </>
  );
}

// Newest first everywhere — so the latest item is always at the top of the feed.

function AnswersView({ answers }: { answers: Answer[] }) {
  if (answers.length === 0) return <div className="empty">Suggestions appear here during a call.</div>;
  return (
    <>
      {[...answers].reverse().map((a) => (
        <div key={a.id} className={`answer ${a.status === "STREAMING" ? "live" : ""}`}>
          {a.question ? <div className="qhighlight">{a.question}</div> : null}
          <div className="atext">{a.text || (a.status === "STREAMING" ? "…" : "")}</div>
          {a.status === "DONE" && a.latencyMs != null && (
            <div className="meta">First token in {a.latencyMs} ms</div>
          )}
          {a.status === "ERROR" && <div className="meta" style={{ color: "var(--red)" }}>Error generating answer</div>}
        </div>
      ))}
    </>
  );
}

function TranscriptView({ lines }: { lines: Line[] }) {
  if (lines.length === 0) return <div className="empty">Waiting for audio… start a call in the app.</div>;
  return (
    <>
      {[...lines].reverse().map((l) => (
        <div key={l.id} className={`line ${l.source === "mic" ? "mic" : ""}`}>
          <div className="src">{l.source === "mic" ? "You" : "Interviewer"}</div>
          {l.text}
        </div>
      ))}
    </>
  );
}

const NOTE_META: Record<string, { icon: string; label: string }> = {
  summary: { icon: "📝", label: "Summary" },
  fact: { icon: "📌", label: "Good to know" },
  topic: { icon: "💡", label: "Context" },
};

function ContextView({ contexts }: { contexts: Ctx[] }) {
  if (contexts.length === 0)
    return <div className="empty">Live context about what&apos;s being discussed appears here during a call.</div>;
  return (
    <>
      {[...contexts].reverse().map((c) => {
        const note = NOTE_META[c.kind];
        if (note) {
          return (
            <div key={c.id} className={`ctx note ${c.kind}`}>
              <div className="ctx-kind">
                <span className="ctx-icon">{note.icon}</span> {note.label}
              </div>
              <div className="ctx-note-text">{c.text}</div>
            </div>
          );
        }
        if (c.kind === "query") {
          return (
            <div key={c.id} className="ctx query">
              <span className="ctx-icon">🔎</span> Searched <span className="ctx-q">{c.text}</span>
            </div>
          );
        }
        return (
          <a
            key={c.id}
            className="ctx source"
            href={c.url || "#"}
            target="_blank"
            rel="noopener noreferrer"
          >
            <div className="ctx-title">{c.text || c.url}</div>
            {c.url && <div className="ctx-url">{prettyHost(c.url)}</div>}
          </a>
        );
      })}
    </>
  );
}

function prettyHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
