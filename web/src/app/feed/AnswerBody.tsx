"use client";

import { ReactNode, useState } from "react";

// Lightweight markdown-ish renderer tuned for streamed interview answers:
// natural prose plus the occasional fenced code block. Dependency-free so it
// can't break the Vercel build, and tolerant of partial markdown while a code
// fence is still streaming (an unterminated ``` renders as an open code block).

type Seg =
  | { type: "prose"; text: string }
  | { type: "code"; lang: string; code: string };

function parseSegments(src: string): Seg[] {
  const segs: Seg[] = [];
  // ```lang\n …code… ``` — the closing fence is optional so a still-streaming
  // block (no closer yet) is captured and shown instead of swallowing the rest.
  const fence = /```([^\n`]*)\n?([\s\S]*?)(?:\n?```|$)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = fence.exec(src)) !== null) {
    if (m.index > last) {
      const prose = src.slice(last, m.index);
      if (prose.trim()) segs.push({ type: "prose", text: prose });
    }
    segs.push({ type: "code", lang: (m[1] || "").trim(), code: m[2] ?? "" });
    last = fence.lastIndex;
    if (m.index === fence.lastIndex) fence.lastIndex++; // guard against zero-width
  }
  if (last < src.length) {
    const prose = src.slice(last);
    if (prose.trim()) segs.push({ type: "prose", text: prose });
  }
  return segs;
}

// Inline `code` and **bold** within a line of prose.
function renderInline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("`")) {
      out.push(<code key={`${keyBase}-${i++}`} className="inline-code">{tok.slice(1, -1)}</code>);
    } else {
      out.push(<strong key={`${keyBase}-${i++}`}>{tok.slice(2, -2)}</strong>);
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function Prose({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const isList = lines.every((l) => /^\s*[-*]\s+/.test(l)) && lines.length > 0;
        if (isList) {
          return (
            <ul key={bi} className="ans-list">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.replace(/^\s*[-*]\s+/, ""), `${bi}-${li}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi} className="ans-p">
            {lines.map((l, li) => (
              <span key={li}>
                {renderInline(l, `${bi}-${li}`)}
                {li < lines.length - 1 ? <br /> : null}
              </span>
            ))}
          </p>
        );
      })}
    </>
  );
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const body = code.replace(/\n+$/, "");
  const lineCount = body ? body.split("\n").length : 0;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard blocked — ignore */
    }
  };

  return (
    <div className="codeblock">
      <div className="cb-head">
        <button className="cb-toggle" onClick={() => setOpen((o) => !o)}>
          <span className="cb-caret">{open ? "▾" : "▸"}</span>
          {lang || "code"}
          {!open && lineCount ? <span className="cb-count"> · {lineCount} lines</span> : null}
        </button>
        <button className="cb-copy" onClick={copy}>
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      {open && (
        <pre className="cb-pre">
          <code>{body}</code>
        </pre>
      )}
    </div>
  );
}

export function AnswerBody({ text }: { text: string }) {
  const segs = parseSegments(text);
  return (
    <div className="ans-body">
      {segs.map((s, i) =>
        s.type === "code" ? (
          <CodeBlock key={i} lang={s.lang} code={s.code} />
        ) : (
          <Prose key={i} text={s.text} />
        )
      )}
    </div>
  );
}
