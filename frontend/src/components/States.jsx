import { WifiOff } from "lucide-react";

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
