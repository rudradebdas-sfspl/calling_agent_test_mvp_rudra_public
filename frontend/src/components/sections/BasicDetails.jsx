import React from "react";
import { TextField, TextArea, Toggle } from "../Fields";

export default function BasicDetails({ agent, update }) {
  return (
    <section className="builder-section">
      <h3>A. Basic Details</h3>
      <TextField label="Agent name" value={agent.name} onChange={(v) => update("name", v)} placeholder="Support Bot" />
      <TextArea label="Description" value={agent.description} onChange={(v) => update("description", v)} />
      <TextField label="Language" value={agent.language} onChange={(v) => update("language", v)} placeholder="en-IN" />
      <TextArea
        label="System prompt"
        rows={5}
        value={agent.system_prompt}
        onChange={(v) => update("system_prompt", v)}
        placeholder="You are a polite IT support assistant…"
      />
      <TextField
        label="Call Transfer Number"
        value={agent.call_transfer_number || ""}
        onChange={(v) => update("call_transfer_number", v)}
        placeholder="+91xxxxxxxxxx"
      />
      <Toggle label="Active" checked={agent.is_active} onChange={(v) => update("is_active", v)} />
    </section>
  );
}
