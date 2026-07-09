// Tiny fetch wrapper for the Agent Builder. Set VITE_API_BASE in your .env.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

export const agentsApi = {
  list: () => request("/api/agents"),
  get: (id) => request(`/api/agents/${id}`),
  create: (data) => request("/api/agents", { method: "POST", body: JSON.stringify(data) }),
  update: (id, data) =>
    request(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  remove: (id) => request(`/api/agents/${id}`, { method: "DELETE" }),
  vadPresets: () => request("/api/agents/vad-presets"),
  setSipDefault: (id) => request(`/api/agents/${id}/set-sip-default`, { method: "POST" }),
};

export const providersApi = {
  // Returns { tts: [...], stt: [...] } with per-provider capability hints.
  get: () => request("/api/providers"),
};

export const sessionsApi = {
  start: (agentId) =>
    request("/api/sessions/start", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId }),
    }),
};

export const kbApi = {
  list: (agentId) => request(`/api/agents/${agentId}/kb`),
  upload: async (agentId, files) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    const res = await fetch(`${API_BASE}/api/agents/${agentId}/kb`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json();
  },
  deleteFile: (agentId, filename) =>
    request(`/api/agents/${agentId}/kb/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),

  // ---- Troubleshooting Excel (structured KB: kb_entries + policy_rules) ----
  troubleshootingSummary: (agentId) =>
    request(`/api/agents/${agentId}/troubleshooting`),
  uploadTroubleshooting: async (agentId, file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/agents/${agentId}/troubleshooting`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json();
  },
  clearTroubleshooting: (agentId) =>
    request(`/api/agents/${agentId}/troubleshooting`, { method: "DELETE" }),

  // ---- Custom policy rules (added from the UI, stored in policy_rules) ----
  listPolicies: (agentId) => request(`/api/agents/${agentId}/policy`),
  addPolicy: (agentId, rule) =>
    request(`/api/agents/${agentId}/policy`, {
      method: "POST",
      body: JSON.stringify(rule),
    }),
  deletePolicy: (agentId, ruleId) =>
    request(`/api/agents/${agentId}/policy/${encodeURIComponent(ruleId)}`, {
      method: "DELETE",
    }),
};