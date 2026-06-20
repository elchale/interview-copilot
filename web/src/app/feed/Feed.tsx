"use client";

import { Fragment, ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnswerBody } from "./AnswerBody";

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

// Scroll container that keeps your reading position when new content streams in
// above you (newest-first). If you're parked on an older answer, a new one no
// longer yanks you to the top — a pill appears so you jump up only when you want.
function ScrollList<T>({
  items,
  itemKey,
  render,
  newLabel,
}: {
  items: T[];
  itemKey: (item: T) => string | number;
  render: (item: T) => ReactNode;
  newLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const prevH = useRef(0);
  const [hasNew, setHasNew] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const newH = el.scrollHeight;
    const atTop = el.scrollTop <= 24;
    if (!atTop && newH > prevH.current) {
      // Content grew above the viewport — counter-scroll so what you're reading stays put.
      el.scrollTop += newH - prevH.current;
      setHasNew(true);
    }
    prevH.current = newH;
  });

  const onScroll = () => {
    const el = ref.current;
    if (el && el.scrollTop <= 24) setHasNew(false);
  };
  const jumpTop = () => {
    ref.current?.scrollTo({ top: 0, behavior: "smooth" });
    setHasNew(false);
  };

  return (
    <div className="scroll-wrap">
      {hasNew && (
        <button className="newpill" onClick={jumpTop}>
          ↑ {newLabel}
        </button>
      )}
      <div ref={ref} className="scroll-list" onScroll={onScroll}>
        {items.map((it) => (
          <Fragment key={itemKey(it)}>{render(it)}</Fragment>
        ))}
      </div>
    </div>
  );
}

async function requestReanswer(question: string): Promise<boolean> {
  try {
    const res = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "reanswer", payload: { question } }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function AnswerCard({ a }: { a: Answer }) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "fail">("idle");
  const streaming = a.status === "STREAMING";

  const reAnswer = async () => {
    setState("sending");
    const ok = await requestReanswer(a.question || a.text || "");
    setState(ok ? "sent" : "fail");
    setTimeout(() => setState("idle"), 2500);
  };

  const label =
    state === "sending" ? "Re-answering…" :
    state === "sent" ? "Requested ✓" :
    state === "fail" ? "Agent offline?" : "↻ Re-answer";

  return (
    <div className={`answer ${streaming ? "live" : ""}`}>
      {a.question ? <div className="qhighlight">{a.question}</div> : null}
      <AnswerBody text={a.text || (streaming ? "…" : "")} />
      <div className="answer-foot">
        {a.status === "DONE" && a.latencyMs != null && (
          <span className="meta">First token in {a.latencyMs} ms</span>
        )}
        {a.status === "ERROR" && <span className="meta" style={{ color: "var(--red)" }}>Error generating answer</span>}
        {!streaming && (
          <button className="reanswer-btn" onClick={reAnswer} disabled={state === "sending"}>
            {label}
          </button>
        )}
      </div>
    </div>
  );
}

function AnswersView({ answers }: { answers: Answer[] }) {
  if (answers.length === 0) return <div className="empty">Suggestions appear here during a call.</div>;
  return (
    <ScrollList
      items={[...answers].reverse()}
      itemKey={(a) => a.id}
      newLabel="New answer"
      render={(a) => <AnswerCard a={a} />}
    />
  );
}

function TranscriptView({ lines }: { lines: Line[] }) {
  if (lines.length === 0) return <div className="empty">Waiting for audio… start a call in the app.</div>;
  return (
    <ScrollList
      items={[...lines].reverse()}
      itemKey={(l) => l.id}
      newLabel="New line"
      render={(l) => (
        <div className={`line ${l.source === "mic" ? "mic" : ""}`}>
          <div className="src">{l.source === "mic" ? "You" : "Interviewer"}</div>
          {l.text}
        </div>
      )}
    />
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
    <ScrollList
      items={[...contexts].reverse()}
      itemKey={(c) => c.id}
      newLabel="New context"
      render={(c) => {
        const note = NOTE_META[c.kind];
        if (note) {
          return (
            <div className={`ctx note ${c.kind}`}>
              <div className="ctx-kind">
                <span className="ctx-icon">{note.icon}</span> {note.label}
              </div>
              <div className="ctx-note-text">{c.text}</div>
            </div>
          );
        }
        if (c.kind === "query") {
          return (
            <div className="ctx query">
              <span className="ctx-icon">🔎</span> Searched <span className="ctx-q">{c.text}</span>
            </div>
          );
        }
        return (
          <a className="ctx source" href={c.url || "#"} target="_blank" rel="noopener noreferrer">
            <div className="ctx-title">{c.text || c.url}</div>
            {c.url && <div className="ctx-url">{prettyHost(c.url)}</div>}
          </a>
        );
      }}
    />
  );
}

function prettyHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
