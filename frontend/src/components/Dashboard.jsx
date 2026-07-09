import React, { useEffect, useState } from "react";
import { agentsApi } from "../api/agents";
import "./Dashboard.css";

/**
 * Agent Dashboard — lists all saved agents with actions.
 * Props:
 *   onEdit(agent)    — navigate to Agent Builder in edit mode
 *   onCall(agent)    — navigate to Voice Call view
 *   onCreate()       — navigate to Agent Builder in create mode
 */
export default function Dashboard({ onEdit, onCall, onCreate }) {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [settingSip, setSettingSip] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const list = await agentsApi.list();
      setAgents(list);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDelete(agent) {
    if (!confirm(`Delete agent "${agent.name}"?`)) return;
    try {
      await agentsApi.remove(agent.id);
      setAgents((prev) => prev.filter((a) => a.id !== agent.id));
    } catch (e) {
      alert("Delete failed: " + e.message);
    }
  }

  async function handleSetSipDefault(agent) {
    if (agent.is_sip_default) return;
    setSettingSip(agent.id);
    try {
      const updated = await agentsApi.setSipDefault(agent.id);
      setAgents((prev) =>
        prev.map((a) =>
          a.id === updated.id
            ? { ...a, is_sip_default: true }
            : { ...a, is_sip_default: false }
        )
      );
    } catch (e) {
      alert("Failed to set SIP default: " + e.message);
    } finally {
      setSettingSip(null);
    }
  }

  if (loading) {
    return <div className="loading">Loading agents…</div>;
  }

  if (error) {
    return (
      <div className="dashboard fade-in">
        <div className="empty-state">
          <div className="empty-state-icon">⚠️</div>
          <h3>Connection Error</h3>
          <p>{error}</p>
          <button className="btn btn-primary" onClick={load}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard fade-in">
      <div className="dashboard-header">
        <div>
          <h1>Your Agents</h1>
          <p>
            {agents.length} agent{agents.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <button className="btn btn-primary" onClick={onCreate}>
          ＋ New Agent
        </button>
      </div>

      {agents.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🤖</div>
          <h3>No agents yet</h3>
          <p>Create your first voice agent to get started.</p>
          <button className="btn btn-primary" onClick={onCreate}>
            ＋ Create Agent
          </button>
        </div>
      ) : (
        <div className="agents-grid">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className={`agent-card${agent.is_sip_default ? " agent-card--sip-default" : ""}`}
            >
              <div className="agent-card-top">
                <span className="agent-card-name">{agent.name}</span>
                <div className="agent-card-badges">
                  {agent.is_sip_default && (
                    <span className="badge badge-sip" title="Handles inbound SIP/telephony calls">
                      📞 SIP Default
                    </span>
                  )}
                  <span
                    className={`badge ${agent.is_active ? "badge-active" : "badge-inactive"}`}
                  >
                    {agent.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>

              {agent.description && (
                <div className="agent-card-desc">{agent.description}</div>
              )}

              <div className="agent-card-meta">
                <span className="meta-chip">
                  <span className="meta-chip-icon">🧠</span>
                  {agent.llm_provider}/{agent.llm_model}
                </span>
                <span className="meta-chip">
                  <span className="meta-chip-icon">🎙️</span>
                  {agent.stt_provider}
                </span>
                <span className="meta-chip">
                  <span className="meta-chip-icon">🔊</span>
                  {agent.tts_provider}
                </span>
                <span className="meta-chip">
                  <span className="meta-chip-icon">🌐</span>
                  {agent.language}
                </span>
              </div>

              <div className="agent-card-actions">
                <button
                  className="btn btn-success"
                  onClick={() => onCall(agent)}
                  disabled={!agent.is_active}
                  title={!agent.is_active ? "Activate agent first" : "Start voice call"}
                >
                  📞 Call
                </button>
                <button
                  className={`btn ${agent.is_sip_default ? "btn-sip-active" : "btn-sip"}`}
                  onClick={() => handleSetSipDefault(agent)}
                  disabled={agent.is_sip_default || settingSip === agent.id}
                  title={
                    agent.is_sip_default
                      ? "This agent handles inbound SIP calls"
                      : "Set as default for inbound SIP/telephony calls"
                  }
                >
                  {settingSip === agent.id ? "…" : agent.is_sip_default ? "☎ SIP" : "Set SIP"}
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => onEdit(agent)}
                >
                  ✏️ Edit
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => handleDelete(agent)}
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
