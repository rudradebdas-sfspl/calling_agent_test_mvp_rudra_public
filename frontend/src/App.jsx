import React, { useState } from "react";
import "./index.css";
import Dashboard from "./components/Dashboard";
import AgentBuilder from "./components/AgentBuilder";
import VoiceCall from "./components/VoiceCall";

/**
 * App root — simple SPA routing between three views:
 *   1. Dashboard  — list agents, pick one to call or edit
 *   2. AgentBuilder — create or edit an agent
 *   3. VoiceCall  — live browser-mic call with a selected agent
 */
export default function App() {
  // view: "dashboard" | "builder" | "call"
  const [view, setView] = useState("dashboard");
  const [selectedAgent, setSelectedAgent] = useState(null);

  function goHome() {
    setView("dashboard");
    setSelectedAgent(null);
  }

  return (
    <div className="app-shell">
      {/* ---- Top bar ---- */}
      <header className="app-topbar">
        <div className="app-logo" onClick={goHome}>
          <div className="app-logo-icon">🎤</div>
          Voice Agent Platform
        </div>
        <nav className="app-nav">
          <button
            className={`nav-btn ${view === "dashboard" ? "active" : ""}`}
            onClick={goHome}
          >
            Dashboard
          </button>
          <button
            className={`nav-btn ${view === "builder" ? "active" : ""}`}
            onClick={() => {
              setSelectedAgent(null);
              setView("builder");
            }}
          >
            ＋ New Agent
          </button>
        </nav>
      </header>

      {/* ---- Main content ---- */}
      <main className="app-main">
        {view === "dashboard" && (
          <Dashboard
            onEdit={(agent) => {
              setSelectedAgent(agent);
              setView("builder");
            }}
            onCall={(agent) => {
              setSelectedAgent(agent);
              setView("call");
            }}
            onCreate={() => {
              setSelectedAgent(null);
              setView("builder");
            }}
          />
        )}

        {view === "builder" && (
          <AgentBuilder
            initial={selectedAgent}
            onSaved={(saved) => {
              // After save, go back to dashboard
              setSelectedAgent(null);
              setView("dashboard");
            }}
          />
        )}

        {view === "call" && selectedAgent && (
          <VoiceCall agent={selectedAgent} onBack={goHome} />
        )}
      </main>
    </div>
  );
}
