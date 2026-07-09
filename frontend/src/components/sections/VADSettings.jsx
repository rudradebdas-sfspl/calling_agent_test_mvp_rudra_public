import React, { useEffect, useState } from "react";
import { SelectField, NumberField, Slider, Toggle } from "../Fields";
import { VAD_MODES } from "../../constants/agentOptions";
import { agentsApi } from "../../api/agents";

export default function VADSettings({ agent, update }) {
  const [presets, setPresets] = useState({});

  useEffect(() => {
    agentsApi.vadPresets().then(setPresets).catch(() => {});
  }, []);

  // When a preset mode is chosen, snap the numeric fields to the preset values
  // (mirrors the backend's normalisation so the UI matches what gets saved).
  function onModeChange(mode) {
    update("vad_mode", mode);
    const p = presets[mode];
    if (p && p.threshold !== undefined) {
      update("vad_threshold", p.threshold);
      update("vad_min_speech_ms", p.min_speech_ms);
      update("vad_min_silence_ms", p.min_silence_ms);
      update("vad_speech_pad_ms", p.speech_pad_ms);
    }
  }

  const isCustom = agent.vad_mode === "custom";
  const note = presets[agent.vad_mode]?.note;

  return (
    <section className="builder-section">
      <h3>F. VAD / Turn Detection</h3>
      <Toggle label="Enable VAD" checked={agent.vad_enabled} onChange={(v) => update("vad_enabled", v)} />
      <SelectField label="Provider" value={agent.vad_provider} onChange={(v) => update("vad_provider", v)} options={["silero"]} />
      <SelectField label="Mode" value={agent.vad_mode} onChange={onModeChange} options={VAD_MODES} />
      {note && <p className="hint">{note}</p>}

      <Slider
        label="Threshold"
        value={agent.vad_threshold}
        onChange={(v) => update("vad_threshold", v)}
        min={0}
        max={1}
        step={0.01}
        disabled={!isCustom}
      />
      <NumberField label="Min speech (ms)" value={agent.vad_min_speech_ms} onChange={(v) => update("vad_min_speech_ms", v)} min={0} max={5000} step={10} />
      <NumberField label="Min silence (ms)" value={agent.vad_min_silence_ms} onChange={(v) => update("vad_min_silence_ms", v)} min={0} max={5000} step={10} />
      <NumberField label="Speech padding (ms)" value={agent.vad_speech_pad_ms} onChange={(v) => update("vad_speech_pad_ms", v)} min={0} max={2000} step={10} />

      {!isCustom && (
        <p className="hint">Threshold/timing are locked to the preset. Choose “Custom” to edit them.</p>
      )}
    </section>
  );
}
