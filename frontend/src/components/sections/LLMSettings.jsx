import React from "react";
import { SelectField, TextField, NumberField, Slider } from "../Fields";
import { LLM_PROVIDERS, LLM_MODEL_SUGGESTIONS } from "../../constants/agentOptions";

export default function LLMSettings({ agent, update }) {
  const suggestions = LLM_MODEL_SUGGESTIONS[agent.llm_provider] || [];
  return (
    <section className="builder-section">
      <h3>C. LLM / SLM Settings</h3>
      <SelectField
        label="Provider"
        value={agent.llm_provider}
        onChange={(v) => update("llm_provider", v)}
        options={LLM_PROVIDERS}
      />
      <TextField
        label="Model"
        value={agent.llm_model}
        onChange={(v) => update("llm_model", v)}
        placeholder={suggestions[0] || "model name"}
      />
      {suggestions.length > 0 && (
        <p className="hint">Suggested: {suggestions.join(", ")}</p>
      )}
      <Slider label="Temperature" value={agent.temperature} onChange={(v) => update("temperature", v)} min={0} max={2} step={0.05} />
      <NumberField
        label="Max response tokens"
        value={agent.max_response_tokens}
        onChange={(v) => update("max_response_tokens", v)}
        min={16}
        max={8192}
        step={16}
      />
      <p className="hint">API keys are read from the server's .env — never entered here.</p>
    </section>
  );
}
