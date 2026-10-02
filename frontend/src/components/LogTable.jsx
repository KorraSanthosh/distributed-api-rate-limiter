import { fmtTime, METHOD_CLASS, statusTone } from "../util.js";

export default function LogTable({ rows }) {
  return (
    <section className="panel" id="log">
      <div className="panel-head">
        <div>
          <h2>Live request stream</h2>
          <p className="muted">Newest 25 events from the Redis stream</p>
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="empty">Waiting for traffic… run <code className="mono">scripts/traffic_generator.py</code></div>
      ) : (
        <div className="table-scroll">
          <table className="log">
            <thead>
              <tr><th>Time</th><th>Client</th><th>Method</th><th>Endpoint</th><th>Status</th><th>Latency</th><th>Result</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.request_id} className={r.allowed ? "" : "row-blocked"}>
                  <td className="mono">{fmtTime(r.timestamp)}</td>
                  <td className="mono">{r.client_ip}</td>
                  <td><span className={`method ${METHOD_CLASS[r.method] ?? ""}`}>{r.method}</span></td>
                  <td className="mono">{r.endpoint}</td>
                  <td><span className={`pill ${statusTone(r.status_code)}`}>{r.status_code}</span></td>
                  <td className="mono">{r.latency_ms.toFixed(2)} ms</td>
                  <td><span className={`pill ${r.allowed ? "ok" : "blocked"}`}>{r.allowed ? "Allowed" : "Blocked"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
