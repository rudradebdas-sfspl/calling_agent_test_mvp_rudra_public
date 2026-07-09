import React from "react";
import { SelectField, TextField, TextArea, Slider } from "../Fields";
import { TTS_PROVIDERS, TTS_TONES } from "../../constants/agentOptions";

/**
 * TTS settings. `providers` (optional) comes from GET /api/providers and, when
 * present, drives the provider dropdown + per-provider UI hints. If it is not
 * supplied we fall back to the hardcoded TTS_PROVIDERS constant.
 */
export default function TTSSettings({ agent, update, providers }) {
  const providerOptions =
    providers && providers.length
      ? providers.map((p) => ({ value: p.value, label: p.label }))
      : TTS_PROVIDERS;

  const selected = (providers || []).find((p) => p.value === agent.tts_provider);
  const isCartesia = agent.tts_provider === "cartesia";

  // Cartesia voice ID is optional: blank => backend uses env voice by language.
  const voiceHelp = isCartesia
    ? "Voice ID is optional. If blank, backend will use the Cartesia voice ID from env based on selected language."
    : "Optional. Provider-specific speaker/voice ID.";

  return (
    <section className="builder-section">
      <h3>E. TTS Settings</h3>
      <SelectField
        label="Provider"
        value={agent.tts_provider}
        onChange={(v) => update("tts_provider", v)}
        options={providerOptions}
      />
      <TextField
        label="Voice ID"
        value={agent.cartesia_voice_id}
        onChange={(v) => update("cartesia_voice_id", v)}
        placeholder={isCartesia ? "optional — env by language" : "optional"}
      />
      <p className="hint">{voiceHelp}</p>
      <TextField label="TTS language" value={agent.tts_language} onChange={(v) => update("tts_language", v)} placeholder="en" />
      <SelectField label="Tone" value={agent.tts_tone} onChange={(v) => update("tts_tone", v)} options={TTS_TONES} />
      <Slider label="Speed" value={agent.tts_speed} onChange={(v) => update("tts_speed", v)} min={0.25} max={3} step={0.05} />
      <Slider label="Pitch" value={agent.tts_pitch} onChange={(v) => update("tts_pitch", v)} min={-12} max={12} step={0.5} />
      <Slider label="Volume" value={agent.tts_volume} onChange={(v) => update("tts_volume", v)} min={0} max={2} step={0.05} />
      <TextField
        label="Emotion / style"
        value={agent.tts_emotion}
        onChange={(v) => update("tts_emotion", v)}
        placeholder="e.g. positivity:high"
      />
      {agent.tts_tone === "custom" && (
        <TextArea
          label="Custom style prompt"
          value={agent.tts_style_prompt}
          onChange={(v) => update("tts_style_prompt", v)}
          placeholder="Speak politely, slowly, and clearly like a professional Indian IT support executive."
        />
      )}
      {selected && selected.supports_tone === false && (
        <p className="hint">Note: {selected.label} ignores tone/emotion controls.</p>
      )}
      <p className="hint">
        Pitch &amp; volume aren't native Cartesia controls; the worker applies them
        to the returned audio. Tone maps to Cartesia speed/emotion inside the
        Cartesia provider's mapper.
      </p>
    </section>
  );
}
