import { Check, Copy, Radio, WifiOff } from "lucide-react";
import { useState } from "react";

export function ErrorBanner({ message, onRetry, hasData }) {
  return (
    <div className="banner">
      <WifiOff size={18} />
      <div>
        <b>{hasData ? "Connection lost — showing last known data" : "Can't reach the API"}</b>
        <span className="muted"> · {message}. Is the gateway running on port 8000?</span>
      </div>
      <button className="btn" onClick={onRetry}>Retry</button>
    </div>
  );
}

export function Skeleton() {
  return (
    <>
      <div className="kpi-grid">
        {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton kpi-skel" />)}
      </div>
      <div className="skeleton chart-skel" />
    </>
  );
}

const SIM_CMD = "python scripts/traffic_generator.py --host http://localhost:8000 --mode all --duration 120";

/** Shown when the API is reachable but has recorded no traffic yet, so zeros don't look like a bug. */
export function EmptyHint() {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(SIM_CMD);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: the command is still visible to copy by hand */
    }
  };
  return (
    <div className="hint-card">
      <div className="hint-icon"><Radio size={20} /></div>
      <div className="hint-body">
        <b>No traffic recorded yet</b>
        <p className="muted">
          The gateway is online, but nothing has been sent through it in this time window. Send some
          requests (or run the traffic simulator) and this page fills in live:
        </p>
        <div className="hint-cmd">
          <code className="mono">{SIM_CMD}</code>
          <button className="btn" onClick={copy} title="Copy command">
            {copied ? <Check size={15} /> : <Copy size={15} />}
          </button>
        </div>
      </div>
    </div>
  );
}
