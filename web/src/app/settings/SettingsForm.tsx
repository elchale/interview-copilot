"use client";

import { useState } from "react";

export default function SettingsForm({ initial }: { initial: string }) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");

  async function save() {
    setSaving(true);
    setStatus("idle");
    try {
      const res = await fetch("/api/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ systemPrompt: value }),
      });
      setStatus(res.ok ? "saved" : "error");
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <textarea
        className="prompt-area"
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setStatus("idle");
        }}
        placeholder="e.g. I'm a senior full-stack engineer with 8 years of experience…"
        rows={16}
        maxLength={8000}
      />
      <div className="prompt-actions">
        <button className="btn" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <span className="muted">{value.length}/8000</span>
        {status === "saved" && <span style={{ color: "var(--green)" }}>Saved ✓</span>}
        {status === "error" && <span style={{ color: "var(--red)" }}>Couldn&apos;t save — try again</span>}
      </div>
    </div>
  );
}
