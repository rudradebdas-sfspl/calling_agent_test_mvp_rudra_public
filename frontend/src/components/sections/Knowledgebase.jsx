import React, { useCallback, useEffect, useRef, useState } from "react";
import { Toggle } from "../Fields";
import { kbApi } from "../../api/agents";

// Shared input style for the policy form.
const inp = {
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid #3a3a3a",
  background: "#1b1b1b",
  color: "#eee",
  fontSize: 13,
  width: "100%",
  boxSizing: "border-box",
};

export default function Knowledgebase({ agent, update }) {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef();

  // ---- troubleshooting Excel state ----
  const [tsSummary, setTsSummary] = useState(null);
  const [tsUploading, setTsUploading] = useState(false);
  const [tsError, setTsError] = useState(null);
  const tsInputRef = useRef();

  const loadFiles = useCallback(async () => {
    if (!agent.id || !agent.kb_enabled) return;
    try {
      const data = await kbApi.list(agent.id);
      setFiles(data.files || []);
    } catch {
      // ignore if agent not yet saved
    }
  }, [agent.id, agent.kb_enabled]);

  const loadTsSummary = useCallback(async () => {
    if (!agent.id || !agent.kb_enabled) return;
    try {
      const data = await kbApi.troubleshootingSummary(agent.id);
      setTsSummary(data);
    } catch {
      // ignore if agent not yet saved
    }
  }, [agent.id, agent.kb_enabled]);

  useEffect(() => { loadFiles(); }, [loadFiles]);
  useEffect(() => { loadTsSummary(); }, [loadTsSummary]);

  const handleTsUpload = async (e) => {
    const file = (e.target.files || [])[0];
    if (!file) return;
    if (!agent.id) {
      setTsError("Save the agent first before uploading.");
      return;
    }
    setTsUploading(true);
    setTsError(null);
    try {
      await kbApi.uploadTroubleshooting(agent.id, file);
      await loadTsSummary();
    } catch (err) {
      setTsError(err.message);
    } finally {
      setTsUploading(false);
      if (tsInputRef.current) tsInputRef.current.value = "";
    }
  };

  const handleTsClear = async () => {
    try {
      await kbApi.clearTroubleshooting(agent.id);
      setTsSummary({ entries: 0, policies: 0, by_answer_mode: {} });
    } catch (err) {
      setTsError(err.message);
    }
  };

  // ---- custom policy rules state ----
  const emptyPolicy = {
    policy_area: "",
    keywords: "",
    agent_says: "",
    answer_mode: "KB-Fetch Only",
    transfer_priority: "P2",
  };
  const [policies, setPolicies] = useState([]);
  const [policyForm, setPolicyForm] = useState(emptyPolicy);
  const [policySaving, setPolicySaving] = useState(false);
  const [policyError, setPolicyError] = useState(null);

  const loadPolicies = useCallback(async () => {
    if (!agent.id || !agent.kb_enabled) return;
    try {
      const data = await kbApi.listPolicies(agent.id);
      setPolicies(data.rules || []);
    } catch {
      // ignore if agent not yet saved
    }
  }, [agent.id, agent.kb_enabled]);

  useEffect(() => { loadPolicies(); }, [loadPolicies]);

  const setPF = (k, v) => setPolicyForm((p) => ({ ...p, [k]: v }));

  const handleAddPolicy = async () => {
    if (!policyForm.policy_area.trim() || !policyForm.agent_says.trim()) {
      setPolicyError("Policy name and 'What the agent says' are required.");
      return;
    }
    setPolicySaving(true);
    setPolicyError(null);
    try {
      await kbApi.addPolicy(agent.id, policyForm);
      setPolicyForm(emptyPolicy);
      await loadPolicies();
    } catch (err) {
      setPolicyError(err.message);
    } finally {
      setPolicySaving(false);
    }
  };

  const handleDeletePolicy = async (ruleId) => {
    try {
      await kbApi.deletePolicy(agent.id, ruleId);
      setPolicies((prev) => prev.filter((p) => p.rule_id !== ruleId));
    } catch (err) {
      setPolicyError(err.message);
    }
  };

  const handleUpload = async (e) => {
    const selected = Array.from(e.target.files || []);
    if (!selected.length) return;
    if (!agent.id) {
      setError("Save the agent first before uploading documents.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await kbApi.upload(agent.id, selected);
      await loadFiles();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleDelete = async (filename) => {
    try {
      await kbApi.deleteFile(agent.id, filename);
      setFiles((prev) => prev.filter((f) => f.filename !== filename));
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="builder-section">
      <h3>B. Knowledgebase</h3>
      <Toggle
        label="Enable knowledgebase (RAG)"
        checked={agent.kb_enabled}
        onChange={(v) => update("kb_enabled", v)}
      />
      {agent.kb_enabled && (
        <div className="kb-upload">
          {!agent.id && (
            <p className="hint" style={{ color: "#f59e0b" }}>
              Save the agent first, then upload documents.
            </p>
          )}
          {agent.id && (
            <>
              <label className="kb-btn" style={{ cursor: uploading ? "not-allowed" : "pointer" }}>
                {uploading ? "Uploading…" : "Choose files (PDF / TXT)"}
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md"
                  style={{ display: "none" }}
                  disabled={uploading}
                  onChange={handleUpload}
                />
              </label>
              {error && <p style={{ color: "#ef4444", marginTop: 6, fontSize: 13 }}>{error}</p>}
              {files.length > 0 && (
                <ul className="kb-file-list">
                  {files.map((f) => (
                    <li key={f.filename}>
                      <span>{f.filename}</span>
                      <span className="kb-chunks">{f.chunk_count} chunks</span>
                      <button
                        className="kb-delete"
                        onClick={() => handleDelete(f.filename)}
                        title="Remove"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {files.length === 0 && !uploading && (
                <p className="hint">No documents uploaded yet.</p>
              )}
            </>
          )}
        </div>
      )}

      {agent.kb_enabled && agent.id && (
        <div className="kb-upload" style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #2a2a2a" }}>
          <h4 style={{ margin: "0 0 4px" }}>Troubleshooting Excel (KB-Fetch vs LLM router)</h4>
          <p className="hint" style={{ marginTop: 0 }}>
            Upload the structured IT troubleshooting .xlsx. Each issue’s ANSWER MODE
            decides whether the agent deep-dives (LLM) or fetches KB/policy verbatim.
          </p>
          <label className="kb-btn" style={{ cursor: tsUploading ? "not-allowed" : "pointer" }}>
            {tsUploading ? "Uploading & embedding…" : "Choose Excel (.xlsx)"}
            <input
              ref={tsInputRef}
              type="file"
              accept=".xlsx,.xlsm"
              style={{ display: "none" }}
              disabled={tsUploading}
              onChange={handleTsUpload}
            />
          </label>
          {tsError && <p style={{ color: "#ef4444", marginTop: 6, fontSize: 13 }}>{tsError}</p>}
          {tsSummary && (tsSummary.entries > 0 || tsSummary.policies > 0) ? (
            <div style={{ marginTop: 8, fontSize: 13 }}>
              <span className="kb-chunks">{tsSummary.entries} entries</span>{" "}
              <span className="kb-chunks">{tsSummary.policies} policy rules</span>
              {tsSummary.by_answer_mode && (
                <div className="hint" style={{ marginTop: 4 }}>
                  {Object.entries(tsSummary.by_answer_mode)
                    .map(([m, c]) => `${m}: ${c}`)
                    .join("  •  ")}
                </div>
              )}
              <button
                className="kb-delete"
                onClick={handleTsClear}
                style={{ marginTop: 6 }}
                title="Remove all troubleshooting data"
              >
                Clear troubleshooting KB
              </button>
            </div>
          ) : (
            !tsUploading && <p className="hint">No troubleshooting Excel uploaded yet.</p>
          )}
        </div>
      )}

      {agent.kb_enabled && agent.id && (
        <div className="kb-upload" style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #2a2a2a" }}>
          <h4 style={{ margin: "0 0 4px" }}>Add Policy / Guardrail Rule</h4>
          <p className="hint" style={{ marginTop: 0 }}>
            Add a strict rule (e.g. lost/stolen device, data breach). When a caller’s
            words match it, the agent won’t improvise — it speaks the line below and escalates.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 560 }}>
            <input
              type="text"
              placeholder="Policy name / area (e.g. Lost or Stolen Device)"
              value={policyForm.policy_area}
              onChange={(e) => setPF("policy_area", e.target.value)}
              style={inp}
            />
            <input
              type="text"
              placeholder="Trigger keywords (e.g. laptop harie gache, device churi)"
              value={policyForm.keywords}
              onChange={(e) => setPF("keywords", e.target.value)}
              style={inp}
            />
            <textarea
              placeholder="What the agent says (verbatim policy line)"
              value={policyForm.agent_says}
              onChange={(e) => setPF("agent_says", e.target.value)}
              rows={3}
              style={{ ...inp, resize: "vertical" }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <select
                value={policyForm.answer_mode}
                onChange={(e) => setPF("answer_mode", e.target.value)}
                style={{ ...inp, flex: 1 }}
              >
                <option>KB-Fetch Only</option>
                <option>LLM-Answered</option>
              </select>
              <select
                value={policyForm.transfer_priority}
                onChange={(e) => setPF("transfer_priority", e.target.value)}
                style={{ ...inp, flex: 1 }}
              >
                <option>P1</option>
                <option>P2</option>
                <option>P3</option>
                <option>P4</option>
              </select>
            </div>
            <button
              className="kb-btn"
              onClick={handleAddPolicy}
              disabled={policySaving}
              style={{ cursor: policySaving ? "not-allowed" : "pointer", alignSelf: "flex-start" }}
            >
              {policySaving ? "Saving & embedding…" : "+ Add Policy Rule"}
            </button>
            {policyError && <p style={{ color: "#ef4444", fontSize: 13 }}>{policyError}</p>}
          </div>

          {policies.length > 0 && (
            <ul className="kb-file-list" style={{ marginTop: 12 }}>
              {policies.map((p) => (
                <li key={p.rule_id}>
                  <span>
                    <strong>{p.policy_area}</strong>
                    <span className="kb-chunks" style={{ marginLeft: 8 }}>
                      {p.answer_mode} · {p.transfer_priority}
                    </span>
                  </span>
                  <button
                    className="kb-delete"
                    onClick={() => handleDeletePolicy(p.rule_id)}
                    title="Remove rule"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}