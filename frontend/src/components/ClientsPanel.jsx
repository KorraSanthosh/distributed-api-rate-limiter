import { ShieldCheck } from "lucide-react";

export default function ClientsPanel({ clients }) {
  const max = Math.max(1, ...clients.map((c) => c.blocked));
  return (
    <section className="panel" id="clients">
      <div className="panel-head">
        <div>
          <h2>Top abusive clients</h2>
          <p className="muted">Most rate-limited IPs in window</p>
        </div>
      </div>
      {clients.length === 0 ? (
        <div className="empty small">
          <ShieldCheck size={26} />
          <span>No client has hit a limit</span>
        </div>
      ) : (
        <ol className="clients">
          {clients.map((c, i) => (
            <li key={c.client_ip}>
              <span className="rank">{i + 1}</span>
              <div className="client-main">
                <div className="client-top">
                  <span className="mono">{c.client_ip}</span>
                  <b>{c.blocked.toLocaleString()}</b>
                </div>
                <div className="bar-track thin">
                  <div className="bar-fill blocked" style={{ width: `${(c.blocked / max) * 100}%` }} />
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
