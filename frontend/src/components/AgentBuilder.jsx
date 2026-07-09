import React, { useState, useEffect } from "react";
import "./AgentBuilder.css";
import { DEFAULT_AGENT } from "../constants/agentOptions";
import { agentsApi, providersApi } from "../api/agents";
import BasicDetails from "./sections/BasicDetails";
import Knowledgebase from "./sections/Knowledgebase";
import LLMSettings from "./sections/LLMSettings";
import STTSettings from "./sections/STTSettings";
import TTSSettings from "./sections/TTSSettings";
import VADSettings from "./sections/VADSettings";
import NoiseCancellationSettings from "./sections/NoiseCancellationSettings";

/**
 * Agent Builder.
 * Pass an existing agent via `initial` to edit; omit it to create a new one.
 * `onSaved(agent)` fires after a successful create/update.
 */
export default function AgentBuilder({ initial, onSaved }) {
  const [agent, setAgent] = useState(initial || DEFAULT_AGENT);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  // Backend-advertised providers (capability-aware). Falls back to constants
  // inside each section if this stays null (e.g. older backend / fetch fails).
  const [providers, setProviders] = useState(null);

  useEffect(() => {
    let alive = true;
    providersApi
      .get()
      .then((data) => {
        if (alive) setProviders(data);
      })
      .catch(() => {
        /* keep null -> sections use hardcoded fallback constants */
      });
    return () => {
      alive = false;
    };
  }, []);

  function update(field, value) {
    setAgent((prev) => ({ ...prev, [field]: value }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = agent.id
        ? await agentsApi.update(agent.id, agent)
        : await agentsApi.create(agent);
      setAgent(saved);
      onSaved?.(saved);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="agent-builder">
      <header className="builder-header">
        <h2>{agent.id ? "Edit Agent" : "Create Agent"}</h2>
      </header>

      <div className="builder-grid">
        <BasicDetails agent={agent} update={update} />
        <Knowledgebase agent={agent} update={update} />
        <LLMSettings agent={agent} update={update} />
        <STTSettings agent={agent} update={update} providers={providers?.stt} />
        <TTSSettings agent={agent} update={update} providers={providers?.tts} />
        <VADSettings agent={agent} update={update} />
        <NoiseCancellationSettings agent={agent} update={update} providers={providers?.noise_cancellation} />
      </div>

      {error && <div className="builder-error">{error}</div>}

      <footer className="builder-footer">
        {/* G. Save Agent */}
        <button className="save-btn" onClick={save} disabled={saving || !agent.name}>
          {saving ? "Saving…" : "Save Agent"}
        </button>
      </footer>
    </div>
  );
}
