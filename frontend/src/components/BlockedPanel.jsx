import { ShieldAlert, ShieldCheck } from "lucide-react";
import { fmtTime } from "../util.js";

function ago(ts, now) {
  const s = Math.max(0, Math.round(now - ts));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

/** Newest blocked requests with the offending client IP. Kept independent of the time window. */
export default function BlockedPanel({ rows, now }) {
  return (
    <section className="panel" id="blocked">
      <div className="panel-head">
        <div>
          <h2>Recently blocked requests</h2>
          <p className="muted">Latest 429 responses and the client IPs behind them</p>
        </div>
        {rows.length > 0 && (
          <span className="pill blocked"><ShieldAlert size={12} style={{ verticalAlign: -2, marginRight: 4 }} />{rows.length} shown</span>
        )}
      </div>
      {rows.length === 0 ? (
        <div className="empty small">
          <ShieldCheck size={26} />
          <span>Nothing has been blocked yet</span>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="log">
            <thead>
              <tr><th>Client IP</th><th>Endpoint</th><th>Method</th><th>When</th><th>Time</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.request_id} className="row-blocked">
                  <td className="mono"><b>{r.client_ip}</b></td>
                  <td className="mono">{r.endpoint}</td>
                  <td><span className="method">{r.method}</span></td>
                  <td className="muted">{ago(r.timestamp, now)}</td>
                  <td className="mono">{fmtTime(r.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
