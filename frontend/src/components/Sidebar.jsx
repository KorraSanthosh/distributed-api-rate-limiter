import { Activity, Ban, Gauge, ListTree, ScrollText, ShieldAlert, ShieldCheck } from "lucide-react";

const NAV = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "traffic", label: "Traffic", icon: Activity },
  { id: "endpoints", label: "Endpoints", icon: ListTree },
  { id: "clients", label: "Abusive clients", icon: ShieldAlert },
  { id: "blocked", label: "Blocked IPs", icon: Ban },
  { id: "log", label: "Live log", icon: ScrollText },
];

export default function Sidebar({ system, online }) {
  const redisOk = online && !!system?.redis_connected;
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><ShieldCheck size={20} /></div>
        <div>
          <div className="brand-name">Limiter Console</div>
          <div className="brand-sub">Traffic Analyzer</div>
        </div>
      </div>

      <nav className="nav">
        {NAV.map(({ id, label, icon: Icon }) => (
          <a key={id} href={`#${id}`} className="nav-item">
            <Icon size={17} />
            <span>{label}</span>
          </a>
        ))}
      </nav>

      <div className="side-card">
        <div className="side-card-title">System</div>
        <div className="side-row">
          <span>API gateway</span>
          <span className={`dot-pill ${online ? "ok" : "bad"}`}>{online ? "Online" : "Offline"}</span>
        </div>
        <div className="side-row">
          <span>Redis</span>
          <span className={`dot-pill ${redisOk ? "ok" : "bad"}`}>{redisOk ? "Connected" : "Down"}</span>
        </div>
        <div className="side-row">
          <span>Environment</span>
          <span className="mono">{online ? system?.environment ?? "—" : "—"}</span>
        </div>
        <div className="side-row">
          <span>Version</span>
          <span className="mono">{online ? system?.version ?? "—" : "—"}</span>
        </div>
      </div>

      <a className="side-link" href="/docs" target="_blank" rel="noreferrer">API docs ↗</a>
    </aside>
  );
}
