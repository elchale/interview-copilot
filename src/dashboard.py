"""Embedded HTML dashboard — served as a single page by FastAPI."""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Interview Copilot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0f0f0f;--surface:#1a1a1a;--border:#2a2a2a;
  --text:#e0e0e0;--muted:#666;--accent:#4fc3f7;
  --green:#66bb6a;--red:#ef5350;--yellow:#ffd54f;
  --font:'Segoe UI',system-ui,-apple-system,sans-serif;
  --mono:'Cascadia Code','Fira Code',monospace;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px;line-height:1.6}
.container{max-width:1400px;margin:0 auto;padding:20px}
header{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border);margin-bottom:20px}
header h1{font-size:18px;font-weight:600;letter-spacing:-.5px}
.status-bar{display:flex;gap:16px;align-items:center;font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px}
.dot.on{background:var(--green)}
.dot.off{background:var(--muted)}
.dot.pulse{background:var(--accent);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.split{display:grid;grid-template-columns:1fr 1fr;gap:20px;height:calc(100vh - 140px)}
.col{background:var(--surface);border:1px solid var(--border);border-radius:8px;display:flex;flex-direction:column;overflow:hidden}
.col h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0}
.scroll{flex:1;overflow-y:auto;padding:16px}
.scroll::-webkit-scrollbar{width:6px}
.scroll::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.transcript-line{margin-bottom:10px;padding:8px 12px;border-radius:6px;background:#1e1e1e;border-left:3px solid var(--accent)}
.transcript-line.mic{border-left-color:var(--green)}
.transcript-line .source{font-size:10px;text-transform:uppercase;color:var(--muted);margin-bottom:2px}
.answer-block{margin-bottom:16px;padding:12px 16px;border-radius:8px;background:#1a2332;border:1px solid #1e3a5f}
.answer-block pre{background:#0d1117;padding:12px;border-radius:6px;overflow-x:auto;font-family:var(--mono);font-size:13px;margin:8px 0}
.answer-block code{font-family:var(--mono);font-size:13px}
.answer-block .meta{font-size:11px;color:var(--muted);margin-top:8px}
.cursor{display:inline-block;width:2px;height:14px;background:var(--accent);animation:blink .8s infinite;vertical-align:text-bottom}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
.empty{color:var(--muted);text-align:center;padding:40px 20px;font-size:13px}
.sessions-link{position:fixed;bottom:16px;right:16px;background:var(--surface);border:1px solid var(--border);color:var(--accent);padding:8px 16px;border-radius:6px;font-size:12px;cursor:pointer;text-decoration:none}
.sessions-link:hover{background:var(--border)}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Interview Copilot</h1>
    <div class="status-bar">
      <span><span class="dot off" id="dot-conn"></span><span id="lbl-conn">connecting</span></span>
      <span><span class="dot off" id="dot-rec"></span><span id="lbl-rec">idle</span></span>
      <span id="analyzing" style="display:none"><span class="dot pulse"></span>analyzing</span>
    </div>
  </header>
  <div class="split">
    <div class="col">
      <h2>Transcript</h2>
      <div class="scroll" id="transcript">
        <div class="empty" id="transcript-empty">Waiting for audio&hellip;</div>
      </div>
    </div>
    <div class="col">
      <h2>Answers</h2>
      <div class="scroll" id="answers">
        <div class="empty" id="answers-empty">Press <kbd>Ctrl+,</kbd> to generate an answer</div>
      </div>
    </div>
  </div>
</div>
<a class="sessions-link" href="/api/sessions" target="_blank">Session History</a>

<script>
const $ = s => document.querySelector(s);
const transcriptEl = $('#transcript');
const answersEl = $('#answers');
const dotConn = $('#dot-conn');
const lblConn = $('#lbl-conn');
const dotRec = $('#dot-rec');
const lblRec = $('#lbl-rec');
const analyzingEl = $('#analyzing');

let answers = {};

function connect() {
  const es = new EventSource('/api/stream');

  es.addEventListener('init', e => {
    const d = JSON.parse(e.data);
    dotConn.className = 'dot on';
    lblConn.textContent = 'connected';
    if (d.status) updateStatus(d.status);
    if (d.transcript) d.transcript.forEach(t => addTranscript(t.text, t.source));
    if (d.answers) d.answers.forEach(a => {
      if (a.status === 'DONE' || a.status === 'ERROR') {
        addCompletedAnswer(a);
      }
    });
  });

  es.onmessage = e => {
    const d = JSON.parse(e.data);
    switch(d.type) {
      case 'status': updateStatus(d); break;
      case 'transcript': addTranscript(d.text, d.source); break;
      case 'answer.start': startAnswer(d.answerId); break;
      case 'answer.delta': appendDelta(d.answerId, d.text); break;
      case 'answer.done': finishAnswer(d.answerId, d.latencyMs); break;
      case 'answer.error': errorAnswer(d.answerId, d.error); break;
    }
  };

  es.onerror = () => {
    dotConn.className = 'dot off';
    lblConn.textContent = 'disconnected';
    es.close();
    setTimeout(connect, 3000);
  };
}

function updateStatus(s) {
  dotRec.className = s.listening || s.recording ? 'dot on' : 'dot off';
  lblRec.textContent = s.listening || s.recording ? 'recording' : 'idle';
  analyzingEl.style.display = s.analyzing ? '' : 'none';
}

function addTranscript(text, source) {
  const empty = $('#transcript-empty');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'transcript-line' + (source === 'mic' ? ' mic' : '');
  div.innerHTML = '<div class="source">' + (source === 'mic' ? 'You' : 'Interviewer') + '</div>' + escapeHtml(text);
  transcriptEl.appendChild(div);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function startAnswer(id) {
  const empty = $('#answers-empty');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'answer-block';
  div.id = 'ans-' + id;
  div.innerHTML = '<div class="answer-text"></div><span class="cursor"></span>';
  answersEl.appendChild(div);
  answers[id] = '';
  answersEl.scrollTop = answersEl.scrollHeight;
}

function appendDelta(id, text) {
  answers[id] = (answers[id] || '') + text;
  const el = document.getElementById('ans-' + id);
  if (!el) return;
  el.querySelector('.answer-text').innerHTML = renderMarkdown(answers[id]);
  answersEl.scrollTop = answersEl.scrollHeight;
}

function finishAnswer(id, latencyMs) {
  const el = document.getElementById('ans-' + id);
  if (!el) return;
  const cursor = el.querySelector('.cursor');
  if (cursor) cursor.remove();
  if (latencyMs != null) {
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = 'First token in ' + latencyMs + ' ms';
    el.appendChild(meta);
  }
}

function errorAnswer(id, error) {
  const el = document.getElementById('ans-' + id);
  if (!el) return;
  const cursor = el.querySelector('.cursor');
  if (cursor) cursor.remove();
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.style.color = 'var(--red)';
  meta.textContent = 'Error generating answer' + (error ? ': ' + error : '');
  el.appendChild(meta);
}

function addCompletedAnswer(a) {
  const empty = $('#answers-empty');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'answer-block';
  div.id = 'ans-' + a.id;
  let html = '<div class="answer-text">' + renderMarkdown(a.text) + '</div>';
  if (a.latencyMs != null) html += '<div class="meta">First token in ' + a.latencyMs + ' ms</div>';
  if (a.status === 'ERROR') html += '<div class="meta" style="color:var(--red)">Error generating answer</div>';
  div.innerHTML = html;
  answersEl.appendChild(div);
  answers[a.id] = a.text;
}

function renderMarkdown(text) {
  const parts = text.split(/```/);
  return parts.map((p, i) => {
    if (i % 2 === 1) {
      const code = p.replace(/^[a-zA-Z]+\n/, '');
      return '<pre><code>' + escapeHtml(code) + '</code></pre>';
    }
    return escapeHtml(p).replace(/\n/g, '<br>').replace(/`([^`]+)`/g, '<code>$1</code>');
  }).join('');
}

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

connect();
</script>
</body>
</html>"""
