import React from "react";
import { SelectField, Toggle } from "../Fields";
import { NC_PROVIDERS } from "../../constants/agentOptions";

export default function NoiseCancellationSettings({ agent, update, providers }) {
  // providers (from /api/providers .noise_cancellation) overrides the fallback list.
  const options =
    providers && providers.length
      ? providers.map((p) => ({ value: p.value, label: p.label }))
      : NC_PROVIDERS;

  return (
    <section className="builder-section">
      <h3>G. Noise Cancellation</h3>
      <Toggle
        label="Enable noise cancellation"
        checked={agent.noise_cancellation_enabled}
        onChange={(v) => update("noise_cancellation_enabled", v)}
      />
      {agent.noise_cancellation_enabled && (
        <>
          <SelectField
            label="Provider"
            value={agent.noise_cancellation_provider}
            onChange={(v) => update("noise_cancellation_provider", v)}
            options={options}
          />
          <p className="hint">
            Suppresses background noise / other speakers in real time while
            preserving the caller's voice. The SDK license is read from the
            server's .env — never entered here. If the SDK or license is missing,
            audio passes through unchanged so calls are never broken.
          </p>
        </>
      )}
    </section>
  );
}
