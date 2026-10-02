import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = { 200: "#6fdcb8", 429: "#f58b9a" };
const FALLBACK = ["#9ea6ff", "#ffc98a", "#b99af0", "#8fd0ff"];

export default function StatusDonut({ statuses, blockRate, total }) {
  const colorFor = (code, i) => COLORS[code] ?? FALLBACK[i % FALLBACK.length];
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Status split</h2>
          <p className="muted">HTTP responses in window</p>
        </div>
      </div>
      <div className="donut-wrap">
        {total === 0 ? (
          <div className="empty small">No requests in this window yet</div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={statuses} dataKey="count" nameKey="status_code" innerRadius="68%" outerRadius="92%"
                     paddingAngle={3} cornerRadius={8} stroke="none" isAnimationActive={false}>
                  {statuses.map((s, i) => <Cell key={s.status_code} fill={colorFor(s.status_code, i)} />)}
                </Pie>
                <Tooltip formatter={(v, n) => [v, `HTTP ${n}`]} />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center">
              <div className="donut-num">{blockRate.toFixed(1)}%</div>
              <div className="muted">blocked</div>
            </div>
          </>
        )}
      </div>
      <ul className="status-list">
        {statuses.map((s, i) => (
          <li key={s.status_code}>
            <span><i className="swatch" style={{ background: colorFor(s.status_code, i) }} />HTTP {s.status_code}</span>
            <b>{s.count.toLocaleString()}</b>
          </li>
        ))}
      </ul>
    </section>
  );
}
