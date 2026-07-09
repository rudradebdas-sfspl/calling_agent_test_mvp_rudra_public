import React, { useState } from "react";
import { sessionsApi } from "../api/agents";
import "./VoiceCall.css";

/**
 * VoiceCall — Interface for initiating SIP Outbound calls
 * and viewing Inbound call instructions.
 */
export default function VoiceCall({ agent, onBack }) {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [status, setStatus] = useState("idle"); // idle | calling | error | success
  const [message, setMessage] = useState(null);

  async function handleOutboundCall(e) {
    e.preventDefault();
    if (!phoneNumber) return;

    setStatus("calling");
    setMessage(null);

    try {
      // Create custom API endpoint wrapper if it doesn't exist, or just fetch directly
      const response = await fetch("/api/sessions/outbound", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agent.id, phone_number: phoneNumber })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || data.message || "Failed to make call");
      }

      setStatus("success");
      setMessage(`Outbound call initiated to ${phoneNumber}. Please wait for the phone to ring.`);
      setPhoneNumber("");
    } catch (err) {
      console.error(err);
      setStatus("error");
      setMessage(err.message);
    }
  }

  return (
    <div className="call-view">
      <button className="btn btn-ghost call-back" onClick={onBack}>
        ← Back to Dashboard
      </button>

      <div className="call-card">
        {/* Avatar */}
        <div className="call-avatar">
          🤖
        </div>

        {/* Agent info */}
        <div className="call-agent-name">{agent.name}</div>
        <div className="call-agent-desc">
          {agent.llm_provider} • {agent.stt_provider} • {agent.tts_provider} • {agent.language}
        </div>

        <div className="telephony-container">
          <div className="telephony-section">
            <h3>📞 Outbound Call</h3>
            <p>Enter a phone number to make the agent call you directly via SIP.</p>
            <form onSubmit={handleOutboundCall} className="outbound-form">
              <input
                type="text"
                placeholder="+91..."
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                disabled={status === "calling"}
                className="input-field"
              />
              <button 
                type="submit" 
                className="btn btn-success"
                disabled={status === "calling" || !phoneNumber}
              >
                {status === "calling" ? "Initiating..." : "Call Number"}
              </button>
            </form>
          </div>

          <div className="telephony-divider"></div>

          <div className="telephony-section">
            <h3>📥 Inbound Call</h3>
            <p>To speak to this agent, dial the configured JIO DID number from your phone.</p>
            <div className="did-box">
              <span className="did-number">+91 333 508 1848</span>
            </div>
            <p className="did-hint">(Make sure the agent is marked as Active in the Dashboard)</p>
          </div>
        </div>

        {message && (
          <div className={`call-message ${status === "error" ? "error" : "success"}`}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
}
