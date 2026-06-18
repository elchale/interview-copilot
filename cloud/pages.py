"""Server-rendered HTML pages for the cloud site (landing, settings, pairing)."""

from __future__ import annotations

import html

# The live feed reuses the local dashboard verbatim — it already talks to
# /api/stream over SSE, which the cloud app serves per-user.
from src.dashboard import DASHBOARD_HTML as FEED_HTML

_BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f0f0f;color:#e0e0e0;font-family:'Segoe UI',system-ui,sans-serif;line-height:1.6}
a{color:#4fc3f7}
.wrap{max-width:860px;margin:0 auto;padding:48px 24px}
.btn{display:inline-block;background:#4fc3f7;color:#0a0a0a;font-weight:600;padding:12px 22px;
  border-radius:8px;text-decoration:none;margin:6px 8px 6px 0}
.btn.alt{background:#1a1a1a;color:#e0e0e0;border:1px solid #2a2a2a}
.card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;padding:24px;margin:20px 0}
h1{font-size:30px;letter-spacing:-.5px;margin-bottom:10px}
h2{font-size:16px;text-transform:uppercase;letter-spacing:.5px;color:#888;margin:24px 0 8px}
.muted{color:#888}
ol{margin:8px 0 0 20px}li{margin:4px 0}
input,textarea,select{width:100%;background:#0d0d0d;border:1px solid #2a2a2a;color:#e0e0e0;
  padding:10px;border-radius:6px;font-family:inherit;margin:4px 0 14px}
label{font-size:13px;color:#aaa}
.topbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #2a2a2a;
  padding:14px 24px}
"""


def _shell(title: str, body: str, account: str = "") -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>{_BASE_CSS}</style></head><body>
<div class="topbar"><a href="/" style="font-weight:600;text-decoration:none;color:#e0e0e0">Interview Copilot</a>
<div>{account}</div></div>
<div class="wrap">{body}</div></body></html>"""


def landing_page(*, exe_url: str, installer_url: str, logged_in: bool) -> str:
    account = '<a href="/app">Open feed</a> &nbsp; <a href="/logout">Log out</a>' if logged_in \
        else '<a href="/login">Log in</a>'
    body = f"""
    <h1>Your AI copilot for live interviews.</h1>
    <p class="muted">Install the capture app on Windows. It listens to your call, detects every
    question, and streams ready-to-read answers to this site — on any device you're logged into.</p>

    <div class="card">
      <h2>1 · Download</h2>
      <a class="btn" href="{html.escape(installer_url)}">Download installer (.exe)</a>
      <a class="btn alt" href="{html.escape(exe_url)}">Portable .exe</a>
      <p class="muted" style="margin-top:10px">Windows 10/11. Everything else (ffmpeg, etc.) is bundled.</p>
    </div>

    <div class="card">
      <h2>2 · How it works</h2>
      <ol>
        <li>Run the app. It opens this site to sign in with Google.</li>
        <li>After login it says <em>"you can go back to the app"</em> and opens your live feed.</li>
        <li>Add your Deepgram + Anthropic API keys in <a href="/settings">Settings</a> (bring your own).</li>
        <li>Start a call from the app — questions and answers appear here in real time.</li>
      </ol>
    </div>

    <p class="muted">{'You are signed in.' if logged_in else ''}
      <a href="/login">{'' if logged_in else 'Sign in with Google →'}</a></p>
    """
    return _shell("Interview Copilot", body, account)


def settings_page(*, email: str, has_deepgram: bool, has_anthropic: bool,
                  answer_mode: str, persona: str, web_search: bool, saved: bool) -> str:
    def opt(v: str) -> str:
        sel = " selected" if v == answer_mode else ""
        return f'<option value="{v}"{sel}>{v}</option>'
    modes = "".join(opt(m) for m in ("GENERAL", "CODING", "BEHAVIORAL", "SYSTEM_DESIGN", "MATH"))
    saved_banner = '<div class="card" style="border-color:#2e7d32">Saved.</div>' if saved else ""
    body = f"""
    <h1>Settings</h1><p class="muted">{html.escape(email)}</p>
    {saved_banner}
    <form method="post" action="/settings" class="card">
      <h2>API keys (bring your own)</h2>
      <label>Deepgram API key {'— set ✓' if has_deepgram else '— not set'}</label>
      <input type="password" name="deepgram_key" placeholder="{'•••••• (leave blank to keep)' if has_deepgram else 'dg_...'}" autocomplete="off">
      <label>Anthropic API key {'— set ✓' if has_anthropic else '— not set'}</label>
      <input type="password" name="anthropic_key" placeholder="{'•••••• (leave blank to keep)' if has_anthropic else 'sk-ant-...'}" autocomplete="off">

      <h2>Answer style</h2>
      <label>Mode</label><select name="answer_mode">{modes}</select>
      <label>Persona / background (optional)</label>
      <textarea name="persona" rows="4" placeholder="Senior backend engineer, 8 yrs Python...">{html.escape(persona)}</textarea>
      <label><input type="checkbox" name="enable_web_search" {'checked' if web_search else ''} style="width:auto"> Use web search in answers</label>
      <div style="margin-top:16px"><button class="btn" type="submit">Save</button>
      <a class="btn alt" href="/app">Open feed</a></div>
    </form>
    """
    return _shell("Settings", body, '<a href="/app">Feed</a> &nbsp; <a href="/logout">Log out</a>')


def pair_success_page() -> str:
    body = """
    <div class="card" style="text-align:center;border-color:#2e7d32">
      <h1>✓ All set</h1>
      <p>Your app is connected. You can go back to the app — opening your live feed now…</p>
      <p style="margin-top:14px"><a class="btn" href="/app">Open feed</a></p>
    </div>
    <script>setTimeout(function(){window.location.href='/app';}, 1800);</script>
    """
    return _shell("Connected", body)
