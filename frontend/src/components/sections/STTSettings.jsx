import React from "react";
import { SelectField, TextField, Toggle } from "../Fields";
import { STT_PROVIDERS, STT_MODEL_SUGGESTIONS } from "../../constants/agentOptions";

/**
 * STT settings. `providers` (optional) comes from GET /api/providers and drives
 * the provider dropdown when present; otherwise we fall back to STT_PROVIDERS.
 */
export default function STTSettings({ agent, update, providers }) {
  const providerOptions =
    providers && providers.length
      ? providers.map((p) => ({ value: p.value, label: p.label }))
      : STT_PROVIDERS;

  const suggestions = STT_MODEL_SUGGESTIONS[agent.stt_provider] || [];
  return (
    <section className="builder-section">
      <h3>D. STT Settings</h3>
      <SelectField
        label="Provider"
        value={agent.stt_provider}
        onChange={(v) => update("stt_provider", v)}
        options={providerOptions}
      />
      <TextField
        label="Model"
        value={agent.stt_model}
        onChange={(v) => update("stt_model", v)}
        placeholder={suggestions[0] || "default from .env"}
      />
      <TextField
        label="Language code"
        value={agent.stt_language_code}
        onChange={(v) => update("stt_language_code", v)}
        placeholder="bn-IN / en-IN"
      />
      <Toggle
        label="Auto language detection"
        checked={agent.stt_auto_language_detection}
        onChange={(v) => update("stt_auto_language_detection", v)}
      />
    </section>
  );
}
