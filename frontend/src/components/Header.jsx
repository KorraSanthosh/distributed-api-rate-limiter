import { Pause, Play, RefreshCw } from "lucide-react";

const WINDOWS = [
  { label: "30s", value: 30 },
  { label: "1m", value: 60 },
  { label: "5m", value: 300 },
  { label: "15m", value: 900 },
];

export default function Header({ windowSeconds, onWindow, paused, onTogglePause, onRefresh, live, lastUpdated }) {
  return (
    <header className="header" id="overview">
      <div>
        <h1>Real-time API traffic</h1>
        <p className="muted">
          Sliding-window rate limiting across your gateway
          {lastUpdated && <> · updated {new Date(lastUpdated).toLocaleTimeString([], { hour12: false })}</>}
        </p>
      </div>

      <div className="header-actions">
        <div className={`live-badge ${paused ? "paused" : live ? "live" : "offline"}`}>
          <span className="pulse" />
          {paused ? "Paused" : live ? "Live" : "Offline"}
        </div>

        <div className="segmented" role="tablist" aria-label="Time window">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              className={windowSeconds === w.value ? "active" : ""}
              onClick={() => onWindow(w.value)}
            >
              {w.label}
            </button>
          ))}
        </div>

        <button className="btn" onClick={onRefresh} title="Refresh now">
          <RefreshCw size={16} />
        </button>
        <button className="btn btn-primary" onClick={onTogglePause}>
          {paused ? <Play size={16} /> : <Pause size={16} />}
          {paused ? "Resume" : "Pause"}
        </button>
      </div>
    </header>
  );
}
