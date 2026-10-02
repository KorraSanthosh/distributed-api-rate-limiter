export default function EndpointsPanel({ endpoints }) {
  return (
    <section className="panel" id="endpoints">
      <div className="panel-head">
        <div>
          <h2>Endpoint traffic</h2>
          <p className="muted">Share of requests, with rate-limited portion</p>
        </div>
      </div>
      {endpoints.length === 0 ? (
        <div className="empty small">No endpoint traffic yet</div>
      ) : (
        <ul className="bars">
          {endpoints.map((e) => {
            const blockedPct = e.requests ? (e.blocked / e.requests) * e.share_pct : 0;
            return (
              <li key={e.endpoint}>
                <div className="bar-top">
                  <span className="mono">{e.endpoint}</span>
                  <span><b>{e.requests.toLocaleString()}</b> <span className="muted">· {e.share_pct}%</span></span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${e.share_pct - blockedPct}%` }} />
                  <div className="bar-fill blocked" style={{ width: `${blockedPct}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
